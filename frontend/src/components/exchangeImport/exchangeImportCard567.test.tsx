// @vitest-environment jsdom
// B5b (#567), from its fresh review's second round: on the import's card, a
// preview is always the file on screen's, read the way the card now says.
import "../../test/setup";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import api from "../../api";
import { ToastProvider } from "../../contexts/ToastContext";
import RiverImport from "../RiverImport";

const PREVIEW = {
  success: true, total_rows: 1, new_count: 1, matched_count: 0, discrepancy_count: 0, errors: [], warnings: [],
  past_years_dated: [],
  proposals: [{
    row_number: 2, date: "2026-03-05T12:00:00Z", type: "Buy", from_account: "Exchange USD", to_account: "Exchange BTC",
    amount: "0.0003", cost_basis_usd: "25.00", type_choices: [], funding_choices: ["Bank", "Exchange USD"],
    basis_autofilled: false, status: "new",
  }],
};

const COLUMNS = {
  header_row: 1, columns: ["When", "Type", "Coins"], samples: [["2026-03-05 12:00", "Buy", "0.0003"]],
  values: { When: ["2026-03-05 12:00"], Type: ["Buy", "BUY", "buy"], Coins: ["0.0003"] }, looks_like: null,
};

function card() {
  vi.restoreAllMocks();
  // The saved mappings answer a moment after the card shows, as on a slow
  // runner: the picker offers "Another exchange" only once they have (#660)
  const mappings = { data: { mappings: [{ id: "river", name: "River", ready_made: true, help: "", checked: true }] } };
  vi.spyOn(api, "get").mockImplementation(() => new Promise((resolve) => { setTimeout(() => resolve(mappings), 50); }));
  vi.spyOn(api, "post").mockImplementation(async (url) => ({ data: url === "/import/exchange/columns" ? COLUMNS : PREVIEW }));
  render(<ToastProvider><RiverImport onPreviewShown={() => undefined} /></ToastProvider>);
  return userEvent.setup();
}

/** "Another exchange: match its columns", once the picker offers it: only
 * after the saved mappings have loaded (#660). */
async function chooseAnotherExchange(user: ReturnType<typeof userEvent.setup>) {
  const choice = "Another exchange: match its columns";
  await screen.findByRole("option", { name: choice });
  await user.selectOptions(screen.getByLabelText("Exchange file"), choice);
}

/** Another exchange's file, its columns matched by their names, previewed. */
async function matchedAndPreviewed(user: ReturnType<typeof userEvent.setup>) {
  await chooseAnotherExchange(user);
  await user.upload(screen.getByLabelText("Exchange CSV file"), new File(["a"], "x.csv", { type: "text/csv" }));
  await user.selectOptions(await screen.findByLabelText("Date"), "When");
  await user.selectOptions(screen.getByLabelText("Bitcoin amount"), "Coins");
  await user.click(screen.getByRole("button", { name: "Preview" }));
  expect(await screen.findByRole("button", { name: "Import 1 Transaction(s)" })).toBeTruthy();
}

describe("the import's card", () => {
  it("drops a preview when another file is chosen: Import never sends the last file's rows", async () => {
    const user = card();
    await user.upload(screen.getByLabelText("River CSV file"), new File(["a"], "first.csv", { type: "text/csv" }));
    await user.click(screen.getByRole("button", { name: "Preview" }));
    expect(await screen.findByRole("button", { name: "Import 1 Transaction(s)" })).toBeTruthy();
    await user.upload(screen.getByLabelText("River CSV file"), new File(["b"], "second.csv", { type: "text/csv" }));
    expect(screen.queryByRole("button", { name: "Import 1 Transaction(s)" })).toBeNull();
  });

  it("keeps the preview while the mapping's name is typed: the name doesn't change how the file is read", async () => {
    const user = card();
    await matchedAndPreviewed(user);
    await user.type(screen.getByLabelText("Mapping's name"), "Mine");
    expect(screen.getByRole("button", { name: "Import 1 Transaction(s)" })).toBeTruthy();
    await user.selectOptions(screen.getByLabelText("Bitcoin amount"), "");
    expect(screen.queryByRole("button", { name: "Import 1 Transaction(s)" })).toBeNull();
  });

  it("lists a kind word once whatever its case, since the import reads it in any case", async () => {
    const user = card();
    await chooseAnotherExchange(user);
    await user.upload(screen.getByLabelText("Exchange CSV file"), new File(["a"], "x.csv", { type: "text/csv" }));
    expect(await screen.findByLabelText("“Buy” is")).toBeTruthy();
    expect(screen.queryByLabelText("“BUY” is")).toBeNull();
    expect(screen.queryByLabelText("“buy” is")).toBeNull();
  });

  it("holds the file input while a preview is on its way", async () => {
    const user = card();
    let answer: (v: unknown) => void = () => {};
    await user.upload(screen.getByLabelText("River CSV file"), new File(["a"], "first.csv", { type: "text/csv" }));
    vi.spyOn(api, "post").mockImplementation(() => new Promise((resolve) => { answer = resolve; }));
    await user.click(screen.getByRole("button", { name: "Preview" }));
    expect((screen.getByLabelText("River CSV file") as HTMLInputElement).disabled).toBe(true);
    await act(async () => answer({ data: PREVIEW }));
    expect((screen.getByLabelText("River CSV file") as HTMLInputElement).disabled).toBe(false);
  });

  it("sends a kind word's kind for every case of it, so what the screen says is what's read", async () => {
    const user = card();
    vi.spyOn(api, "post").mockImplementation(async (url) => ({ data: url === "/import/exchange/columns"
      ? { ...COLUMNS, values: { ...COLUMNS.values, Type: ["Buy", "BUY", "Sell"] } } : PREVIEW }));
    await chooseAnotherExchange(user);
    await user.upload(screen.getByLabelText("Exchange CSV file"), new File(["a"], "x.csv", { type: "text/csv" }));
    await user.selectOptions(await screen.findByLabelText("Date"), "When");
    await user.selectOptions(screen.getByLabelText("Bitcoin amount"), "Coins");
    await user.selectOptions(screen.getByLabelText("“Buy” is"), "leave out");
    await user.click(screen.getByRole("button", { name: "Preview" }));
    const sent = vi.mocked(api.post).mock.calls.find(([url]) => url === "/import/exchange/preview")!;
    expect(JSON.parse(String((sent[1] as FormData).get("mapping"))).kinds).toEqual({ Buy: "leave out", Sell: "sell" });
  });

  it("holds the file and the exchange file while a mapping is being saved", async () => {
    const user = card();
    await matchedAndPreviewed(user);
    await user.type(screen.getByLabelText("Mapping's name"), "Mine");
    vi.spyOn(api, "post").mockImplementation(() => new Promise(() => {}));
    await user.click(screen.getByRole("button", { name: "Save this mapping" }));
    expect((screen.getByLabelText(/CSV file$/) as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText("Exchange file") as HTMLSelectElement).disabled).toBe(true);
  });
});
