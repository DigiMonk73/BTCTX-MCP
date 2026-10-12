// The price card's pictures for #145's pull requests, not part of the test suite:
//   PRICE_SHOTS_DIR=/some/dir npx playwright test -c e2e/shots/price.config.ts
// Uses the e2e server with its offline prices.
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: "price.ts",
  globalSetup: "../global-setup.ts",
  workers: 1,
  timeout: 120_000,
  reporter: "list",
  use: { ...devices["Desktop Chrome"], locale: "en-US", timezoneId: "America/Chicago", colorScheme: "dark" },
});
