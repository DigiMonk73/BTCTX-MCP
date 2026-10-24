// @vitest-environment jsdom
// B5b (#567): which exchange's file it is: a ready-made mapping, one of the
// owner's own, or another exchange's, whose columns the owner matches.
import "../../test/setup";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MATCH_COLUMNS } from "../../utils/exchangeMapping";
import ExchangeFilePicker from "./ExchangeFilePicker";

const MAPPINGS: ExchangeMapping[] = [
  { id: "river", name: "River", ready_made: true, help: "river.com → Taxes & Documents → Bitcoin activity (CSV).", checked: true },
  { id: "kraken", name: "Kraken", ready_made: true, help: "kraken.com → Documents → Export → Ledgers.", checked: false },
  { id: "own-1", name: "Example Exchange", ready_made: false, help: "", checked: true },
];

describe("ExchangeFilePicker", () => {
  it("lists the exchanges, then the owner's mappings, then another exchange's file", () => {
    render(<ExchangeFilePicker mappings={MAPPINGS} value="river" disabled={false} onChange={() => {}} />);
    const options = Array.from((screen.getByLabelText("Exchange file") as HTMLSelectElement).options).map((o) => o.text);
    expect(options).toEqual(["River", "Kraken", "Example Exchange", "Another exchange: match its columns"]);
  });

  it("says where to download the chosen exchange's file", () => {
    const view = render(<ExchangeFilePicker mappings={MAPPINGS} value="kraken" disabled={false} onChange={() => {}} />);
    expect(screen.getByText("kraken.com → Documents → Export → Ledgers.")).toBeTruthy();
    view.rerender(<ExchangeFilePicker mappings={MAPPINGS} value={MATCH_COLUMNS} disabled={false} onChange={() => {}} />);
    expect(screen.getByText(/then say which of its columns holds what/)).toBeTruthy();
  });

  it("says to check the preview of a mapping no real export has been checked against", () => {
    const view = render(<ExchangeFilePicker mappings={MAPPINGS} value="kraken" disabled={false} onChange={() => {}} />);
    expect(screen.getByText(/not yet checked against a real one/)).toBeTruthy();
    view.rerender(<ExchangeFilePicker mappings={MAPPINGS} value="river" disabled={false} onChange={() => {}} />);
    expect(screen.queryByText(/not yet checked against a real one/)).toBeNull();
  });

  it("tells which one was chosen", () => {
    const chosen = vi.fn();
    render(<ExchangeFilePicker mappings={MAPPINGS} value="river" disabled={false} onChange={chosen} />);
    fireEvent.change(screen.getByLabelText("Exchange file"), { target: { value: "own-1" } });
    expect(chosen).toHaveBeenCalledWith("own-1");
  });

  it("offers River until the list is read", () => {
    render(<ExchangeFilePicker mappings={undefined} value="river" disabled={false} onChange={() => {}} />);
    const options = Array.from((screen.getByLabelText("Exchange file") as HTMLSelectElement).options).map((o) => o.text);
    expect(options).toEqual(["River"]);
  });
});
