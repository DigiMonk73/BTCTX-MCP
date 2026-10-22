// @vitest-environment jsdom
// B6a-7: a Deposit and a Withdrawal by ids (spec 5.13: "Deposit: To, any account …
// Withdrawal: From"; D1). Which fields show, and what's sent, follow the chosen
// account's currency in the book (#449), never its number or its name.
import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MISSING, TWO_OF_EACH as TWO } from "../../test/accountBooks";
import { renderForm, type RenderedForm, type SentRequest } from "../../test/renderForm";

const RENT: ITransactionRaw = {
  id: 11, type: "Withdrawal", timestamp: "2026-05-01T09:00:00Z", from_account_id: 100, to_account_id: 99,
  amount: "200", fee_amount: "0", fee_currency: "USD", purpose: "Rent",
} as unknown as ITransactionRaw;

const DEPOSIT: ITransactionRaw = {
  id: 12, type: "Deposit", timestamp: "2026-05-02T09:00:00Z", from_account_id: 99, to_account_id: 104,
  amount: "0.01", fee_amount: "0", fee_currency: "BTC", source: "MyBTC", cost_basis_usd: "500",
} as unknown as ITransactionRaw;

const GIFT: ITransactionRaw = {
  id: 13, type: "Withdrawal", timestamp: "2026-05-03T09:00:00Z", from_account_id: 104, to_account_id: 99,
  amount: "0.01", fee_amount: "0", fee_currency: "BTC", purpose: "Gift", fmv_usd: "400",
} as unknown as ITransactionRaw;

const writes = (requests: SentRequest[]) => requests.filter((r) => r.method !== "get");
const accountField = () => screen.getByLabelText("Account");

/** A new transaction of `type`, from or into the account called `name`, of `amount`. */
async function start({ user }: RenderedForm, type: "Deposit" | "Withdrawal", name: string, amount: string) {
  await user.selectOptions(screen.getByLabelText("Transaction Type"), type);
  await user.selectOptions(accountField(), name);
  await user.type(screen.getByLabelText("Amount"), amount);
}

/** The one write's body. */
function sent(requests: SentRequest[]): unknown {
  const all = writes(requests);
  expect(all).toHaveLength(1);
  return all[0].body;
}

describe("a new Deposit", () => {
  it("of income into a wallet: BTC, its basis left to the price", async () => {
    const form = await renderForm({ book: TWO });
    await start(form, "Deposit", "Cold Storage", "0.01");
    expect(screen.getByLabelText("Currency")).toHaveValue("BTC");
    await form.user.selectOptions(screen.getByLabelText("Source"), "Income");
    await form.save();
    expect(sent(form.requests)).toMatchObject({
      type: "Deposit", from_account_id: 99, to_account_id: 101, amount: 0.01,
      source: "Income", cost_basis_usd: null, fee_currency: "BTC",
    });
  });

  it("of dollars into a bank: USD, no source and no basis", async () => {
    const form = await renderForm({ book: TWO });
    await start(form, "Deposit", "Credit Union", "500.00");
    expect(screen.getByLabelText("Currency")).toHaveValue("USD");
    expect(screen.queryByLabelText("Source")).toBeNull();
    expect(screen.queryByLabelText("Cost Basis (USD)")).toBeNull();
    await form.save();
    expect(sent(form.requests)).toMatchObject({
      from_account_id: 99, to_account_id: 100, amount: 500, source: "N/A", cost_basis_usd: null, fee_currency: "USD",
    });
  });

  it("of My BTC asks the date originally acquired only into a bitcoin account", async () => {
    const form = await renderForm({ book: TWO });
    await start(form, "Deposit", "Kraken BTC", "0.01");
    await form.user.selectOptions(screen.getByLabelText("Source"), "MyBTC");
    expect(screen.getByLabelText("Date originally acquired")).toBeInTheDocument();
    await form.user.selectOptions(accountField(), "Kraken USD");
    expect(screen.queryByLabelText("Date originally acquired")).toBeNull();
  });

  it("whose account changes from bitcoin to dollars sends no source (#449)", async () => {
    const form = await renderForm({ book: TWO });
    await start(form, "Deposit", "Cold Storage", "0.01");
    await form.user.selectOptions(screen.getByLabelText("Source"), "Income");
    await form.user.selectOptions(accountField(), "Credit Union");
    await form.save();
    expect(sent(form.requests)).toMatchObject({ to_account_id: 100, source: "N/A", cost_basis_usd: null });
  });
});

describe("a new Withdrawal", () => {
  it("spent from an exchange's bitcoin, its proceeds left to the price", async () => {
    const form = await renderForm({ book: TWO });
    await start(form, "Withdrawal", "Kraken BTC", "0.02");
    await form.user.selectOptions(screen.getByLabelText("Purpose (BTC only)"), "Spent");
    await form.save();
    expect(sent(form.requests)).toMatchObject({
      from_account_id: 103, to_account_id: 99, amount: 0.02, purpose: "Spent", proceeds_usd: null,
    });
  });

  it("as a gift asks its value only from a bitcoin account", async () => {
    const form = await renderForm({ book: TWO });
    await start(form, "Withdrawal", "Cold Storage", "0.01");
    await form.user.selectOptions(screen.getByLabelText("Purpose (BTC only)"), "Gift");
    expect(screen.getByLabelText("FMV (USD)")).toBeInTheDocument();
    await form.user.selectOptions(accountField(), "Kraken USD");
    expect(screen.queryByLabelText("FMV (USD)")).toBeNull();
  });
});

describe("an edit", () => {
  it("of dollars paid out as rent, saved unchanged, keeps its account and its label", async () => {
    const form = await renderForm({ book: TWO, transaction: RENT });
    await form.save();
    expect(sent(form.requests)).toMatchObject({
      from_account_id: 100, to_account_id: 99, amount: 200, purpose: "Rent", proceeds_usd: null, fmv_usd: null,
    });
  });

  it.each([
    ["deposit into", DEPOSIT, { from_account_id: 99, to_account_id: 104 }],
    ["withdrawal from", GIFT, { from_account_id: 104, to_account_id: 99 }],
  ])("of a %s a hidden account lists it, chosen, and keeps it", async (_, saved, ids) => {
    const form = await renderForm({ book: TWO, transaction: saved });
    expect(within(accountField()).getByRole("option", { name: "Old Wallet" })).toBeInTheDocument();
    expect(accountField()).toHaveValue("104");
    await form.save();
    expect(sent(form.requests)).toMatchObject(ids);
  });

  it.each([
    ["deposit into", { ...DEPOSIT, to_account_id: MISSING }],
    ["withdrawal from", { ...GIFT, from_account_id: MISSING }],
  ])("of a %s an account the book lacks: blank, named as missing, nothing saved", async (_, saved) => {
    const form = await renderForm({ book: TWO, transaction: saved as ITransactionRaw });
    expect(accountField()).toHaveValue("");
    expect(screen.getByText("account 999 (missing)")).toBeInTheDocument();
    await form.save();
    expect(writes(form.requests)).toEqual([]);
  });
});
