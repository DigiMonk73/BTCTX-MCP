// The README's (docs/images/) and landing page's screenshots, not part of the test suite:
//   make site-shots   (or SITE_SHOTS_DIR=/some/dir npx playwright test -c e2e/shots/site.config.ts)
// Uses the e2e server with its offline prices ($60,000), so the figures are real.
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: "site.ts",
  globalSetup: "../global-setup.ts",
  workers: 1,
  timeout: 120_000,
  reporter: "list",
  use: { ...devices["Desktop Chrome"], locale: "en-US", timezoneId: "America/Chicago" },
});
