import { test, expect } from '../fixtures/test';

test('public and coach pages render at a mobile viewport', async ({ page }) => {
  await page.goto('/guides/shoulder-pain');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.goto('/athletes');
  await expect(page.getByRole('heading', { level: 1, name: 'Athletes', exact: true })).toBeVisible();
  await expect(page.locator('body')).not.toHaveCSS('overflow-x', 'scroll');
});
