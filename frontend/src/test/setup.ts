// What every mounted test needs (P-1): jest-dom's matchers, and a clean page and
// fresh mocks after each case. A test file using it runs in jsdom
// (`// @vitest-environment jsdom`), so the other tests stay in Node.
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
