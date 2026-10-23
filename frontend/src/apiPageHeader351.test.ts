// Every request says which page sent it (2.0 spec 5.13, #351): the server
// refuses a browser's change from a page older than 2.0, which would save a
// Buy or Sell into the first exchange (backend/security_headers.py).
import { readFileSync } from "node:fs";
import axios, { type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { afterEach, describe, expect, it } from "vitest";
import api, { downloadPdfWithAxios } from "./api";

// The repository's VERSION, read here rather than through the build's value
const VERSION = readFileSync(new URL("../../VERSION", import.meta.url), "utf8").trim();

const sent: InternalAxiosRequestConfig[] = [];

/** Records each request and answers it at once; nothing leaves the test. */
const recorder: AxiosAdapter = async (config) => {
  sent.push(config);
  return { data: new Blob(), status: 200, statusText: "OK", headers: {}, config };
};

const pageOf = (config: InternalAxiosRequestConfig) => config.headers?.get?.("X-BitcoinTX-Page") ?? undefined;

const instanceAdapter = api.defaults.adapter;
const bareAdapter = axios.defaults.adapter;

afterEach(() => {
  api.defaults.adapter = instanceAdapter;
  axios.defaults.adapter = bareAdapter;
  sent.length = 0;
});

describe("the page's version on every request", () => {
  it("is the repository's VERSION", () => {
    expect(VERSION).toMatch(/^\d+\.\d+\.\d+/);
  });

  it("goes with a GET, POST, PUT and DELETE through api", async () => {
    api.defaults.adapter = recorder;
    await api.get("/transactions");
    await api.post("/transactions", { type: "Deposit" });
    await api.put("/transactions/7", { type: "Deposit" });
    await api.delete("/transactions/7");
    expect(sent.map((config) => [config.method, pageOf(config)])).toEqual([
      ["get", VERSION],
      ["post", VERSION],
      ["put", VERSION],
      ["delete", VERSION],
    ]);
  });

  it("goes with a PDF download, which uses the bare axios", async () => {
    axios.defaults.adapter = recorder;
    await downloadPdfWithAxios("/api/reports/complete_tax_report?year=2025");
    expect(sent).toHaveLength(1);
    expect(pageOf(sent[0])).toBe(VERSION);
  });
});
