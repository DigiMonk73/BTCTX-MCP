// @vitest-environment jsdom
// The Transfer form lists the coins that will move before it saves (#706;
// the owner's decision, 2026-10-25): on a Transfer between two bitcoin
// accounts, a line saying the oldest coins in the From account go first,
// and the server's list of the coins its save moves, each with its date
// acquired, amount and cost. Asked with the body the Save sends, so the
// list is what the save then does; nothing is listed for a move within one
// wallet or for dollars, and a save the server would refuse says why.
import { act, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MANY } from "../../test/books";
import { renderForm, type PlannedAnswer, type RenderedForm, type SentRequest } from "../../test/renderForm";
import { COINS_WAIT_MS } from "./useCoinsMoved";

const OLDEST_FIRST =
  "Per-wallet FIFO: your oldest coins in Sparrow move first (the IRS default when you don't pick specific coins).";
const LISTED = {
  coins: [
    { acquired: "2017-03-01", btc: "0.29990000", cost_usd: "299.90", inherited: false },
    { acquired: "2024-05-01", btc: "0.10010000", cost_usd: "6006.00", inherited: false },
  ],
  fee_btc: "0.00010000",
  detail: null,
};

const asked = (form: RenderedForm) => form.requests.filter((r) => r.url.endsWith("/coins-moved"));

/** The list's answer: `answer` for every request for it. */
const coinsAnswer = (answer: PlannedAnswer) => (request: SentRequest) =>
  request.url.endsWith("/coins-moved") ? answer : undefined;

/** The form waits a moment after the last change before it asks: let it, and the answer come in. */
async function waitForCoins(form: RenderedForm) {
  await act(() => new Promise((resolve) => setTimeout(resolve, COINS_WAIT_MS + 50)));
  await form.settle();
}

async function sparrowToColdcard(form: RenderedForm, amountFrom = "0.4001", amountTo = "0.4") {
  await form.pickType("Transfer");
  await form.choose("From Account", "Sparrow");
  await form.choose("To Account", "Coldcard");
  await form.user.type(screen.getByLabelText("Amount (From)"), amountFrom);
  await form.user.type(screen.getByLabelText("Amount (To)"), amountTo);
  await waitForCoins(form);
}

function rows(): string[][] {
  const table = screen.getByRole("table", { name: "Coins that will move" });
  return within(table).getAllByRole("row").map((row) =>
    [...row.querySelectorAll("th, td")].map((cell) => cell.textContent ?? ""));
}

