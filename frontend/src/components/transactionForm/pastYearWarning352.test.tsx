// @vitest-environment jsdom
// The past-year warning on the mounted form (2.0 spec 5.8, #352): an add,
// edit or delete the server answers with the warning's 409 is saved only once
// the owner confirms it, by the same request sent again with its confirm.
// Cancel saves nothing and keeps what was typed. For adds only, "Don't ask
// again" keeps a year quiet while the page is open: the page then confirms
// an add to it by itself. Any other 409 is the toast it always was.
import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ONE_OF_EACH } from "../../test/books";
import { renderForm, shown, type PlannedAnswer, type RenderedForm, type SentRequest } from "../../test/renderForm";
import { keepAddsQuiet, yearsInWords, type PastYearChange, type PastYearWarning } from "../../utils/pastYears";

const TITLE = "Change an earlier tax year?";
const SAVE_ANYWAY = "Save anyway (a copy is made first)";
const DELETE_ANYWAY = "Delete anyway (a copy is made first)";
const quietBox = (years: string) => `Don't ask again for adds to ${years} while this page is open`;

const SELL: PastYearChange = {
  id: 12, date: "2024-06-01 12:00", type: "Sell", purpose: null, source: null, amount: "0.25", unit: "BTC",
  realized_gain_usd: "14500.00", issue: "Changes with this save.",
  change: "basis 250.00 -> 500.00; gain 14750.00 -> 14500.00.", years: [2024],
};
const ADDED: PastYearChange = {
  id: null, date: "2025-08-01 12:00", type: "Deposit", purpose: null, source: "MyBTC", amount: "0.5", unit: "BTC",
  realized_gain_usd: null, issue: "Changes with this save.",
  change: "Added: basis 30000.00; cost of the lots it made 30000.00.", years: [2025],
};

/** The server's warning naming `years`, its fingerprint told apart by `tag`. */
function warning(years: number[], tag = "a", extra: Partial<PastYearWarning> = {}): PastYearWarning {
  return {
    detail: `This changes the figures of tax years ${yearsInWords(years)}, which you may already have filed. ` +
      "Confirm to save it: a copy of your ledger is made first.",
    years,
    changes: [SELL, ADDED],
    pending: [],
    recalc_error: null,
    exact: true,
    why_not_exact: null,
    confirm: `${tag}${years.join("")}`.padEnd(64, "0"),
    ...extra,
  };
}

const refused = (data: unknown): PlannedAnswer => ({ status: 409, data });
const isWrite = (r: SentRequest) => r.method !== "get";
const confirmOf = (r: SentRequest) => r.params?.confirm;

/** The warning for each unconfirmed write, by its date's year; a confirmed one is saved. */
const warnsByYear = (r: SentRequest) => {
  if (!isWrite(r) || confirmOf(r)) return undefined;
  return refused(warning([Number(String(r.body?.timestamp).slice(0, 4))]));
};

/** A dollar deposit into Bank, dated `when`. */
async function fillDeposit(form: RenderedForm, when: string, amount = "500") {
  await form.pickType("Deposit");
  await form.choose("Account", "Bank");
  const amountField = screen.getByLabelText("Amount", { exact: true });
  await form.user.clear(amountField);
  await form.user.type(amountField, amount);
  fireEvent.change(screen.getByLabelText("Date & Time"), { target: { value: when } });
}

const dialog = () => screen.getByRole("dialog", { name: TITLE });

async function click(form: RenderedForm, name: string) {
  await form.user.click(within(dialog()).getByRole("button", { name }));
  await form.settle();
}

const usdDeposit = { id: 7, type: "Deposit" as const, from_account_id: 99, to_account_id: 1, amount: "500",
  fee_amount: "0", fee_currency: "USD", source: "N/A" };

