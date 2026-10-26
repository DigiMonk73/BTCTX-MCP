// @vitest-environment jsdom
// The import's fields in the order they're needed (#773): with more than one
// exchange, Preview waits for the file's exchange (#707), so the choice comes
// before the file and Preview, and Preview says what it waits for.
import "../../test/setup";
import { act, fireEvent, render, screen } from "@testing-library/react";
import type { AxiosResponse } from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";
import api from "../../api";
import { ToastContext } from "../../contexts/useToast";
import type { ToastContextValue } from "../../contexts/ToastContext";
import { MANY, ONE_OF_EACH } from "../../test/books";
import RiverImport from "../RiverImport";

const toast = { error: vi.fn(), success: vi.fn() } as unknown as ToastContextValue;

// 1.x's Exchange and an exchange added in 2.0: neither is River's
const TWO_EXCHANGES = [...ONE_OF_EACH, ...MANY.filter((a) => a.exchange === "Kraken")];
const WAITING = "Choose the exchange first.";

function answered<T>(data: T): AxiosResponse<T> {
  return { data, status: 200, statusText: "OK", headers: {}, config: {} as AxiosResponse["config"] };
}

const PREVIEW = {
  success: true, total_rows: 1, new_count: 1, matched_count: 0, discrepancy_count: 0, errors: [], warnings: [],
  proposals: [{
    row_number: 2, date: "2026-02-15T10:00:00Z", type: "Buy", amount: "0.001", from_account: "Checking",
    to_account: "River BTC", status: "new", type_choices: ["Buy"], funding_choices: ["Checking", "River USD"],
    basis_autofilled: false,
  }],
} as unknown as RiverPreviewResponse;

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "get").mockResolvedValue(answered({ mappings: [
    { id: "river", name: "River", ready_made: true, help: "", checked: true },
    { id: "kraken", name: "Kraken", ready_made: true, help: "", checked: false },
  ] }));
});

function show(book: AccountBook) {
  return render(
    <ToastContext.Provider value={toast}><RiverImport onPreviewShown={() => {}} book={book} /></ToastContext.Provider>,
  );
}

function chooseFile(view: ReturnType<typeof render>) {
  const file = new File(["Date,Sent Amount\n"], "river.csv", { type: "text/csv" });
  fireEvent.change(view.getByLabelText("River CSV file"), { target: { files: [file] } });
}

const before = (a: Element, b: Element) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);

describe("the import's fields", () => {
  it("ask for the exchange and the wallet before the file and Preview", () => {
    const view = show(MANY);
    const preview = view.getByRole("button", { name: "Preview" });
    for (const label of ["Exchange", "Wallet for sends and receives", "River CSV file"]) {
      expect(before(view.getByLabelText(label), preview)).toBe(true);
    }
    expect(before(view.getByLabelText("Exchange"), view.getByLabelText("River CSV file"))).toBe(true);
  });

  it("say by Preview what it waits for, until the exchange is chosen", () => {
    const view = show(TWO_EXCHANGES);
    expect(screen.getByText(WAITING)).toBeTruthy(); // asked first, before the file
    chooseFile(view);
    const preview = view.getByRole("button", { name: "Preview" }) as HTMLButtonElement;
    expect(preview.disabled).toBe(true);
    expect(preview.getAttribute("aria-describedby")).toBe(screen.getByText(WAITING).id);
    fireEvent.change(view.getByLabelText("Exchange"), { target: { value: "103" } });
    expect(preview.disabled).toBe(false);
    expect(screen.queryByText(WAITING)).toBeNull();
    expect(preview.getAttribute("aria-describedby")).toBeNull();
  });

  it("keep an exchange picked for the next file before it's chosen (above it), with no preview made", () => {
    const view = show(TWO_EXCHANGES);
    chooseFile(view);
    fireEvent.change(view.getByLabelText("Exchange"), { target: { value: "103" } });
    chooseFile(view);
    expect((view.getByLabelText("Exchange") as HTMLSelectElement).value).toBe("103");
    expect((view.getByRole("button", { name: "Preview" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("ask the exchange again for another exchange's file once a preview was made (the re-check's finding)", async () => {
    vi.spyOn(api, "post").mockResolvedValue(answered(PREVIEW));
    const view = show(MANY); // River's file: River chosen by its name
    chooseFile(view);
    await act(async () => {
      fireEvent.click(view.getByRole("button", { name: "Preview" }));
    });
    expect((view.getByLabelText("Exchange") as HTMLSelectElement).value).toBe("4");
    await act(async () => {
      fireEvent.change(await view.findByLabelText("Exchange file"), { target: { value: "kraken" } });
    });
    fireEvent.change(view.getByLabelText("Kraken CSV file"),
      { target: { files: [new File(["Time,Type\n"], "kraken.csv", { type: "text/csv" })] } });
    // Kraken's file by its name, as a fresh start would choose, never River's carried over
    expect((view.getByLabelText("Exchange") as HTMLSelectElement).value).toBe("103");
  });

  it("say nothing with one exchange, chosen already", () => {
    const view = show(ONE_OF_EACH);
    chooseFile(view);
    expect((view.getByRole("button", { name: "Preview" }) as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByText(WAITING)).toBeNull();
  });
});
