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
