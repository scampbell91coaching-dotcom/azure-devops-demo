import { test, expect } from '../fixtures/test';

test.use({ mutationScope: 'services' });

test.beforeEach(async ({ page, authenticatedState }) => {
  await authenticatedState(page);
});

test('coach dashboard renders deterministic athlete data', async ({ page }) => {
  await page.goto('/coach');
  await expect(page.getByRole('heading', { name: 'Daily review' })).toBeVisible();
  await expect(page.getByText('Alex Rivera').first()).toBeVisible();
});

test('disabled nutrition entitlement removes active surfaces and protects direct routes', async ({
  page,
  request,
  resetE2EFixture,
}) => {
  const athleteId = 202;
  await resetE2EFixture(request, 'services');

  await page.goto(`/athletes/${athleteId}`);
  const services = page.locator('#client-services');
  await services.locator('select[name="nutrition"]').selectOption('no');

  page.once('dialog', async dialog => {
    await dialog.accept();
  });

  await services.getByRole('button', { name: 'Save client services' }).click();

  try {
    await page.goto(`/athletes/${athleteId}`);
    await expect(page.getByRole('link', { name: 'Add nutrition check-in' })).toHaveCount(0);
    await expect(page.getByText('History only')).toBeVisible();

    await page.goto(`/athletes/${athleteId}/nutrition-checkins/new`);
    await expect(page.getByRole('heading', { name: 'Access denied' })).toBeVisible();
  } finally {
    await page.goto(`/athletes/${athleteId}`);
    const restore = page.locator('#client-services');
    await restore.locator('select[name="nutrition"]').selectOption('yes');
    await restore.getByRole('button', { name: 'Save client services' }).click();
  }
});

test('athlete list opens an athlete detail', async ({ page }) => {
  await page.goto('/athletes');
  await expect(page.getByRole('heading', { level: 1, name: 'Athletes', exact: true })).toBeVisible();
  await page.getByRole('link', { name: /Alex Rivera/ }).click();
  await expect(page).toHaveURL(/\/athletes\/101$/);
  await expect(page.getByRole('heading', { name: 'Alex Rivera' })).toBeVisible();
});

test('coach manages concise client services with safe disable confirmation', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/athletes/101');
  const services = page.locator('#client-services');
  await expect(services.getByRole('heading', { name: 'Client services' })).toBeVisible();
  await expect(services.getByText(/Existing programmes, check-ins, reviews and notes are retained/)).toBeVisible();
  await services.locator('select[name="video_review"]').selectOption('limited');
  await services.getByRole('button', { name: 'Save client services' }).click();
  await expect(page).toHaveURL(/#client-services$/);
  await expect(services.locator('select[name="video_review"]')).toHaveValue('limited');
  const videoService = services
    .locator('label')
    .filter({ hasText: 'Video review' });

  await expect(
    videoService.getByText(/Set by coach\.e2e@example\.test/)
  ).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBeTruthy();
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
  await page.locator('a[href="/programming/blocks/301"]').click();
  await expect(page.getByRole('heading', { name: 'Deterministic strength block' })).toBeVisible();
  await page.getByRole('link', { name: /Foundation week/ }).click();
  await expect(page.getByRole('heading', { name: 'Foundation week' })).toBeVisible();
  await expect(
    page.locator('#session-501').getByTestId('lift-slot').filter({
      hasText: 'Competition Squat',
    }).first()
  ).toBeVisible();
});

