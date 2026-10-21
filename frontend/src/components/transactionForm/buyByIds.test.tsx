// @vitest-environment jsdom
// B6a-6: a Buy by ids (spec 5.13: "Paid from", no default when more than one fits,
// and "Exchange", fixed to the paying exchange when paid from an exchange's dollars,
// Q15). Today's mapper sends 1 or 3 → 4 for every Buy.
import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ONE_OF_EACH as ONE, TWO_OF_EACH as TWO } from "../../test/accountBooks";
import { renderForm, type RenderedForm, type SentRequest } from "../../test/renderForm";

const BUY: ITransactionRaw = {
  id: 9, type: "Buy", timestamp: "2026-02-10T10:00:00Z", from_account_id: 1, to_account_id: 103,
  amount: "0.05", fee_amount: "5", fee_currency: "USD", cost_basis_usd: "3000",
} as unknown as ITransactionRaw;

/** Derived books: one with only the bank to pay from, one with Kraken hidden. */
const ONE_PAYER: AccountBook = ONE.map((account) => (account.id === 3 ? { ...account, hidden: true } : account));
const KRAKEN_HIDDEN: AccountBook = TWO.map((account) => (account.exchange_id === 2 ? { ...account, hidden: true } : account));

const writes = (requests: SentRequest[]) => requests.filter((r) => r.method !== "get");
const paidFrom = () => screen.getByLabelText("Paid from");
const exchange = () => screen.getByLabelText("Exchange");

/** A new Buy of 0.05 BTC for $3,000.00 with a $5.00 fee; its accounts left to the test. */
async function newBuy({ user }: RenderedForm): Promise<void> {
  await user.selectOptions(screen.getByLabelText("Transaction Type"), "Buy");
  await user.type(screen.getByLabelText("Amount USD"), "3000.00");
  await user.type(screen.getByLabelText("Amount BTC"), "0.05");
  await user.clear(screen.getByLabelText("Fee (USD)"));
  await user.type(screen.getByLabelText("Fee (USD)"), "5.00");
}

const BOUGHT = { amount: 0.05, cost_basis_usd: 3000, fee_amount: 5, fee_currency: "USD" };

/** The one write, a POST of a Buy from `from` into `to`. */
function postedBuy(requests: SentRequest[], from: number, to: number) {
  expect(writes(requests)).toEqual([
    expect.objectContaining({
      method: "post",
      body: expect.objectContaining({ type: "Buy", from_account_id: from, to_account_id: to, ...BOUGHT }),
    }),
  ]);
}

describe("an edited Buy", () => {
  it("saved unchanged keeps its exchange: 1 → 103", async () => {
    const form = await renderForm({ book: TWO, transaction: BUY });
    await form.save();
    const [put] = writes(form.requests);
    expect(put).toMatchObject({ method: "put", url: "/transactions/9" });
    expect(put.body).toMatchObject({ from_account_id: 1, to_account_id: 103, ...BOUGHT });
  });

  it("paid from a hidden exchange's dollars lists it, chosen, and keeps it", async () => {
    const form = await renderForm({ book: KRAKEN_HIDDEN, transaction: { ...BUY, from_account_id: 102 } });
    expect(paidFrom()).toHaveValue("102");
    expect(exchange()).toHaveValue("Kraken");
    await form.save();
    expect(writes(form.requests)[0]?.body).toMatchObject({ from_account_id: 102, to_account_id: 103 });
  });
});

describe("a new Buy with one of each", () => {
  it("starts blank, saves nothing until paid from, then buys on the exchange", async () => {
    const form = await renderForm({ book: ONE });
    await newBuy(form);
    expect(paidFrom()).toHaveValue("");
    await form.save();
    expect(writes(form.requests)).toEqual([]);
    expect(screen.getByText("Please select an account")).toBeInTheDocument();
    await form.user.selectOptions(paidFrom(), "Exchange USD");
    expect(exchange()).toHaveValue("Exchange");
    expect(exchange()).toHaveAttribute("readonly");
    await form.save();
    postedBuy(form.requests, 3, 4);
  });

  it("from the bank: the one exchange is filled in", async () => {
    const form = await renderForm({ book: ONE });
    await newBuy(form);
    await form.user.selectOptions(paidFrom(), "Bank (auto-buy)");
    expect(exchange()).toHaveValue("Exchange");
    expect(exchange()).toHaveAttribute("readonly");
    await form.save();
    postedBuy(form.requests, 1, 4);
  });

  it("with only one account to pay from: it's filled in", async () => {
    const form = await renderForm({ book: ONE_PAYER });
    await newBuy(form);
    expect(paidFrom()).toHaveValue("Bank (auto-buy)");
    expect(paidFrom()).toHaveAttribute("readonly");
    await form.save();
    postedBuy(form.requests, 1, 4);
  });
});

describe("a new Buy with two exchanges", () => {
  it("from a bank: the exchange starts blank until one is chosen", async () => {
    const form = await renderForm({ book: TWO });
    await newBuy(form);
    await form.user.selectOptions(paidFrom(), "Credit Union (auto-buy)");
    expect(exchange()).toHaveValue("");
    await form.save();
    expect(writes(form.requests)).toEqual([]);
    expect(screen.getByText("Please select an exchange")).toBeInTheDocument();
    await form.user.selectOptions(exchange(), "Kraken");
    await form.save();
    postedBuy(form.requests, 100, 103);
  });

  it("from an exchange's dollars: only that exchange, read-only (Q15)", async () => {
    const form = await renderForm({ book: TWO });
    await newBuy(form);
    await form.user.selectOptions(paidFrom(), "Kraken USD");
    expect(exchange()).toHaveValue("Kraken");
    expect(exchange()).toHaveAttribute("readonly");
    await form.save();
    postedBuy(form.requests, 102, 103);
  });

  it("paid from another exchange's dollars: the exchange follows, never left on the first", async () => {
    const form = await renderForm({ book: TWO });
    await newBuy(form);
    await form.user.selectOptions(paidFrom(), "Kraken USD");
    await form.user.selectOptions(paidFrom(), "Exchange USD");
    expect(exchange()).toHaveValue("Exchange");
    await form.save();
    postedBuy(form.requests, 3, 4);
  });
});
