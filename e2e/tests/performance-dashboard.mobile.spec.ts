import { test, expect } from '../fixtures/test';

test('athlete performance dashboard remains readable without horizontal overflow at 390px', async ({
  page,
  authenticatedState,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticatedState(page);
  await page.goto('/athletes/404');

  const dashboard = page.locator('#performance-dashboard');
  await expect(dashboard.getByRole('heading', { name: 'Performance dashboard' })).toBeVisible();
  await expect(dashboard.getByLabel('Training block')).toBeVisible();
  await expect(dashboard.getByText('Review prescription before progressing')).toBeVisible();
  await expect(dashboard.getByRole('heading', { name: 'Squat / bench / deadlift e1RM' })).toBeVisible();
  await expect(dashboard.getByRole('list', { name: 'SBD volume by training date' })).toBeVisible();

  const viewport = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(viewport.clientWidth).toBe(390);
  expect(viewport.scrollWidth).toBeLessThanOrEqual(viewport.clientWidth);
});
