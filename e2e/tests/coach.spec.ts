import { test, expect } from '../fixtures/test';

test.beforeEach(async ({ context, authenticatedState }) => {
  await authenticatedState(context);
});

test('coach dashboard renders deterministic athlete data', async ({ page }) => {
  await page.goto('/coach');
  await expect(page.getByRole('heading', { name: 'Daily review' })).toBeVisible();
  await expect(page.getByText('Alex Rivera').first()).toBeVisible();
});

test('athlete list opens an athlete detail', async ({ page }) => {
  await page.goto('/athletes');
  await expect(page.getByRole('heading', { level: 1, name: 'Athletes', exact: true })).toBeVisible();
  await page.getByRole('link', { name: /Alex Rivera/ }).click();
  await expect(page).toHaveURL(/\/athletes\/101$/);
  await expect(page.getByRole('heading', { name: 'Alex Rivera' })).toBeVisible();
});

test('creates an athlete from deterministic fixture values', async ({ page }, testInfo) => {
  await page.goto('/athletes');
  await page.locator('input[name="first_name"]').fill('Release');
  await page.locator('input[name="last_name"]').fill('Candidate');
  await page.locator('input[name="email"]').fill(`release.candidate.${testInfo.retry}@example.test`);
  await page.getByRole('button', { name: 'Create athlete' }).click();
  await expect(page.getByRole('heading', { name: 'Release Candidate' })).toBeVisible();
});

test('navigates from a programming block to its week', async ({ page }) => {
  await page.goto('/programming');
  await page.getByRole('link', { name: /Deterministic strength block/ }).click();
  await expect(page.getByRole('heading', { name: 'Deterministic strength block' })).toBeVisible();
  await page.getByRole('link', { name: /Foundation week/ }).click();
  await expect(page.getByRole('heading', { name: 'Foundation week' })).toBeVisible();
  await expect(page.getByText('Competition Squat')).toBeVisible();
});

test('filters the exercise library', async ({ page }) => {
  await page.goto('/exercise-library');
  await page.locator('input[name="q"]').fill('Pulldown');
  await page.getByRole('button', { name: 'Filter' }).click();
  await expect(page.getByRole('heading', { name: 'Lat Pulldown' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Competition Squat' })).toHaveCount(0);
});

test('renders and submits a supported weekly check-in', async ({ page, athleteIds }) => {
  await page.goto(`/athletes/${athleteIds.primary}/check-ins/new`);
  await expect(page.getByRole('heading', { name: 'Weekly check-in' })).toBeVisible();
  await page.locator('input[name="training_adherence"]').fill('90');
  await page.locator('input[name="fatigue"]').fill('6');
  await page.locator('input[name="recovery"]').fill('8');
  await page.locator('textarea[name="general_notes"]').fill('Deterministic E2E submission');
  await page.getByRole('button', { name: 'Submit' }).click();
  await expect(page.getByText('Deterministic E2E submission')).toBeVisible();
});

test('nutrition page renders for an athlete', async ({ page, athleteIds }) => {
  await page.goto(`/athletes/${athleteIds.primary}/nutrition-checkins/new`);
  await expect(page.getByRole('heading', { name: 'Weekly check-in' })).toBeVisible();
  await expect(page.locator('input[name="average_calories"]')).toBeVisible();
  await expect(page.locator('select[name="nutrition_adherence"]')).toBeVisible();
});

test('athlete dashboard is isolated to the selected test athlete', async ({ page, request, athleteIds, athleteSession }) => {
  const unauthenticated = await page.goto('/athlete/dashboard');
  expect(unauthenticated?.status()).toBe(401);
  await athleteSession(page.request, athleteIds.primary);
  await page.goto('/athlete/dashboard');
  await expect(page.getByRole('heading', { name: 'Welcome back, Alex' })).toBeVisible();
  await expect(page.getByText('Deterministic strength block')).toBeVisible();
  await expect(page.getByText('Sam Morgan')).toHaveCount(0);
  await expect(page.getByText('sam.private@example.test')).toHaveCount(0);
});