describe("a Transfer between two of your bitcoin accounts", () => {
  it("lists the coins its save moves, asked with the body the Save sends", async () => {
    const form = await renderForm({ book: MANY, respond: coinsAnswer({ status: 200, data: LISTED }) });
    await sparrowToColdcard(form);
    expect(screen.getByText(OLDEST_FIRST)).toBeTruthy();
    expect(rows()).toEqual([
      ["Date acquired", "Amount (BTC)", "Cost (USD)"],
      ["Mar 1, 2017", "0.29990000", "$299.90"],
      ["May 1, 2024", "0.10010000", "$6,006.00"],
    ]);
    expect(screen.getByText(/^The network fee, 0\.0001 BTC, is paid first, from your oldest coins/)).toBeTruthy();

    const listedFor = asked(form).at(-1);
    expect(listedFor?.url).toBe("/transactions/coins-moved");
    await form.save();
    expect(form.writes().map((w) => w.url)).toEqual(["/transactions"]);
    expect(form.sent()).toEqual(listedFor?.body);
  });

  it("asks once the typing stops, not for every key", async () => {
    const form = await renderForm({ book: MANY, respond: coinsAnswer({ status: 200, data: LISTED }) });
    await form.pickType("Transfer");
    await form.choose("From Account", "Sparrow");
    await form.choose("To Account", "Coldcard");
    // What arrived first: then each key of what left, from "0.4" on, is a transfer the list could be asked for
    await form.user.type(screen.getByLabelText("Amount (To)"), "0.4");
    await form.user.type(screen.getByLabelText("Amount (From)"), "0.40015");
    await waitForCoins(form);
    expect(asked(form)).toHaveLength(1);
    expect(asked(form)[0].body).toMatchObject({ amount: 0.40015 });
  });

  it("keeps the list shown, dimmed with its fee, while the changed transfer's is asked", async () => {
    const form = await renderForm({ book: MANY, respond: coinsAnswer({ status: 200, data: LISTED }) });
    await sparrowToColdcard(form);
    const list = () => screen.getByRole("table", { name: "Coins that will move" }).closest("[aria-busy]");
    expect(list()?.getAttribute("aria-busy")).toBe("false");
    expect(list()?.textContent).toContain("The network fee");
    expect(screen.getByRole("status").textContent).toBe("");
    await form.user.clear(screen.getByLabelText("Amount (To)"));
    await form.user.type(screen.getByLabelText("Amount (To)"), "0.3");
    expect(list()?.getAttribute("aria-busy")).toBe("true");
    expect(screen.getByRole("status").textContent).toBe("Working out which coins move…");
    await waitForCoins(form);
    expect(list()?.getAttribute("aria-busy")).toBe("false");
    expect(screen.getByRole("status").textContent).toBe("");
    expect(asked(form)).toHaveLength(2);
  });

  it("never keeps another account's coins under the new From", async () => {
    const form = await renderForm({ book: MANY, respond: coinsAnswer({ status: 200, data: LISTED }) });
    await sparrowToColdcard(form);
    await form.choose("From Account", "Kraken BTC");
    expect(screen.getByText(/^Per-wallet FIFO: your oldest coins in Kraken BTC move first/)).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("Working out which coins move…");
    await waitForCoins(form);
    expect(asked(form).at(-1)?.body).toMatchObject({ from_account_id: 103, to_account_id: 100 });
    expect(screen.getByRole("table", { name: "Coins that will move" })).toBeTruthy();
  });

  it("says the line before the amounts are there, and asks nothing yet", async () => {
    const form = await renderForm({ book: MANY, respond: coinsAnswer({ status: 200, data: LISTED }) });
    await form.pickType("Transfer");
    await form.choose("From Account", "Sparrow");
    await form.choose("To Account", "Coldcard");
    await waitForCoins(form);
    expect(screen.getByText(OLDEST_FIRST)).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    expect(asked(form)).toEqual([]);
  });

  it("says why when the save would be refused, nothing yet saved", async () => {
    const refused = {
      status: 400,
      data: { detail: "Not saved: with it, the account would lack BTC on its date or later. Not enough BTC to " +
        "transfer 2 (including fee 0)" },
    };
    const form = await renderForm({ book: MANY, respond: coinsAnswer(refused) });
    await sparrowToColdcard(form, "2", "2");
    expect(screen.getByText("This transfer can't be saved as it is: with it, the account would lack BTC on its " +
      "date or later. Not enough BTC to transfer 2 (including fee 0)")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("says so when the ledger is too big to work it out quickly", async () => {
    const slow = { coins: null, fee_btc: null, detail: "BitcoinTX couldn't work out in time which coins move. Saving isn't affected." };
    const form = await renderForm({ book: MANY, respond: coinsAnswer({ status: 200, data: slow }) });
    await sparrowToColdcard(form);
    expect(screen.getByText(slow.detail)).toBeTruthy();
    expect(screen.getByText(OLDEST_FIRST)).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("an edit asks for the coins the edited transfer moves", async () => {
    const saved = {
      id: 7, type: "Transfer" as const, from_account_id: 2, to_account_id: 100, amount: "0.2", fee_amount: "0.0001",
      fee_currency: "BTC",
    };
    const form = await renderForm({ book: MANY, transaction: saved, respond: coinsAnswer({ status: 200, data: LISTED }) });
    await waitForCoins(form);
    expect(asked(form).map((r) => r.url)).toEqual(["/transactions/7/coins-moved"]);
    await form.save();
    expect(form.sent()).toEqual(asked(form).at(-1)?.body);
  });
});

describe("no coins move", () => {
  it("within one wallet, which records only its fee (#159)", async () => {
    const form = await renderForm({ book: MANY, respond: coinsAnswer({ status: 200, data: LISTED }) });
    await form.pickType("Transfer");
    await form.choose("From Account", "Sparrow");
    await form.choose("To Account", "Sparrow: consolidate / move within the same wallet");
    await form.user.type(screen.getByLabelText("Amount (From)"), "0.4001");
    await form.user.type(screen.getByLabelText("Amount (To)"), "0.4");
    await waitForCoins(form);
    expect(screen.queryByText(/^Per-wallet FIFO/)).toBeNull();
    expect(asked(form)).toEqual([]);
  });

  it("in dollars", async () => {
    const form = await renderForm({ book: MANY, respond: coinsAnswer({ status: 200, data: LISTED }) });
    await form.pickType("Transfer");
    await form.choose("From Account", "Checking");
    await form.choose("To Account", "Savings");
    await form.user.type(screen.getByLabelText("Amount (From)"), "500");
    await form.user.type(screen.getByLabelText("Amount (To)"), "498");
    await waitForCoins(form);
    expect(screen.queryByText(/^Per-wallet FIFO/)).toBeNull();
    expect(asked(form)).toEqual([]);
  });
});
