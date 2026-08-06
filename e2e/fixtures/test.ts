import { test as base, expect, type APIRequestContext, type Page } from '@playwright/test';

type Fixtures = {
  athleteIds: { primary: number; isolated: number };
  authenticatedState: (page: Page) => Promise<void>;
  athleteSession: (request: APIRequestContext, athleteId: number) => Promise<void>;
};

export const test = base.extend<Fixtures>({
  athleteIds: async ({}, use) => use({ primary: 101, isolated: 202 }),

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
      expect(athleteId).toBe(101);
      const current = await request.get('/coach');
      const currentToken = (await current.text()).match(/name="csrf_token" value="([^"]+)"/)?.[1];
      if (currentToken) await request.post('/logout', { form: { csrf_token: currentToken } });
      const login = await request.get('/login');
      const token = (await login.text()).match(/name="csrf_token" value="([^"]+)"/)?.[1];
      expect(token).toBeTruthy();
      const response = await request.post('/login', {
        form: { email: 'alex.e2e@example.test', password: 'Athlete E2E password!', csrf_token: token! },
      });
      expect(
        response.ok(),
        `E2E session failed: ${response.status()} ${await response.text()} tokenLength=${(process.env.E2E_RUN_TOKEN ?? '').length}`,
      ).toBeTruthy();
    });
  },
});

export { expect };