test('coach duplicates and safely deletes programme structure', async ({ page }) => {
  await page.goto('/programming/blocks/301');
  await page.getByRole('button', { name: 'Duplicate block' }).click();
  await expect(page.getByRole('heading', { name: 'Deterministic strength block Copy' })).toBeVisible();
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Delete draft' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Alex Rivera' })).toBeVisible();

  await page.goto('/programming/weeks/401');
  await page.getByRole('button', { name: 'Duplicate week' }).click();
  await expect(page.getByRole('heading', { name: 'Foundation week Copy' })).toBeVisible();
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Delete week' }).click();
  await expect(page.getByRole('heading', { name: 'Deterministic strength block' })).toBeVisible();
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
  await page.locator('a[href="/programming/blocks/301"]').click();
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
  expect(response.request().postDataJSON()).toEqual({
    exercise_name: 'Lat Pulldown',
    sets: '3',
    reps: '10',
    load_kg: '',
    percentage: '',
    rpe: '',
    tempo: '',
    rest_seconds: '',
    notes: '',
  });
  expect(response.request().headers()['x-csrf-token']).toBeTruthy();

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
  await page.goto('/programming/weeks/902');
  const session = page.getByTestId('programming-session').filter({ hasText: 'Lift slot persistence session' });
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
  const restoredEditor = session.getByTestId('lift-slot-editor').first();
  await expect(restoredEditor.locator('select[name="top_rpe_mode"]')).toHaveValue('range');
  await expect(restoredEditor.locator('input[name="top_rpe_min"]')).toHaveValue('5.0');
  await expect(restoredEditor.locator('input[name="top_rpe_max"]')).toHaveValue('6.0');
  await expect(restoredEditor.locator('input[name="back_off_enabled"]')).toBeChecked();
  await expect(restoredEditor.locator('select[name="back_off_exercise_id"]')).toHaveValue('');
  await expect(session.getByText(/Top: Competition Squat 3 x 5 @ RPE 5-6/)).toBeVisible();
  await expect(session.getByText(/Back-off: Competition Squat 3 x 6 @ RPE 6/)).toBeVisible();
  await expect(page.getByLabel('Taxonomy-backed competition lift exposures')).toContainText('Squat 1');
});

test('Block Factory persists more than three coach-selected accessories per session', async ({ page }) => {
  await page.goto('/programming/factory');
  await page.getByLabel('Athlete').selectOption({ label: 'Alex Rivera' });
  await page.locator('input[name="name"]').fill('Unlimited accessory block');
  await page.getByLabel('Training days').fill('3');

  const accessoryCount = 12;
  const selectedValues = new Set<string>();

  for (let index = 0; index < accessoryCount; index += 1) {
    await page.getByRole('button', { name: 'Add accessory' }).click();

    const select = page
      .locator('select[name="accessory_exercise_id"]')
      .nth(index);

    const values = await select.locator('option').evaluateAll((options) =>
      options
        .map((option) => (option as HTMLOptionElement).value)
        .filter(Boolean)
    );

    const value = values.find((candidate) => !selectedValues.has(candidate));
    expect(value, `Distinct accessory choice for row ${index + 1}`).toBeTruthy();

    selectedValues.add(value!);
    await select.selectOption(value!);
  }

  expect(selectedValues.size).toBe(12);

  await expect(page.locator('[data-accessory-summary]')).toContainText(
    '12 coach-selected assistance exercises'
  );

  await page.getByRole('button', { name: 'Preview' }).click();

  const previewAssistanceCounts = await page
    .locator('.factory-preview__count')
    .evaluateAll(elements => elements.map(element =>
      Number(element.textContent?.match(/(\d+) assistance exercises?/)?.[1] ?? 0)
    ));
  expect(previewAssistanceCounts.reduce((total, count) => total + count, 0)).toBe(12);
  expect(Math.max(...previewAssistanceCounts)).toBeGreaterThan(3);

  await page.getByRole('button', { name: 'Accept proposal' }).click();

  await expect(
    page.getByRole('heading', { name: 'Unlimited accessory block' })
  ).toBeVisible();

  await page.getByRole('link', { name: /Week 1/ }).click();

  const sessions = page.getByTestId('programming-session');
  await expect(sessions).toHaveCount(3);

  const persistedCounts: number[] = [];
  for (let index = 0; index < 3; index += 1) {
    persistedCounts.push(
      await sessions.nth(index).getByTestId('assistance-provenance').count()
    );
  }
  expect(persistedCounts.reduce((total, count) => total + count, 0)).toBe(12);
  expect(Math.max(...persistedCounts)).toBeGreaterThan(3);

  await page.reload();

  for (let index = 0; index < 3; index += 1) {
    await expect(
      page.getByTestId('programming-session')
        .nth(index)
        .getByTestId('assistance-provenance')
    ).toHaveCount(persistedCounts[index]);
  }
});

