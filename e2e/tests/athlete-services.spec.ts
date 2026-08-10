import { test, expect } from '../fixtures/test';
import type { Page } from '@playwright/test';

async function configureServices(
  page: Page,
  authenticatedState: (page: Page) => Promise<void>,
  nutrition: boolean,
) {
  await authenticatedState(page);
  await page.goto('/athletes/101/check-in-settings');
  await page.getByLabel('Weekly check-in workflow active').check();
  await page.getByLabel('Weekly training check-in').check();
  await page.getByLabel('Weekly nutrition check-in').setChecked(nutrition);
  await page.getByRole('button', { name: 'Save' }).click();
}

test('training-only athlete gets a focused dashboard with no nutrition links', async ({
  page,
  authenticatedState,
  athleteSession,
  athleteIds,
}) => {
  await configureServices(page, authenticatedState, false);
  await athleteSession(page.request, athleteIds.primary);
  await page.goto('/athlete/dashboard');

  await expect(page.getByRole('heading', { level: 2, name: 'Training' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Athlete navigation' }).first().getByText('Programme')).toBeVisible();
  await expect(page.getByRole('heading', { level: 2, name: /Nutrition/ })).toHaveCount(0);
  await expect(page.locator('a[href*="nutrition-checkins"]')).toHaveCount(0);
  const disabledNutrition = await page.request.get('/athletes/101/nutrition-checkins/new');
  expect(disabledNutrition.status()).toBe(404);
});

test('training and nutrition athlete gets both services without changing the primary training action', async ({
  page,
  authenticatedState,
  athleteSession,
  athleteIds,
}) => {
  await configureServices(page, authenticatedState, true);
  await athleteSession(page.request, athleteIds.primary);
  await page.goto('/athlete/dashboard');

  await expect(page.getByRole('heading', { level: 2, name: 'Training' })).toBeVisible();
  await expect(page.getByRole('heading', { level: 2, name: 'Nutrition & bodyweight' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'View session' })).toBeVisible();
  await expect(page.locator('.athlete-mobile-nav a')).toHaveCount(5);
});
