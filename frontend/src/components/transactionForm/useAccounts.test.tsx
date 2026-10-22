// @vitest-environment jsdom
// B6a-4: the account book loaded once per page (spec 5.4, useAccounts), and the
// form reading a row back with it (5.13: both ids kept, for every type).
import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ToastProvider } from "../../contexts/ToastContext";
import { parseTransaction } from "../../utils/format";
import { mapTransactionToFormData } from "../../utils/transactionForm";
import { ACCOUNTS_FAILED } from "../../utils/useAccounts";
import { MISSING, TWO_OF_EACH as TWO } from "../../test/accountBooks";
import { renderForm, type SentRequest } from "../../test/renderForm";
import TransactionForm from "../TransactionForm";

const SELL: ITransactionRaw = {
  id: 7, type: "Sell", timestamp: "2026-03-02T15:00:00Z", from_account_id: 103, to_account_id: 102,
  amount: "0.1", fee_amount: "12", fee_currency: "USD", gross_proceeds_usd: "6000", proceeds_usd: "5988",
} as unknown as ITransactionRaw;

const SPEND: ITransactionRaw = {
  id: 8, type: "Withdrawal", timestamp: "2026-04-01T12:00:00Z", from_account_id: 101, to_account_id: 99,
  amount: "0.01", fee_amount: "0", fee_currency: "BTC", purpose: "Spent", proceeds_usd: "900",
  gross_proceeds_usd: "900",
} as unknown as ITransactionRaw;

function readBack(raw: ITransactionRaw, changes: Partial<ITransactionRaw> = {}) {
  return mapTransactionToFormData(parseTransaction({ ...raw, ...changes }), TWO);
}

const listReads = (requests: SentRequest[]) =>
  requests.filter((r) => r.method === "get" && r.url === "/accounts/").length;

/** Let the second form's requests and renders run. */
async function settled(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

describe("the page's one request", () => {
  it("is shared by two forms mounted on one page", async () => {
    const { requests } = await renderForm({ book: TWO });
    render(<ToastProvider><TransactionForm id="second-form" /></ToastProvider>);
    await settled();
    expect(listReads(requests)).toBe(1);
  });

  it("is asked again by the next form after it failed", async () => {
    const { requests } = await renderForm({ book: TWO, accountsFail: true });
    render(<ToastProvider><TransactionForm id="second-form" /></ToastProvider>);
    await settled();
    expect(listReads(requests)).toBe(2);
  });
});

describe("a list that won't load", () => {
  it("shows why in place of the fields, and Save sends nothing", async () => {
    const { user, requests, save } = await renderForm({ book: TWO, accountsFail: true });
    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load your accounts: reload the page.");
    expect(ACCOUNTS_FAILED).toBe("Couldn't load your accounts: reload the page.");
    await user.selectOptions(screen.getByLabelText("Transaction Type"), "Deposit");
    await save();
    expect(requests.filter((r) => r.method !== "get")).toEqual([]);
  });
});

describe("reading a row back with the book", () => {
  it("keeps a Sell's two ids", () => {
    const form = readBack(SELL);
    expect(form.fromAccountId).toBe(103);
    expect(form.toAccountId).toBe(102);
  });

  it("takes a withdrawal's currency from the book: proceeds only from a bitcoin account", () => {
    expect(readBack(SPEND).proceeds_usd).toBe(900);
    expect(readBack(SPEND, { from_account_id: 100 }).proceeds_usd).toBeUndefined();
  });

  it("reads a row naming an account the book lacks, keeping its id", () => {
    expect(readBack(SPEND, { from_account_id: MISSING }).fromAccountId).toBe(MISSING);
  });

  it("opens an edit with the row's values whichever answer comes first", async () => {
    const { answerAccounts } = await renderForm({ book: TWO, transaction: SELL, accountsHeld: true });
    await answerAccounts();
    expect(screen.getByLabelText("Transaction Type")).toHaveValue("Sell");
    expect(screen.getByLabelText("Amount BTC")).toHaveValue(0.1);
  });
});
