import { test, expect } from '../fixtures/test';
import type { Page } from '@playwright/test';

test.use({ mutationScope: 'services' });

async function configureServices(
  page: Page,
  authenticatedState: (page: Page) => Promise<void>,
  athleteId: number,
  nutrition: boolean,
) {
  await authenticatedState(page);

  // Product access is controlled by client service entitlements.
  await page.goto(`/athletes/${athleteId}`);
  const services = page.locator('#client-services');
  await services.locator('select[name="training"]').selectOption('yes');
  await services.locator('select[name="nutrition"]').selectOption(
    nutrition ? 'yes' : 'no',
  );
  await services.locator('select[name="meet_day"]').selectOption('no');
  await services.locator('select[name="video_review"]').selectOption('none');

  if (!nutrition) {
    page.once('dialog', async dialog => {
      await dialog.accept();
    });
  }

  await services.getByRole('button', { name: 'Save client services' }).click();
  await expect(services.locator('select[name="nutrition"]')).toHaveValue(
    nutrition ? 'yes' : 'no',
  );

  // Weekly check-in modules remain independently configurable.
  await page.goto(`/athletes/${athleteId}/check-in-settings`);
  await page.getByLabel('Weekly check-in workflow active').check();
  await page.getByLabel('Weekly training check-in').check();
  await page.getByLabel('Weekly nutrition check-in').setChecked(nutrition);
  await page.getByRole('button', { name: 'Save' }).click();
}

test.beforeEach(async ({ request, resetE2EFixture }) => {
  await resetE2EFixture(request, 'services');
});

test('training-only athlete gets a focused dashboard with no nutrition links', async ({
  page,
  authenticatedState,
  athleteSession,
  athleteIds,
}) => {
  await configureServices(page, authenticatedState, athleteIds.isolated, false);
  await athleteSession(page.request, athleteIds.isolated);

  const disabledNutrition = await page.request.get(
    `/athletes/${athleteIds.isolated}/nutrition-checkins/new`,
  );
  expect(disabledNutrition.status()).toBe(404);

  await page.goto('/athlete/dashboard');

  await expect(page.getByRole('heading', { level: 2, name: 'Training' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Athlete navigation' }).first().getByText('Programme')).toBeVisible();
  await expect(page.getByRole('heading', { level: 2, name: /Nutrition/ })).toHaveCount(0);
  await expect(page.locator('a[href*="nutrition-checkins"]')).toHaveCount(0);
});

test('training and nutrition athlete gets both services without changing the primary training action', async ({
  page,
  authenticatedState,
  athleteSession,
  athleteIds,
}) => {
  await configureServices(page, authenticatedState, athleteIds.isolated, true);
  await athleteSession(page.request, athleteIds.isolated);

  const enabledNutrition = await page.request.get(
    `/athletes/${athleteIds.isolated}/nutrition-checkins/new`,
  );
  expect(enabledNutrition.status()).toBe(200);

  await page.goto('/athlete/dashboard');

  await expect(page.getByRole('heading', { level: 2, name: 'Training' })).toBeVisible();
  await expect(page.getByRole('heading', { level: 2, name: 'Nutrition & bodyweight' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'View session' })).toBeVisible();
  await expect(page.locator('.athlete-mobile-nav a')).toHaveCount(5);
});
