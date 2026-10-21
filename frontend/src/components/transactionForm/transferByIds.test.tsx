// @vitest-environment jsdom
// B6a-8: a Transfer by ids (spec 5.13: From, then To among the accounts of the same
// currency, the same account offered only for a bitcoin account, as "Consolidation";
// filled only when exactly one fits, D6), dollars included (5.6, #447).
import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ONE_OF_EACH as ONE, TWO_OF_EACH as TWO } from "../../test/accountBooks";
import { renderForm, type RenderedForm, type SentRequest } from "../../test/renderForm";

/** A saved transfer from `from` to `to`, as GET /api/transactions/{id} sends it. */
function saved(from: number, to: number, amount: string, fee: string, currency: Currency): ITransactionRaw {
  return {
    id: 21, type: "Transfer", timestamp: "2026-06-01T08:00:00Z", from_account_id: from, to_account_id: to,
    amount, fee_amount: fee, fee_currency: currency,
  } as unknown as ITransactionRaw;
}

const writes = (requests: SentRequest[]) => requests.filter((r) => r.method !== "get");
const fromField = () => screen.getByLabelText("From Account");
const toField = () => screen.getByLabelText("To Account");

/** The one write's body. */
function sent(requests: SentRequest[]): unknown {
  const all = writes(requests);
  expect(all).toHaveLength(1);
  return all[0].body;
}

/** A new Transfer from the account called `from`; To left to the test. */
async function newTransfer({ user }: RenderedForm, from: string): Promise<void> {
  await user.selectOptions(screen.getByLabelText("Transaction Type"), "Transfer");
  await user.selectOptions(fromField(), from);
}

/** Type both amounts. */
async function amounts({ user }: RenderedForm, sentOut: string, arrived: string): Promise<void> {
  await user.clear(screen.getByLabelText("Amount (From)"));
  await user.type(screen.getByLabelText("Amount (From)"), sentOut);
  await user.clear(screen.getByLabelText("Amount (To)"));
  await user.type(screen.getByLabelText("Amount (To)"), arrived);
}

describe("a new bitcoin Transfer", () => {
  it("between two wallets' and exchanges' accounts sends both ids and the fee", async () => {
    const form = await renderForm({ book: TWO });
    await newTransfer(form, "Cold Storage");
    await form.user.selectOptions(toField(), "Kraken BTC");
    await amounts(form, "0.50000000", "0.49990000");
    await form.save();
    expect(sent(form.requests)).toMatchObject({
      type: "Transfer", from_account_id: 101, to_account_id: 103, amount: 0.5, fee_amount: 0.0001, fee_currency: "BTC",
    });
  });

  it("within one account is a consolidation", async () => {
    const form = await renderForm({ book: TWO });
    await newTransfer(form, "Kraken BTC");
    await form.user.selectOptions(toField(), "Consolidation: Kraken BTC");
    await amounts(form, "0.1", "0.0999");
    await form.save();
    expect(sent(form.requests)).toMatchObject({ from_account_id: 103, to_account_id: 103, amount: 0.1, fee_amount: 0.0001 });
  });

  it("from the one wallet starts with To blank (D6), and saves nothing", async () => {
    const form = await renderForm({ book: ONE });
    await newTransfer(form, "Wallet");
    expect(toField()).toHaveValue("");
    await amounts(form, "0.1", "0.0999");
    await form.save();
    expect(writes(form.requests)).toEqual([]);
  });
});

