// @vitest-environment jsdom
// B6a-5: a Sell by ids (spec 5.13: "Sell: 'Exchange'"; a row read back keeps both
// ids). Today's mapper sends 4 → 3 for every Sell, so an edit would move a second
// exchange's sale to the first (5.10, item 5).
import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MISSING, ONE_OF_EACH as ONE, TWO_OF_EACH as TWO } from "../../test/accountBooks";
import { renderForm, type RenderedForm, type SentRequest } from "../../test/renderForm";

const SELL: ITransactionRaw = {
  id: 7, type: "Sell", timestamp: "2026-03-02T15:00:00Z", from_account_id: 103, to_account_id: 102,
  amount: "0.1", fee_amount: "12", fee_currency: "USD", gross_proceeds_usd: "6000", proceeds_usd: "5988",
} as unknown as ITransactionRaw;

/** TWO_OF_EACH with Kraken hidden: hiding an exchange hides both its accounts. */
const KRAKEN_HIDDEN: AccountBook = TWO.map((account) => (account.exchange_id === 2 ? { ...account, hidden: true } : account));

const writes = (requests: SentRequest[]) => requests.filter((r) => r.method !== "get");
const accountField = () => screen.getByLabelText("Account");

/** A new Sell of 0.1 BTC for a gross of $6,000.00, with a $12.00 fee. */
async function newSell({ user }: RenderedForm): Promise<void> {
  await user.selectOptions(screen.getByLabelText("Transaction Type"), "Sell");
  await user.clear(screen.getByLabelText("Amount BTC"));
  await user.type(screen.getByLabelText("Amount BTC"), "0.1");
  await user.clear(screen.getByLabelText("Gross Proceeds (USD)"));
  await user.type(screen.getByLabelText("Gross Proceeds (USD)"), "6000.00");
  await user.clear(screen.getByLabelText("Fee (USD)"));
  await user.type(screen.getByLabelText("Fee (USD)"), "12.00");
}

const SOLD = { amount: 0.1, gross_proceeds_usd: 6000, fee_amount: 12, fee_currency: "USD" };

describe("a new Sell", () => {
  it("with one exchange: the Account is that exchange, read-only, and sells 4 → 3", async () => {
    const form = await renderForm({ book: ONE });
    await newSell(form);
    expect(accountField()).toHaveValue("Exchange");
    expect(accountField()).toHaveAttribute("readonly");
    await form.save();
    expect(writes(form.requests)).toEqual([
      expect.objectContaining({ method: "post", body: expect.objectContaining({ from_account_id: 4, to_account_id: 3, ...SOLD }) }),
    ]);
  });

  it("with two exchanges: starts blank, saves nothing until one is chosen, then sells there", async () => {
    const form = await renderForm({ book: TWO });
    await newSell(form);
    expect(accountField()).toHaveValue("");
    await form.save();
    expect(writes(form.requests)).toEqual([]);
    expect(screen.getByText("Please select an exchange")).toBeInTheDocument();
    await form.user.selectOptions(accountField(), "Kraken");
    await form.save();
    expect(writes(form.requests)).toEqual([
      expect.objectContaining({ method: "post", body: expect.objectContaining({ from_account_id: 103, to_account_id: 102, ...SOLD }) }),
    ]);
  });

  it("keeps no account through a change of type", async () => {
    const form = await renderForm({ book: TWO });
    await newSell(form);
    await form.user.selectOptions(accountField(), "Kraken");
    await form.user.selectOptions(screen.getByLabelText("Transaction Type"), "Buy");
    await form.user.selectOptions(screen.getByLabelText("Transaction Type"), "Sell");
    expect(accountField()).toHaveValue("");
  });

  it("changed to a Buy and back sells 4 → 3 again with one exchange", async () => {
    const form = await renderForm({ book: ONE });
    await newSell(form);
    await form.user.selectOptions(screen.getByLabelText("Transaction Type"), "Buy");
    await newSell(form);
    await form.save();
    expect(writes(form.requests)).toEqual([
      expect.objectContaining({ method: "post", body: expect.objectContaining({ from_account_id: 4, to_account_id: 3, ...SOLD }) }),
    ]);
  });
});

describe("an edited Sell", () => {
  it("saved unchanged keeps its exchange: 103 → 102, the same amount, gross and fee", async () => {
    const form = await renderForm({ book: TWO, transaction: SELL });
    await form.save();
    const [put] = writes(form.requests);
    expect(put).toMatchObject({ method: "put", url: "/transactions/7" });
    expect(put.body).toMatchObject({ from_account_id: 103, to_account_id: 102, ...SOLD });
  });

  it("on a hidden exchange lists it, chosen, and keeps it", async () => {
    const form = await renderForm({ book: KRAKEN_HIDDEN, transaction: SELL });
    expect(within(accountField()).getByRole("option", { name: "Kraken" })).toBeInTheDocument();
    expect(accountField()).toHaveValue("103");
    await form.save();
    expect(writes(form.requests)[0]?.body).toMatchObject({ from_account_id: 103, to_account_id: 102 });
  });

  it("from an account the book lacks: blank, named as missing, and nothing saved", async () => {
    const missing = { ...SELL, from_account_id: MISSING, to_account_id: 3 } as ITransactionRaw;
    const form = await renderForm({ book: TWO, transaction: missing });
    expect(accountField()).toHaveValue("");
    expect(screen.getByText("account 999 (missing)")).toBeInTheDocument();
    await form.save();
    expect(writes(form.requests)).toEqual([]);
  });

  it("from an account the book lacks isn't filled over, even when one exchange fits", async () => {
    const missing = { ...SELL, from_account_id: MISSING, to_account_id: 3 } as ITransactionRaw;
    const form = await renderForm({ book: ONE, transaction: missing });
    expect(accountField()).toHaveValue("");
    expect(screen.getByText("account 999 (missing)")).toBeInTheDocument();
    await form.save();
    expect(writes(form.requests)).toEqual([]);
  });
});
