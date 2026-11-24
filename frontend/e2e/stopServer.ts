// Stopping a server the click-through fixtures started (#987). kill() only
// sends the signal: a server still shutting down writes into its folder (the
// database, its log, a safety copy), and a folder removed meanwhile fails
// with ENOTEMPTY, or is left behind with the server's last files. So its exit
// comes first, then the folder. Node only, with no Playwright, so Vitest can
// test it (src/e2eStopServer987.test.ts).
import type { ChildProcess } from "node:child_process";
import { rmSync } from "node:fs";

/** How long a server may take to exit after it's asked, before it's killed. */
export const EXIT_GRACE_MS = 10_000;

/** Stop the server, wait until it has exited, then remove its folder. */
export async function stopServer(proc: ChildProcess, dir: string, graceMs = EXIT_GRACE_MS): Promise<void> {
  await exited(proc, graceMs);
  // A second guard: a file system that is slow to report the folder empty.
  rmSync(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
}

/** The process's exit: asked with SIGTERM, then killed if it hasn't gone within `graceMs`. */
function exited(proc: ChildProcess, graceMs: number): Promise<void> {
  if (proc.exitCode !== null || proc.signalCode !== null) return Promise.resolve();
  return new Promise((resolve) => {
    const killing = setTimeout(() => proc.kill("SIGKILL"), graceMs);
    proc.once("exit", () => {
      clearTimeout(killing);
      resolve();
    });
    proc.kill();
  });
}
