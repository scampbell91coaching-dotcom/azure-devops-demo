import { test, expect } from '../fixtures/test';

test.use({ mutationScope: 'meal-plan' });

test('coach builds, previews, publishes and revises a meal plan that the athlete reads', async ({
  page, request, authenticatedState, athleteSession, resetE2EFixture,
}) => {
  await resetE2EFixture(request, 'meal-plan');
  await authenticatedState(page);

  await page.goto('/athletes/101/nutrition-prescriptions');
  await page.locator('input[name="effective_from"]').fill('2026-08-01');
  await page.locator('input[name="calories"]').fill('2000');
  await page.locator('input[name="protein_g"]').fill('150');
  await page.locator('input[name="carbohydrate_g"]').fill('230');
  await page.locator('input[name="fat_g"]').fill('53');
  await page.locator('input[name="fibre_g"]').fill('25');
  await page.getByRole('button', { name: 'Assign nutrition targets' }).click();

  await page.goto('/coach/meal-plans');
  await page.getByRole('button', { name: 'New meal plan' }).click();
  await page.locator('input[name="name"]').fill('Competition week meals');
  await page.getByRole('button', { name: 'Create meal plan' }).click();
  await page.locator('input[name="name"]').fill('Training day');
  await page.getByRole('button', { name: 'Add day' }).click();
  await page.getByRole('heading', { name: 'Add meal' }).locator('..').locator('input[name="name"]').fill('Breakfast');
  await page.getByRole('button', { name: 'Add meal' }).click();
  await page.getByText('Add meal component').click();
  const component = page.locator('details[open] form');
  await component.locator('input[name="name"]').fill('Oats');
  await component.locator('input[name="amount"]').fill('100');
  await component.locator('input[name="calories"]').fill('2000');
  await component.locator('input[name="protein_g"]').fill('150');
  await component.locator('input[name="carbohydrate_g"]').fill('230');
  await component.locator('input[name="fat_g"]').fill('53');
  await component.locator('input[name="fibre_g"]').fill('25');
  await component.getByRole('button', { name: 'Add component' }).click();
  await page.locator('form').filter({ hasText: 'Update portion' }).locator('input[name="amount"]').fill('100');
  await page.getByRole('button', { name: 'Update portion' }).click();

  await page.getByRole('link', { name: 'Preview and assign' }).click();
  await page.locator('select[name="athlete_id"]').selectOption('101');
  await page.locator('input[name="effective_from"]').first().fill('2026-08-01');
  await page.getByRole('button', { name: 'Reconcile plan' }).click();
  await expect(page.getByText('Matched')).toBeVisible();
  await page.getByRole('button', { name: 'Publish and assign' }).click();
  await expect(page.getByRole('heading', { name: 'Competition week meals' })).toBeVisible();

  await page.goto('/coach/meal-plans');
  await page.getByRole('button', { name: 'Create revision' }).click();
  await expect(page.getByText('Revision 6')).toBeVisible();

  await athleteSession(page.request, 101);
  for (const width of [320, 390, 430]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto('/athlete/meal-plan');
    await expect(page.locator('body')).toHaveClass(/athlete-workspace/);
    await expect(page.getByRole('navigation', { name: 'Athlete navigation' }).last()).toBeVisible();
    await expect(page.locator('.coach-sidebar, [data-coach-navigation]')).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Competition week meals' })).toBeVisible();
    await expect(page.getByText('Oats')).toBeVisible();
    await expect(page.getByText(/Assigned target 2000 kcal/)).toBeVisible();
    expect(await page.evaluate(() => document.body.scrollWidth <= document.documentElement.clientWidth)).toBeTruthy();

    const more = page.locator('[data-athlete-more]');
    const moreSummary = more.locator('summary');
    await expect(moreSummary).toHaveCSS('color', 'rgb(213, 189, 141)');
    await moreSummary.focus();
    await page.keyboard.press('Enter');
    await expect(more).toHaveAttribute('open', '');
    await expect(more.getByRole('link', { name: 'Meal plan', exact: true }))
      .toHaveAttribute('aria-current', 'page');
    await page.keyboard.press('Escape');
    await expect(moreSummary).toBeFocused();
  }
});
