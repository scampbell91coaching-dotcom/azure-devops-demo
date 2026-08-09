import { test, expect } from '../fixtures/test';

test('coach assigns an ordered reusable warm-up and athlete sees it before work sets', async ({ page }) => {
  await page.goto('/login');
  await page.locator('input[name="email"]').fill('coach.e2e@example.test');
  await page.locator('input[name="password"]').fill('Coach E2E password!');
  await page.getByRole('button', { name: /sign in/i }).click();
  await page.goto('/programming/sessions/502');
  await page.getByText('Create and assign a reusable plan').click();
  const editor = page.locator('details').filter({ hasText: 'Create and assign a reusable plan' });
  await editor.locator('input[name="name"]').fill('E2E squat warm-up');
  await editor.locator('input[name="reason"]').fill('Coach-reviewed session preparation');
  await editor.locator('textarea[name="steps"]').fill('general | Bike | duration | 180 | 1 | 30 | Easy pace\nbarbell | Empty bar | barbell | 5@20kg | 2 | 60');
  await editor.getByRole('button', { name: 'Create and assign' }).click();
  await expect(page.getByTestId('warmup-editor').getByText('Bike')).toBeVisible();

  await page.context().clearCookies();
  await page.goto('/login');
  await page.locator('input[name="email"]').fill('alex.e2e@example.test');
  await page.locator('input[name="password"]').fill('Athlete E2E password!');
  await page.getByRole('button', { name: /sign in/i }).click();
  await page.goto('/athlete/programme/sessions/502');
  const warmup = page.getByTestId('athlete-warmup');
  await expect(warmup.getByText('Bike')).toBeVisible();
  await expect(warmup.getByText('Empty bar')).toBeVisible();
  const warmupBox = await warmup.boundingBox();
  const firstWorkSetBox = await page.locator('[data-exercise]').first().boundingBox();
  expect(warmupBox!.y).toBeLessThan(firstWorkSetBox!.y);
});

test('athlete records and finishes a session on a phone, then coach reviews it', async ({ page }) => {
  await page.setViewportSize({ width: 412, height: 915 });

  await page.goto('/login');
  await page.locator('input[name="email"]').fill('alex.e2e@example.test');
  await page.locator('input[name="password"]').fill('Athlete E2E password!');
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page).toHaveURL('/athlete/dashboard');

  await page.getByRole('link', { name: 'View session' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Squat day' })).toBeVisible();
  await expect(page.getByText('Not Started')).toBeVisible();

  const sets = page.locator('[data-set-row]');
  const setCount = await sets.count();

  for (let index = 0; index < setCount; index += 1) {
    const row = sets.nth(index);
    await row.getByLabel('Complete').check();
    await row.locator('input[name$="-load"]').fill(
      index < 3 ? String(100 + index * 2.5) : '100'
    );
    await row.locator('input[name$="-reps"]').fill('5');
    await row.locator('input[name$="-rpe"]').fill(
      index < 3 ? String(7 + index * 0.5) : '7'
    );
  }
  await sets.first().getByText('Add note').click();
  await sets.first().locator('textarea').fill('Moved well on video.');
  await expect(page.locator('html')).toHaveJSProperty('scrollWidth', 412);

  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: 'Finish session' }).click();
  await expect(page.getByText('Session complete', { exact: true })).toBeVisible();
  await expect(
    page.getByText(/^Finished \d{2} [A-Z][a-z]{2} \d{4}, \d{2}:\d{2}$/)
  ).toBeVisible();

  await page.reload();
  await expect(page.getByText('102.5 kg')).toBeVisible();
  await expect(page.getByText('Moved well on video.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Finish session' })).toHaveCount(0);
  await expect(page.locator('html')).toHaveJSProperty('scrollWidth', 412);

  await page.context().clearCookies();
  await page.goto('/login');
  await page.locator('input[name="email"]').fill('coach.e2e@example.test');
  await page.locator('input[name="password"]').fill('Coach E2E password!');
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page).toHaveURL('/coach');
  const reviewItem = page.locator('.coach-dashboard-list article').filter({
    hasText: 'Alex Rivera',
  }).filter({ hasText: 'Squat day' });
  await expect(reviewItem).toContainText('Needs review');
  await expect(reviewItem).toContainText('Notes: Moved well on video.');
  await reviewItem.getByRole('link', { name: 'Review session' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Squat day' })).toBeVisible();
  await expect(page.getByText('Moved well on video.')).toBeVisible();
  console.log(
    'COACH REVIEW CARDS:',
    await page.locator('.coach-checkin-card').allInnerTexts()
  );

});
