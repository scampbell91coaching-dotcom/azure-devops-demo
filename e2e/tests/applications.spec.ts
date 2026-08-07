import { test, expect } from '../fixtures/test';

test('public application submission appears in coach inbox and can be progressed', async ({ page }) => {
  const publicBaseUrl = process.env.E2E_PUBLIC_BASE_URL ?? 'http://127.0.0.1:8092';
  const uniqueEmail = `inbox.${Date.now()}@example.test`;

  await page.goto(`${publicBaseUrl}/apply`);
  await page.getByLabel('First name').fill('Inbox');
  await page.getByLabel('Last name').fill('Candidate');
  await page.getByLabel('Email address').fill(uniqueEmail);
  await page.getByLabel('Instagram').fill('@inboxcandidate');
  await page.getByLabel('Country').fill('United Kingdom');
  await page.getByRole('button', { name: 'Continue' }).click();

  await page.getByLabel('Years training').fill('4');
  await page.getByLabel('Squat (kg)').fill('180');
  await page.getByLabel('Bench (kg)').fill('115');
  await page.getByLabel('Deadlift (kg)').fill('220');
  await page.getByLabel('Competition planned?').fill('E2E Open');
  await page.getByRole('button', { name: 'Continue' }).click();

  await page.getByLabel('What are you working towards?').fill('Qualify for nationals through consistent progress.');
  await page.getByLabel('What is holding you back?').fill('Managing fatigue across the training week.');
  await page.getByRole('button', { name: 'Continue' }).click();

  await page.getByLabel('What would a successful coaching experience look like for you?').fill('Clear programming and direct technical feedback.');
  await page.locator('input[name="video_feedback_ready"][value="yes"]').check();
  await page.locator('input[name="communication_ready"][value="yes"]').check();
  await page.locator('input[name="minimum_term_ready"][value="yes"]').check();
  await page.getByRole('button', { name: 'Continue' }).click();

  await page.locator('input[name="privacy_consent"][value="yes"]').check();
  await page.getByRole('button', { name: 'Submit Application' }).click();
  await expect(page.getByText('Application received')).toBeVisible();

  await page.goto('/login');
  await page.getByLabel('Email address').fill('coach.e2e@example.test');
  await page.getByLabel('Password').fill('Coach E2E password!');
  await page.getByRole('button', { name: /sign in/i }).click();
  await page.getByRole('link', { name: /Applications/ }).click();

  await expect(page.getByRole('heading', { level: 1, name: 'Applications' })).toBeVisible();
  await expect(page.getByText('Inbox Candidate')).toBeVisible();
  await expect(page.getByText(uniqueEmail)).toBeVisible();
  await page.getByRole('link', { name: /Review application from Inbox Candidate/ }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Inbox Candidate' })).toBeVisible();
  await expect(page.getByText('Qualify for nationals through consistent progress.')).toBeVisible();

  await page.getByLabel('Update status').selectOption('contacted');
  await page.getByRole('button', { name: 'Save status' }).click();
  await expect(page.getByLabel('Current status: contacted')).toBeVisible();
});
