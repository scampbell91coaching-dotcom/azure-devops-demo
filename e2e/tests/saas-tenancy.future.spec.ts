import { futureFeatureFlags } from '../fixtures/saas';
import { test } from '../fixtures/test';

test.describe('future SaaS tenant isolation', () => {
  test.skip(
    !futureFeatureFlags.tenancy,
    'Enable only after organization membership and tenant-qualified lookups are implemented.',
  );

  test('tenant B coach cannot retrieve tenant A athlete by direct ID', async ({
    page,
    roleSession,
    tenantFixtures,
    directIdIsolationProbe,
  }) => {
    await roleSession(page, tenantFixtures.tenantB.coaches[0]);
    await directIdIsolationProbe(page, [
      `/athletes/${tenantFixtures.tenantA.athletes[0].athleteId}`,
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

test.describe('future organization invitation contract', () => {
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

test.describe('future organization onboarding contract', () => {
  test.skip(
    !futureFeatureFlags.onboarding,
    'Onboarding coverage is reserved behind E2E_ENABLE_ORG_ONBOARDING=1.',
  );

  test('fixture reserves two deterministic organization slugs', async ({ tenantFixtures }) => {
    test.fail(true, 'Replace this placeholder when the organization onboarding flow lands.');
    await Promise.resolve(tenantFixtures.tenantB.slug);
  });
});
