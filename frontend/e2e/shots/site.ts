// The README's and the landing page's screenshots (docs/images/ and
// DigiMonk73/btctx-site's img/), retaken at each release (AGENTS.md,
// "Releasing", step 5): `make site-shots`. Not part
// of the test suite. One small saved ledger, so the Dashboard and the
// Transactions list agree, at the site's size (1470 x 867, 2x) and theme.
import { readFileSync } from "node:fs";
import path from "node:path";
import type { Page } from "@playwright/test";
import { test, expect, createTx, REPO, type TxPayload } from "../fixtures";

const OUT = process.env.SITE_SHOTS_DIR ?? path.join(REPO, "docs", "images");

// testdata/showcase_ledger.json: a typical portfolio, not the reference test ledger,
// whose latest entries (built to cover every tax case) would show no sales.
const LEDGER: TxPayload[] = (
  JSON.parse(readFileSync(path.join(REPO, "testdata", "showcase_ledger.json"), "utf8"))
    .transactions as Record<string, string | number | null>[]
);

test.use({
  viewport: { width: 1470, height: 867 },
  deviceScaleFactor: 2,
  colorScheme: "dark",
});

async function shot(page: Page, name: string) {
  await page.mouse.move(0, 866); // no hover state in the shot
  await page.waitForLoadState("networkidle");
  await page.screenshot({ path: path.join(OUT, `${name}.png`), animations: "disabled" });
}

test("dashboard, transactions and reports", async ({ authedPage: page }) => {
  for (const tx of LEDGER) await createTx(page.request, tx);

  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Portfolio Overview" })).toBeVisible();
  await expect(page.locator(".btc-price-value")).toContainText("60,000");
  await expect(page.getByText("Rebates (received)")).toBeVisible();
  await shot(page, "dashboard");

  await page.getByRole("link", { name: "Transactions" }).click();
  await expect(page.getByText(/Loading transactions/i)).toHaveCount(0);
  await expect(page.getByRole("listitem").first()).toBeVisible();
  await shot(page, "transactions");

  await page.goto("/reports");
  await expect(page.getByRole("heading", { name: "Reports" })).toBeVisible();
  await shot(page, "reports");
});

test.describe("in the Mac app", () => {
  test.use({ appMode: "mac" });

  test("settings: Connect an AI Assistant", async ({ authedPage: page }) => {
    await page.goto("/settings");
    const ai = page.getByRole("region", { name: "Connect an AI Assistant" });
    await expect(ai.getByRole("button", { name: "Copy" })).toBeVisible();
    await ai.evaluate((el) => el.scrollIntoView({ block: "start" }));
    await page.mouse.move(0, 866);
    await page.waitForLoadState("networkidle");
    // The test server keeps its key file in a temp folder; the Mac app's is
    // in the user's Library (its full path names the Mac's user, so "~").
    // Set last, so no re-render puts the temp path back.
    const keyFile = ai.getByText(/AI apps on this Mac reach BitcoinTX/).locator("code");
    await keyFile.evaluate((el) => { el.textContent = "~/Library/Application Support/BitcoinTX/mcp.json"; });
    await expect(keyFile).toHaveText("~/Library/Application Support/BitcoinTX/mcp.json");
    const box = (await ai.boundingBox())!;
    // The section ends the page, so it can't scroll to the top: the whole
    // section from the full page, in page coordinates (#242).
    const scrollY = await page.evaluate(() => window.scrollY);
    const margin = 28; // the section's own padding, as on the page
    const top = box.y + scrollY + 2; // below the line between sections
    await page.screenshot({
      path: path.join(OUT, "settings.png"), animations: "disabled", fullPage: true,
      clip: { x: box.x - margin, y: top, width: box.width + 2 * margin, height: box.height - 2 },
    });
  });
});
