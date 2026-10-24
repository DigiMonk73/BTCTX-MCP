// @vitest-environment jsdom
// B5b (#567): the exchange file the import reads, its mapping and its routes.
import "../test/setup";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { AxiosResponse } from "axios";
import { describe, expect, it, vi } from "vitest";
import api from "../api";
import { MATCH_COLUMNS } from "../components/exchangeImport/ExchangeFilePicker";
import { useExchangeFile } from "./useExchangeFile";

const OWN: OwnMapping = {
  name: "Example Exchange", columns: { date: "When", kind: "Type", btc: "Coins" }, kinds: { Bought: "buy" },
  zone: "UTC", dollars_after_fee: [], send_fee_included: false, decimal_comma: false, day_first: false,
  btc_assets: ["BTC"], done: [],
};
const MAPPINGS: ExchangeMapping[] = [
  { id: "river", name: "River", ready_made: true, help: "", checked: true },
  { id: "kraken", name: "Kraken", ready_made: true, help: "", checked: false },
  { id: "own-1", name: "Example Exchange", ready_made: false, help: "", checked: true, mapping: OWN },
];
const COLUMNS: FileColumnsResponse = {
  header_row: 1, columns: ["Timestamp", "Type", "Amount BTC"], samples: [], values: { Type: ["Buy", "Card"] },
  looks_like: null,
};

function answered<T>(data: T): AxiosResponse<T> {
  return { data, status: 200, statusText: "OK", headers: {}, config: {} as AxiosResponse["config"] };
}

const toast = { error: vi.fn(), success: vi.fn() };
const FILE = new File(["Timestamp,Type,Amount BTC\n"], "f.csv", { type: "text/csv" });

function setUp() {
  vi.restoreAllMocks();
  vi.spyOn(api, "get").mockResolvedValue(answered({ mappings: MAPPINGS }));
  return vi.spyOn(api, "post").mockImplementation(async (url) => {
    if (url === "/import/exchange/columns") return answered(COLUMNS);
    if (url === "/import/exchange/mappings") return answered({ ...MAPPINGS[2], id: "own-2" });
    throw new Error(`unexpected ${url}`);
  });
}

describe("useExchangeFile", () => {
  it("reads River's file by River's own routes, as before", async () => {
    setUp();
    const { result } = renderHook(() => useExchangeFile(toast));
    await waitFor(() => expect(result.current.mappings).toEqual(MAPPINGS));
    expect(result.current.urls).toEqual({ preview: "/import/river/preview", execute: "/import/river/execute" });
    const form = new FormData();
    result.current.addMapping(form);
    expect(form.has("mapping_id") || form.has("mapping")).toBe(false);
    expect(result.current.name).toBe("River");
  });

  it("reads a ready-made mapping's file by its id on the exchange routes", async () => {
    setUp();
    const { result } = renderHook(() => useExchangeFile(toast));
    await waitFor(() => expect(result.current.mappings).toBeDefined());
    await act(async () => result.current.choose("kraken", null));
    expect(result.current.urls).toEqual({ preview: "/import/exchange/preview", execute: "/import/exchange/execute" });
    const form = new FormData();
    result.current.addMapping(form);
    expect(form.get("mapping_id")).toBe("kraken");
    expect(result.current.matching).toBe(false);
  });

  it("matches another exchange's columns, guessing what their names say, and sends the draft", async () => {
    setUp();
    const { result } = renderHook(() => useExchangeFile(toast));
    await waitFor(() => expect(result.current.mappings).toBeDefined());
    await act(async () => result.current.choose(MATCH_COLUMNS, FILE));
    expect(result.current.columns).toEqual(COLUMNS);
    expect(result.current.draft.columns).toMatchObject({ date: "Timestamp", kind: "Type", btc: "Amount BTC" });
    expect(result.current.draft.kinds).toEqual({ Buy: "buy" });
    expect(result.current.ready).toBe(true);
    const form = new FormData();
    result.current.addMapping(form);
    expect(JSON.parse(String(form.get("mapping")))).toMatchObject({ columns: { date: "Timestamp" }, kinds: { Buy: "buy" } });
  });

  it("opens a saved mapping in the matcher, and saving a new one chooses it", async () => {
    const posted = setUp();
    const { result } = renderHook(() => useExchangeFile(toast));
    await waitFor(() => expect(result.current.mappings).toBeDefined());
    await act(async () => result.current.choose("own-1", FILE));
    expect(result.current.matching).toBe(true);
    expect(result.current.draft.name).toBe("Example Exchange");
    await act(async () => result.current.choose(MATCH_COLUMNS, FILE));
    act(() => result.current.setDraft({ ...result.current.draft, name: "Another one" }));
    await act(async () => result.current.save());
    expect(posted).toHaveBeenCalledWith("/import/exchange/mappings", expect.objectContaining({ name: "Another one" }));
    expect(result.current.chosenId).toBe("own-2");
  });

  it("can't preview a matched file until it says what each column holds", async () => {
    setUp();
    vi.spyOn(api, "post").mockResolvedValue(answered({ ...COLUMNS, columns: ["When", "Coins"], values: {} }));
    const { result } = renderHook(() => useExchangeFile(toast));
    await waitFor(() => expect(result.current.mappings).toBeDefined());
    await act(async () => result.current.choose(MATCH_COLUMNS, FILE));
    expect(result.current.ready).toBe(false);
  });
});