describe("a new dollar Transfer", () => {
  it("from the bank, with one of each: To is Exchange USD, read-only", async () => {
    const form = await renderForm({ book: ONE });
    await newTransfer(form, "Bank");
    expect(toField()).toHaveValue("Exchange USD");
    expect(toField()).toHaveAttribute("readonly");
    await amounts(form, "100.00", "100.00");
    await form.save();
    expect(sent(form.requests)).toMatchObject({ from_account_id: 1, to_account_id: 3, fee_currency: "USD" });
  });

  it.each([
    ["Credit Union", "Kraken USD", "250.00", "249.75", { from_account_id: 100, to_account_id: 102, amount: 249.75, fee_amount: 0.25 }],
    ["Exchange USD", "Credit Union", "1000.10", "1000.10", { from_account_id: 3, to_account_id: 100, amount: 1000.1, fee_amount: 0 }],
    ["Kraken USD", "Exchange USD", "0.30", "0.10", { from_account_id: 102, to_account_id: 3, amount: 0.1, fee_amount: 0.2 }],
  ])("from %s to %s: what arrived, its fee in cents", async (from, to, sentOut, arrived, body) => {
    const form = await renderForm({ book: TWO });
    await newTransfer(form, from);
    await form.user.selectOptions(toField(), to);
    await amounts(form, sentOut, arrived);
    await form.save();
    expect(sent(form.requests)).toMatchObject({ ...body, fee_currency: "USD" });
  });

  it("never offers its own account", async () => {
    const form = await renderForm({ book: TWO });
    await newTransfer(form, "Credit Union");
    expect(within(toField()).queryByRole("option", { name: /Credit Union/ })).toBeNull();
  });

  it.each([
    ["10.00", "0", "Amount (To) must be more than 0."],
    ["10.00", "9.999", "A USD amount can have at most 2 decimal places."],
  ])("refuses From %s, To %s", async (sentOut, arrived, problem) => {
    const form = await renderForm({ book: TWO });
    await newTransfer(form, "Credit Union");
    await form.user.selectOptions(toField(), "Kraken USD");
    await amounts(form, sentOut, arrived);
    await form.save();
    expect(writes(form.requests)).toEqual([]);
    expect(screen.getByText(problem)).toBeInTheDocument();
  });
});

describe("an edited Transfer", () => {
  it.each([
    [1, 100, "100", "0", "USD"],
    [2, 101, "0.5", "0.0001", "BTC"],
    [4, 103, "0.5", "0.0001", "BTC"],
  ] as const)("%i → %i saved unchanged keeps both ids", async (from, to, amount, fee, currency) => {
    const form = await renderForm({ book: TWO, transaction: saved(from, to, amount, fee, currency) });
    await form.save();
    expect(sent(form.requests)).toMatchObject({ from_account_id: from, to_account_id: to });
  });

  it("whose From becomes a dollar account loses its bitcoin To", async () => {
    const form = await renderForm({ book: TWO, transaction: saved(2, 101, "0.5", "0.0001", "BTC") });
    await form.user.selectOptions(fromField(), "Credit Union");
    expect(toField()).toHaveValue("");
  });

  it("whose From moves to another bitcoin account keeps its To", async () => {
    const form = await renderForm({ book: TWO, transaction: saved(2, 103, "0.5", "0.0001", "BTC") });
    await form.user.selectOptions(fromField(), "Cold Storage");
    expect(toField()).toHaveValue("103");
  });

  it("4 → 4 reads back as a consolidation, never a move between exchanges", async () => {
    await renderForm({ book: ONE, transaction: saved(4, 4, "0.1", "0.0001", "BTC") });
    const chosen = within(toField()).getByRole("option", { name: "Consolidation: Exchange BTC" }) as HTMLOptionElement;
    expect(chosen.selected).toBe(true);
  });

  it("of dollars reads back what left and what arrived, and saves the same figures", async () => {
    const form = await renderForm({ book: TWO, transaction: saved(102, 100, "249.75", "0.25", "USD") });
    expect(screen.getByLabelText("Amount (From)")).toHaveValue(250);
    expect(screen.getByLabelText("Amount (To)")).toHaveValue(249.75);
    await form.save();
    expect(sent(form.requests)).toMatchObject({
      from_account_id: 102, to_account_id: 100, amount: 249.75, fee_amount: 0.25, fee_currency: "USD",
    });
  });
});
