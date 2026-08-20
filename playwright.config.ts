import { defineConfig, devices } from '@playwright/test';
import { randomBytes } from 'node:crypto';

const port = Number(process.env.E2E_PORT ?? 8091);
const baseURL = `http://127.0.0.1:${port}`;
const pythonExecutable = process.env.E2E_PYTHON ?? 'python3';

if (process.env.E2E_TEST_ONLY !== '1') {
  throw new Error('Refusing to run: set E2E_TEST_ONLY=1 to acknowledge the disposable test-only environment.');
}
if (process.env.E2E_BASE_URL) {
  throw new Error('Refusing E2E_BASE_URL: browser tests may only target the disposable local server.');
}
if (!Number.isInteger(port) || port < 1024 || port > 65535) {
  throw new Error('E2E_PORT must be an unprivileged TCP port (1024-65535).');
}

const runToken =
  process.env.E2E_RUN_TOKEN ?? randomBytes(32).toString('hex');
process.env.E2E_RUN_TOKEN = runToken;
process.env.E2E_DATABASE_PATH = `${process.cwd()}/.tmp/applications-${runToken}.sqlite`;
if (!/^[A-Za-z0-9_./-]+$/.test(pythonExecutable)) {
  throw new Error('E2E_PYTHON contains unsupported characters.');
}

export default defineConfig({
  testDir: './e2e/tests',
  outputDir: '.tmp/playwright-test-results',
  preserveOutput: 'never',
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  timeout: 30_000,
  expect: { timeout: 5_000 },
  reporter: 'line',
  use: {
    baseURL,
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
    extraHTTPHeaders: { 'X-E2E-Run-Token': runToken },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    video: 'off',
  },
  webServer: [
    {
      command: 'python e2e/support/run_server.py',
      url: 'http://127.0.0.1:8091/health',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: 'python e2e/support/run_public_server.py',
      url: 'http://127.0.0.1:8092/apply',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],

  projects: [
    {
      name: 'chromium',
      testIgnore: /(mobile|safari-ios)\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'mobile-chromium',
      testMatch: /mobile\.spec\.ts/,
      use: { ...devices['Pixel 7'] },
    },
    {
      name: 'webkit-safari',
      testMatch: /safari-ios\.spec\.ts/,
      use: { ...devices['Desktop Safari'] },
    },
  ],
});
