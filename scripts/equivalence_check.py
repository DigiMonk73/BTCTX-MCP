#!/usr/bin/env python3
"""
Before/after check for a change that must not change behaviour.

Snapshots everything BitcoinTX produces for a set of ledgers: database rows,
API answers, Form 8949 / Schedule D field values, report PDFs (bytes and
text), CSV files, import previews, MCP tool outputs and every error message
from a set of bad inputs (scripts/equivalence_snapshot.py). It does so for a
release, checked out in a temporary git worktree, and for this checkout,
then compares the two. The snapshot code always comes from this checkout;
only the app code differs.

    python scripts/equivalence_check.py                  # against v1.2.2-1
    python scripts/equivalence_check.py --against v1.3.0
    python scripts/equivalence_check.py --bench          # recalculation time too

Snapshots are kept in .equivalence/ (gitignored); the release's is reused
while the snapshot code and the day are unchanged. Exit status 1 on any
difference, or when recalculation is more than 5% slower.
"""

import argparse
import difflib
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / ".equivalence"
BASELINE = "v1.2.2-1"
SLOWER_ALLOWED = 1.05
DIFF_LINES = 40


def main() -> int:
    args = _arguments()
    if args.command == "snapshot":
        return _snapshot(Path(args.root), Path(args.out), args.bench)
    base = _baseline_snapshot(args.against, args.bench, args.fresh)
    here = _take(ROOT, STORE / "working", args.bench)
    return _compare(base, here, args.bench)


def _arguments():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", nargs="?", default="compare", choices=("compare", "snapshot"))
    parser.add_argument("--against", default=BASELINE, help="the git ref to compare with")
    parser.add_argument("--bench", action="store_true", help="also time a full recalculation")
    parser.add_argument("--fresh", action="store_true", help="retake the release's snapshot")
    parser.add_argument("--root", default=str(ROOT), help=argparse.SUPPRESS)
    parser.add_argument("--out", help=argparse.SUPPRESS)
    return parser.parse_args()


def _baseline_snapshot(ref: str, bench: bool, fresh: bool) -> Path:
    """The release's snapshot, taken in a temporary worktree of `ref`."""
    commit = _git("rev-parse", f"{ref}^{{commit}}").strip()
    out = STORE / f"{commit[:12]}-{_snapshot_code_digest()}-{date.today().isoformat()}"
    if fresh or not (out / "done").exists() or (bench and not (out / "bench.json").exists()):
        worktree = Path(tempfile.mkdtemp(prefix="btctx-baseline-")) / "checkout"
        _git("worktree", "add", "--detach", str(worktree), commit)
        try:
            _take(worktree, out, bench)
        finally:
            _git("worktree", "remove", "--force", str(worktree))
    return out


def _snapshot_code_digest() -> str:
    """Changes when the snapshot code does, so an old snapshot isn't reused."""
    digest = hashlib.sha256()
    for name in ("equivalence_check.py", "equivalence_snapshot.py", "equivalence_inputs.py"):
        digest.update((ROOT / "scripts" / name).read_bytes())
    return digest.hexdigest()[:8]


def _take(root: Path, out: Path, bench: bool) -> Path:
    """Runs the snapshot of `root`'s code in a process of its own."""
    print(f"Snapshot of {root} ...", flush=True)
    command = [sys.executable, str(Path(__file__).resolve()), "snapshot", "--root", str(root), "--out", str(out)]
    if bench:
        command.append("--bench")
    subprocess.run(command, cwd=root, check=True)
    (out / "done").touch()
    return out


def _snapshot(root: Path, out: Path, bench: bool) -> int:
    """In the child process: `root`'s code first on the path, throwaway
    folders for everything the app writes, then the snapshot."""
    work = Path(tempfile.mkdtemp(prefix="btctx-snapshot-"))
    (work / "dist").mkdir()
    os.environ.update({
        "DATABASE_FILE": str(work / "btctx.db"),
        "BTCTX_FRONTEND_DIST": str(work / "dist"),
        "LOG_LEVEL": "ERROR",
    })
    for name in ("BTCTX_TIMEZONE", "BTCTX_PRICE_SOURCE", "DEBUG"):
        os.environ.pop(name, None)
    sys.path[:0] = [str(root), str(root / "mcp_server")]

    import equivalence_snapshot

    equivalence_snapshot.take(out, work, bench)
    return 0


def _compare(base: Path, here: Path, bench: bool) -> int:
    differences = 0
    for path in sorted(base.glob("*.json")):
        if path.name == "bench.json":
            continue
        differences += _compare_file(path, here / path.name)
    if bench:
        differences += _compare_bench(base / "bench.json", here / "bench.json")
    print("\nNo difference." if not differences else f"\n{differences} difference(s).")
    return 1 if differences else 0


def _compare_file(before: Path, after: Path) -> int:
    """Differences per top-level entry, each shown as a short diff."""
    if not after.exists():
        print(f"✗ {after.name}: missing")
        return 1
    old, new = json.loads(before.read_text()), json.loads(after.read_text())
    differences = 0
    for key in sorted(set(old) | set(new)):
        old_lines, new_lines = _lines(old.get(key)), _lines(new.get(key))
        if old_lines == new_lines:  # as text, so a change of key order counts
            continue
        differences += 1
        print(f"✗ {before.stem} → {key}")
        diff = difflib.unified_diff(old_lines, new_lines, "before", "after", lineterm="", n=2)
        for line in list(diff)[:DIFF_LINES]:
            print(f"    {line}")
    if not differences:
        print(f"✓ {before.stem}")
    return differences


def _lines(value) -> list:
    return json.dumps(value, indent=1, default=str, ensure_ascii=False).splitlines()


def _compare_bench(before: Path, after: Path) -> int:
    old, new = json.loads(before.read_text())["fastest"], json.loads(after.read_text())["fastest"]
    ratio = new / old
    verdict = "✓" if ratio <= SLOWER_ALLOWED else "✗"
    print(f"{verdict} recalculation: {old:.3f} s before, {new:.3f} s after ({ratio - 1:+.1%})")
    return 0 if verdict == "✓" else 1


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


if __name__ == "__main__":
    sys.exit(main())
