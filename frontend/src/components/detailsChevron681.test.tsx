// @vitest-environment jsdom
// The two boxes that open with a native <details> take the app's one
// chevron (#681, #674): Settings' "Set it up yourself" and the error page's
// "Error details" (a development build's). How the browser's own marker is
// hidden, and the chevron turned, is the click-through's (settings.e2e.ts).
import "../test/setup";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import api from "../api";
import { ToastProvider } from "../contexts/ToastContext";
import ConnectAiSetting from "./ConnectAiSetting";
import ErrorBoundary from "./ErrorBoundary";

const SERVER = { mode: "server", on: false, has_key: false, key_file: null };

/** The summary holding `words`: its class, the chevron in it, and whether its box is open. */
function summaryOf(words: string) {
  const summary = screen.getByText(words).closest("summary");
  if (!summary) throw new Error(`no summary holds ${words}`);
  return { summary, chevron: summary.querySelector("svg.chevron"), open: () => summary.closest("details")?.open };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe("a native <details> opens with the app's chevron", () => {
  it("Settings → Connect an AI Assistant → Set it up yourself", async () => {
    vi.spyOn(api, "get").mockImplementation(async (url: string) => {
      if (url === "/settings/ai-access") return { data: SERVER };
      if (url === "/health") return { data: { version: "2.0.0-alpha.2" } };
      throw new Error(`not in this test: ${url}`);
    });
    render(<ToastProvider><ConnectAiSetting /></ToastProvider>);
    const { summary, chevron, open } = summaryOf("Set it up yourself");
    expect(summary.classList.contains("chevron-toggle")).toBe(true);
    expect(chevron).not.toBeNull();
    expect(open()).toBe(false);
    await userEvent.setup().click(summary);
    expect(open()).toBe(true);
  });

  it("the error page's Error details", () => {
    vi.stubEnv("NODE_ENV", "development"); // only a development build shows them
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const Broken = () => {
      throw new Error("broken on purpose");
    };
    render(<ErrorBoundary><Broken /></ErrorBoundary>);
    const { summary, chevron } = summaryOf("Error details");
    expect(summary.classList.contains("chevron-toggle")).toBe(true);
    expect(chevron).not.toBeNull();
  });
});
