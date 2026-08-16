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

async function expectEvenlyFilledMobileNavigation(page: Page, expectedItems: number) {
  const navigation = page.getByRole('navigation', { name: 'Athlete navigation' }).last();
  const items = navigation.locator(':scope > a, :scope > details');
  await expect(items).toHaveCount(expectedItems);
  const boxes = await items.evaluateAll(elements => elements.map(element => {
    const box = element.getBoundingClientRect();
    return { left: box.left, right: box.right, width: box.width };
  }));
  expect(boxes[0].left).toBeLessThanOrEqual(1);
  expect(Math.abs(boxes.at(-1)!.right - 390)).toBeLessThanOrEqual(1);
  expect(Math.max(...boxes.map(box => box.width)) - Math.min(...boxes.map(box => box.width))).toBeLessThanOrEqual(1);
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
  await page.setViewportSize({ width: 390, height: 844 });
  await expectEvenlyFilledMobileNavigation(page, 4);
  const more = page.locator('[data-athlete-more]');
  await more.locator('summary').focus();
  await page.keyboard.press('Enter');
  await expect(more.getByRole('link', { name: 'Account' })).toBeVisible();
  await expect(more.getByRole('link', { name: 'Meal plan', exact: true })).toHaveCount(0);
  await page.keyboard.press('Escape');
  await expect(more.locator('summary')).toBeFocused();
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
  await expect(page.locator('.athlete-mobile-nav a')).toHaveCount(7);
  await page.setViewportSize({ width: 390, height: 844 });
  await expectEvenlyFilledMobileNavigation(page, 5);
});
