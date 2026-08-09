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
  await page.getByTestId('programming-athlete').filter({ hasText: 'Alex Rivera' }).click();
  await expect(
    page.getByRole('heading', { level: 1, name: 'Alex Rivera' })
  ).toBeVisible();
  await page.getByRole('link', { name: 'Open block' }).click();
  await expect(page.getByRole('heading', { name: 'Deterministic strength block' })).toBeVisible();
  await page.getByRole('link', { name: /Foundation week/ }).click();
  await expect(page.getByRole('heading', { name: 'Foundation week' })).toBeVisible();
  await expect(
    page.locator('#session-501').getByTestId('lift-slot').filter({
      hasText: 'Competition Squat',
    }).first()
  ).toBeVisible();
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
  await page.goto('/programming');
  await page.getByTestId('programming-athlete').filter({ hasText: 'Alex Rivera' }).click();
  await expect(
    page.getByRole('heading', { level: 1, name: 'Alex Rivera' })
  ).toBeVisible();
  await page.getByRole('link', { name: 'Open block' }).click();
  await page.getByRole('link', { name: /Foundation week/ }).click();
  await page.getByTestId('programming-session').filter({ hasText: 'Squat day' }).getByRole('link', { name: 'Open session' }).click();
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

  await form.getByRole('button', { name: 'Add exercise' }).click();

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
  await added.getByRole('button', { name: 'Delete Lat Pulldown' }).click();
  await expect(added).toHaveCount(0);
  expect(failedResponses).toEqual([]);
  await expect(
    page.getByTestId('lift-slot').filter({ hasText: 'Competition Squat' }).first()
  ).toBeVisible();

  await expect(page.locator('[data-prescription-row]').filter({
    has: page.locator('input[name="exercise_name"][value="Competition Squat"]'),
  })).toHaveCount(0);
});

test('lift-slot editor persists an RPE range and same-family back-off after reload', async ({ page }) => {
  await page.goto('/programming/weeks/401');
  const session = page.getByTestId('programming-session').filter({ hasText: 'Squat day' });
  const editor = session.getByTestId('lift-slot-editor').first();
  await editor.locator('select[name="top_rpe_mode"]').selectOption('range');
  await editor.locator('input[name="top_rpe_min"]').fill('5');
  await editor.locator('input[name="top_rpe_max"]').fill('6');
  await editor.locator('input[name="back_off_enabled"]').check();
  await editor.locator('select[name="back_off_exercise_id"]').selectOption('');
  await editor.locator('input[name="back_off_sets"]').fill('3');
  await editor.locator('input[name="back_off_reps"]').fill('6');
  await editor.locator('input[name="back_off_rpe"]').fill('6');
  const benchChoice = editor.locator('select[name="back_off_exercise_id"] option[data-family="bench"]').first();
  await expect(benchChoice).toHaveAttribute('disabled', '');
  await editor.getByRole('button', { name: 'Save lift slot' }).click();
  await page.reload();
  await expect(session.getByText(/Top: Competition Squat 3 x 5 @ RPE 5-6/)).toBeVisible();
  await expect(session.getByText(/Back-off: Competition Squat 3 x 6 @ RPE 6/)).toBeVisible();
  await expect(page.getByLabel('Taxonomy-backed competition lift exposures')).toContainText('Squat 2');
});

