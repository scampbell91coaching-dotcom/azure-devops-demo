import { test, expect } from '../fixtures/test';

test('public and coach pages render and navigation toggles at a mobile viewport', async ({ page, authenticatedState }) => {
  await page.goto('/guides/shoulder-pain');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await authenticatedState(page);
  await page.goto('/athletes');
  await expect(page.getByRole('heading', { level: 1, name: 'Athletes', exact: true })).toBeVisible();
  await expect(page.locator('body')).not.toHaveCSS('overflow-x', 'scroll');
  const menu = page.getByRole('button', { name: 'Menu' });
  await menu.click();
  await expect(menu).toHaveAttribute('aria-expanded', 'true');
  await expect(page.locator('[data-coach-navigation]')).toHaveClass(/is-open/);
  await menu.click();
  await expect(menu).toHaveAttribute('aria-expanded', 'false');
});
