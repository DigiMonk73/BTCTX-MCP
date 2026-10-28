// @vitest-environment jsdom
// The form's coin picker (#711, step C3; the owner's Q3): a Spent, Gift,
// Donation or Lost withdrawal from one of your wallets, or a Transfer out of
// one, lists the coins that leave (the oldest first, the IRS's default) and
// can choose others: one line per purchase the wallet holds then, filled
// oldest first, "Highest cost first" only on a transaction dated today. The
// rule's words are always beside it, Save waits until the choice adds up to
// what leaves, and the save sends the coins chosen (`chosen_coins`), or null
// to go back to oldest first. An edit opens on its stored choice, with the
// day it was chosen, and keeps it when the list can't be worked out in time.
import { act, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MANY } from "../../test/books";
import { renderForm, type PlannedAnswer, type RenderedForm, type SentRequest } from "../../test/renderForm";
import { CHOOSE_RULE } from "../../utils/chosenCoins";
import { COINS_WAIT_MS } from "./useCoinsMoved";

const held = (id: number, acquired: string, btc: string, cost: string, oldest: string, term = "LONG") => ({
  acquired_txn_id: id, kind: "Deposit", source: "MyBTC", acquired_in: "Sparrow", date: acquired, acquired,
  inherited: false, btc, cost_usd: cost, term, oldest_first: oldest,
});
// Sparrow holds 0.3 BTC from 2017 ($1,000 a BTC) and 0.5 from 2025 ($90,000 a BTC)
const HELD = [held(11, "2017-03-01", "0.30000000", "300.00", "0.10010000"),
              held(13, "2025-01-15", "0.50000000", "45000.00", "0.00000000", "SHORT")];
const LISTED = {
  coins: [{ acquired: "2017-03-01", btc: "0.10000000", cost_usd: "100.00", inherited: false, acquired_txn_id: 11 }],
  fee_btc: "0.00010000", detail: null, held: HELD, dated_today: false,
};
const SLOW = { coins: null, fee_btc: null, held: null, dated_today: false,
               detail: "BitcoinTX couldn't work out in time which coins move. Saving isn't affected." };

const asked = (form: RenderedForm) => form.requests.filter((r) => r.url.endsWith("/coins-moved"));
const coinsAnswer = (answer: PlannedAnswer) => (request: SentRequest) =>
  request.url.endsWith("/coins-moved") ? answer : undefined;

async function waitForCoins(form: RenderedForm) {
  await act(() => new Promise((resolve) => setTimeout(resolve, COINS_WAIT_MS + 50)));
  await form.settle();
}

/** A Spent of 0.1 BTC (a 0.0001 fee) from Sparrow, its coins listed. */
async function spentFromSparrow(form: RenderedForm) {
  await form.pickType("Withdrawal");
  await form.choose("Account", "Sparrow");
  await form.user.type(screen.getByLabelText("Amount"), "0.1");
  await form.user.selectOptions(screen.getByLabelText("Purpose (BTC only)"), "Spent");
  await form.user.clear(screen.getByLabelText("Fee (BTC)"));
  await form.user.type(screen.getByLabelText("Fee (BTC)"), "0.0001");
  await form.user.type(screen.getByLabelText("Proceeds (USD)"), "10000");
  await waitForCoins(form);
}

const chosenField = (acquired: string) => screen.getByLabelText(`BTC chosen from the coins acquired ${acquired}`);

async function choose(form: RenderedForm, acquired: string, btc: string) {
  await form.user.clear(chosenField(acquired));
  if (btc) await form.user.type(chosenField(acquired), btc);
  await waitForCoins(form);
}

