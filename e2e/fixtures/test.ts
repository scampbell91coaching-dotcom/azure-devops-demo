import { test as base, expect, type APIRequestContext, type BrowserContext } from '@playwright/test';

type Fixtures = {
  athleteIds: { primary: number; isolated: number };
  authenticatedState: (context: BrowserContext) => Promise<void>;
  athleteSession: (request: APIRequestContext, athleteId: number) => Promise<void>;
};

export const test = base.extend<Fixtures>({
  athleteIds: async ({}, use) => use({ primary: 101, isolated: 202 }),

  // AUTH PLACEHOLDER: there is no login/session workflow to exercise yet.
  // Keep callers behind this fixture so real storageState setup can replace it.
  authenticatedState: async ({}, use) => {
    await use(async (_context: BrowserContext) => {});
  },

  // This selects a test identity directly; it must not be described as login/auth coverage.
  athleteSession: async ({}, use) => {
    await use(async (request, athleteId) => {
      const response = await request.post(`/__e2e__/athlete-session/${athleteId}`, {
        headers: {
          'X-E2E-Run-Token': process.env.E2E_RUN_TOKEN ?? '',
        },
      });
      expect(
        response.ok(),
        `E2E session failed: ${response.status()} ${await response.text()} tokenLength=${(process.env.E2E_RUN_TOKEN ?? '').length}`,
      ).toBeTruthy();
    });
  },
});

export { expect };
