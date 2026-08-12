import { test as base, expect, type APIRequestContext, type Page } from '@playwright/test';
import { mkdir, rm } from 'node:fs/promises';
import { join } from 'node:path';
import {
  probeDirectIdIsolation,
  signInPage,
  signInRequest,
  tenants,
  type E2EIdentity,
  type TenantFixture,
  type TenantKey,
} from './saas';

type Fixtures = {
  athleteIds: { primary: number; isolated: number };
  authenticatedState: (page: Page) => Promise<void>;
  athleteSession: (request: APIRequestContext, athleteId: number) => Promise<void>;
  resetE2EFixture: (request: APIRequestContext, name: string) => Promise<void>;
  mutationScope: string | undefined;
  mutationLease: void;
  tenantFixtures: Readonly<Record<TenantKey, TenantFixture>>;
  roleSession: (page: Page, identity: E2EIdentity) => Promise<void>;
  roleRequestSession: (request: APIRequestContext, identity: E2EIdentity) => Promise<void>;
  directIdIsolationProbe: (page: Page, paths: readonly string[]) => Promise<void>;
};

export const test = base.extend<Fixtures>({
  mutationScope: [undefined, { option: true }],
  mutationLease: [async ({ mutationScope }, use) => {
    if (!mutationScope) {
      await use();
      return;
    }
    const runToken = process.env.E2E_RUN_TOKEN ?? 'missing-run-token';
    const lockPath = join(process.cwd(), '.tmp', `e2e-${runToken}-${mutationScope}.lock`);
    const deadline = Date.now() + 30_000;
    while (true) {
      try {
        await mkdir(lockPath, { recursive: false });
        break;
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== 'EEXIST' || Date.now() >= deadline) throw error;
        await new Promise(resolve => setTimeout(resolve, 50));
      }
    }
    try {
      await use();
    } finally {
      await rm(lockPath, { recursive: true });
    }
  }, { auto: true }],
  athleteIds: async ({}, use) => use({ primary: 101, isolated: 202 }),
  tenantFixtures: async ({}, use) => use(tenants),
  roleSession: async ({}, use) => use(signInPage),
  roleRequestSession: async ({}, use) => use(signInRequest),
  directIdIsolationProbe: async ({}, use) => {
    await use(async (page, paths) => {
      await probeDirectIdIsolation(page, paths);
    });
  },

  authenticatedState: async ({}, use) => {
    await use(async (page: Page) => {
      await page.goto('/login');
      await page.locator('input[name="email"]').fill('coach.e2e@example.test');
      await page.locator('input[name="password"]').fill('Coach E2E password!');
      await page.getByRole('button', { name: /sign in/i }).click();
      await expect(page).toHaveURL(/\/coach$/);
    });
  },

  athleteSession: async ({}, use) => {
    await use(async (request, athleteId) => {
      const accounts: Record<number, { email: string; password: string }> = {
        101: { email: 'alex.e2e@example.test', password: 'Athlete E2E password!' },
        202: { email: 'sam.private@example.test', password: 'Service Athlete password!' },
      };
      const account = accounts[athleteId];
      expect(account, `No E2E athlete account for ${athleteId}`).toBeTruthy();
      const current = await request.get('/coach');
      const currentToken = (await current.text()).match(/name="csrf_token" value="([^"]+)"/)?.[1];
      if (currentToken) await request.post('/logout', { form: { csrf_token: currentToken } });
      const login = await request.get('/login');
      const token = (await login.text()).match(/name="csrf_token" value="([^"]+)"/)?.[1];
      expect(token).toBeTruthy();
      const response = await request.post('/login', {
        form: { ...account, csrf_token: token! },
      });
      expect(
        response.ok(),
        `E2E session failed: ${response.status()} ${await response.text()} tokenLength=${(process.env.E2E_RUN_TOKEN ?? '').length}`,
      ).toBeTruthy();
    });
  },

  resetE2EFixture: async ({}, use) => {
    await use(async (request, name) => {
      const login = await request.get('/login');
      const loginToken = (await login.text()).match(/name="csrf_token" value="([^"]+)"/)?.[1];
      expect(loginToken).toBeTruthy();
      const signedIn = await request.post('/login', {
        form: {
          email: 'coach.e2e@example.test',
          password: 'Coach E2E password!',
          csrf_token: loginToken!,
        },
      });
      expect(signedIn.ok()).toBeTruthy();
      const coach = await request.get('/coach');
      const csrfToken = (await coach.text()).match(/name="csrf_token" value="([^"]+)"/)?.[1];
      expect(csrfToken).toBeTruthy();
      const reset = await request.post(`/__e2e/reset/${name}`, {
        form: { csrf_token: csrfToken! },
      });
      expect(reset.ok(), await reset.text()).toBeTruthy();
    });
  },
});

export { expect };
