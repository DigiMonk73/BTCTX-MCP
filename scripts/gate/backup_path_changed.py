#!/usr/bin/env python3
"""
Whether a release changes the StartOS backup path, and so whether the gate
runs BAK-5 and UPG-5b: the only Track A and B steps that need the VM's
StartOS password, a person's (#924; docs/AGENT-TESTS.md, "What stays by
hand"). When they aren't needed, they're recorded as not needed with this
script's output, the diff that shows it.

    scripts/gate/backup_path_changed.py FROM TO

FROM is the last release whose BAK-5 and UPG-5b passed, not just the last
release: one that shipped with them deferred or BLOCKED left its changes
untested. TO is the release candidate.

The backup path is what a StartOS backup and its restore go through:
- the package's backup settings: startos/startos/backups.ts, and the
  start-sdk version that runs them (startos/package.json);
- what the package runs on a restore and holds in its volumes: init/
  (restoreInit, and the tasks a restore raises or not), fileModels/ (the
  startos volume's store.json), main.ts (the migrate step, the entrypoint
  and the mounts), utils.ts (the volume's mount, DATABASE_FILE, the app's
  commands and the migrations' helpers) and the manifest's volumes;
- the package's own migrations (versions/: everything but a version's
  release notes, its whole comment lines, its links to the repository and,
  for current.ts, bumped in place at each release, its version line), which
  a restore below the current version runs, and the version graph that
  chains them; and its entry point (startos/startos/index.ts);
- backup.py (the service and the router), migrate.py, the migrations and
  database.py;
- the data folder's layout: the Dockerfile's /data, DATABASE_FILE and its
  user, and the session key kept beside the database (backend/secret_key.py).
  A StartOS backup holds the whole volume, so a file the app keeps there (a
  price cache, the draft forms) comes back with a restore whatever its name;
- the image's entrypoint: docker-entrypoint.sh, and the Dockerfile's
  ENTRYPOINT, CMD and the line that copies the script in.

A file a rule covers counts whenever the part that matters differs: a
false "needed" costs a person's few minutes, a false "not needed" an
untested restore.

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
    """Files on the backup path. For a file that also holds other things,
    `keep` keeps only what matches (the Dockerfile's build steps, package.json's
    other tools, the manifest's other fields), or `drop` leaves out what
    doesn't matter (a StartOS version's release notes)."""

    path: str
    why: str
    keep: str | None = None
    drop: str | None = None

    def covers(self, path: str) -> bool:
        return path.startswith(self.path) if self.path.endswith("/") else path == self.path

    def part(self, text: str | None) -> str | None:
        if text is None:
            return None
        if self.keep is not None:
            return "\n".join(re.findall(self.keep, text, re.MULTILINE))
        if self.drop is not None:
            # What's left keeps its lines, blank ones aside: a note added or
            # dropped leaves a blank line where it was
            kept = re.sub(self.drop, "", text, flags=re.MULTILINE)
            return "\n".join(line for line in kept.splitlines() if line.strip())
        return text


# What changes in a StartOS version file without changing what it runs:
# its notes (each language's template string, a whole line of its own), whole
# comment lines and the links to the repository the notes name (the
# CHANGELOG, a release). Each is anchored to its own line, so a string or a
# template in the code itself always counts.
NOTES_TEXT = (r"^\s*(?:[a-z]{2}_[A-Z]{2}|releaseNotes):\s*`(?:\\.|[^`\\])*`,?[ \t]*$"
              r"|^\s*/\*[\s\S]*?\*/[ \t]*$|^\s*//.*$"
              r"|^const [A-Z0-9_]+ =\s*'https://github\.com/DigiMonk73/BTCTX-MCP/[^']*'$"
              r"|'https://github\.com/DigiMonk73/BTCTX-MCP/[^']*'")
# current.ts is bumped in place at a release whose migration is empty
# (Start9's versions.md), so its own version line is release text too; an
# older version's is where its migration sits in the graph
CURRENT_TEXT = NOTES_TEXT + r"|^\s*version: '[^']*',?[ \t]*$"

RULES = (
    Rule("startos/startos/backups.ts", "the package's backup settings"),
    Rule("startos/package.json", "the start-sdk version", keep=r"^.*@start9labs/start-sdk.*$"),
    Rule("startos/startos/init/", "what the package runs on a restore (init)"),
    Rule("startos/startos/fileModels/", "what the startos volume holds (store.json)"),
    Rule("startos/startos/main.ts", "how the service starts (its migrate step, entrypoint and mounts)"),
    Rule("startos/startos/utils.ts", "the data folder's mount, the app's commands or the migrations' helpers"),
    Rule("startos/startos/manifest/index.ts", "the package's volumes", keep=r"volumes:\s*\[[^\]]*\]"),
    Rule("startos/startos/index.ts", "the package's entry point (its backups and init)"),
    Rule("startos/startos/versions/index.ts", "the package's own migrations (the version graph)"),
    Rule("startos/startos/versions/current.ts", "the package's own migrations", drop=CURRENT_TEXT),
    Rule("startos/startos/versions/", "the package's own migrations", drop=NOTES_TEXT),
    Rule("backend/services/backup.py", "backup.py (the service)"),
    Rule("backend/routers/backup.py", "backup.py (the router)"),
    Rule("backend/migrate.py", "migrate.py"),
    Rule("backend/migrations/", "the migrations"),
    Rule("backend/database.py", "database.py"),
    Rule("backend/secret_key.py", "the data folder's layout (the session key kept beside the database)"),
    Rule("Dockerfile", "the data folder's layout or the image's entrypoint",
         keep=r"^\s*(?:ENTRYPOINT|CMD|USER|VOLUME)\b.*$|^.*(?:DATABASE_FILE|/data|useradd|groupadd|docker-entrypoint).*$"),
    Rule("docker-entrypoint.sh", "the image's entrypoint"),
)


def reasons(changes: list[Change]) -> list[str]:
    """Each changed file on the backup path, with why: empty when none is.
    A file's first rule decides it (current.ts's before the versions/ one)."""
    found = []
    for change in changes:
        rule = next((rule for rule in RULES if rule.covers(change.path)), None)
        if rule is not None and rule.part(change.before) != rule.part(change.after):
            found.append(f"{change.path}: {rule.why}")
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
