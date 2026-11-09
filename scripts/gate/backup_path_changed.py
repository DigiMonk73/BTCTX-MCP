#!/usr/bin/env python3
"""
Whether a release changes the StartOS backup path, and so whether the gate
runs BAK-5 and UPG-5b: the only Track A and B steps that need the VM's
StartOS password, a person's (#924; docs/AGENT-TESTS.md, "What stays by
hand"). When they aren't needed, they're recorded as not needed with this
script's output, the diff that shows it.

    scripts/gate/backup_path_changed.py FROM TO     # e.g. v2.0.1 origin/develop

The backup path is what a StartOS backup and its restore go through:
- the package's backup settings: startos/startos/backups.ts, and the
  start-sdk version that runs them (startos/package.json);
- the package's own migrations (startos/startos/versions/: a version's
  migrations, never its release notes), which a restore below the current
  version runs;
- backup.py (the service and the router), migrate.py, the migrations and
  database.py;
- the data folder's layout: the volume, where it's mounted and what the app
  keeps in it (startos/startos/utils.ts's mount and DATABASE_FILE, the
  manifest's volumes, the Dockerfile's /data, DATABASE_FILE and its user,
  backend/secret_key.py);
- the image's entrypoint: docker-entrypoint.sh, the Dockerfile's ENTRYPOINT
  and CMD.

Prints each file that changes it, and why, or every file the release changes;
then a last line "needed" or "not needed". Exits 0 either way, 2 when git
can't compare the two.
"""

import re
import subprocess
import sys
from dataclasses import dataclass

NEEDED = "BAK-5 and UPG-5b: needed"
NOT_NEEDED = "BAK-5 and UPG-5b: not needed"


@dataclass(frozen=True)
class Change:
    """A file the release changes, as it was and as it is (None: absent)."""

    path: str
    before: str | None
    after: str | None


@dataclass(frozen=True)
class Rule:
    """Files on the backup path. `lines` keeps only the lines that matter, for
    a file that also holds other things (the Dockerfile's build steps,
    package.json's other tools); `from_text` keeps the file from that text on
    (a StartOS version's migrations, after its release notes)."""

    path: str
    why: str
    lines: str | None = None
    from_text: str | None = None

    def covers(self, path: str) -> bool:
        return path.startswith(self.path) if self.path.endswith("/") else path == self.path

    def part(self, text: str | None) -> str | None:
        if text is None or (self.lines is None and self.from_text is None):
            return text
        if self.lines is not None:
            return "\n".join(line for line in text.splitlines() if re.search(self.lines, line))
        start = text.find(self.from_text)
        return text[start:] if start >= 0 else ""


RULES = (
    Rule("startos/startos/backups.ts", "the package's backup settings"),
    Rule("startos/package.json", "the start-sdk version", lines=r"@start9labs/start-sdk"),
    Rule("startos/startos/versions/", "the package's own migrations", from_text="migrations:"),
    Rule("backend/services/backup.py", "backup.py (the service)"),
    Rule("backend/routers/backup.py", "backup.py (the router)"),
    Rule("backend/migrate.py", "migrate.py"),
    Rule("backend/migrations/", "the migrations"),
    Rule("backend/database.py", "database.py"),
    Rule("backend/secret_key.py", "the data folder's layout (the session key kept beside the database)"),
    Rule("startos/startos/utils.ts", "the data folder's layout (the volume's mount, DATABASE_FILE)",
         lines=r"DATABASE_FILE|volumeId|mountpoint|subpath|readonly|/data"),
    Rule("startos/startos/manifest/index.ts", "the data folder's layout (the volumes)", lines=r"volumes"),
    Rule("Dockerfile", "the data folder's layout or the image's entrypoint",
         lines=r"^\s*(ENTRYPOINT|CMD|USER|VOLUME)\b|DATABASE_FILE|/data|useradd|groupadd"),
    Rule("docker-entrypoint.sh", "the image's entrypoint"),
)


def reasons(changes: list[Change]) -> list[str]:
    """Each changed file on the backup path, with why: empty when none is."""
    found = []
    for change in changes:
        for rule in RULES:
            if rule.covers(change.path) and rule.part(change.before) != rule.part(change.after):
                found.append(f"{change.path}: {rule.why}")
                break
    return found


def report(changes: list[Change]) -> str:
    """What the gate records: the files that make BAK-5 and UPG-5b needed, or
    every file the release changes, none on the backup path."""
    found = reasons(changes)
    if found:
        return "\n".join([*found, NEEDED])
    listed = [f"  {change.path}" for change in changes]
    return "\n".join([f"{len(changes)} files changed, none on the backup path:", *listed, NOT_NEEDED])


def changes_between(before: str, after: str) -> list[Change]:
    """Every file that differs between two commits, with its text at each
    when a rule covers it. No rename detection: a moved file is its old path
    gone and its new one added, so a file moved off the backup path still
    counts."""
    names = [name for name in git("diff", "--name-only", "--no-renames", before, after).split("\n") if name]
    return [Change(name, text_at(before, name), text_at(after, name))
            if any(rule.covers(name) for rule in RULES) else Change(name, None, None) for name in names]


def text_at(rev: str, path: str) -> str | None:
    shown = subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True)
    return shown.stdout.decode("utf-8", "replace") if shown.returncode == 0 else None


def git(*args: str) -> str:
    done = subprocess.run(["git", *args], capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout.strip()


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        print(report(changes_between(sys.argv[1], sys.argv[2])))
    except RuntimeError as failed:
        print(failed, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
