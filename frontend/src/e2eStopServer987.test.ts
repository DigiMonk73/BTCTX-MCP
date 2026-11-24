// The click-through fixtures' teardown (#987): a server's folder is removed
// only once the server has exited, so files it writes while it shuts down
// can't make the removal fail (ENOTEMPTY) or be left behind.
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { stopServer } from "../e2e/stopServer";

const made: string[] = [];

afterEach(() => {
  for (const dir of made.splice(0)) rmSync(dir, { recursive: true, force: true });
});

/** A stand-in server: on SIGTERM it writes into its folder for a moment, then exits. */
function slowToStop(ignoreTerm = false) {
  const dir = mkdtempSync(join(tmpdir(), "btctx-stop-"));
  made.push(dir);
  const script = `
    const fs = require("node:fs"), path = require("node:path");
    const dir = ${JSON.stringify(dir)};
    process.on("SIGTERM", () => {
      if (${ignoreTerm}) return;
      setTimeout(() => {
        fs.mkdirSync(dir, { recursive: true });
        fs.writeFileSync(path.join(dir, "last-words.log"), "shutting down");
        process.exit(0);
      }, 200);
    });
    process.stdout.write("ready");
    setInterval(() => {}, 1000);
  `;
  const proc = spawn(process.execPath, ["-e", script]);
  const ready = new Promise<void>((resolve) => proc.stdout.once("data", () => resolve()));
  return { proc, dir, ready };
}

describe("stopServer", () => {
  it("removes the folder only after the server has exited", async () => {
    const { proc, dir, ready } = slowToStop();
    await ready;
    await stopServer(proc, dir);
    expect(proc.exitCode !== null || proc.signalCode !== null).toBe(true);
    await new Promise((r) => setTimeout(r, 300));
    expect(existsSync(dir)).toBe(false);
  });

  it("a removal that doesn't wait leaves the server's last files behind", async () => {
    // What the fixture did before #987: the signal, then the folder at once.
    const { proc, dir, ready } = slowToStop();
    await ready;
    proc.kill();
    rmSync(dir, { recursive: true, force: true });
    await new Promise((resolve) => proc.once("exit", resolve));
    expect(existsSync(join(dir, "last-words.log"))).toBe(true);
  });

  it("kills a server that doesn't exit within the grace period", async () => {
    const { proc, dir, ready } = slowToStop(true);
    await ready;
    await stopServer(proc, dir, 300);
    expect(proc.signalCode).toBe("SIGKILL");
    expect(existsSync(dir)).toBe(false);
  });

  it("removes the folder of a server that had already exited", async () => {
    const { proc, dir, ready } = slowToStop();
    await ready;
    proc.kill("SIGKILL");
    await new Promise((resolve) => proc.once("exit", resolve));
    await stopServer(proc, dir);
    expect(existsSync(dir)).toBe(false);
  });
});
