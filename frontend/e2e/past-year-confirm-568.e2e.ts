// The fixtures confirm 2.0's past-year warning (plan 5.8, 5.15): a write the server answers with a 409 that
// gives a fingerprint (`confirm`) is sent again, once, with ?confirm=<fingerprint> and the same body, as the
// scripts do (backend/tests/test_confirm_helpers.py). Against a stand-in server, not BitcoinTX: until the
// warning is built (B6b), no save answers so.
import http from "node:http";
import type net from "node:net";
import { test, expect } from "@playwright/test";
import { createTx, sendConfirmed } from "./fixtures";

const FINGERPRINT = "5f2d0c9b1e7a4c38a6d2b9e0f1c3a5d7e9b2c4d6f8a0b1c3d5e7f9a2b4c6d8e0";
const ASKS = {
  status: 409,
  body: {
    detail: "This changes the figures of tax year 2024, which you may already have filed.",
    years: [2024], changes: [], pending: [], confirm: FINGERPRINT,
  },
};
const SAVED = { status: 200, body: { id: 7 } };

type Answer = { status: number; body: unknown };
type Seen = { method: string; url: string; body: string };

/** A server that gives the next of `answers` to each request, keeping what it was sent. */
async function standIn(answers: Answer[]) {
  const seen: Seen[] = [];
  const server = http.createServer((req, res) => {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => {
      seen.push({ method: req.method ?? "", url: req.url ?? "", body });
      const answer = answers.shift() ?? { status: 500, body: "no answer left" };
      res.writeHead(answer.status, { "Content-Type": "application/json" });
      res.end(typeof answer.body === "string" ? answer.body : JSON.stringify(answer.body));
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const url = `http://127.0.0.1:${(server.address() as net.AddressInfo).port}`;
  return { url, seen, close: () => new Promise((resolve) => server.close(resolve)) };
}

test("createTx sends a 409 that asks again, once, with its fingerprint", async ({ playwright }) => {
  const server = await standIn([ASKS, SAVED]);
  const api = await playwright.request.newContext({ baseURL: server.url });
  const row = { type: "Buy", timestamp: "2024-01-10T12:00:00Z", amount: "0.2" };
  expect(await createTx(api, row)).toEqual({ id: 7 });
  expect(server.seen.map(({ method, url }) => `${method} ${url}`)).toEqual([
    "POST /api/transactions",
    `POST /api/transactions?confirm=${FINGERPRINT}`,
  ]);
  expect(server.seen.map(({ body }) => JSON.parse(body))).toEqual([row, row]);
  await api.dispose();
  await server.close();
});

test("a write is confirmed once, and only for a 409 that asks", async ({ playwright }) => {
  const again = { ...ASKS, body: { ...ASKS.body, confirm: "0".repeat(64) } };
  const deleteAll = { status: 409, body: { detail: "To go ahead, confirm with DELETE.", transactions: 3 } };
  const cases: Array<{ answers: Answer[]; status: number; sent: number }> = [
    { answers: [ASKS, again], status: 409, sent: 2 },
    { answers: [deleteAll], status: 409, sent: 1 },
    { answers: [{ status: 409, body: "Conflict" }], status: 409, sent: 1 },
    { answers: [{ status: 400, body: { detail: "Amount must be positive.", confirm: FINGERPRINT } }], status: 400, sent: 1 },
    { answers: [SAVED], status: 200, sent: 1 },
  ];
  for (const { answers, status, sent } of cases) {
    const server = await standIn([...answers]);
    const api = await playwright.request.newContext({ baseURL: server.url });
    const r = await sendConfirmed((params) => api.put("/api/transactions/7", { data: { amount: "0.3" }, params }));
    expect([r.status(), server.seen.length], JSON.stringify(answers)).toEqual([status, sent]);
    await api.dispose();
    await server.close();
  }
});
