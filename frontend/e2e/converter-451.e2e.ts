// The sidebar converter counts satoshis exactly (#451): a BTC amount from its
// typed digits (0.29 BTC as a float times 100,000,000 is 28,999,999.99…, which
// was cut off to a satoshi too few), and from dollars one count that the BTC
// and Sats fields both show.
import { test, expect } from "./fixtures";

const TYPED = [
  ["0.29", "29000000"],
  ["0.57", "57000000"],
  ["1.15", "115000000"],
  ["2.01", "201000000"],
];

test("converter: a BTC amount is counted from its digits, to the satoshi (#451)", async ({ authedPage: page }) => {
  for (const [btc, sats] of TYPED) {
    await page.getByLabel("BTC", { exact: true }).fill(btc);
    await expect(page.getByLabel("Sats", { exact: true })).toHaveValue(sats);
  }
});

test("converter: from dollars, BTC and Sats show the same count (#451)", async ({ authedPage: page }) => {
  await expect(page.getByText("BTC Price: $60,000.00")).toBeVisible();
  // $1 at $60,000 is 1,666.67 sats: 1,667 to the nearest, in both fields
  await page.getByLabel("USD", { exact: true }).fill("1");
  await expect(page.getByLabel("BTC", { exact: true })).toHaveValue("0.00001667");
  await expect(page.getByLabel("Sats", { exact: true })).toHaveValue("1667");
  // $2 is 3,333.33 sats: 3,333
  await page.getByLabel("USD", { exact: true }).fill("2");
  await expect(page.getByLabel("BTC", { exact: true })).toHaveValue("0.00003333");
  await expect(page.getByLabel("Sats", { exact: true })).toHaveValue("3333");
});

test("converter: a new price converts the dollars again, the two fields still agreeing (#451)", async ({ authedPage: page }) => {
  await page.getByRole("button", { name: "Manual" }).click();
  const price = page.getByLabel("BTC price (USD)");
  await expect(price).toHaveValue("60000");
  await page.getByLabel("USD", { exact: true }).fill("1");
  await price.fill("70000"); // $1 is 1,428.57 sats
  await expect(page.getByLabel("BTC", { exact: true })).toHaveValue("0.00001429");
  await expect(page.getByLabel("Sats", { exact: true })).toHaveValue("1429");
});
