import { test, expect } from '../fixtures/test';

test.use({ mutationScope: 'spreadsheet-import' });

test('coach maps and reviews training history before explicit import', async ({
  page,
  authenticatedState,
  athleteIds,
}) => {
  await authenticatedState(page);
  await page.goto(`/athletes/${athleteIds.primary}`);
  await page.getByRole('link', { name: 'Import spreadsheet' }).click();
  await expect(page.getByRole('heading', { name: 'Bring existing training history over' })).toBeVisible();

  await page.getByLabel('Training spreadsheet').setInputFiles({
    name: 'existing-history.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(
      'Training Date,Day,Movement,Sets,Reps,Weight,RPE,Comments\n2026-08-01,Day 1,Squat,3,5,100,7,Smooth\n',
    ),
  });
  await page.getByRole('button', { name: 'Inspect spreadsheet' }).click();
  await expect(page.getByRole('heading', { name: 'Check the column mapping' })).toBeVisible();
  await expect(page.getByText('mapped · high').first()).toBeVisible();

  await page.getByRole('button', { name: 'Review interpreted rows' }).click();
  await expect(page.getByRole('heading', { name: 'Review before importing' })).toBeVisible();
  await expect(page.getByText('3').first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Confirm and import history' })).toBeVisible();
  await page.getByRole('button', { name: 'Back to mapping' }).click();
  await expect(page.getByRole('heading', { name: 'Check the column mapping' })).toBeVisible();
});
