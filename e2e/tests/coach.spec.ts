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

test('Meet Day creates a meet and calculates plates and all warm-up plans without overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/meet-day');
  await expect(page.getByRole('button', { name: 'Create meet' })).toBeVisible();
  await page.locator('input[name="name"]').fill('E2E Meet Day Open');
  await page.locator('select[name="athlete_id"]').selectOption('101');
  await page.getByRole('button', { name: 'Create meet' }).click();
  await expect(page.getByRole('heading', { name: 'E2E Meet Day Open' })).toBeVisible();
  const plateForm = page.locator('form[action$="/plate-calculator"]');
  await plateForm.locator('input[name="target_kg"]').fill('202.5');
  await plateForm.getByRole('button', { name: 'Calculate plate load' }).click();
  await expect(page.getByText(/Per side, load/)).toBeVisible();
  for (const [lift, opener] of [
    ['squat', '200'],
    ['bench', '120'],
    ['deadlift', '220'],
  ] as const) {
    const form = page
      .locator('form[action$="/warmups"]')
      .filter({ has: page.locator(`input[value="${lift}"]`) });

    const openerInput = form.locator('input[name="opener_kg"]');

    if (!(await openerInput.isVisible())) {
      const details = form.locator('xpath=ancestor::details[1]');

      if (await details.count()) {
        const isOpen = await details.evaluate(
          element => element.hasAttribute('open')
        );

        if (!isOpen) {
          await details.locator('summary').click();
        }
      }
    }

    await expect(openerInput).toBeVisible();
    await openerInput.fill(opener);

    await form
      .getByRole('button', { name: `Save ${lift} plan` })
      .click();

    const liftSection = page
      .getByRole('heading', {
        level: 3,
        name: new RegExp(`^${lift}$`, 'i'),
      })
      .locator('xpath=ancestor::section[contains(@class, "meet-day__lift")][1]');

    const openerRow = liftSection
      .getByRole('row')
      .filter({ has: page.getByRole('cell', { name: 'Attempt 1', exact: true }) });

    await expect(openerRow).toBeVisible();
    await expect(openerRow).toContainText(
      new RegExp(`${opener}(?:\\.0+)? kg`)
    );
    await expect(openerRow).toContainText('100%');
  }

  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBeTruthy();
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
  await page.getByRole('button', { name: 'Preview' }).click();
  const firstPreview = page.locator('.factory-preview__day').first();
  const previewText = await firstPreview.locator('li').allTextContents();
  expect(previewText.findIndex(text => text.includes('Cable Row'))).toBeLessThan(
    previewText.findIndex(text => text.includes('Bulgarian Split Squat'))
  );
  await page.getByRole('button', { name: 'Generate block' }).click();
  await expect(page.getByRole('heading', { name: 'Catalogue accessory block' })).toBeVisible();
  await page.getByRole('link', { name: /Week 1/ }).click();
  await expect(page.getByText('Cable Row').first()).toBeVisible();
  await expect(page.getByText('Bulgarian Split Squat').first()).toBeVisible();
});

test('Block Factory previews Standard role-balanced accessory volume', async ({ page }) => {
  await page.goto('/programming/factory');
  await page.locator('select[name="athlete_id"]').selectOption('101');
  await page.locator('input[name="training_days"]').fill('3');
  await page.locator('input[name="squat_frequency"]').fill('0');
  await page.locator('input[name="bench_frequency"]').fill('3');
  await page.locator('input[name="deadlift_frequency"]').fill('0');
  await page.locator('select[name="accessory_volume"]').selectOption('standard');
  await page.getByRole('button', { name: 'Preview' }).click();
  await expect(page.locator('.factory-preview__count')).toHaveCount(3);
  await expect(page.locator('.factory-preview__count').first()).toContainText('4 accessories');
  await expect(page.locator('.factory-preview__day').first()).toContainText('balancing');
});

test('Block Factory previews High and exact Custom accessory volume', async ({ page }) => {
  await page.goto('/programming/factory');
  await page.locator('select[name="athlete_id"]').selectOption('101');
  await page.locator('select[name="accessory_volume"]').selectOption('high');
  await page.getByRole('button', { name: 'Preview' }).click();
  for (const count of await page.locator('.factory-preview__count').allTextContents()) {
    expect(Number(count.match(/\d+/)?.[0])).toBeGreaterThanOrEqual(5);
    expect(Number(count.match(/\d+/)?.[0])).toBeLessThanOrEqual(6);
  }

  await page.locator('select[name="accessory_volume"]').selectOption('custom');
  await page.locator('input[name="accessory_count_min"]').fill('4');
  await page.locator('input[name="accessory_count_max"]').fill('4');
  await page.getByRole('button', { name: 'Preview' }).click();
  for (const count of await page.locator('.factory-preview__count').allTextContents()) {
    expect(count).toContain('4 accessories · target 4');
  }
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
