// Settings in sections, and its "Wallets, exchanges and banks" (#355; 2.0 spec
// 5.9, 7.4's B7b; P7's mockups, #572): one section open at a time, by its
// button or the keyboard, the open one remembered by this browser; your accounts by
// kind, Add with its help text and Q5's note, Hide, Show and Delete. Saving
// into a new account waits for the gate (B7a), whose rows this spec gains then.
import { test, expect, openSection, seedKnownLedger } from "./fixtures";
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
  return openSection(page, "Wallets, exchanges and banks");
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

test("sections start closed, open one at a time by their buttons and the keyboard, and the open one stays open for this browser", async ({
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

  // The keyboard: Tab goes into the open section first; Enter opens a
  // section, closing the one before; Space closes it
  await toggle(page, "Account").focus();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("region", { name: "Account" }).getByRole("button", { name: "Logout" })).toBeFocused();
  await toggle(page, "Ledger Review").focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "Ledger review" })).toBeVisible();
  await expect(toggle(page, "Account")).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByRole("region", { name: "Account" })).toHaveCount(0);
  await page.keyboard.press(" ");
  await expect(page.getByRole("region", { name: "Ledger review" })).toHaveCount(0);
  await page.keyboard.press("Enter");

  // Remembered by this browser
  await page.reload();
  await expect(toggle(page, "Ledger Review")).toHaveAttribute("aria-expanded", "true");
  for (const name of SECTIONS.filter((n) => n !== "Ledger Review")) {
    await expect(toggle(page, name)).toHaveAttribute("aria-expanded", "false");
  }
  await toggle(page, "Ledger Review").click();
  await page.reload();
  for (const name of SECTIONS) await expect(toggle(page, name)).toHaveAttribute("aria-expanded", "false");
});

test("a link to a section opens it, in place of the one left open, as if its button were pressed", async ({
  authedPage: page,
}) => {
  await page.getByRole("link", { name: "Settings" }).click();
  await toggle(page, "Account").click();
  await page.goto("/settings#privacy");
  await expect(toggle(page, "Privacy & Network")).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("region", { name: "Privacy & network" })).toBeVisible();
  await expect(toggle(page, "Account")).toHaveAttribute("aria-expanded", "false");
  // The link's "#" goes, and what's open now is what a reload shows
  await expect(page).toHaveURL(/\/settings$/);
  await page.reload();
  await expect(toggle(page, "Privacy & Network")).toHaveAttribute("aria-expanded", "true");
  await toggle(page, "Account").click();
  await page.reload();
  await expect(toggle(page, "Account")).toHaveAttribute("aria-expanded", "true");
  await expect(toggle(page, "Privacy & Network")).toHaveAttribute("aria-expanded", "false");
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

  const addWalletButton = wallets.getByRole("button", { name: "Add a wallet" });
  await addWalletButton.click();
  await expect(addWalletButton).toHaveAttribute("aria-expanded", "true");
  const addWallet = section.getByRole("form", { name: "Add a wallet" });
  await expect(addWallet.getByLabel("Name")).toBeFocused();
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
  await expect(addWalletButton).toBeFocused(); // the keyboard back where the form opened from
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
  await expect(group(section, "Banks").getByRole("button", { name: "Add a bank" })).toBeFocused();
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
  // The keyboard goes where the row went: its group's folded list of hidden ones
  await expect(wallets.getByRole("button", { name: "Show hidden (1)" })).toBeFocused();
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
  await expect(row(wallets, "Phone")).toBeFocused();

  await row(wallets, "Phone").click();
  await section.getByRole("region", { name: "Phone" }).getByRole("button", { name: "Delete" }).click();
  expect(dialogs).toEqual(["Delete Phone? It has no transactions."]);
  await expect(row(wallets, "Phone")).toHaveCount(0);
  await expect(wallets.getByRole("button", { name: "Add a wallet" })).toBeFocused();
  expect((await listed(page)).map((a) => a.name)).not.toContain("Phone");

  // Unused, but your first wallet: Hide only
  await row(wallets, "Wallet").click();
  const first = section.getByRole("region", { name: "Wallet" });
  await expect(first.getByRole("button", { name: "Delete" })).toHaveCount(0);
  await expect(first).toContainText("Your first bank, wallet and exchange can't be deleted. Hide one you don't use.");
});

