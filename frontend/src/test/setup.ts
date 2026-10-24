// What every mounted test needs: a clean page and fresh stubs after each
// case. A test file importing it runs in jsdom (`// @vitest-environment
// jsdom` at its top), so the other tests stay in Node.
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
