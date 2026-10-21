// @vitest-environment jsdom
// B6b-12's proving test: the transaction form through the past-year warning
// (spec 5.8). A save, an edit or a delete the server answers with its 409 opens
// the dialog; Save anyway sends the same write again with ?confirm=<the 409's
// fingerprint>, and a new 409 asks again; Cancel saves nothing and keeps what
// was typed. Only an add offers "Don't ask again for adds to …", and once it's
// ticked the next adds to that year confirm their own 409 without asking.
import { screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { TWO_OF_EACH as TWO } from "../../test/accountBooks";
import { renderForm, type RenderedForm, type SentRequest } from "../../test/renderForm";
import { askForAddsAgain } from "../../utils/pastYears";

const SAVE = "Save anyway (a copy is made first)";
const BOX = "Don't ask again for adds to 2025 while this page is open";
const DETAIL = "This changes the figures of tax year 2025, which you may already have filed. " +
  "Confirm to save it: a copy of your ledger is made first.";
const PAST = { years: [2025] };

const DEPOSIT: ITransactionRaw = {
  id: 12, type: "Deposit", timestamp: "2025-05-02T09:00:00Z", from_account_id: 99, to_account_id: 101,
  amount: "0.01", fee_amount: "0", fee_currency: "BTC", source: "MyBTC", cost_basis_usd: "500",
} as unknown as ITransactionRaw;

const writes = (requests: SentRequest[]) => requests.filter((r) => r.method !== "get");
const dialog = () => screen.getByRole("dialog", { name: "Change an earlier tax year?" });

/** A new income Deposit of 0.01 BTC into Cold Storage (its value left to the price), saved once. */
async function addDeposit(form: RenderedForm) {
  await form.user.selectOptions(screen.getByLabelText("Transaction Type"), "Deposit");
  await form.user.selectOptions(screen.getByLabelText("Account"), "Cold Storage");
  await form.user.type(screen.getByLabelText("Amount"), "0.01");
  await form.user.selectOptions(screen.getByLabelText("Source"), "Income");
  await form.save();
}

async function answer(form: RenderedForm, button: string) {
  await form.user.click(within(dialog()).getByRole("button", { name: button }));
  await form.settle();
}

afterEach(() => askForAddsAgain());

describe("a new transaction into an earlier tax year", () => {
  it("asks with the server's sentence and what changes, before anything is saved", async () => {
    const form = await renderForm({ book: TWO, pastYears: PAST });
    await addDeposit(form);
    expect(dialog()).toHaveAccessibleDescription(DETAIL);
    expect(within(dialog()).getByRole("list", { name: "What changes" })).toHaveTextContent(
      "2025-03-01 12:00 · Withdrawal (Spent) · 0.50000000 BTC · Wallet: gain 10000.00 -> 5000.00.");
    expect(writes(form.requests)).toHaveLength(1);
    expect(writes(form.requests)[0].params).toBeUndefined();
  });

  it("Save anyway sends the same transaction again, confirmed, and it's saved", async () => {
    const form = await renderForm({ book: TWO, pastYears: PAST });
    await addDeposit(form);
    await answer(form, SAVE);
    const [first, again] = writes(form.requests);
    expect(again).toEqual({ ...first, params: { confirm: "fp-1" } });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByLabelText("Transaction Type")).toHaveValue(""); // saved: the form starts again
  });

  it("Cancel saves nothing and keeps what was typed", async () => {
    const form = await renderForm({ book: TWO, pastYears: PAST });
    await addDeposit(form);
    await answer(form, "Cancel");
    expect(writes(form.requests)).toHaveLength(1);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByLabelText("Transaction Type")).toHaveValue("Deposit");
    expect(screen.getByLabelText("Amount")).toHaveValue(0.01);
  });

  it("a ledger that changed meanwhile gets a new 409, asked again, and its fingerprint is sent", async () => {
    const form = await renderForm({ book: TWO, pastYears: { years: [2025], fingerprints: ["fp-1", "fp-2"] } });
    await addDeposit(form);
    await answer(form, SAVE);
    expect(dialog()).toBeInTheDocument();
    await answer(form, SAVE);
    expect(writes(form.requests).map((r) => r.params)).toEqual([undefined, { confirm: "fp-1" }, { confirm: "fp-2" }]);
    expect(screen.getByLabelText("Transaction Type")).toHaveValue(""); // saved: the form starts again
  });

  it("with the box ticked, the next add to that year confirms its own 409 without asking", async () => {
    const form = await renderForm({ book: TWO, pastYears: PAST });
    await addDeposit(form);
    await form.user.click(within(dialog()).getByRole("checkbox", { name: BOX }));
    await answer(form, SAVE);
    await addDeposit(form);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(writes(form.requests).map((r) => r.params)).toEqual([
      undefined, { confirm: "fp-1" }, undefined, { confirm: "fp-1" },
    ]);
  });
});

describe("an edit or a delete in an earlier tax year", () => {
  it("an edit asks, offers no box, and Save anyway sends the PUT again confirmed", async () => {
    const form = await renderForm({ book: TWO, transaction: DEPOSIT, pastYears: PAST });
    await form.save();
    expect(within(dialog()).queryByRole("checkbox")).toBeNull();
    await answer(form, SAVE);
    expect(writes(form.requests).map((r) => [r.method, r.url, r.params])).toEqual([
      ["put", "/transactions/12", undefined], ["put", "/transactions/12", { confirm: "fp-1" }],
    ]);
  });

  it("an edit asks even for a year whose adds were let through", async () => {
    const form = await renderForm({ book: TWO, transaction: DEPOSIT, pastYears: PAST });
    const { stopAskingForAdds } = await import("../../utils/pastYears");
    stopAskingForAdds([2025]);
    await form.save();
    expect(dialog()).toBeInTheDocument();
  });

  it("a delete asks, and Save anyway sends the DELETE again confirmed", async () => {
    const form = await renderForm({ book: TWO, transaction: DEPOSIT, pastYears: PAST });
    await form.remove();
    await answer(form, SAVE);
    expect(writes(form.requests).map((r) => [r.method, r.url, r.params])).toEqual([
      ["delete", "/transactions/12", undefined], ["delete", "/transactions/12", { confirm: "fp-1" }],
    ]);
  });

  it("a delete cancelled deletes nothing", async () => {
    const form = await renderForm({ book: TWO, transaction: DEPOSIT, pastYears: PAST });
    await form.remove();
    await answer(form, "Cancel");
    expect(writes(form.requests)).toHaveLength(1);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
