#!/usr/bin/env python3
"""
Run the checked-out code in a browser, on a throwaway database.

    python scripts/preview.py [PORT]        # default 8777; `make preview`

Builds frontend/, creates a fresh database in a temp folder, gives it the
smoke test's login (SMOKE_USER / SMOKE_PASSWORD in scripts/smoke_test.py),
and serves it on 127.0.0.1 with the smoke test's stubbed offline prices.
Your real database and the network are never touched. Ctrl-C stops it and
deletes the temp folder. `.claude/launch.json` starts this for Claude's
browser preview.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import smoke_test  # noqa: E402


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8777
    subprocess.run(["npx", "vite", "build", "--logLevel", "warn"], cwd=ROOT / "frontend", check=True)

    workdir = tempfile.mkdtemp(prefix="btctx-preview-")
    db_path = os.path.join(workdir, "btctx.db")
    try:
        subprocess.run(
            [sys.executable, "-m", "backend.cli", "set-password",
             "--username", smoke_test.SMOKE_USER, "--password-stdin"],
            input=smoke_test.SMOKE_PASSWORD + "\n", text=True, cwd=ROOT,
            env={**os.environ, "DATABASE_FILE": db_path}, check=True,
            stdout=subprocess.DEVNULL,
        )
        print(f"BitcoinTX preview: http://127.0.0.1:{port} (throwaway data in {workdir})", flush=True)
        smoke_test.serve(port, db_path)
    except KeyboardInterrupt:
        pass
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