describe("a Spent from one of your wallets", () => {
  it("lists the coins that leave, oldest first, and can choose others", async () => {
    const form = await renderForm({ book: MANY, respond: coinsAnswer({ status: 200, data: LISTED }) });
    await spentFromSparrow(form);
    expect(asked(form).at(-1)?.body).toMatchObject({ type: "Withdrawal", from_account_id: 2 });
    expect(screen.getByText(/^Per-wallet FIFO: your oldest coins in Sparrow leave first/)).toBeTruthy();
    expect(screen.getByRole("table", { name: "Coins that will leave" })).toBeTruthy();

    await form.user.click(screen.getByRole("button", { name: "Choose which coins leave" }));
    expect(screen.getByText(CHOOSE_RULE)).toBeTruthy();
    expect((chosenField("Mar 1, 2017") as HTMLInputElement).value).toBe("0.1001"); // filled oldest first
    expect((chosenField("Jan 15, 2025") as HTMLInputElement).value).toBe("");
    await choose(form, "Mar 1, 2017", "");
    await choose(form, "Jan 15, 2025", "0.1001");
    expect(screen.getByText(
      "Chosen 0.10010000 of 0.10010000 BTC: the amount 0.10000000 and the network fee 0.00010000.")).toBeTruthy();
    expect(asked(form).at(-1)?.body).toMatchObject({ chosen_coins: [{ acquired_txn_id: 13, btc: "0.10010000" }] });

    await form.save();
    expect(form.sent()).toMatchObject({ chosen_coins: [{ acquired_txn_id: 13, btc: "0.10010000" }] });
  });

  it("waits to save until the coins chosen add up to what leaves", async () => {
    const form = await renderForm({ book: MANY, respond: coinsAnswer({ status: 200, data: LISTED }) });
    await spentFromSparrow(form);
    await form.user.click(screen.getByRole("button", { name: "Choose which coins leave" }));
    await choose(form, "Mar 1, 2017", "0.05");
    expect(screen.getByText(
      "Chosen 0.05000000 of 0.10010000 BTC: the amount 0.10000000 and the network fee 0.00010000.")).toBeTruthy();
    await form.save();
    expect(form.writes()).toEqual([]);
    expect(screen.getByText("The coins chosen must add up to what leaves: choose coins for all of it, or don't " +
      "choose them.")).toBeTruthy();
  });

  it("says so where it's seen: scrolled to, focused and announced, after each Save (#771)", async () => {
    const scrolled = vi.fn();
    Element.prototype.scrollIntoView = scrolled;  // jsdom has none
    try {
      const form = await renderForm({ book: MANY, respond: coinsAnswer({ status: 200, data: LISTED }) });
      await spentFromSparrow(form);
      await form.user.click(screen.getByRole("button", { name: "Choose which coins leave" }));
      await choose(form, "Mar 1, 2017", "0.05");
      await form.save();
      const refusal = screen.getByRole("alert");
      expect(refusal.textContent).toBe("The coins chosen must add up to what leaves: choose coins for all of it, " +
        "or don't choose them.");
      expect(document.activeElement).toBe(refusal);
      expect(scrolled).toHaveBeenCalledTimes(1);
      expect(scrolled.mock.contexts[0]).toBe(refusal);
      await form.save();  // again: a new alert, announced again, and in sight again
      expect(screen.getByRole("alert")).not.toBe(refusal);
      expect(document.activeElement).toBe(screen.getByRole("alert"));
      expect(scrolled).toHaveBeenCalledTimes(2);
    } finally {
      delete (Element.prototype as Partial<Element>).scrollIntoView;
    }
  });

  it("leaves focus on a field above that was refused too, where the form puts it (#771, the review's)", async () => {
    const scrolled = vi.fn();
    Element.prototype.scrollIntoView = scrolled;  // jsdom has none
    try {
      const form = await renderForm({ book: MANY, respond: coinsAnswer({ status: 200, data: LISTED }) });
      await spentFromSparrow(form);
      await form.user.click(screen.getByRole("button", { name: "Choose which coins leave" }));
      await choose(form, "Mar 1, 2017", "0.05");
      await form.user.clear(screen.getByLabelText("Amount"));
      await form.save();
      await act(() => new Promise((resolve) => setTimeout(resolve, 50)));  // the form's second focus, a moment later
      expect(screen.getByRole("alert").textContent).toMatch(/^The coins chosen must add up/);
      expect(document.activeElement).toBe(screen.getByLabelText("Amount"));
      expect(scrolled).not.toHaveBeenCalled();
    } finally {
      delete (Element.prototype as Partial<Element>).scrollIntoView;
    }
  });

  it("can go back to oldest first, and then sends no choice", async () => {
    const form = await renderForm({ book: MANY, respond: coinsAnswer({ status: 200, data: LISTED }) });
    await spentFromSparrow(form);
    await form.user.click(screen.getByRole("button", { name: "Choose which coins leave" }));
    await choose(form, "Mar 1, 2017", "0.05");
    await form.user.click(screen.getByRole("button", { name: "Don't choose coins" }));
    await waitForCoins(form);
    expect(screen.queryByText(CHOOSE_RULE)).toBeNull();
    await form.save();
    expect(form.sent()).not.toHaveProperty("chosen_coins");
  });

  it("offers \"Highest cost first\" only on a transaction dated today (Q3)", async () => {
    const form = await renderForm({ book: MANY, respond: coinsAnswer({ status: 200, data: LISTED }) });
    await spentFromSparrow(form);
    await form.user.click(screen.getByRole("button", { name: "Choose which coins leave" }));
    expect(screen.getByRole("button", { name: "Oldest first" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Highest cost first" })).toBeNull();
    form.unmount();

    const today = await renderForm({ book: MANY, respond: coinsAnswer({ status: 200, data: { ...LISTED, dated_today: true } }) });
    await spentFromSparrow(today);
    await today.user.click(screen.getByRole("button", { name: "Choose which coins leave" }));
    // Opening it asks again (the choice is in the question): never filled from the answer before it
    expect((screen.getByRole("button", { name: "Highest cost first" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Oldest first" }) as HTMLButtonElement).disabled).toBe(true);
    await waitForCoins(today);
    await today.user.click(screen.getByRole("button", { name: "Highest cost first" }));
    expect((chosenField("Jan 15, 2025") as HTMLInputElement).value).toBe("0.1001");
    expect((chosenField("Mar 1, 2017") as HTMLInputElement).value).toBe("");
  });

  it("says each purchase's term and how and where it was acquired", async () => {
    const form = await renderForm({ book: MANY, respond: coinsAnswer({ status: 200, data: LISTED }) });
    await spentFromSparrow(form);
    await form.user.click(screen.getByRole("button", { name: "Choose which coins leave" }));
    const table = screen.getByRole("table", { name: "Coins in Sparrow then" });
    const cells = within(table).getAllByRole("row").map((row) =>
      [...row.querySelectorAll("th, td")].map((cell) => cell.textContent ?? ""));
    expect(cells[0]).toEqual(["Acquired", "Held (BTC)", "Chosen (BTC)"]);
    expect(cells[1].slice(0, 2)).toEqual(["Mar 1, 2017Long-term · My BTC · Sparrow · Mar 1, 2017",
                                          "0.30000000cost $300.00"]);
    expect(cells[2][0]).toBe("Jan 15, 2025Short-term · My BTC · Sparrow · Jan 15, 2025");
  });
});

describe("a Transfer out of a wallet", () => {
  it("chooses its coins in its own terms: Amount (To) and the fee", async () => {
    const answer = { ...LISTED, held: [held(11, "2017-03-01", "0.30000000", "300.00", "0.01010000"), HELD[1]] };
    const form = await renderForm({ book: MANY, respond: coinsAnswer({ status: 200, data: answer }) });
    await form.pickType("Transfer");
    await form.choose("From Account", "Sparrow");
    await form.choose("To Account", "Coldcard");
    await form.user.type(screen.getByLabelText("Amount (From)"), "0.0101");
    await form.user.type(screen.getByLabelText("Amount (To)"), "0.01");
    await waitForCoins(form);
    await form.user.click(screen.getByRole("button", { name: "Choose which coins leave" }));
    expect(screen.getByText(
      "Chosen 0.01010000 of 0.01010000 BTC: Amount (To) 0.01000000 and the network fee 0.00010000.")).toBeTruthy();
    await choose(form, "Mar 1, 2017", "");
    await choose(form, "Jan 15, 2025", "0.0101");
    await form.save();
    expect(form.sent()).toMatchObject({ type: "Transfer", chosen_coins: [{ acquired_txn_id: 13, btc: "0.01010000" }] });
  });
});

describe("no coins are chosen", () => {
  it("from an exchange: they leave oldest first, as its Form 1099-DA reports them", async () => {
    const form = await renderForm({ book: MANY, respond: coinsAnswer({ status: 200, data: LISTED }) });
    await form.pickType("Withdrawal");
    await form.choose("Account", "River BTC");
    await form.user.type(screen.getByLabelText("Amount"), "0.1");
    await waitForCoins(form);
    expect(screen.queryByRole("button", { name: "Choose which coins leave" })).toBeNull();
    expect(asked(form)).toEqual([]);
  });
});

describe("an edit of a transaction whose coins were chosen", () => {
  const SAVED = {
    id: 7, type: "Withdrawal" as const, from_account_id: 2, to_account_id: 99, amount: "0.1", fee_amount: "0.0001",
    fee_currency: "BTC", purpose: "Spent", proceeds_usd: "10000", gross_proceeds_usd: "10000",
    timestamp: "2025-06-01T12:00:00Z", chosen_coins: [{ acquired_txn_id: 13, btc: "0.10010000" }],
    coins_chosen_at: "2025-07-04T15:00:00Z",
  } as Partial<ITransactionRaw> & { id: number; type: TransactionType };

  it("opens on them, with the day they were chosen, and sends them back unchanged", async () => {
    const form = await renderForm({ book: MANY, transaction: SAVED, respond: coinsAnswer({ status: 200, data: LISTED }) });
    await waitForCoins(form);
    expect((chosenField("Jan 15, 2025") as HTMLInputElement).value).toBe("0.1001");
    expect(screen.getByText("Chosen on Jul 4, 2025, after the coins left on Jun 1, 2025. A choice counts only if you " +
      "made it by then and your records show it.")).toBeTruthy();
    await form.save();
    expect(form.sent()).toMatchObject({ chosen_coins: [{ acquired_txn_id: 13, btc: "0.10010000" }] });
  });

  it("an edit of the amount shows the choice no longer adding up, then sends the new one or null", async () => {
    const form = await renderForm({ book: MANY, transaction: SAVED, respond: coinsAnswer({ status: 200, data: LISTED }) });
    await waitForCoins(form);
    await form.user.clear(screen.getByLabelText("Amount"));
    await form.user.type(screen.getByLabelText("Amount"), "0.2");
    await waitForCoins(form);
    expect(screen.getByText(
      "Chosen 0.10010000 of 0.20010000 BTC: the amount 0.20000000 and the network fee 0.00010000.")).toBeTruthy();
    await form.save();
    expect(form.writes()).toEqual([]);
    await choose(form, "Jan 15, 2025", "0.2001");
    await form.save();
    expect(form.sent()).toMatchObject({ amount: 0.2, chosen_coins: [{ acquired_txn_id: 13, btc: "0.20010000" }] });
  });

  it("set back to oldest first sends null", async () => {
    const form = await renderForm({ book: MANY, transaction: SAVED, respond: coinsAnswer({ status: 200, data: LISTED }) });
    await waitForCoins(form);
    await form.user.click(screen.getByRole("button", { name: "Don't choose coins" }));
    await form.save();
    expect(form.sent()).toMatchObject({ chosen_coins: null });
  });

  it("an edit that moves it to an exchange says the choice goes, and sends null (the review's)", async () => {
    const form = await renderForm({ book: MANY, transaction: SAVED, respond: coinsAnswer({ status: 200, data: LISTED }) });
    await waitForCoins(form);
    await form.choose("Account", "River BTC");
    expect(screen.getByText("The coins chosen on Jul 4, 2025 go back to oldest first when you save.")).toBeTruthy();
    await form.save();
    expect(form.sent()).toMatchObject({ from_account_id: 4, chosen_coins: null });
  });

  it("a BTC field that isn't a plain number is refused before the save (the review's)", async () => {
    const form = await renderForm({ book: MANY, transaction: SAVED, respond: coinsAnswer({ status: 200, data: LISTED }) });
    await waitForCoins(form);
    await choose(form, "Jan 15, 2025", "-0.1001");
    await form.save();
    expect(form.writes()).toEqual([]);
    expect(screen.getByText("Each BTC chosen must be a plain number, with at most 8 decimal places.")).toBeTruthy();
  });

  it("keeps them, shown and sent back, when the list can't be worked out in time", async () => {
    const form = await renderForm({ book: MANY, transaction: SAVED, respond: coinsAnswer({ status: 200, data: SLOW }) });
    await waitForCoins(form);
    expect(screen.getByText("BitcoinTX couldn't list this wallet's coins quickly enough here.")).toBeTruthy();
    expect(screen.getByText("Transaction 13: 0.10010000 BTC")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
    await form.save();
    expect(form.sent()).toMatchObject({ chosen_coins: [{ acquired_txn_id: 13, btc: "0.10010000" }] });
  });
});

describe("an edit of a transaction whose coins weren't chosen", () => {
  it("sends no chosen_coins: its body is as it always was (call (f), the review's)", async () => {
    const saved = {
      id: 8, type: "Withdrawal" as const, from_account_id: 2, to_account_id: 99, amount: "0.1", fee_amount: "0",
      fee_currency: "BTC", purpose: "Spent", proceeds_usd: "10000", gross_proceeds_usd: "10000",
      timestamp: "2025-06-01T12:00:00Z",
    } as Partial<ITransactionRaw> & { id: number; type: TransactionType };
    const form = await renderForm({ book: MANY, transaction: saved, respond: coinsAnswer({ status: 200, data: LISTED }) });
    await waitForCoins(form);
    await form.save();
    expect(form.sent()).not.toHaveProperty("chosen_coins");
    expect(screen.queryByText(/go back to oldest first/)).toBeNull();
  });
});
