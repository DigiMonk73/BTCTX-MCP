// @vitest-environment jsdom
// The import's fields in the order they're needed (#773): with more than one
// exchange, Preview waits for the file's exchange (#707), so the choice comes
// before the file and Preview, and Preview says what it waits for.
import "../../test/setup";
import { fireEvent, render, screen } from "@testing-library/react";
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

  it("say nothing with one exchange, chosen already", () => {
    const view = show(ONE_OF_EACH);
    chooseFile(view);
    expect((view.getByRole("button", { name: "Preview" }) as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByText(WAITING)).toBeNull();
  });
});
