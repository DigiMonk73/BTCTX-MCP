import { afterEach, describe, expect, it, vi } from "vitest";
import { onAppWindowApi } from "./appWindow";

describe("onAppWindowApi", () => {
  afterEach(() => vi.unstubAllGlobals());

  function stubWindow(pywebview?: { api: PyWebViewAPI }) {
    const target = Object.assign(new EventTarget(), { pywebview });
    vi.stubGlobal("window", target);
    return target;
  }

  const api = { setup_code: async () => "ABCD-EFGH-JKMN" } as unknown as PyWebViewAPI;

  it("calls back at once when the window already has its API", () => {
    stubWindow({ api });
    const seen: PyWebViewAPI[] = [];
    onAppWindowApi((a) => seen.push(a));
    expect(seen).toEqual([api]);
  });

  it("waits for pywebviewready when pywebview adds it after the page loads", () => {
    const win = stubWindow();
    const seen: PyWebViewAPI[] = [];
    const stop = onAppWindowApi((a) => seen.push(a));
    expect(seen).toEqual([]);
    win.pywebview = { api };
    win.dispatchEvent(new Event("pywebviewready"));
    expect(seen).toEqual([api]);
    stop();
    win.dispatchEvent(new Event("pywebviewready"));
    expect(seen).toHaveLength(1);
  });

  it("never calls back in a browser", () => {
    const win = stubWindow();
    const seen: PyWebViewAPI[] = [];
    onAppWindowApi((a) => seen.push(a));
    win.dispatchEvent(new Event("pywebviewready"));
    expect(seen).toEqual([]);
  });
});
