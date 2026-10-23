// Settings in sections, and its "Wallets, exchanges and banks" (#355; 2.0 spec
// 5.9, 7.4's B7b; P7's mockups, #572): each section opens when asked, by its
// button or the keyboard, and stays open for this browser; your accounts by
// kind, Add with its help text and Q5's note, Hide, Show and Delete. Saving
// into a new account waits for the gate (B7a), whose rows this spec gains then.
import { test, expect, seedKnownLedger } from "./fixtures";
import type { Locator, Page } from "@playwright/test";

const SECTIONS = [
  "Account", "Wallets, exchanges and banks", "Ledger Review", "Privacy & Network", "Connect an AI Assistant",
  "Data Management", "Import from River", "Backup & Restore", "About BitcoinTX",
];

const WALLET_HELP =
  "A wallet is one set of keys: every address it makes is part of it. A backup of the same keys (a seed phrase, " +
  "or another device with the same keys) isn't a second wallet. If you use multiple wallets, add each one: since " +
  "2025 the IRS figures cost basis wallet by wallet.";

/** Q5's note (5.8, with P6's sentence) begins so; the unit test has every word. */
const POOLED_WALLET = "Years before you add this wallet were figured with your wallets together";
const POOLED_EXCHANGE = "Years before you add this exchange were figured with your exchange accounts together";

const toggle = (page: Page, name: string) => page.getByRole("button", { name, exact: true });

async function openAccounts(page: Page): Promise<Locator> {
  await page.getByRole("link", { name: "Settings" }).click();
  const button = toggle(page, "Wallets, exchanges and banks");
  if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
  return page.getByRole("region", { name: "Wallets, exchanges and banks" });
}

/** One kind's group in the section ("Wallets", "Exchanges", "Banks"). */
const group = (section: Locator, title: string) => section.getByRole("group", { name: title });

/** An account's row button: its name, then its kind and balance. */
const row = (section: Locator, name: string) => section.getByRole("button", { name: new RegExp(`^${name}\\b`) });

/** GET /api/accounts/, as B2b's API lists them. */
async function listed(page: Page) {
  const r = await page.request.get("/api/accounts/");
  expect(r.ok()).toBeTruthy();
  return (await r.json()) as { id: number; name: string; kind: string; currency: string; hidden: boolean }[];
}

test.describe("sections", () => {
  test.use({ settingsOpen: "remembered" });

  test("start closed, open and close by their buttons and the keyboard, and stay open for this browser", async ({
    authedPage: page,
  }) => {
    await page.getByRole("link", { name: "Settings" }).click();
    for (const name of SECTIONS) await expect(toggle(page, name)).toHaveAttribute("aria-expanded", "false");
    // Each with its one-line summary, read with its button
    await expect(toggle(page, "Wallets, exchanges and banks")).toHaveAccessibleDescription(
      "1 wallet · 1 exchange · 1 bank",
    );
    await expect(toggle(page, "Ledger Review")).toHaveAccessibleDescription("Nothing to review");
    await expect(page.getByRole("region", { name: "Account" })).toHaveCount(0);
    await expect(page.getByText("Recalculate Ledger")).toBeHidden();

    await toggle(page, "Account").click();
    await expect(toggle(page, "Account")).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByRole("region", { name: "Account" }).getByText("Recalculate Ledger")).toBeVisible();

    // The keyboard: Tab to a section's button, Enter opens it, Space closes it
    await toggle(page, "Account").focus();
    await page.keyboard.press("Tab");
    await expect(toggle(page, "Wallets, exchanges and banks")).not.toBeFocused(); // Account's own fields come first
    await toggle(page, "Ledger Review").focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("region", { name: "Ledger review" })).toBeVisible();
    await page.keyboard.press(" ");
    await expect(page.getByRole("region", { name: "Ledger review" })).toHaveCount(0);
    await page.keyboard.press("Enter");

    // Remembered by this browser
    await page.reload();
    await expect(toggle(page, "Account")).toHaveAttribute("aria-expanded", "true");
    await expect(toggle(page, "Ledger Review")).toHaveAttribute("aria-expanded", "true");
    await expect(toggle(page, "Privacy & Network")).toHaveAttribute("aria-expanded", "false");
    await toggle(page, "Account").click();
    await toggle(page, "Ledger Review").click();
    await page.reload();
    for (const name of SECTIONS) await expect(toggle(page, name)).toHaveAttribute("aria-expanded", "false");
  });

  test("a link to a section opens it", async ({ authedPage: page }) => {
    await page.goto("/settings#privacy");
    await expect(toggle(page, "Privacy & Network")).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByRole("region", { name: "Privacy & network" })).toBeVisible();
    await expect(toggle(page, "Account")).toHaveAttribute("aria-expanded", "false");
  });
});

