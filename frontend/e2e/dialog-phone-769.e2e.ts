// A dialog's buttons on a phone (#769): "Save anyway (a copy is made first)"
// is wider than half a phone, and the one-line row pushed Cancel off the
// screen's left edge. Every button stays whole on the screen, a thumb's width.
import { type Locator, type Page } from "@playwright/test";
import { SAVE_ANYWAY, createTx, expect, openSection, seedFunds, test } from "./fixtures";

/** `inner` lies whole within `outer`'s box (a button in its dialog), or the screen's `width`. */
async function within(inner: Locator, outer: Locator | number) {
  const box = await inner.boundingBox();
  const frame = typeof outer === "number" ? { x: 0, width: outer } : await outer.boundingBox();
  expect(box).not.toBeNull();
  expect(frame).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(frame!.x);
  expect(box!.x + box!.width).toBeLessThanOrEqual(frame!.x + frame!.width);
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

// A common phone, and the narrowest still in use, where the label's words must wrap
for (const width of [375, 320]) {
  test.describe(`at ${width} px`, () => {
    test.use({ viewport: { width, height: 812 } });

    test("the past-year dialog's Cancel and Save anyway both fit the screen", async ({ authedPage: page }) => {
      const dialog = await pastYearDialog(page);
      const cancel = dialog.getByRole("button", { name: "Cancel" });
      await within(dialog, width);
      await within(cancel, dialog);
      await within(dialog.getByRole("button", { name: SAVE_ANYWAY }), dialog);
      await cancel.click(); // a finger's tap on it, not the keyboard
      await expect(dialog).toHaveCount(0);
    });
  });
}
