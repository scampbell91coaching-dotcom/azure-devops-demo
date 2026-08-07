import { test, expect } from '../fixtures/test';

test('health endpoint and public landing page render', async ({ request, page }) => {
  const health = await request.get('/health');
  expect(health.ok()).toBeTruthy();
  await expect(health.json()).resolves.toEqual({ status: 'healthy' });

  await page.goto('/guides/hip-pain');
  await expect(page).toHaveTitle(/Traditional Strength/);
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByRole('link', { name: /Apply for Coaching/i }).first()).toBeVisible();
  await expect(page.getByRole('link', { name: 'Traditional Strength home' })).toBeVisible();
});

test('coaching application progress updates under its CSP', async ({ page }) => {
  const publicBaseUrl =
    process.env.E2E_PUBLIC_BASE_URL ?? 'http://127.0.0.1:8092';

  await page.goto(`${publicBaseUrl}/apply`);

  const progress = page.locator('[data-progress-bar]');
  await expect(progress).toHaveCSS('width', '0px');

  await page.getByLabel('First name').fill('Ada');
  await page.getByLabel('Last name').fill('Lovelace');
  await page.getByLabel('Email address').fill('ada@example.test');
  await page.getByLabel('Country').fill('United Kingdom');
  await page.getByRole('button', { name: 'Continue' }).click();

  await expect(progress).toHaveClass(/progress-25/);
  await expect.poll(async () => parseFloat(await progress.evaluate(
    (element) => getComputedStyle(element).width,
  ))).toBeGreaterThan(0);
  await expect(page.locator('[data-progress-label]')).toHaveText('Step 2 of 5');
});

test('application validation is clear and keeps entered values', async ({ page }) => {
  const publicBaseUrl = process.env.E2E_PUBLIC_BASE_URL ?? 'http://127.0.0.1:8092';
  await page.goto(`${publicBaseUrl}/apply`);
  await page.getByLabel('First name').fill('Ada');
  await page.getByRole('button', { name: 'Continue' }).click();

  await expect(page.getByLabel('Last name')).toBeFocused();
  await expect(page.locator('[data-error-for="last_name"]')).toContainText('Complete this');
  await expect(page.getByLabel('First name')).toHaveValue('Ada');
});

test('public mobile menu supports keyboard escape', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await page.goto('/guides/hip-pain');
  const menu = page.getByRole('button', { name: 'Menu' });

  await menu.focus();
  await page.keyboard.press('Enter');
  await expect(menu).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByRole('navigation', { name: 'Public navigation' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(menu).toHaveAttribute('aria-expanded', 'false');
  await expect(menu).toBeFocused();
});

for (const width of [320, 390, 430]) {
  test(`public application has no horizontal overflow at ${width}px`, async ({ page }) => {
    const publicBaseUrl = process.env.E2E_PUBLIC_BASE_URL ?? 'http://127.0.0.1:8092';
    await page.setViewportSize({ width, height: 800 });
    await page.goto(`${publicBaseUrl}/apply`);

    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Continue' })).toBeVisible();
    await expect(page.locator('html')).toHaveJSProperty('scrollWidth', width);
  });
}

test('guide offers a contextual route into coaching', async ({ page }) => {
  const publicBaseUrl =
    process.env.E2E_PUBLIC_BASE_URL ?? 'http://127.0.0.1:8092';

  await page.goto(`${publicBaseUrl}/guides/shoulder-pain`);
  await page.getByRole('link', { name: 'Explore coaching' }).click();

  await expect(page).toHaveURL(`${publicBaseUrl}/apply`);
  await expect(page.getByRole('heading', { level: 1 })).toContainText(
    'Coaching built around'
  );
});