test("your accounts by kind, each with its kind and balance, its details behind its row", async ({
  authedPage: page,
}) => {
  await seedKnownLedger(page.request);
  const section = await openAccounts(page);
  await expect(group(section, "Wallets")).toBeVisible();
  await expect(row(group(section, "Wallets"), "Wallet")).toHaveAccessibleName("Wallet Wallet 0.50990000 BTC");
  await expect(row(group(section, "Exchanges"), "Exchange")).toHaveAccessibleName(
    "Exchange Exchange $15,980.00 · 0.15000000 BTC",
  );
  await expect(row(group(section, "Banks"), "Bank")).toHaveAccessibleName("Bank Bank $80,000.00");
  await expect(section.getByText("BTC Fees")).toHaveCount(0);

  const wallet = row(section, "Wallet");
  await expect(wallet).toHaveAttribute("aria-expanded", "false");
  await wallet.click();
  await expect(wallet).toHaveAttribute("aria-expanded", "true");
  const details = section.getByRole("region", { name: "Wallet" });
  await expect(details.getByRole("button", { name: "Hide" })).toBeVisible();
  // In use: no Delete, and why
  await expect(details.getByRole("button", { name: "Delete" })).toHaveCount(0);
  await expect(details).toContainText("This account has transactions, so it can't be deleted. Hide it instead: its history stays.");
  await wallet.click();
  await expect(details).toHaveCount(0);
});

test("add a wallet and an exchange: their help texts, Q5's note, the server's refusal, the new rows", async ({
  authedPage: page,
}) => {
  await seedKnownLedger(page.request);
  const section = await openAccounts(page);
  const wallets = group(section, "Wallets");

  await wallets.getByRole("button", { name: "Add a wallet" }).click();
  const addWallet = section.getByRole("form", { name: "Add a wallet" });
  await expect(addWallet).toContainText(WALLET_HELP);
  await expect(addWallet).toContainText(POOLED_WALLET); // Wallet has transactions
  await addWallet.getByLabel("Name").fill("wallet");
  await addWallet.getByRole("button", { name: "Add", exact: true }).click();
  await expect(section.getByRole("alert")).toHaveText(
    "'wallet' always means your first wallet in files (CSV, River, BitcoinTX 1.x): choose another name.",
  );
  await addWallet.getByLabel("Name").fill("Coldcard");
  await addWallet.getByRole("button", { name: "Add", exact: true }).click();
  await expect(addWallet).toHaveCount(0);
  await expect(row(wallets, "Coldcard")).toHaveAccessibleName("Coldcard Wallet 0.00000000 BTC");
  await expect(toggle(page, "Wallets, exchanges and banks")).toHaveAccessibleDescription(
    "2 wallets · 1 exchange · 1 bank",
  );

  const exchanges = group(section, "Exchanges");
  await exchanges.getByRole("button", { name: "Add an exchange" }).click();
  const addExchange = section.getByRole("form", { name: "Add an exchange" });
  await expect(addExchange).toContainText(
    "BitcoinTX keeps an exchange's dollars and bitcoin as two accounts, 'name USD' and 'name BTC'.",
  );
  await expect(addExchange).toContainText(POOLED_EXCHANGE);
  await addExchange.getByLabel("Name").fill("Kraken");
  await expect(addExchange).toContainText("two accounts, 'Kraken USD' and 'Kraken BTC'.");
  await addExchange.getByRole("button", { name: "Add", exact: true }).click();
  await expect(row(exchanges, "Kraken")).toHaveAccessibleName("Kraken Exchange $0.00 · 0.00000000 BTC");

  const added = (await listed(page)).filter((a) => a.id >= 100);
  expect(added.map((a) => [a.id, a.name, a.kind, a.currency])).toEqual([
    [100, "Coldcard", "wallet", "BTC"], [101, "Kraken USD", "exchange", "USD"], [102, "Kraken BTC", "exchange", "BTC"],
  ]);

  // A bank: no help text, no note; Cancel adds nothing
  await group(section, "Banks").getByRole("button", { name: "Add a bank" }).click();
  const addBank = section.getByRole("form", { name: "Add a bank" });
  await expect(addBank.getByRole("note")).toHaveCount(0);
  await addBank.getByRole("button", { name: "Cancel" }).click();
  await expect(addBank).toHaveCount(0);
  expect(await listed(page)).toHaveLength(9);
});