test('Block Factory golden programme prefills an editable canonical six-day week', async ({ page }) => {
  await page.goto('/programming/factory');

  await page.getByLabel('Athlete').selectOption({ label: 'Alex Rivera' });
  await page.getByLabel('Start from').selectOption('golden');
  await expect(page.locator('select[name="golden_programme"]')).toBeVisible();
  await page.locator('select[name="golden_programme"]').selectOption('advanced-6-day-high-frequency-bench');

  await expect(page.getByLabel('Split')).toHaveValue('POWERLIFTING_6');
  await expect(page.getByLabel('Training days')).toHaveValue('6');
  await expect(page.getByLabel('Squat frequency')).toHaveValue('2');
  await expect(page.getByLabel('Bench frequency')).toHaveValue('5');
  await expect(page.getByLabel('Deadlift frequency')).toHaveValue('2');

  await page.getByLabel('Block name').fill('Edited six-day golden');
  await page.getByRole('button', { name: /preview/i }).click();
  await expect(page.getByText('Day 6 \u00b7 SBD', { exact: false })).toBeVisible();
  await expect(page.getByLabel('Block name')).toHaveValue('Edited six-day golden');
});

test('Block Factory automatic assistance falls back to suitable library metadata and persists', async ({ page }) => {
  await page.goto('/programming/factory');
  await page.getByLabel('Athlete').selectOption({ label: 'Alex Rivera' });
  await page.getByLabel('Block name').fill('Automatic accessory fallback block');
  await page.getByLabel('Split').selectOption('POWERLIFTING_3');
  await page.getByLabel('Training days').fill('3');
  await page.getByLabel('Selection mode').selectOption('automatic');
  await page.getByLabel('Accessory volume').selectOption('medium');
  await expect(page.getByLabel('Selection mode')).toHaveValue('automatic');

  await page.getByRole('button', { name: 'Preview' }).click();

  const previewCounts = await page.locator('.factory-preview__count').allTextContents();
  const assistanceTotal = previewCounts.reduce((total, text) => {
    const match = text.match(/(\d+) assistance exercises?/);
    return total + Number(match?.[1] ?? 0);
  }, 0);
  expect(assistanceTotal).toBeGreaterThan(0);

  await page.getByRole('button', { name: 'Accept proposal' }).click();
  await expect(
    page.getByRole('heading', { name: 'Automatic accessory fallback block' })
  ).toBeVisible();
  await page.getByRole('link', { name: /Week 1/ }).click();

  const persistedAssistance = page.getByTestId('assistance-provenance');
  await expect(persistedAssistance.first()).toBeVisible();
  const persistedCount = await persistedAssistance.count();
  expect(persistedCount).toBeGreaterThan(0);

  await page.reload();
  await expect(page.getByTestId('assistance-provenance')).toHaveCount(persistedCount);
});

test('Block Factory previews taxonomy-backed exposures with zero assistance and incomplete state', async ({ page }) => {
  await page.goto('/programming/factory');
  await page.getByLabel('Athlete').selectOption({ label: 'Sam Morgan' });
  await expect(page.getByText('No assistance selected.')).toBeVisible();
  await page.getByLabel('Training days').fill('3');
  await page.getByLabel('Squat frequency').fill('1');
  await page.getByLabel('Bench frequency').fill('1');
  await page.getByLabel('Deadlift frequency').fill('1');
  await page.getByLabel('Selection mode').selectOption('none');
  await page.getByRole('button', { name: 'Preview' }).click();
  await expect(page.getByRole('heading', { name: 'Proposal explanation' })).toBeVisible();
  await expect(
    page.locator('.factory-preview__intelligence p').filter({ hasText: 'Exposures' })
  ).toContainText('1 squat · 1 bench · 1 deadlift');

  await page
    .getByText('Review decision evidence and progression', { exact: true })
    .click();

  await expect(page.getByText(/Incomplete data:/)).toBeVisible();
  await expect(page.getByText('Reported fatigue:', { exact: false })).toHaveCount(0);
  const zeroAssistanceDays = page.locator('.factory-preview__count', {
    hasText: '0 assistance exercises',
  });
  await expect(zeroAssistanceDays).toHaveCount(3);
  await expect(page.getByText('Accessory Day', { exact: false })).toHaveCount(0);
});

test('Block Factory keeps no assistance authoritative across volume and grip context', async ({ page }) => {
  await page.goto('/programming/factory');
  await page.getByLabel('Athlete').selectOption({ label: 'Sam Morgan' });
  await page.getByLabel('Competition deadlift grip').selectOption('hook');
  await page.getByLabel('Training strap usage').selectOption('most');
  await page.getByLabel('Grip work priority').selectOption('priority');
  await page.getByLabel('Accessory volume').selectOption('high');
  await page.getByLabel('Selection mode').selectOption('none');
  await page.getByRole('button', { name: 'Preview' }).click();

  await expect(page.getByLabel('Competition deadlift grip')).toHaveValue('hook');
  await expect(page.getByLabel('Training strap usage')).toHaveValue('most');
  await expect(page.getByLabel('Grip work priority')).toHaveValue('priority');
  await expect(page.getByLabel('Accessory volume')).toHaveValue('high');
  await expect(page.getByText(/0 assistance exercises/)).toHaveCount(4);
});

