import { test, expect } from '../fixtures/test';

const pilot = {
  id: 303,
  name: 'Taylor Jordan',
  email: 'taylor.pilot@example.test',
  password: 'Pilot Athlete password!',
  block: 'First paying athlete strength pilot',
  session: 'Squat strength and assistance',
};

async function signIn(
  page: import('@playwright/test').Page,
  email: string,
  password: string,
) {
  await page.goto('/login');
  await page.locator('input[name="email"]').fill(email);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole('button', { name: /sign in/i }).click();
}

async function changeAccount(page: import('@playwright/test').Page) {
  await page.context().clearCookies();
}

test('first paying athlete money path: draft to immutable coach-reviewed training', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });

  // Test-only account bootstrap is pre-provisioned because current main has no
  // invitation delivery flow. From sign-in onward this is the real athlete path.
  await signIn(page, pilot.email, pilot.password);
  await expect(page).toHaveURL('/athlete/dashboard');
  await expect(page.getByRole('heading', { name: 'Taylor’s training' })).toBeVisible();
  await expect(page.getByText('No current programme')).toBeVisible();
  await page.goto('/athlete/programme/sessions/801');
  await expect(page).toHaveURL('/athlete/programme/sessions/801');
  await expect(page.getByRole('heading', { name: 'Page not found' })).toBeVisible();

  await changeAccount(page);
  await signIn(page, 'coach.e2e@example.test', 'Coach E2E password!');
  await expect(page).toHaveURL('/coach');
  await page.goto(`/athletes/${pilot.id}/programming`);
  await expect(page.getByRole('heading', { name: pilot.name })).toBeVisible();
  const draft = page.locator('.coach-list__item').filter({ hasText: pilot.block });
  await expect(draft).toContainText('Draft');
  await draft.getByRole('link', { name: 'Open block' }).click();
  await expect(page.getByText('Draft', { exact: true })).toBeVisible();

  await page.getByRole('link', { name: 'Pilot week 1' }).click();
  const sessionCard = page.getByTestId('programming-session').filter({ hasText: pilot.session });
  const liftSlot = sessionCard
    .getByTestId('lift-slot')
    .filter({ hasText: 'Competition Squat' })
    .first();
  await expect(liftSlot).toContainText('Competition Squat');
  await expect(liftSlot).toContainText('1 x 3');
  await expect(liftSlot).toContainText('@ RPE 7.5-8.5');
  await expect(liftSlot).toContainText('Pause Squat');

  await expect(liftSlot).toContainText('2 x 5');
  await expect(liftSlot).toContainText('@ RPE 6.5-7.5');

  const prescriptions = sessionCard.locator('.week-prescription');
  await expect(prescriptions.first()).toContainText('Cable Row');

  await page.getByRole('link', { name: pilot.block, exact: true }).click();
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Publish programme' }).click();
  await expect(page.getByText('Active', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText('Active', { exact: true })).toBeVisible();

  await changeAccount(page);
  await signIn(page, pilot.email, pilot.password);
  await expect(page).toHaveURL('/athlete/dashboard');
  await expect(page.getByText(pilot.block)).toBeVisible();
  await expect(page.getByText('Alex Rivera')).toHaveCount(0);
  await expect(page.getByText('Sam Morgan')).toHaveCount(0);
  await expect(page.locator('html')).toHaveJSProperty('scrollWidth', 390);
  await page.getByRole('link', { name: 'View session' }).click();
  await expect(page.getByRole('heading', { level: 1, name: pilot.session })).toBeVisible();

  const rows = page.locator('[data-set-row]');
  await expect(rows).toHaveCount(5);
  for (let index = 0; index < 5; index += 1) {
    const row = rows.nth(index);
    await row.getByLabel('Complete').check();
    await row.locator('input[name$="-load"]').fill(String([122.5, 102.5, 100, 45, 47.5][index]));
    await row.locator('input[name$="-reps"]').fill(String([3, 5, 5, 10, 10][index]));
    await row.locator('input[name$="-rpe"]').fill(String([8, 7, 7.5, 6.5, 7][index]));
  }
  await rows.first().getByText('Add note').click();
  await rows.first().locator('textarea').fill('Top set moved cleanly; keep the same load next week.');
  await expect(page.locator('html')).toHaveJSProperty('scrollWidth', 390);
  await expect(page.getByRole('button', { name: 'Finish session' })).toBeVisible();
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Finish session' }).click();
  await expect(page.getByText('Session complete', { exact: true })).toBeVisible();

  await page.reload();
  await expect(page.getByText('122.5 kg')).toBeVisible();
  await expect(page.getByText('Top set moved cleanly; keep the same load next week.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Finish session' })).toHaveCount(0);

  await expect(
    page.locator(
      '[data-set-row] input:not([type="hidden"]), [data-set-row] textarea'
    )
  ).toHaveCount(0);
  await expect(page.locator('html')).toHaveJSProperty('scrollWidth', 390);

  await changeAccount(page);
  await signIn(page, 'coach.e2e@example.test', 'Coach E2E password!');
  await page.goto(`/athletes/${pilot.id}`);
  await expect(page.getByRole('heading', { name: pilot.name })).toBeVisible();
  await expect(page.getByText('Alex Rivera')).toHaveCount(0);
  await page.getByRole('link', { name: 'Review training' }).click();
  await expect(page.getByRole('heading', { level: 1, name: pilot.session })).toBeVisible();
  await expect(page.getByText(pilot.name, { exact: true })).toBeVisible();
  const topSet = page.locator('.coach-checkin-card').first();
  await expect(topSet).toContainText('Load: 122.5 kg (target 120.0 kg)');
  await expect(topSet).toContainText('Reps: 3 (target 3)');
  await expect(topSet).toContainText('RPE: 8.0');
  await expect(topSet).toContainText('Top set moved cleanly; keep the same load next week.');
  await expect(page.getByText('Alex Rivera')).toHaveCount(0);
  await expect(page.getByText('Sam Morgan')).toHaveCount(0);
});
