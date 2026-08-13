import { test, expect } from '../fixtures/test';

const performanceAthleteId = 404;
const emptyAthleteId = 405;

test.beforeEach(async ({ page, authenticatedState }) => {
  await authenticatedState(page);
});

test('presents deterministic coaching metrics and chart data', async ({ page }) => {
  await page.goto(`/athletes/${performanceAthleteId}`);

  await expect(page.getByRole('heading', { level: 1, name: 'Morgan Performance' })).toBeVisible();
  const dashboard = page.locator('#performance-dashboard');
  await expect(dashboard.getByRole('heading', { name: 'Performance dashboard' })).toBeVisible();
  await expect(dashboard.getByText('Review prescription before progressing')).toBeVisible();

  const summary = dashboard.getByRole('region', { name: 'Training summary' });
  await expect(summary).toContainText('1,730 kg');
  await expect(summary).toContainText('75%');
  await expect(summary).toContainText('13 / 1');
  await expect(summary).toContainText('Top sets recorded4');
  await expect(dashboard.getByLabel('Primary training metrics')).toContainText('75%');
  await expect(dashboard.getByLabel('Supporting training metrics')).toContainText('13 / 1');

  const decisionMethod = dashboard.getByText('How this decision is made');
  await decisionMethod.click();
  await expect(dashboard.getByText(/missed exact-prescription reps/)).toBeVisible();

  const strengthChart = dashboard.locator('#personal-records');
  await expect(strengthChart.getByRole('heading', { name: 'Squat / bench / deadlift e1RM' })).toBeVisible();
  await expect(strengthChart).toContainText('165.0 kg');
  await expect(strengthChart).toContainText('116.7 kg');
  await expect(strengthChart).toContainText('192.0 kg');
  await expect(strengthChart).toContainText(/Estimated with Epley/);
  await expect(dashboard.getByRole('list', { name: 'SBD volume by training date' })).toBeVisible();
  await expect(dashboard.getByText('8.0 → 8.4')).toBeVisible();
  await expect(dashboard.getByText('83 kg', { exact: true })).toBeVisible();
  await expect(dashboard.getByText(/Autumn Open/)).toBeVisible();

  const chartResponse = await page.request.get(
    `/api/v1/athletes/${performanceAthleteId}/performance/charts?from=2026-07-01&to=2026-08-31`,
  );
  expect(chartResponse.status()).toBe(200);
  const chart = await chartResponse.json();
  expect(chart.athlete_id).toBe(performanceAthleteId);
  expect(chart.datasets.e1rm).toEqual(expect.arrayContaining([
    expect.objectContaining({ lift: 'squat', value_kg: 165 }),
    expect.objectContaining({ lift: 'bench', value_kg: 116.67 }),
    expect.objectContaining({ lift: 'deadlift', value_kg: 192 }),
  ]));
  expect(chart.datasets.rpe).toEqual(expect.arrayContaining([
    expect.objectContaining({ exercise: 'Competition Deadlift', delta: 1, adherent: false }),
  ]));
  expect(chart.datasets.bodyweight).toHaveLength(2);
});

test('filters every dashboard metric to the selected training block', async ({ page }) => {
  await page.goto(`/athletes/${performanceAthleteId}`);
  await page.locator('#performance-block').selectOption('1401');

  await expect(page).toHaveURL(`/athletes/${performanceAthleteId}?block=1401`);
  const dashboard = page.locator('#performance-dashboard');
  await expect(dashboard.getByRole('region', { name: 'Training summary' })).toContainText('1,310 kg');
  await expect(dashboard.getByRole('region', { name: 'Training summary' })).toContainText('10 / 1');
  await expect(dashboard.getByRole('region', { name: 'Training summary' })).toContainText('Top sets recorded3');
  await expect(dashboard.locator('#personal-records')).toContainText('1 sessions');
  await expect(dashboard.locator('#personal-records')).not.toContainText('154.0 kg');

  const response = await page.request.get(
    `/api/v1/athletes/${performanceAthleteId}/performance/charts?from=2026-07-01&to=2026-08-31&block_id=1401`,
  );
  expect(response.status()).toBe(200);
  const chart = await response.json();
  expect(chart.filters).toMatchObject({ block_id: 1401, block_name: 'Peak strength block' });
  expect(chart.datasets.e1rm).toHaveLength(3);
  expect(chart.datasets.e1rm).not.toEqual(expect.arrayContaining([
    expect.objectContaining({ date: '2026-07-11' }),
  ]));
});

test('explains incomplete history instead of fabricating metrics', async ({ page }) => {
  await page.goto(`/athletes/${emptyAthleteId}`);

  const dashboard = page.locator('#performance-dashboard');
  await expect(dashboard.getByText('No training decision yet')).toBeVisible();
  await expect(dashboard.getByText('No e1RM trend yet')).toBeVisible();
  await expect(dashboard.getByText('No SBD volume yet')).toBeVisible();
  await expect(dashboard.getByRole('region', { name: 'Training summary' })).toContainText('Not available');
  await expect(dashboard.getByRole('region', { name: 'Training summary' })).toContainText('0 / —');
  await expect(dashboard.getByText('Not recorded', { exact: true })).toBeVisible();

  const response = await page.request.get(
    `/api/v1/athletes/${emptyAthleteId}/performance/charts?from=2026-07-01&to=2026-08-31`,
  );
  expect(response.status()).toBe(200);
  const chart = await response.json();
  expect(chart.athlete_id).toBe(emptyAthleteId);
  expect(chart.datasets).toMatchObject({ e1rm: [], volume: [], rpe: [], bodyweight: [] });
  expect(Object.values(chart.availability)).toHaveLength(6);
  expect(Object.values(chart.availability)).toEqual(
    expect.arrayContaining(
      Array(6).fill('insufficient_data')
    )
  );
});

test('enforces coach authorization and athlete-owned block boundaries', async ({ page, athleteSession, athleteIds }) => {
  const foreignBlockResponse = await page.request.get(
    `/api/v1/athletes/${performanceAthleteId}/performance/charts?from=2026-07-01&to=2026-08-31&block_id=1201`,
  );
  expect(foreignBlockResponse.status()).toBe(404);

  await athleteSession(page.request, athleteIds.primary);
  const otherAthleteApi = await page.request.get(
    `/api/v1/athletes/${performanceAthleteId}/performance/charts?from=2026-07-01&to=2026-08-31`,
  );
  expect(otherAthleteApi.status()).toBe(403);
  const otherAthletePage = await page.goto(`/athletes/${performanceAthleteId}`);
  expect(otherAthletePage?.status()).toBe(403);
  await expect(page.getByRole('heading', { name: 'Access denied' })).toBeVisible();
});
