// @vitest-environment jsdom
// A file's exchange with more than one (#707, the owner's decision of
// 2026-10-25): none is taken unasked, but the one the file is named for; each
// file is asked again; and a line for whoever recorded an exchange's trades
// in another before 2.0, as 1.x's guide said.
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
const POOLED = /Recorded this exchange's trades in another one before 2\.0\?/;

const PREVIEW = {
  success: true, total_rows: 1, new_count: 1, matched_count: 0, discrepancy_count: 0, errors: [], warnings: [],
  proposals: [{
    row_number: 2, date: "2026-02-15T10:00:00Z", type: "Buy", amount: "0.001", from_account: "Bank",
    to_account: "Kraken BTC", status: "new", type_choices: ["Buy"], funding_choices: ["Bank", "Kraken USD"],
    basis_autofilled: false,
  }],
} as unknown as RiverPreviewResponse;

function answered<T>(data: T): AxiosResponse<T> {
  return { data, status: 200, statusText: "OK", headers: {}, config: {} as AxiosResponse["config"] };
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "get").mockResolvedValue(answered({ mappings: [
    { id: "river", name: "River", ready_made: true, help: "", checked: true },
  ] }));
});

function show(book: AccountBook) {
  return render(
    <ToastContext.Provider value={toast}><RiverImport onPreviewShown={() => {}} book={book} /></ToastContext.Provider>,
  );
}

function chooseFile(view: ReturnType<typeof render>, name = "river.csv") {
  const file = new File(["Date,Sent Amount\n"], name, { type: "text/csv" });
  fireEvent.change(view.getByLabelText("River CSV file"), { target: { files: [file] } });
}

const exchangePicker = (view: ReturnType<typeof render>) => view.getByLabelText("Exchange") as HTMLSelectElement;
const previewButton = (view: ReturnType<typeof render>) =>
  view.getByRole("button", { name: "Preview" }) as HTMLButtonElement;

describe("a file's exchange, with more than one", () => {
  it("is never taken unasked: Preview waits for the pick, and the preview is made with it", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue(answered(PREVIEW));
    const view = show(TWO_EXCHANGES);
    chooseFile(view);
    expect(exchangePicker(view).value).toBe("");
    expect(screen.getByRole("option", { name: "Choose an exchange" })).toBeTruthy();
    expect(previewButton(view).disabled).toBe(true);
    fireEvent.change(exchangePicker(view), { target: { value: "103" } });
    expect(previewButton(view).disabled).toBe(false);
    await act(async () => {
      fireEvent.click(previewButton(view));
    });
    expect((post.mock.calls[0][1] as FormData).get("exchange_account_id")).toBe("103");
  });

  it("is the one the file is named for, when there's one", () => {
    const view = show(MANY); // its first exchange is called River
    chooseFile(view);
    expect(exchangePicker(view).value).toBe("4");
    expect(previewButton(view).disabled).toBe(false);
  });

  it("is asked again for another file once a preview was made with it", async () => {
    vi.spyOn(api, "post").mockResolvedValue(answered(PREVIEW));
    const view = show(TWO_EXCHANGES);
    chooseFile(view);
    fireEvent.change(exchangePicker(view), { target: { value: "103" } });
    await act(async () => {
      fireEvent.click(previewButton(view));
    });
    expect(exchangePicker(view).value).toBe("103");
    chooseFile(view, "another.csv");
    expect(exchangePicker(view).value).toBe("");
    expect(previewButton(view).disabled).toBe(true);
  });

  it("comes with a line for whoever recorded its trades in another exchange before 2.0", () => {
    show(TWO_EXCHANGES);
    expect(screen.getByRole("note").textContent).toMatch(POOLED);
  });
});

describe("a file's exchange, with one", () => {
  it("is taken, as before, with no line about another exchange", () => {
    const view = show(ONE_OF_EACH);
    chooseFile(view);
    expect(view.queryByLabelText("Exchange")).toBeNull();
    expect(previewButton(view).disabled).toBe(false);
    expect(screen.queryByText(POOLED)).toBeNull();
  });
});
