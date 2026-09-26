// End-to-end click-through tests: the real backend (temp database, stubbed
// BTC prices) serving the built frontend, driven through Chromium.
// Run with `make e2e` or `npx playwright test` (build frontend/dist first).
import { defineConfig, devices } from "@playwright/test";

const tzSpecs = /(create|edit|transactions-list)\.e2e\.ts/;

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.e2e.ts",
  globalSetup: "./e2e/global-setup.ts",
  // Each test starts its own server on a fresh database, so tests are
  // independent; one worker keeps timing deterministic.
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    locale: "en-US",
  },
  projects: [
    {
      // US zone: everything runs here.
      name: "chicago",
      use: { ...devices["Desktop Chrome"], timezoneId: "America/Chicago" },
    },
    {
      // UTC+ zone: the date and time flows again (the v0.9.1 time bug was
      // invisible in UTC and showed up with an offset).
      name: "tokyo",
      testMatch: tzSpecs,
      use: { ...devices["Desktop Chrome"], timezoneId: "Asia/Tokyo" },
    },
    {
      // The Mac app renders with WebKit; CI runs this project where WebKit
      // is installed (E2E_WEBKIT=1).
      name: "webkit",
      use: { ...devices["Desktop Safari"], timezoneId: "America/Chicago" },
      grep: process.env.E2E_WEBKIT ? undefined : /$^/,
    },
  ],
});
