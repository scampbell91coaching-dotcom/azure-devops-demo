import { test, expect } from '../fixtures/test';

test('unauthenticated coach routes redirect to login', async ({ page }) => {
  await page.goto('/programming');
  await expect(page).toHaveURL(/\/login\?next=/);
});

test('coach login, invalid credentials, and logout are usable', async ({ page }) => {
  await page.goto('/login');
  await page.locator('input[name="email"]').fill('coach.e2e@example.test');
  await page.locator('input[name="password"]').fill('wrong password');
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page.getByRole('alert')).toContainText('Invalid email or password');

  // Invalid-login handling may clear submitted fields. Re-enter the complete
  // credential pair before testing the successful authentication path.
  await page.locator('input[name="email"]').fill('coach.e2e@example.test');
  await page.locator('input[name="password"]').fill(
    process.env.E2E_COACH_PASSWORD ?? 'Coach E2E password!'
  );
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/coach$/);
  await expect(
    page.locator('.coach-user').getByText('coach.e2e@example.test', { exact: true })
  ).toBeVisible();
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/login$/);
});

test('athlete cannot access coach programming or mutation controls', async ({ page }) => {
  await page.goto('/login');
  await page.locator('input[name="email"]').fill('alex.e2e@example.test');
  await page.locator('input[name="password"]').fill('Athlete E2E password!');
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/athlete\/dashboard$/);
  const response = await page.goto('/exercise-library');
  expect(response?.status()).toBe(403);
  await expect(page.getByRole('heading', { name: 'Access denied' })).toBeVisible();
  await expect(page.getByRole('button', { name: /add exercise/i })).toHaveCount(0);
});

test('branded login is keyboard accessible and responsive', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto('/login');

  await expect(page.getByRole('img', { name: 'Traditional Strength' })).toBeVisible();
  await expect(page.getByText('Coach access', { exact: true })).toBeVisible();
  await expect(page.getByText('Athlete access', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

  await page.keyboard.press('Tab');
  await expect(page.locator('input[name="email"]')).toBeFocused();
  await page.keyboard.type('coach.e2e@example.test');
  await page.keyboard.press('Tab');
  await expect(page.locator('input[name="password"]')).toBeFocused();
  await page.keyboard.type('visible secret');
  await page.keyboard.press('Tab');
  const toggle = page.getByRole('button', { name: 'Show password' });
  await expect(toggle).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('input[name="password"]')).toHaveAttribute('type', 'text');
  await expect(page.getByRole('button', { name: 'Hide password' })).toHaveAttribute('aria-pressed', 'true');
});

test('invalid credential error is announced', async ({ page }) => {
  await page.goto('/login');
  await page.locator('input[name="email"]').fill('unknown@example.test');
  await page.locator('input[name="password"]').fill('wrong password');
  await page.getByRole('button', { name: /sign in securely/i }).click();

  const alert = page.getByRole('alert');
  await expect(alert).toContainText('Invalid email or password.');
  await expect(alert).toHaveAttribute('aria-live', 'assertive');
  await expect(page.locator('input[name="email"]')).toHaveAttribute('aria-invalid', 'true');
});
