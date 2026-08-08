import { test, expect } from '../fixtures/test';

test.beforeEach(async ({ page, authenticatedState }) => {
  await authenticatedState(page);
});

test('observability renders complete telemetry and populated controls without an exception', async ({ page }) => {
  const errors: Error[] = [];
  page.on('pageerror', error => errors.push(error));
  await page.route('**/api/v1/observability', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      generated_at: '2026-08-08T12:00:00Z',
      telemetry: {
        metrics_api: { status: 'AVAILABLE', value: true },
        service_monitor: { status: 'NOT_CONFIGURED', value: false },
        health: { status: 'UNAVAILABLE', http_code: '503' },
        latency_sample: { status: 'DEGRADED', seconds: 1.234 },
      },
      controls: [
        { area: 'Observability', name: 'Metrics API', status: 'PASS', detail: 'Available' },
        { area: 'Availability', name: 'Public health', status: 'FAIL', detail: 'HTTP 503' },
      ],
    }),
  }));

  await page.goto('/observability');

  await expect(page.locator('[data-field="metrics"]')).toHaveText('AVAILABLE');
  await expect(page.locator('[data-field="servicemonitor"]')).toHaveText('NOT CONFIGURED');
  await expect(page.locator('[data-field="healthtelemetry"]')).toHaveText('UNAVAILABLE');
  await expect(page.locator('[data-field="latencysample"]')).toHaveText('1.234s (DEGRADED)');
  await expect(page.locator('#checks tr')).toHaveCount(2);
  expect(errors).toEqual([]);
});

test('observability handles missing fields and malformed response without an exception', async ({ page }) => {
  const errors: Error[] = [];
  page.on('pageerror', error => errors.push(error));
  await page.route('**/api/v1/observability', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ telemetry: { metrics_api: {} }, controls: null }),
  }));

  await page.goto('/observability');

  await expect(page.locator('[data-field="metrics"]')).toHaveText('UNKNOWN');
  await expect(page.locator('[data-field="latencysample"]')).toHaveText('UNKNOWN');
  await expect(page.locator('#checks')).toContainText('No controls were reported.');
  expect(errors).toEqual([]);
});

test('observability exposes backend errors as unavailable', async ({ page }) => {
  const errors: Error[] = [];
  page.on('pageerror', error => errors.push(error));
  await page.route('**/api/v1/observability', route => route.fulfill({
    status: 503,
    contentType: 'application/json',
    body: JSON.stringify({ error: 'unavailable' }),
  }));

  await page.goto('/observability');

  await expect(page.locator('[data-field="metrics"]')).toHaveText('UNAVAILABLE');
  await expect(page.locator('#checks')).toContainText('Status request failed: 503');
  expect(errors).toEqual([]);
});