test('Block Factory adds ordered upper and lower accessories and persists generated prescriptions', async ({ page }) => {
  await page.goto('/programming/factory');
  await page.getByLabel('Athlete').selectOption({ label: 'Alex Rivera' });
  await page.locator('input[name="name"]').fill('Catalogue accessory block');
  await page.getByRole('button', { name: 'Add accessory' }).click();
  const selectAccessory = async (
    select: ReturnType<typeof page.locator>,
    exerciseName: string
  ) => {
    const option = select.locator('option').filter({ hasText: exerciseName });

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
  const previewText = await page.locator('.factory-preview__day li').allTextContents();
  const previewCableRow = previewText.findIndex(text => text.includes('Cable Row'));
  const previewSplitSquat = previewText.findIndex(text => text.includes('Bulgarian Split Squat'));

  expect(previewCableRow).toBeGreaterThanOrEqual(0);
  expect(previewSplitSquat).toBeGreaterThanOrEqual(0);
  expect(previewCableRow).toBeLessThan(previewSplitSquat);
  await page.getByRole('button', { name: 'Accept proposal' }).click();
  await expect(page.getByRole('heading', { name: 'Catalogue accessory block' })).toBeVisible();
  await page.getByRole('link', { name: /Week 1/ }).click();
  const persistedText = await page
    .getByTestId('programming-session')
    .locator('.week-prescription')
    .allTextContents();

  const persistedCableRow = persistedText.findIndex(text => text.includes('Cable Row'));
  const persistedSplitSquat = persistedText.findIndex(text => text.includes('Bulgarian Split Squat'));

  expect(persistedCableRow).toBeGreaterThanOrEqual(0);
  expect(persistedSplitSquat).toBeGreaterThanOrEqual(0);
  expect(persistedCableRow).toBeLessThan(persistedSplitSquat);
});

test('Block Factory previews taxonomy-backed exposures with zero assistance and incomplete state', async ({ page }) => {
  await page.goto('/programming/factory');
  await page.getByLabel('Athlete').selectOption({ label: 'Sam Morgan' });
  await expect(page.getByText('Zero assistance is valid')).toBeVisible();
  await page.getByRole('button', { name: 'Preview' }).click();
  await expect(page.getByRole('heading', { name: 'Weekly programming intelligence' })).toBeVisible();
  await expect(
    page.locator('.factory-preview__intelligence p').filter({ hasText: 'Exposures:' })
  ).toContainText('2 squat · 3 bench · 1 deadlift');
  await expect(page.getByText(/Incomplete data:/)).toBeVisible();
  await expect(page.getByText('Reported fatigue:', { exact: false })).toHaveCount(0);
  await expect(page.getByText(/0 coach-selected assistance/)).toHaveCount(4);
  await expect(page.getByText('Accessory Day', { exact: false })).toHaveCount(0);
});

test('Block Factory edit presents coach override provenance', async ({ page }) => {
  await page.goto('/programming/factory');
  await page.getByLabel('Athlete').selectOption({ label: 'Alex Rivera' });
  await page.getByRole('button', { name: 'Preview' }).click();
  await page.getByLabel('Block name').fill('Coach adjusted proposal');
  await page.getByLabel('Coach override reason (required after editing)').fill('Meet timing requires a clearer block label');
  await page.getByRole('button', { name: 'Preview' }).click();
  await expect(page.getByTestId('coach-override-provenance')).toContainText('Meet timing requires a clearer block label');
  await expect(page.getByTestId('coach-override-provenance')).toContainText('coach.e2e@example.test');
});

test('Block Factory rejects an edit without the required reason', async ({ page }) => {
  await page.goto('/programming/factory');
  await page.getByLabel('Athlete').selectOption({ label: 'Alex Rivera' });
  await page.getByRole('button', { name: 'Preview' }).click();
  await page.getByLabel('Block name').fill('Unreasoned browser edit');
  const rejected = page.waitForResponse(response =>
    response.url().endsWith('/programming/factory/preview') && response.request().method() === 'POST'
  );
  await page.getByRole('button', { name: 'Preview' }).click();
  expect((await rejected).status()).toBe(400);
  await expect(page.getByText(/requires a coach override reason/)).toBeVisible();
});

test('Block Factory rejects a stale superseded proposal', async ({ page }) => {
  await page.goto('/programming/factory');
  await page.getByLabel('Athlete').selectOption({ label: 'Alex Rivera' });
  await page.getByRole('button', { name: 'Preview' }).click();
  const originalFields = await page.locator('#block-factory-form').evaluate(form =>
    Array.from(new FormData(form as HTMLFormElement).entries()).map(([key, value]) => [key, String(value)])
  );
  await page.getByLabel('Block name').fill('Superseding browser edit');
  await page.getByLabel('Coach override reason (required after editing)').fill('Supersede the first browser proposal');
  await page.getByRole('button', { name: 'Preview' }).click();
  const stale = await page.evaluate(async fields => {
    const response = await fetch('/programming/factory', {
      method: 'POST',
      body: new URLSearchParams(fields),
      redirect: 'follow',
    });
    return { status: response.status, body: await response.text() };
  }, originalFields);
  expect(stale.status).toBe(409);
  expect(stale.body).toContain('already decided');
});

test('Block Factory prevents replay after acceptance', async ({ page }) => {
  await page.goto('/programming/factory');
  await page.getByLabel('Athlete').selectOption({ label: 'Alex Rivera' });
  await page.getByLabel('Block name').fill('Replay protected browser proposal');
  await page.getByRole('button', { name: 'Preview' }).click();
  const statuses = await page.locator('#block-factory-form').evaluate(async form => {
    const fields = Array.from(new FormData(form as HTMLFormElement).entries()).map(([key, value]) => [key, String(value)]);
    const submit = () => fetch('/programming/factory', {
      method: 'POST',
      body: new URLSearchParams(fields),
      redirect: 'manual',
    });
    const first = await submit();
    const second = await submit();
    return [first.status, second.status];
  });
  // Chromium exposes a manually handled navigation redirect as an opaque
  // redirect with status 0. The second identical POST must be rejected.
  expect(statuses[0]).toBe(0);
  expect(statuses[1]).toBe(409);
});

test('Block Factory accepts once and persists the block after reload', async ({ page }) => {
  await page.goto('/programming/factory');
  await page.getByLabel('Athlete').selectOption({ label: 'Alex Rivera' });
  await page.getByLabel('Block name').fill('Accepted browser proposal');
  await page.getByRole('button', { name: 'Preview' }).click();
  await page.getByRole('button', { name: 'Accept proposal' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Accepted browser proposal' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { level: 1, name: 'Accepted browser proposal' })).toBeVisible();
});

test('Block Factory dismisses a proposal without creating a block', async ({ page }) => {
  await page.goto('/programming/factory');
  await page.getByLabel('Athlete').selectOption({ label: 'Alex Rivera' });
  await page.getByLabel('Block name').fill('Dismissed browser proposal');
  await page.getByRole('button', { name: 'Preview' }).click();
  await page.getByRole('button', { name: 'Dismiss proposal' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Block Factory' })).toBeVisible();
  await page.goto('/programming');
  await expect(page.getByText('Dismissed browser proposal')).toHaveCount(0);
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
  await expect(page.getByRole('heading', { name: 'Alex’s training' })).toBeVisible();
  await expect(page.getByText('Deterministic strength block')).toBeVisible();
  await expect(page.getByText('Sam Morgan')).toHaveCount(0);
  await expect(page.getByText('sam.private@example.test')).toHaveCount(0);
});
