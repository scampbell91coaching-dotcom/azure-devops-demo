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
  await expect(page.getByText('coach.e2e@example.test')).toBeVisible();
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
