import { describe, expect, it } from "vitest";
import { requestLogout, takeLogoutRequest } from "./logoutRequest";

describe("a request to log out (#583's re-check)", () => {
  it("is taken once, by its own token", () => {
    const token = requestLogout();
    expect(takeLogoutRequest(token)).toBe(true);
    expect(takeLogoutRequest(token)).toBe(false); // Back or Forward onto /logout
  });

  it("is never taken without a token: a link from another site, a typed address", () => {
    requestLogout();
    for (const token of [undefined, null, true, "1", {}]) expect(takeLogoutRequest(token)).toBe(false);
  });

  it("an older token no longer counts once a newer one is asked for", () => {
    const old = requestLogout();
    const latest = requestLogout();
    expect(takeLogoutRequest(old)).toBe(false);
    expect(takeLogoutRequest(latest)).toBe(true);
  });
});
