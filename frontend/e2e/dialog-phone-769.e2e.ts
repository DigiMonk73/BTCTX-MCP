// A dialog's buttons on a phone (#769): "Save anyway (a copy is made first)"
// is wider than half a phone, and the one-line row pushed Cancel off the
// screen's left edge. Every button stays whole on the screen, a thumb's width.
import { type Locator, type Page } from "@playwright/test";
import { createTx, expect, openSection, seedFunds, test } from "./fixtures";

const PHONE = { width: 375, height: 812 };
test.use({ viewport: PHONE });

async function onScreen(button: Locator) {
  const box = await button.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(PHONE.width);
}

/** The past-year dialog, asked by turning the Exchange's 1099-DA switch off over a 2025 sale. */
async function pastYearDialog(page: Page) {
  await seedFunds(page.request);
  await createTx(page.request, {
    type: "Sell", timestamp: "2025-03-03T15:00:00Z", from_account_id: 4, to_account_id: 3,
    amount: "0.1", gross_proceeds_usd: "9000", fee_amount: "0", fee_currency: "USD",
  });
  await page.goto("/settings");
  const section = await openSection(page, "Wallets, exchanges and banks");
  await section.getByRole("button", { name: /^Exchange\b/ }).click();
  await section.getByRole("region", { name: "Exchange" }).getByLabel("This exchange sends me a Form 1099-DA").click();
  return page.getByRole("dialog", { name: "Change an earlier tax year?" });
}

test("the past-year dialog's Cancel and Save anyway both fit a phone's width", async ({ authedPage: page }) => {
  const dialog = await pastYearDialog(page);
  const cancel = dialog.getByRole("button", { name: "Cancel" });
  const save = dialog.getByRole("button", { name: "Save anyway (a copy is made first)" });
  await onScreen(cancel);
  await onScreen(save);
  await cancel.click(); // a finger's tap on it, not the keyboard
  await expect(dialog).toHaveCount(0);
});