describe("an add that changes an earlier tax year", () => {
  it("asks, with the years and what changes, then sends the same body again with its confirm", async () => {
    const form = await renderForm({ book: ONE_OF_EACH, respond: warnsByYear });
    await fillDeposit(form, "2025-08-01T12:00:00");
    await form.save();

    expect(form.writes()).toHaveLength(1);
    const asked = dialog();
    expect(within(asked).getByText(warning([2025]).detail)).toBeTruthy();
    expect(within(asked).getByText(
      "2024-06-01 12:00 · Sell · 0.25 BTC — basis 250.00 -> 500.00; gain 14750.00 -> 14500.00.")).toBeTruthy();
    expect(within(asked).getByText(
      "2025-08-01 12:00 · Deposit (MyBTC) · 0.5 BTC — Added: basis 30000.00; cost of the lots it made 30000.00.",
    )).toBeTruthy();
    expect(within(asked).getByRole("list", { name: "Tax year 2024" })).toBeTruthy();
    expect(within(asked).getByRole("checkbox", { name: quietBox("2025") })).toBeTruthy();
    expect(form.toasts()).toEqual([]);

    await click(form, SAVE_ANYWAY);
    const [first, second] = form.writes();
    expect([first.method, first.url, first.params]).toEqual(["post", "/transactions", undefined]);
    expect([second.method, second.url, second.params]).toEqual(["post", "/transactions", { confirm: warning([2025]).confirm }]);
    expect(second.body).toEqual(first.body);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(form.toasts()).toEqual([{ type: "success", message: "Transaction created successfully!" }]);
    expect(shown("Transaction Type")).toBe("Select Transaction Type");
  });

  it("Cancel sends nothing more, keeps what was typed and shows no error", async () => {
    const form = await renderForm({ book: ONE_OF_EACH, respond: warnsByYear });
    await fillDeposit(form, "2025-08-01T12:34:56", "750");
    await form.save();
    await click(form, "Cancel");

    expect(form.writes()).toHaveLength(1);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(form.toasts()).toEqual([]);
    expect([shown("Transaction Type"), shown("Account"), shown("Amount"), shown("Date & Time")])
      .toEqual(["Deposit", "Bank", "750", "2025-08-01T12:34:56"]);
    // and it can be saved again: asked again
    await form.save();
    expect(form.writes()).toHaveLength(2);
    expect(dialog()).toBeTruthy();
  });

  it("with the box ticked, the next add to that year is confirmed by the page; another year still asks", async () => {
    const form = await renderForm({ book: ONE_OF_EACH, respond: warnsByYear });
    await fillDeposit(form, "2025-08-01T12:00:00");
    await form.save();
    await form.user.click(within(dialog()).getByRole("checkbox", { name: quietBox("2025") }));
    await click(form, SAVE_ANYWAY);
    expect(form.writes()).toHaveLength(2);

    await fillDeposit(form, "2025-09-01T12:00:00");
    await form.save();
    expect(screen.queryByRole("dialog")).toBeNull();
    const quiet = form.writes().slice(2);
    expect(quiet.map(confirmOf)).toEqual([undefined, warning([2025]).confirm]);
    expect(quiet[1].body).toEqual(quiet[0].body);
    expect(form.toasts().filter((t) => t.type === "success")).toHaveLength(2);

    await fillDeposit(form, "2024-09-01T12:00:00");
    await form.save();
    expect(form.writes()).toHaveLength(5);
    expect(within(dialog()).getByText(warning([2024]).detail)).toBeTruthy();
    expect(within(dialog()).getByRole("checkbox", { name: quietBox("2024") })).toBeTruthy();
  });

  it("unticked, the next add to that year asks again", async () => {
    const form = await renderForm({ book: ONE_OF_EACH, respond: warnsByYear });
    await fillDeposit(form, "2025-08-01T12:00:00");
    await form.save();
    await click(form, SAVE_ANYWAY);
    await fillDeposit(form, "2025-09-01T12:00:00");
    await form.save();
    expect(form.writes()).toHaveLength(3);
    expect(dialog()).toBeTruthy();
  });

  it("a quiet year's add the server warns about again (the ledger changed meanwhile) is asked", async () => {
    const answers = [refused(warning([2025], "a")), refused(warning([2025], "b", { changes: [ADDED] }))];
    const form = await renderForm({ book: ONE_OF_EACH, respond: (r) => (isWrite(r) ? answers.shift() : undefined) });
    keepAddsQuiet([2025]);
    await fillDeposit(form, "2025-08-01T12:00:00");
    await form.save();

    expect(form.writes().map(confirmOf)).toEqual([undefined, warning([2025], "a").confirm]);
    expect(within(dialog()).getAllByRole("listitem")).toHaveLength(1);
    await click(form, SAVE_ANYWAY);
    expect(form.writes().map(confirmOf).at(-1)).toBe(warning([2025], "b").confirm);
    expect(form.toasts()).toEqual([{ type: "success", message: "Transaction created successfully!" }]);
  });

  it("a confirm the ledger outdated meanwhile is asked again, saying so, with the new confirm", async () => {
    const answers = [refused(warning([2025], "a")), refused(warning([2024, 2025], "b"))];
    const form = await renderForm({ book: ONE_OF_EACH, respond: (r) => (isWrite(r) ? answers.shift() : undefined) });
    await fillDeposit(form, "2025-08-01T12:00:00");
    await form.save();
    expect(screen.queryByRole("alert")).toBeNull();
    await click(form, SAVE_ANYWAY);

    expect(within(dialog()).getByRole("alert").textContent).toMatch(/The ledger changed while this was open\. Nothing was saved/);
    expect(within(dialog()).getByText(warning([2024, 2025]).detail)).toBeTruthy();
    expect(within(dialog()).getByRole("checkbox", { name: quietBox("2024 and 2025") })).toBeTruthy();
    await click(form, SAVE_ANYWAY);
    expect(form.writes().map(confirmOf)).toEqual([undefined, warning([2025], "a").confirm, warning([2024, 2025], "b").confirm]);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("a failure of the confirmed save closes the question and shows the server's reason", async () => {
    const answers = [refused(warning([2025])), { status: 503, data: { detail: "Not saved: BitcoinTX was busy." } }];
    const form = await renderForm({ book: ONE_OF_EACH, respond: (r) => (isWrite(r) ? answers.shift() : undefined) });
    await fillDeposit(form, "2025-08-01T12:00:00");
    await form.save();
    await click(form, SAVE_ANYWAY);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(form.toasts()).toEqual([{ type: "error", message: "Failed to create transaction: Not saved: BitcoinTX was busy." }]);
    expect(shown("Amount")).toBe("500");
  });
});

describe("the warning's other forms", () => {
  it("the page-version 409 (no confirm) is the error toast it always was, with no question", async () => {
    const reload = { detail: "BitcoinTX was updated: reload the page." };
    const form = await renderForm({ book: ONE_OF_EACH, respond: (r) => (isWrite(r) ? refused(reload) : undefined) });
    await fillDeposit(form, "2025-08-01T12:00:00");
    await form.save();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(form.writes()).toHaveLength(1);
    expect(form.toasts()).toEqual([
      { type: "error", message: "Failed to create transaction: BitcoinTX was updated: reload the page." },
    ]);
  });

  it("the date-based warning says why it isn't exact, and lists nothing", async () => {
    const byDate = warning([2024, 2025], "d", {
      detail: "This is dated in 2024, so it can change 2024's figures and later years you may have filed. " +
        "Save it? A copy of your ledger is made first.",
      changes: [], exact: false,
      why_not_exact: "BitcoinTX couldn't work out exactly what changes quickly enough here, so it names every year this can reach.",
    });
    const form = await renderForm({ book: ONE_OF_EACH, respond: (r) => (isWrite(r) && !confirmOf(r) ? refused(byDate) : undefined) });
    await fillDeposit(form, "2024-08-01T12:00:00");
    await form.save();
    expect(within(dialog()).getByText(byDate.detail)).toBeTruthy();
    expect(within(dialog()).getByText(byDate.why_not_exact as string)).toBeTruthy();
    expect(within(dialog()).queryAllByRole("listitem")).toEqual([]);
    await click(form, SAVE_ANYWAY);
    expect(form.writes().map(confirmOf)).toEqual([undefined, byDate.confirm]);
  });

  it("pending changes and Recalculate Ledger's refusal show apart from the save's own", async () => {
    const pendingSell: PastYearChange = {
      ...SELL, id: 30, date: "2023-03-01 09:00", issue: "Stored figures differ from what the current rules give.",
      change: "gain 10.00 -> 12.00.", years: [2023],
    };
    const withFixes = warning([2024, 2025], "p", { changes: [SELL], pending: [pendingSell], recalc_error: "Row 31 spends more than it holds." });
    const form = await renderForm({ book: ONE_OF_EACH, respond: (r) => (isWrite(r) && !confirmOf(r) ? refused(withFixes) : undefined) });
    await fillDeposit(form, "2024-08-01T12:00:00");
    await form.save();

    const pending = within(dialog()).getByRole("group", { name: "These also change, from rules fixed since they were saved" });
    expect(within(pending).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "2023-03-01 09:00 · Sell · 0.25 BTC — gain 10.00 -> 12.00.",
    ]);
    expect(within(pending).getByText("Recalculate Ledger can't run now: Row 31 spends more than it holds.")).toBeTruthy();
    expect(within(dialog()).getAllByRole("listitem")).toHaveLength(2);
  });
});

describe("an edit", () => {
  it("is asked about every time, with no box, and saved with its confirm", async () => {
    const form = await renderForm({ book: ONE_OF_EACH, transaction: usdDeposit, respond: warnsByYear });
    keepAddsQuiet([2024]);
    await form.save();
    expect(form.writes().map((r) => [r.method, r.url])).toEqual([["put", "/transactions/7"]]);
    expect(within(dialog()).queryByRole("checkbox")).toBeNull();
    await click(form, SAVE_ANYWAY);
    const [first, second] = form.writes();
    expect([second.method, second.url, second.params]).toEqual(["put", "/transactions/7", { confirm: warning([2024]).confirm }]);
    expect(second.body).toEqual(first.body);
    expect(form.toasts()).toEqual([{ type: "success", message: "Transaction updated successfully!" }]);
  });
});

describe("a delete", () => {
  // A delete sends no date: the stub names its row's year
  const warnsOnDelete = (r: SentRequest) =>
    (r.method === "delete" && !confirmOf(r) ? refused(warning([2024])) : undefined);

  async function deleteIt(form: RenderedForm) {
    await form.user.click(document.querySelector("#trigger-form-delete") as HTMLButtonElement);
    await form.settle();
  }

  it("asks the browser first, then the warning, and deletes with its confirm", async () => {
    const asked = vi.spyOn(window, "confirm").mockReturnValue(true);
    const form = await renderForm({ book: ONE_OF_EACH, transaction: usdDeposit, respond: warnsOnDelete });
    await deleteIt(form);
    expect(asked).toHaveBeenCalledTimes(1);
    expect(form.writes().map((r) => [r.method, r.url, r.params])).toEqual([["delete", "/transactions/7", undefined]]);
    expect(within(dialog()).queryByRole("checkbox")).toBeNull();
    expect(within(dialog()).queryByRole("button", { name: SAVE_ANYWAY })).toBeNull();

    await click(form, DELETE_ANYWAY);
    expect(form.writes().map((r) => [r.method, r.url, r.params])).toEqual([
      ["delete", "/transactions/7", undefined],
      ["delete", "/transactions/7", { confirm: warning([2024]).confirm }],
    ]);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(form.toasts()).toEqual([{ type: "success", message: "Transaction deleted successfully!" }]);
  });

  it("Cancel deletes nothing and shows no error", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const form = await renderForm({ book: ONE_OF_EACH, transaction: usdDeposit, respond: warnsOnDelete });
    await deleteIt(form);
    await click(form, "Cancel");
    expect(form.writes()).toHaveLength(1);
    expect(form.toasts()).toEqual([]);
  });

  it("refused in the browser's question, nothing is sent", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const form = await renderForm({ book: ONE_OF_EACH, transaction: usdDeposit, respond: warnsOnDelete });
    await deleteIt(form);
    expect(form.writes()).toEqual([]);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
