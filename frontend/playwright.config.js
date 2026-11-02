import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 45_000,
  expect: {
    timeout: 8_000,
  },
  reporter: 'list',
  outputDir: process.env.PODOBANK_UI_OUTPUT_DIR || './test-results',
  use: {
    baseURL: process.env.PODOBANK_UI_URL || 'http://127.0.0.1:8081',
    viewport: { width: 384, height: 832 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
});
