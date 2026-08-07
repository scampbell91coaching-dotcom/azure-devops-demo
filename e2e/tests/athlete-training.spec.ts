import { test, expect } from '../fixtures/test';

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
  for (let index = 0; index < 3; index += 1) {
    const row = sets.nth(index);
    await row.getByLabel('Complete').check();
    await row.locator('input[name$="-load"]').fill(String(100 + index * 2.5));
    await row.locator('input[name$="-reps"]').fill('5');
    await row.locator('input[name$="-rpe"]').fill(String(7 + index * 0.5));
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
  await page.goto('/athletes/101');
  await page.getByRole('link', { name: 'Review training' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Squat day' })).toBeVisible();
  await expect(page.getByText('Moved well on video.')).toBeVisible();
  console.log(
    'COACH REVIEW CARDS:',
    await page.locator('.coach-checkin-card').allInnerTexts()
  );

});
