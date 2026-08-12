import { futureFeatureFlags } from '../fixtures/saas';
import { test } from '../fixtures/test';

test.describe('future SaaS Organisation tenant isolation', () => {
  test.skip(
    !futureFeatureFlags.tenancy,
    'Enable only after Organisation membership and tenant-qualified lookups are implemented.',
  );

  test('tenant B coach cannot retrieve tenant A athlete by direct ID', async ({
    page,
    roleSession,
    tenantFixtures,
    directIdIsolationProbe,
  }) => {
    await roleSession(page, tenantFixtures.tenantB.coaches[0]);
    const athleteId = tenantFixtures.tenantA.athletes[0].athleteId;
    await directIdIsolationProbe(page, [
      `/athletes/${athleteId}`,
      `/athletes/${athleteId}/programming`,
      `/athletes/${athleteId}/check-ins/new`,
      `/athletes/${athleteId}/nutrition-checkins/new`,
      `/athletes/${athleteId}/nutrition-import`,
      `/athletes/${athleteId}/nutrition-prescriptions`,
    ]);
  });

  test('tenant A athlete cannot retrieve tenant B athlete by direct ID', async ({
    page,
    roleSession,
    tenantFixtures,
    directIdIsolationProbe,
  }) => {
    await roleSession(page, tenantFixtures.tenantA.athletes[0]);
    await directIdIsolationProbe(page, [
      `/athletes/${tenantFixtures.tenantB.athletes[0].athleteId}`,
    ]);
  });
});

test.describe('future Organisation invitation contract', () => {
  test.skip(
    !futureFeatureFlags.invitations,
    'Invitation coverage is reserved behind E2E_ENABLE_ORG_INVITATIONS=1.',
  );

  test('fixture exposes an owner and coach without contacting an email provider', async ({
    tenantFixtures,
  }) => {
    test.fail(true, 'Replace this placeholder when the organization invitation adapter lands.');
    await Promise.resolve(tenantFixtures.tenantA.owner);
  });
});

test.describe('future Organisation onboarding contract', () => {
  test.skip(
    !futureFeatureFlags.onboarding,
    'Onboarding coverage is reserved behind E2E_ENABLE_ORG_ONBOARDING=1.',
  );

  test('fixture reserves two deterministic Organisation slugs', async ({ tenantFixtures }) => {
    test.fail(true, 'Replace this placeholder when the Organisation onboarding flow lands.');
    await Promise.resolve(tenantFixtures.tenantB.slug);
  });
});
