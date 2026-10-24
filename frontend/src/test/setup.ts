// What every mounted test needs: a clean page and fresh stubs after each
// case. A test file importing it runs in jsdom (`// @vitest-environment
// jsdom` at its top), so the other tests stay in Node.
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Tests never touch the network (AGENTS.md, #683): a request no test stubbed
// would go from jsdom to its page's origin. It's refused unsent, and the test
// that made it fails afterwards, since the app's own code catches a failed
// request and the test could pass all the same.
const unstubbed: string[] = [];
XMLHttpRequest.prototype.open = function (method: string, url: string | URL) {
  unstubbed.push(`${method} ${url}`);
  throw new Error(`A test sent ${method} ${url} without stubbing it`);
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  const sent = unstubbed.splice(0);
  if (sent.length > 0) throw new Error(`Requests no test stubbed: ${sent.join(", ")}`);
});
