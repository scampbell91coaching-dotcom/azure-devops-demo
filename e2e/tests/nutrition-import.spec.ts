import { test, expect } from '../fixtures/test';

const csv = Buffer.from([
  'Date,Meal,Calories,Fat (g),Carbohydrates (g),Protein (g),Fiber (g)',
  '2026-08-04,Breakfast,600,15,70,35,8',
  '2026-08-04,Dinner,900,30,100,60,10',
].join('\n'));

test('athlete import preview, commit and mobile summary have no overflow', async ({ page, athleteSession, athleteIds }) => {
  await athleteSession(page.request, athleteIds.primary);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/athletes/${athleteIds.primary}/nutrition-import`);
  await expect(page.getByRole('heading', { name: 'Import nutrition data' })).toBeVisible();
  await page.locator('input[type=file]').setInputFiles({ name: 'Nutrition-Summary.csv', mimeType: 'text/csv', buffer: csv });
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Preview import' }).click();
  await expect(page.getByRole('heading', { name: 'Preview import' })).toBeVisible();
  await expect(page.getByText('1500')).toBeVisible();
  await page.getByRole('button', { name: /Import 1 days/ }).click();
  await expect(page.getByText(/1 of 7 days present/)).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBeFalsy();
});

test('import presents a safe error state', async ({ page, athleteSession, athleteIds }) => {
  await athleteSession(page.request, athleteIds.primary);
  await page.goto(`/athletes/${athleteIds.primary}/nutrition-import`);
  await page.locator('input[type=file]').setInputFiles({ name: 'not-an-export.txt', mimeType: 'text/plain', buffer: Buffer.from('no') });
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Preview import' }).click();
  await expect(page.getByRole('alert')).toContainText('Upload a MyFitnessPal .zip or .csv export');
});
