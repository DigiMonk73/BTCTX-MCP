// Every request says which page sent it (2.0 spec 5.13, #351): the server
// refuses a browser's change from a page older than 2.0, which would save a
// Buy or Sell into the first exchange (backend/security_headers.py).
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
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

/** Every source file under `dir`, tests left out. */
function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === "test" ? [] : sources(path);
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : [];
  });
}

describe("no request goes around api.ts", () => {
  const src = fileURLToPath(new URL(".", import.meta.url));
  // A request the page makes without its version: the server refuses its change
  const AROUND = /\bfetch\(|\baxios(\.(get|post|put|patch|delete|request|create)\b|\()|XMLHttpRequest|sendBeacon/;

  it("finds the page's source, and what goes around", () => {
    expect(sources(src).length).toBeGreaterThan(100);
    expect(['fetch("/api/x")', "axios.post(url, body)", 'axios({ method: "post" })', "new XMLHttpRequest()"]
      .every((l) => AROUND.test(l))).toBe(true);
    expect(["api.post(url, body)", "await api.get(`/x`)", "prefetch(x)"].some((l) => AROUND.test(l))).toBe(false);
  });

  it("makes every request through api.ts's two", () => {
    const found = sources(src)
      .filter((file) => !file.endsWith(join("src", "api.ts")))
      .flatMap((file) => readFileSync(file, "utf8").split("\n")
        .map((line, i) => [file.slice(src.length), i + 1, line] as const)
        .filter(([, , line]) => AROUND.test(line)));
    expect(found).toEqual([]);
  });
});
