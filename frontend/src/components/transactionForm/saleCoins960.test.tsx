// @vitest-environment jsdom
// The coins a sale uses (#960): the Sell form lists them, read-only, once
// its exchange and BTC are typed (its proceeds start at $0, a sale's own), asked with the body the Save
// sends, each with its date acquired, amount, cost, proceeds, gain and
// term, as Form 8949 will print them. An exchange's coins leave oldest
// first: no picker.
import { act, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MANY } from "../../test/books";
import { renderForm, type PlannedAnswer, type RenderedForm, type SentRequest } from "../../test/renderForm";
import { COINS_WAIT_MS } from "./useCoinsMoved";

const SOLD = {
  coins: [
    { acquired: "2023-01-10", btc: "0.30000000", cost_usd: "300.00", inherited: false, acquired_txn_id: 2,
      proceeds_usd: "30000.00", gain_usd: "29700.00", term: "LONG" },
    { acquired: "2025-01-10", btc: "0.10000000", cost_usd: "6000.00", inherited: false, acquired_txn_id: 3,
      proceeds_usd: "10000.00", gain_usd: "4000.00", term: "SHORT" },
  ],
  fee_btc: "0.00000000", detail: null, held: null, dated_today: false,
};

const asked = (form: RenderedForm) => form.requests.filter((r) => r.url.endsWith("/coins-moved"));
const coinsAnswer = (answer: PlannedAnswer) => (request: SentRequest) =>
  request.url.endsWith("/coins-moved") ? answer : undefined;

async function waitForCoins(form: RenderedForm) {
  await act(() => new Promise((resolve) => setTimeout(resolve, COINS_WAIT_MS + 50)));
  await form.settle();
}

async function aSale(form: RenderedForm) {
  await form.pickType("Sell");
  await form.choose("Exchange", "River");
  await form.user.type(screen.getByLabelText("Amount BTC"), "0.4");
  await form.user.clear(screen.getByLabelText("Gross Proceeds (USD)"));
  await form.user.type(screen.getByLabelText("Gross Proceeds (USD)"), "40000");
  await waitForCoins(form);
}

describe("a sale's coins", () => {
  it("are listed with each piece's proceeds, gain and term", async () => {
    const form = await renderForm({ book: MANY, respond: coinsAnswer({ status: 200, data: SOLD }) });
    await aSale(form);
    const body = asked(form).at(-1)?.body;
    expect(body).toMatchObject({ type: "Sell", from_account_id: 4, amount: 0.4 });
    const table = screen.getByRole("table", { name: "Coins this sale uses" });
    const headers = within(table).getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["Date acquired", "Amount (BTC)", "Cost (USD)", "Proceeds (USD)", "Gain (USD)", "Term"]);
    const rows = within(table).getAllByRole("row").slice(1).map((r) =>
      within(r).getAllByRole("cell").map((c) => c.textContent));
    expect(rows[0]).toEqual(["Jan 10, 2023", "0.30000000", "$300.00", "$30,000.00", "$29,700.00", "Long-term"]);
    expect(rows[1]).toEqual(["Jan 10, 2025", "0.10000000", "$6,000.00", "$10,000.00", "$4,000.00", "Short-term"]);
    expect(screen.queryByRole("button", { name: "Choose which coins leave" })).toBeNull();
  });

  it("follow the proceeds typed, and wait while the field is cleared: the save needs them", async () => {
    const form = await renderForm({ book: MANY, respond: coinsAnswer({ status: 200, data: SOLD }) });
    await aSale(form);
    expect(asked(form).at(-1)?.body).toMatchObject({ gross_proceeds_usd: 40000 });
    const before = asked(form).length;
    await form.user.clear(screen.getByLabelText("Gross Proceeds (USD)"));
    await waitForCoins(form);
    expect(asked(form).length).toBe(before);
  });

  it("say what the save refuses, as a sale's", async () => {
    const refused = { status: 400, data: { detail: "Not saved: Not enough BTC to sell 0.40000000 BTC" } };
    const form = await renderForm({ book: MANY, respond: coinsAnswer(refused) });
    await aSale(form);
    expect(screen.getByText("This sale can't be saved as it is: Not enough BTC to sell 0.40000000 BTC")).toBeTruthy();
  });
});
