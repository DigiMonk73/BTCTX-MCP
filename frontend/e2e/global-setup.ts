import { existsSync } from "node:fs";
import { execSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// The backend serves frontend/dist, so test what the source says now: build
// it first. E2E_SKIP_BUILD=1 reuses an existing build (CI downloads one).
export default function globalSetup() {
  const root = path.resolve(__dirname, "..");
  const built = existsSync(path.join(root, "dist", "index.html"));
  if (!built || !process.env.E2E_SKIP_BUILD) {
    execSync("npx vite build --logLevel warn", { cwd: root, stdio: "inherit" });
  }
}
