// Screenshots for design review (Phase 5), not part of the test suite:
//   SHOTS_DIR=/some/dir npx playwright test -c e2e/shots/screenshots.config.ts
// Uses the e2e server and the known ledger, so the figures are real.
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: "screenshots.ts",
  globalSetup: "../global-setup.ts",
  workers: 1,
  timeout: 120_000,
  reporter: "list",
  use: { ...devices["Desktop Chrome"], locale: "en-US", timezoneId: "America/Chicago" },
});