test('Block Factory edit presents coach override provenance', async ({ page }) => {
  await page.goto('/programming/factory');
  await page.getByLabel('Athlete').selectOption({ label: 'Alex Rivera' });
  await page.getByRole('button', { name: 'Preview' }).click();
  await page.getByLabel('Block name').fill('Coach adjusted proposal');
  await page.getByLabel('Coach override reason (required)').fill('Meet timing requires a clearer block label');
  await page.getByRole('button', { name: 'Preview' }).click();
  await expect(page.getByTestId('coach-override-provenance')).toContainText('Meet timing requires a clearer block label');
  await expect(page.getByTestId('coach-override-provenance')).toContainText('coach.e2e@example.test');
});

test('Block Factory rejects an edit without the required reason', async ({ page }) => {
  await page.goto('/programming/factory');
  await page.getByLabel('Athlete').selectOption({ label: 'Alex Rivera' });
  await page.getByRole('button', { name: 'Preview' }).click();
  await page.getByLabel('Block name').fill('Unreasoned browser edit');
  await expect(page.getByRole('button', { name: 'Accept proposal' })).toBeDisabled();
  await expect(page.getByText('This preview is out of date. Generate preview again before accepting.')).toBeVisible();
  await expect(page.getByLabel('Coach override reason (required)')).toBeVisible();
  await page.locator('#block-factory-form').evaluate((form: HTMLFormElement) => { form.noValidate = true; });
  const rejected = page.waitForResponse(response =>
    response.url().endsWith('/programming/factory/preview') && response.request().method() === 'POST'
  );
  await page.getByRole('button', { name: 'Preview' }).click();
  expect((await rejected).status()).toBe(422);
  await expect(page.locator('[data-error-summary]')).toContainText(
    'Editing a generated proposal requires a coach override reason.'
  );
  await expect(page.getByLabel('Block name')).toHaveValue('Unreasoned browser edit');
  const overrideReason = page.getByLabel('Coach override reason (required)');
  await expect(overrideReason).toHaveAttribute('aria-invalid', 'true');
  await expect(overrideReason).toBeFocused();
});

test('Block Factory re-preview enables acceptance after a proposal edit', async ({ page }) => {
  await page.goto('/programming/factory');
  await page.getByLabel('Athlete').selectOption({ label: 'Alex Rivera' });
  await page.getByRole('button', { name: 'Preview' }).click();
  await expect(page.getByRole('button', { name: 'Accept proposal' })).toBeEnabled();
  await page.getByLabel('Block name').fill('Re-previewed proposal');
  await expect(page.getByRole('button', { name: 'Accept proposal' })).toBeDisabled();
  await page.getByLabel('Coach override reason (required)').fill('Use the coach-facing block name');
  await page.getByRole('button', { name: 'Preview' }).click();
  await expect(page.getByRole('button', { name: 'Accept proposal' })).toBeEnabled();
});

test('Block Factory rejects a stale superseded proposal', async ({ page }) => {
  await page.goto('/programming/factory');
  await page.getByLabel('Athlete').selectOption({ label: 'Alex Rivera' });
  await page.getByRole('button', { name: 'Preview' }).click();
  const originalFields = await page.locator('#block-factory-form').evaluate(form =>
    Array.from(new FormData(form as HTMLFormElement).entries()).map(([key, value]) => [key, String(value)])
  );
  await page.getByLabel('Block name').fill('Superseding browser edit');
  await page.getByLabel('Coach override reason (required)').fill('Supersede the first browser proposal');
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
  async ({ page, athleteIds, athleteSession, request, resetE2EFixture }) => {
    await resetE2EFixture(request, 'check-in');
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
  await expect(page.getByRole('heading', { name: 'Alex’s coaching' })).toBeVisible();
  await expect(page.getByText('Deterministic strength block')).toBeVisible();
  await expect(page.getByText('Sam Morgan')).toHaveCount(0);
  await expect(page.getByText('sam.private@example.test')).toHaveCount(0);
});