// River's file: a send of River's to the wallet (row 2) and a buy (row 3)
const RIVER_CSV = [
  "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag",
  "2026-02-15 10:00:00,0.00100000,BTC,,,0.00000500,BTC,",
  "2026-02-03 15:30:00,148.50,USD,0.00180000,BTC,1.50,USD,Buy",
].join("\n") + "\n";

/** From now on, the text fields of each form the page sends (Chromium keeps
 * no body of a request with a file for Playwright to read). */
async function recordForms(page: Page) {
  await page.evaluate(() => {
    const sent: Record<string, string>[] = [];
    Object.assign(window, { sentForms: sent });
    const send = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function (body) {
      if (body instanceof FormData) {
        sent.push(Object.fromEntries([...body.entries()].filter((e): e is [string, string] => typeof e[1] === "string")));
      }
      return send.call(this, body);
    };
  });
}

const sentForms = (page: Page) => page.evaluate(() => (window as unknown as { sentForms: Record<string, string>[] }).sentForms);

test("River: with one of each nothing is asked; with two of each the file's exchange and wallet, never a hidden one", async ({
  authedPage: page,
}) => {
  await page.getByRole("link", { name: "Settings" }).click();
  const river = await openSection(page, "Import from River");
  await expect(river.getByLabel("River CSV file")).toBeVisible();
  await expect(river.getByLabel("Exchange", { exact: true })).toHaveCount(0);
  await expect(river.getByLabel("Wallet for sends and receives")).toHaveCount(0);

  for (const [kind, name] of [["wallet", "Coldcard"], ["exchange", "Kraken"], ["wallet", "Old phone"]]) {
    expect((await page.request.post("/api/accounts/", { data: { kind, name } })).status()).toBe(201);
  }
  const phone = (await listed(page)).find((a) => a.name === "Old phone")!;
  expect((await page.request.put(`/api/accounts/${phone.id}`, { data: { hidden: true } })).ok()).toBeTruthy();
  await page.reload();

  // Asked, the first shown one of each chosen (Q8)
  const exchange = river.getByLabel("Exchange", { exact: true });
  const wallet = river.getByLabel("Wallet for sends and receives");
  await expect(exchange).toHaveValue("4");
  await expect(exchange.getByRole("option")).toHaveText(["Exchange", "Kraken"]);
  await expect(wallet).toHaveValue("2");
  // A hidden one is still yours: offered, never chosen for you
  await expect(wallet.getByRole("option")).toHaveText(["Wallet", "Coldcard", "Old phone (hidden)"]);

  // The choice goes with the file's preview
  await exchange.selectOption({ label: "Kraken" });
  await wallet.selectOption({ label: "Coldcard" });
  await river.getByLabel("River CSV file").setInputFiles({
    name: "river.csv", mimeType: "text/csv", buffer: Buffer.from(RIVER_CSV),
  });
  await recordForms(page);
  await river.getByRole("button", { name: "Preview" }).click();
  await expect(river.getByText("2 rows in file")).toBeVisible();
  expect(await sentForms(page)).toEqual([{ exchange_account_id: "102", wallet_account_id: "100" }]);

  // A new pick makes a new preview
  await wallet.selectOption({ label: "Wallet" });
  await expect.poll(() => sentForms(page)).toHaveLength(2);
  expect((await sentForms(page))[1]).toEqual({ exchange_account_id: "102", wallet_account_id: "2" });
  await expect(wallet).toHaveValue("2");

  // One that fails leaves the pick as the preview on screen has it
  await page.route("**/api/import/river/preview", (route) =>
    route.fulfill({ status: 500, json: { detail: "Down for a moment." } }));
  await wallet.selectOption({ label: "Coldcard" });
  await expect.poll(() => sentForms(page)).toHaveLength(3);
  await expect(page.getByText("Down for a moment.")).toBeVisible();
  await expect(wallet).toHaveValue("2");
});
