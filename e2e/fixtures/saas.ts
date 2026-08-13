import { expect, type APIRequestContext, type Page, type Response } from '@playwright/test';

export type TenantKey = 'tenantA' | 'tenantB';
export type TenantRole = 'owner' | 'coach' | 'athlete';

export type E2EIdentity = Readonly<{
  key: string;
  tenant: TenantKey;
  role: TenantRole;
  email: string;
  password: string;
  athleteId?: number;
}>;

export type TenantFixture = Readonly<{
  key: TenantKey;
  slug: string;
  name: string;
  owner: E2EIdentity;
  coaches: readonly E2EIdentity[];
  athletes: readonly E2EIdentity[];
}>;

const identity = (value: E2EIdentity): E2EIdentity => Object.freeze(value);

// These identities map to canonical Organisation, OrganisationMembership and
// CoachAthleteOwnership rows in the disposable seed. The global User role stays
// coach-compatible while the membership role distinguishes owner from coach.
export const tenants: Readonly<Record<TenantKey, TenantFixture>> = Object.freeze({
  tenantA: Object.freeze({
    key: 'tenantA',
    slug: 'traditional-strength-e2e-a',
    name: 'Traditional Strength E2E A',
    owner: identity({
      key: 'tenant-a-owner',
      tenant: 'tenantA',
      role: 'owner',
      email: 'coach.e2e@example.test',
      password: 'Coach E2E password!',
    }),
    coaches: Object.freeze([
      identity({
        key: 'tenant-a-coach',
        tenant: 'tenantA',
        role: 'coach',
        email: 'coach.a.e2e@example.test',
        password: 'Tenant A coach password!',
      }),
    ]),
    athletes: Object.freeze([
      identity({
        key: 'tenant-a-athlete',
        tenant: 'tenantA',
        role: 'athlete',
        email: 'athlete.a.e2e@example.test',
        password: 'Tenant A athlete password!',
        athleteId: 1101,
      }),
    ]),
  }),
  tenantB: Object.freeze({
    key: 'tenantB',
    slug: 'traditional-strength-e2e-b',
    name: 'Traditional Strength E2E B',
    owner: identity({
      key: 'tenant-b-owner',
      tenant: 'tenantB',
      role: 'owner',
      email: 'owner.b.e2e@example.test',
      password: 'Tenant B owner password!',
    }),
    coaches: Object.freeze([
      identity({
        key: 'tenant-b-coach',
        tenant: 'tenantB',
        role: 'coach',
        email: 'coach.b.e2e@example.test',
        password: 'Tenant B coach password!',
      }),
    ]),
    athletes: Object.freeze([
      identity({
        key: 'tenant-b-athlete',
        tenant: 'tenantB',
        role: 'athlete',
        email: 'athlete.b.e2e@example.test',
        password: 'Tenant B athlete password!',
        athleteId: 2101,
      }),
    ]),
  }),
});

export const futureFeatureFlags = Object.freeze({
  tenancy: process.env.E2E_ENABLE_TENANCY === '1',
  invitations: process.env.E2E_ENABLE_ORG_INVITATIONS === '1',
  onboarding: process.env.E2E_ENABLE_ORG_ONBOARDING === '1',
});

export async function signInPage(page: Page, account: E2EIdentity): Promise<void> {
  await page.goto('/login');
  await page.locator('input[name="email"]').fill(account.email);
  await page.locator('input[name="password"]').fill(account.password);
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page).toHaveURL(
    account.role === 'athlete' ? /\/athlete\/dashboard$/ : /\/coach$/,
  );
}

export async function signInRequest(
  request: APIRequestContext,
  account: E2EIdentity,
): Promise<void> {
  const login = await request.get('/login');
  const csrfToken = (await login.text()).match(/name="csrf_token" value="([^"]+)"/)?.[1];
  expect(csrfToken).toBeTruthy();
  const response = await request.post('/login', {
    form: { email: account.email, password: account.password, csrf_token: csrfToken! },
  });
  expect(response.ok(), `Could not create ${account.key} session: ${response.status()}`).toBeTruthy();
}

export async function probeDirectIdIsolation(
  page: Page,
  paths: readonly string[],
): Promise<readonly Response[]> {
  const responses: Response[] = [];
  for (const path of paths) {
    const response = await page.goto(path);
    expect(response, `No response while probing ${path}`).not.toBeNull();
    expect([403, 404], `${path} disclosed a direct-ID resource`).toContain(response!.status());
    responses.push(response!);
  }
  return responses;
}
