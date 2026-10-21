// A gift, donation or lost coins has no proceeds (#457). The form saved a
// hidden $0 on one, so made a Spent later without proceeds (the AI
// connector, the API) it was a $0 sale, its whole basis a loss. Saved
// unchanged, a gift now keeps none; made a Spent, it's priced like a Spent
// left blank, in the form as through the API.
import { test, expect, createTx, listTx, seedFunds, saveForm, confirmedRequest } from "./fixtures";
import type { Page } from "@playwright/test";

const GIFT = {
  type: "Withdrawal", timestamp: "2024-06-10T15:20:00Z", from_account_id: 4, to_account_id: 99, amount: "0.1",
  fee_amount: "0", fee_currency: "BTC", purpose: "Gift",
};

/** Open the most recently added transaction, a withdrawal, in the edit panel. */
async function openEdit(page: Page) {
  await page.getByRole("link", { name: "Transactions" }).click();
  await page.getByLabel("Sort transactions").selectOption("CREATION_DESC");
  const row = page.getByRole("listitem").first();
  await expect(row).toContainText("Withdrawal");
  await row.getByRole("button", { name: "Edit" }).click();
  await expect(page.getByRole("heading", { name: "Edit Transaction" })).toBeVisible();
}

async function saved(page: Page, id: unknown) {
  return (await listTx(page.request)).find((t) => t.id === id)!;
}

test("a gift saved unchanged keeps no proceeds; made a Spent through the API, it's priced (#457)", async ({
  authedPage: page,
}) => {
  await seedFunds(page.request);
  const gift = await createTx(page.request, GIFT);
  await openEdit(page);
  await saveForm(page, "Update Transaction");
  expect(await saved(page, gift.id)).toMatchObject({ purpose: "Gift", gross_proceeds_usd: null, proceeds_usd: null });

  // What the AI connector's update_transaction(purpose="Spent") sends
  const r = await confirmedRequest((params) =>
    page.request.put(`/api/transactions/${gift.id}`, { data: { purpose: "Spent" }, params }));
  expect(r.ok(), await r.text()).toBeTruthy();
  const spent = await r.json();
  expect(spent.proceeds_from_price).toBe(true);
  expect(Number(spent.gross_proceeds_usd)).toBeGreaterThan(0);
  expect(spent.proceeds_usd).toBe(spent.gross_proceeds_usd);
});

test("a gift holding an older form's $0 made a Spent in the form shows its proceeds blank, priced on save (#457)", async ({
  authedPage: page,
}) => {
  await seedFunds(page.request);
  const gift = await createTx(page.request, { ...GIFT, proceeds_usd: "0" });
  expect(gift.gross_proceeds_usd).toBe("0.00");
  await openEdit(page);
  await page.getByLabel("Purpose (BTC only)").selectOption("Spent");
  await expect(page.getByLabel("Proceeds (USD)")).toHaveValue("");
  await expect(page.getByText("Leave blank to use the BTC price when that hour began")).toBeVisible();
  await saveForm(page, "Update Transaction");

  const spent = await saved(page, gift.id);
  expect(spent).toMatchObject({ purpose: "Spent", proceeds_from_price: true });
  expect(Number(spent.gross_proceeds_usd)).toBeGreaterThan(0);
});
