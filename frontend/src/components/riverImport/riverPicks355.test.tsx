// @vitest-environment jsdom
// River's file and its exchange and wallet (#355): the preview on screen and
// the pickers always say the same, whatever happens to the account book.
import "../../test/setup";
import { act, fireEvent, render, screen } from "@testing-library/react";
import type { AxiosResponse } from "axios";
import { describe, expect, it, vi } from "vitest";
import api from "../../api";
import { ToastContext } from "../../contexts/useToast";
import type { ToastContextValue } from "../../contexts/ToastContext";
import { MANY } from "../../test/books";
import RiverImport from "../RiverImport";

const toast = { error: vi.fn(), success: vi.fn() } as unknown as ToastContextValue;

const PREVIEW = {
  success: true, total_rows: 1, new_count: 1, matched_count: 0, discrepancy_count: 0, errors: [], warnings: [],
  proposals: [{
    row_number: 2, date: "2026-02-15T10:00:00Z", type: "Transfer", amount: "0.001", from_account: "River BTC",
    to_account: "Sparrow", status: "new", type_choices: ["Transfer", "Withdrawal"], funding_choices: [],
    basis_autofilled: false,
  }],
} as unknown as RiverPreviewResponse;

function answered<T>(data: T): AxiosResponse<T> {
  return { data, status: 200, statusText: "OK", headers: {}, config: {} as AxiosResponse["config"] };
}

const River: React.FC<{ book?: AccountBook }> = ({ book }) => (
  <ToastContext.Provider value={toast}><RiverImport onPreviewShown={() => {}} book={book} /></ToastContext.Provider>
);

async function previewFile(view: ReturnType<typeof render>) {
  const file = new File(["Date,Sent Amount\n"], "river.csv", { type: "text/csv" });
  fireEvent.change(view.getByLabelText("River CSV file"), { target: { files: [file] } });
  await act(async () => {
    fireEvent.click(view.getByRole("button", { name: "Preview" }));
  });
}

describe("River's preview and its pickers", () => {
  it("keep the preview when the book can't be read again (a failed reload says nothing about the accounts)", async () => {
    vi.spyOn(api, "post").mockResolvedValue(answered(PREVIEW));
    const view = render(<River book={MANY} />);
    await previewFile(view);
    expect(screen.getByText("1 rows in file")).toBeTruthy();
    view.rerender(<River book={undefined} />);
    expect(screen.getByText("1 rows in file")).toBeTruthy();
    expect(screen.queryByText(/preview the file again/)).toBeNull();
  });

  it("drop a preview whose exchange is gone from the book, and say so", async () => {
    vi.spyOn(api, "post").mockResolvedValue(answered(PREVIEW));
    const view = render(<River book={MANY} />);
    fireEvent.change(view.getByLabelText("Exchange"), { target: { value: "103" } });
    await previewFile(view);
    expect(screen.getByText("1 rows in file")).toBeTruthy();
    view.rerender(<River book={MANY.filter((a) => a.exchange_id !== 2)} />);
    expect(screen.queryByText("1 rows in file")).toBeNull();
    expect(screen.getByText("The preview was made with another exchange or wallet: preview the file again.")).toBeTruthy();
  });

  it("show a new pick while its preview is on its way, and the old one back if it fails", async () => {
    let fail: (reason: unknown) => void = () => {};
    vi.spyOn(api, "post")
      .mockResolvedValueOnce(answered(PREVIEW))
      .mockImplementationOnce(() => new Promise((_, reject) => { fail = reject; }));
    const view = render(<River book={MANY} />);
    await previewFile(view);
    const wallet = view.getByLabelText("Wallet for sends and receives") as HTMLSelectElement;
    expect(wallet.value).toBe("2");
    fireEvent.change(wallet, { target: { value: "100" } });
    expect(wallet.value).toBe("100");
    await act(async () => fail(new Error("down")));
    expect(wallet.value).toBe("2");
    expect(toast.error).toHaveBeenCalled();
  });
});
