// @vitest-environment jsdom
// A signed-in page whose session ended (another browser changed the password
// or logged it out: SECURITY-RULES.md, "Sessions") goes to the sign-in page
// at its next request, rather than show load errors (#919). The answers that
// are a page's own stay with it: the sign-in's wrong password,
// PrivateRoute's own check, the signed-out pages', a 403.
import "./test/setup";
import axios from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";
import api, { downloadPdfWithAxios, holdSignIn } from "./api";
import { NOT_AUTHENTICATED, answers, pageAt } from "./test/endedSession";

const instanceAdapter = api.defaults.adapter;
const bareAdapter = axios.defaults.adapter;

afterEach(() => {
  api.defaults.adapter = instanceAdapter;
  axios.defaults.adapter = bareAdapter;
  vi.unstubAllGlobals();
});

const ENDED = answers(() => NOT_AUTHENTICATED);
const AS_401 = { response: { status: 401 } };

describe("a 401 on a signed-in page: its session ended", () => {
  it("goes to the sign-in page, and still reaches the page that asked", async () => {
    const sentTo = pageAt("/transactions");
    api.defaults.adapter = ENDED;
    await expect(api.get("/accounts/")).rejects.toMatchObject(AS_401);
    expect(sentTo).toEqual(["/login"]);
  });

  it("from a PDF download too, which goes through the bare axios", async () => {
    const sentTo = pageAt("/reports");
    axios.defaults.adapter = ENDED;
    await expect(downloadPdfWithAxios("/api/reports/complete_tax_report?year=2025")).rejects.toMatchObject(AS_401);
    expect(sentTo).toEqual(["/login"]);
  });
});

describe("answers that stay with the page that asked", () => {
  it("the sign-in's own 401, a wrong username or password, wherever it's sent from", async () => {
    for (const path of ["/login", "/dashboard"]) {
      const sentTo = pageAt(path);
      api.defaults.adapter = answers(() => [401, { detail: "Invalid username or password." }]);
      await expect(api.post("/login", { username: "someone", password: "wrong" })).rejects.toMatchObject(AS_401);
      expect(sentTo).toEqual([]);
    }
  });

  it("PrivateRoute's /protected, which goes to the sign-in page itself", async () => {
    const sentTo = pageAt("/dashboard");
    api.defaults.adapter = ENDED;
    await expect(api.get("/protected")).rejects.toMatchObject(AS_401);
    expect(sentTo).toEqual([]);
  });

  it("any 401 on the signed-out pages: the sign-in, logging out, Create account", async () => {
    // The sign-in page sent to itself would load again, and again
    for (const path of ["/login", "/logout", "/register"]) {
      const sentTo = pageAt(path);
      api.defaults.adapter = ENDED;
      await expect(api.get("/users/")).rejects.toMatchObject(AS_401);
      expect(sentTo).toEqual([]);
    }
  });

  it("a 403: a wrong current password stays on the form", async () => {
    const sentTo = pageAt("/settings");
    api.defaults.adapter = answers(() => [403, { detail: "Current password is incorrect." }]);
    await expect(api.patch("/users/1", { password: "a-new-password-1234", current_password: "wrong" }))
      .rejects.toMatchObject({ response: { status: 403 } });
    expect(sentTo).toEqual([]);
  });
});

describe("a hold on the sign-in page, while a restore's notice shows", () => {
  const poll = () => expect(api.get("/bitcoin/price/status")).rejects.toMatchObject(AS_401);

  it("keeps the page while held, and nothing once released, however often released", async () => {
    const sentTo = pageAt("/settings");
    api.defaults.adapter = ENDED;
    const release = holdSignIn();
    const another = holdSignIn();
    await poll();
    release();
    release(); // a second release changes nothing: `another` still holds
    await poll();
    expect(sentTo).toEqual([]);
    another();
    await poll();
    expect(sentTo).toEqual(["/login"]);
  });
});
