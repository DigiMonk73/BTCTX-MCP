// A time typed in the form goes to the server with its text and the
// browser's zone, for the server to read by its own timezone rules (#964);
// a time the form put in itself and the owner left alone goes as the
// moment it was. An up-to-date browser's reading agrees with the server's,
// so the form warns of nothing.
import type { Page, Request } from "@playwright/test";
import { test, expect, createTx, openAddForm, saveForm } from "./fixtures";

function bodyOf(page: Page, method: "POST" | "PUT"): Promise<Request> {
  return page.waitForRequest((r) => r.method() === method && /\/api\/transactions(\/\d+)?$/.test(r.url()));
}

test("a typed time is sent as typed, with the browser's zone (#964)", async ({ authedPage: page }) => {
  const zone = await page.evaluate(() => Intl.DateTimeFormat().resolvedOptions().timeZone);
  await openAddForm(page, "Deposit");
  await page.getByLabel("Date & Time").fill("2024-07-04T09:15");
  await page.getByLabel("Account").selectOption("Wallet");
  await page.getByLabel("Amount").fill("0.25");
  await page.getByLabel("Source").selectOption("MyBTC");
  await page.getByLabel("Cost Basis (USD)").fill("7000");
  const sent = bodyOf(page, "POST");
  await saveForm(page);
  const body = (await sent).postDataJSON();
  expect(body.typed_time).toEqual({ local: "2024-07-04T09:15", zone });
  // The server's reading and this browser's agree: no warning
  await expect(page.getByText("This device's rules differ")).toHaveCount(0);
});

test("an edit that leaves Date & Time alone sends the moment saved (#964)", async ({ authedPage: page }) => {
  await createTx(page.request, {
    type: "Deposit", timestamp: "2024-07-04T14:15:00Z", from_account_id: 99, to_account_id: 1,
    amount: "100", fee_amount: "0", fee_currency: "USD", source: "N/A",
  });
  await page.getByRole("link", { name: "Transactions" }).click();
  await page.getByRole("listitem").first().getByRole("button", { name: "Edit" }).click();
  await expect(page.getByRole("heading", { name: "Edit Transaction" })).toBeVisible();
  await page.getByLabel("Amount").fill("150");
  const sent = bodyOf(page, "PUT");
  await saveForm(page, "Update Transaction");
  const body = (await sent).postDataJSON();
  expect(body.typed_time).toBeUndefined();
  expect(new Date(body.timestamp).toISOString()).toBe("2024-07-04T14:15:00.000Z");
});
