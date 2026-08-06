import { test, expect } from '../fixtures/test';

test('health endpoint and public landing page render', async ({ request, page }) => {
  const health = await request.get('/health');
  expect(health.ok()).toBeTruthy();
  await expect(health.json()).resolves.toEqual({ status: 'healthy' });

  await page.goto('/guides/hip-pain');
  await expect(page).toHaveTitle(/Traditional Strength/);
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByRole('link', { name: /Apply for Coaching/i }).first()).toBeVisible();
});

test('coaching application progress updates under its CSP', async ({ page }) => {
  await page.goto('/apply');

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
});
