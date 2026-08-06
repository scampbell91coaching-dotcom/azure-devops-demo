import { test, expect } from '../fixtures/test';

test.beforeEach(async ({ page, authenticatedState }) => {
  await authenticatedState(page);
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

test('adds, edits, deletes, and preserves prescription order without an HTTP 400', async ({ page }) => {
  await page.goto('/programming/sessions/501');
  const failedResponses: number[] = [];
  page.on('response', response => {
    if (response.url().includes('/prescriptions') && response.status() >= 400) failedResponses.push(response.status());
  });
  const form = page.locator('[data-new-prescription-form]');
  await form.locator('input[name="exercise_name"]').fill('Lat Pulldown');
  await form.locator('input[name="sets"]').fill('3');
  await form.locator('input[name="reps"]').fill('10');
  const creationResponse = page.waitForResponse(response =>
    response.url().includes('/programming/api/sessions/') &&
    response.url().endsWith('/prescriptions') &&
    response.request().method() === 'POST'
  );

  await form.getByRole('button', { name: '+' }).click();

  const response = await creationResponse;
  expect(response.status()).toBe(201);

  const rows = page.locator('[data-prescription-row]');
  const addedIndex = await rows.evaluateAll((elements) =>
    elements.findIndex((element) => {
      const input = element.querySelector<HTMLInputElement>(
        'input[name="exercise_name"]'
      );
      return input?.value === 'Lat Pulldown';
    })
  );

  expect(addedIndex).toBeGreaterThanOrEqual(0);

  const added = rows.nth(addedIndex);
  await expect(
    added.locator('input[name="exercise_name"]')
  ).toHaveValue('Lat Pulldown');

  await added.locator('input[name="sets"]').fill('4');
  await expect(page.getByText('Saved', { exact: true })).toBeVisible();
  page.once('dialog', dialog => dialog.accept());
  await added.getByRole('button', { name: '×' }).click();
  await expect(added).toHaveCount(0);
  expect(failedResponses).toEqual([]);
  await expect(page.locator('[data-prescription-row]').first().locator('input[name="exercise_name"]')).toHaveValue('Competition Squat');
});

test('Block Factory adds ordered upper and lower accessories and persists generated prescriptions', async ({ page }) => {
  await page.goto('/programming/factory');
  await page.locator('select[name="athlete_id"]').selectOption('101');
  await page.locator('input[name="name"]').fill('Catalogue accessory block');
  await page.getByRole('button', { name: 'Add accessory' }).click();
  const selectAccessory = async (
    select: ReturnType<typeof page.locator>,
    exerciseName: string
  ) => {
    const option = select
      .locator('option')
      .filter({ hasText: exerciseName })
      .first();

    await expect(option).toHaveCount(1);

    const value = await option.getAttribute('value');
    expect(value, `Value for ${exerciseName}`).toBeTruthy();

    await select.selectOption(value!);
  };

  await selectAccessory(
    page.locator('select[name="accessory_exercise_id"]').nth(0),
    'Cable Row'
  );

  await page.getByRole('button', { name: 'Add accessory' }).click();

  await selectAccessory(
    page.locator('select[name="accessory_exercise_id"]').nth(1),
    'Bulgarian Split Squat'
  );
  await page.getByRole('button', { name: 'Generate block' }).click();
  await expect(page.getByRole('heading', { name: 'Catalogue accessory block' })).toBeVisible();
  await page.getByRole('link', { name: /Week 1/ }).click();
  await expect(page.getByText('Cable Row').first()).toBeVisible();
  await expect(page.getByText('Bulgarian Split Squat').first()).toBeVisible();
});

test(
  'renders and submits a supported weekly check-in',
  async ({ page, athleteIds, athleteSession }) => {
    await athleteSession(page.request, athleteIds.primary);

    await page.goto(`/athletes/${athleteIds.primary}/check-ins/new`);
  await expect(
    page.getByRole('heading', { level: 1 })
  ).toBeVisible();
  await expect(page.locator('input[name="fatigue"]')).toBeVisible();
  await expect(page.locator('input[name="recovery"]')).toBeVisible();
  await page.locator('input[name="fatigue"]').fill('6');
  await page.locator('input[name="recovery"]').fill('8');
  await page.locator('textarea[name="general_notes"]').fill('Deterministic E2E submission');
  await page.getByRole('button', { name: 'Send check-in' }).click();
  await expect(page.getByText('Deterministic E2E submission')).toBeVisible();
});

test(
  'nutrition page renders for an athlete',
  async ({ page, athleteIds, athleteSession }) => {
    await athleteSession(page.request, athleteIds.primary);

    await page.goto(`/athletes/${athleteIds.primary}/nutrition-checkins/new`);
  await expect(
    page.getByRole('heading', { level: 1 })
  ).toBeVisible();
  await expect(page.locator('input[name="average_calories"]')).toBeVisible();
  await expect(page.locator('select[name="nutrition_adherence"]')).toBeVisible();
});

test('athlete dashboard is isolated to the selected test athlete', async ({ page, athleteIds, athleteSession }) => {
  await page.getByRole('button', { name: 'Sign out' }).click();
  await page.goto('/athlete/dashboard');
  await expect(page).toHaveURL(/\/login\?next=/);
  await athleteSession(page.request, athleteIds.primary);
  await page.goto('/athlete/dashboard');
  await expect(page.getByRole('heading', { name: 'Welcome back, Alex' })).toBeVisible();
  await expect(page.getByText('Deterministic strength block')).toBeVisible();
  await expect(page.getByText('Sam Morgan')).toHaveCount(0);
  await expect(page.getByText('sam.private@example.test')).toHaveCount(0);
});