test("a new user's second wallet, before any transaction, gets no note", async ({ authedPage: page }) => {
  const section = await openAccounts(page);
  await group(section, "Wallets").getByRole("button", { name: "Add a wallet" }).click();
  const addWallet = section.getByRole("form", { name: "Add a wallet" });
  await expect(addWallet).toContainText(WALLET_HELP);
  await expect(addWallet).not.toContainText(POOLED_WALLET);
});

test("hide, show and delete an unused account; your first wallet is hidden, never deleted", async ({
  authedPage: page,
}) => {
  const dialogs: string[] = [];
  page.on("dialog", async (d) => {
    dialogs.push(d.message());
    await d.accept();
  });
  const made = await page.request.post("/api/accounts/", { data: { kind: "wallet", name: "Phone" } });
  expect(made.status()).toBe(201);
  const section = await openAccounts(page);
  const wallets = group(section, "Wallets");

  await row(wallets, "Phone").click();
  await section.getByRole("region", { name: "Phone" }).getByRole("button", { name: "Hide" }).click();
  await expect(row(wallets, "Phone")).toHaveCount(0);
  await expect(toggle(page, "Wallets, exchanges and banks")).toHaveAccessibleDescription(
    "1 wallet · 1 exchange · 1 bank · 1 hidden",
  );
  const more = wallets.getByRole("button", { name: "Show hidden (1)" });
  await expect(more).toHaveAttribute("aria-expanded", "false");
  await more.click();
  await expect(more).toHaveAttribute("aria-expanded", "true");
  await expect(row(wallets, "Phone")).toHaveAccessibleName("Phone Wallet Hidden 0.00000000 BTC");
  expect((await listed(page)).find((a) => a.name === "Phone")?.hidden).toBe(true);

  await row(wallets, "Phone").click();
  const phone = section.getByRole("region", { name: "Phone" });
  await phone.getByRole("button", { name: "Show" }).click();
  await expect(wallets.getByRole("button", { name: /^Show hidden/ })).toHaveCount(0);
  await expect(row(wallets, "Phone")).toHaveAccessibleName("Phone Wallet 0.00000000 BTC");

  await row(wallets, "Phone").click();
  await section.getByRole("region", { name: "Phone" }).getByRole("button", { name: "Delete" }).click();
  expect(dialogs).toEqual(["Delete Phone? It has no transactions."]);
  await expect(row(wallets, "Phone")).toHaveCount(0);
  expect((await listed(page)).map((a) => a.name)).not.toContain("Phone");

  // Unused, but your first wallet: Hide only
  await row(wallets, "Wallet").click();
  const first = section.getByRole("region", { name: "Wallet" });
  await expect(first.getByRole("button", { name: "Delete" })).toHaveCount(0);
  await expect(first).toContainText("Your first bank, wallet and exchange can't be deleted. Hide one you don't use.");
});
