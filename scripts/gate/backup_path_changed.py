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
- everything else in startos/startos/, whole: what the package runs on a
  restore and holds in its volumes (init/ and every file its steps use:
  the actions it registers and its tasks name, dependencies.ts,
  interfaces.ts, sdk.ts, priceSource.ts; fileModels/, the startos volume's
  store.json; main.ts, the migrate step, the entrypoint and the mounts;
  utils.ts; the manifest's volumes; its entry point, index.ts);
- the package's own migrations (versions/, each file whole), which a
  restore below the current version runs, and the version graph that
  chains them. Every release changes current.ts (its version and its
  notes), so for now every release reads "needed" (the owner's choice,
  2026-11-10, #957), until #962 tells a release that changes only those
  apart safely;
- backup.py (the service and the router), migrate.py, the migrations,
  database.py, and backend/cli.py, the commands the package runs (migrate,
  set-password);
- the data folder's layout: the session key kept beside the database
  (backend/secret_key.py), and the Dockerfile, whole, which sets /data, the
  user, the environment the database reads (DATABASE_FILE, DATABASE_URL)
  and the base image with its SQLite. A StartOS backup holds the whole
  volume, so a file the app keeps there (a price cache, the draft forms)
  comes back with a restore whatever its name;
- the image's entrypoint: docker-entrypoint.sh, and the Dockerfile.

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
    `keep` keeps only what matches (package.json's other tools)."""

    path: str
    why: str
    keep: str | None = None

    def covers(self, path: str) -> bool:
        return path.startswith(self.path) if self.path.endswith("/") else path == self.path

    def part(self, text: str | None) -> str | None:
        if text is None or self.keep is None:
            return text
        return "\n".join(re.findall(self.keep, text, re.MULTILINE))


RULES = (
    Rule("startos/startos/backups.ts", "the package's backup settings"),
    Rule("startos/package.json", "the start-sdk version", keep=r"^.*@start9labs/start-sdk.*$"),
    Rule("startos/startos/init/", "what the package runs on a restore (init)"),
    Rule("startos/startos/actions/", "the actions init registers and a restore's tasks name"),
    Rule("startos/startos/priceSource.ts", "the price source init and the service set"),
    Rule("startos/startos/fileModels/", "what the startos volume holds (store.json)"),
    Rule("startos/startos/main.ts", "how the service starts (its migrate step, entrypoint and mounts)"),
    Rule("startos/startos/utils.ts", "the data folder's mount, the app's commands or the migrations' helpers"),
    Rule("startos/startos/manifest/", "the package's manifest (its volumes, its image)"),
    Rule("startos/startos/index.ts", "the package's entry point (its backups and init)"),
    Rule("startos/startos/versions/index.ts", "the package's own migrations (the version graph)"),
    Rule("startos/startos/versions/", "the package's own migrations (every change, until #962)"),
    # Last of the package's: what the rules above don't name (an init step's
    # own file, the interfaces, the sdk) counts too
    Rule("startos/startos/", "the package's code init and the service use"),
    Rule("backend/services/backup.py", "backup.py (the service)"),
    Rule("backend/routers/backup.py", "backup.py (the router)"),
    Rule("backend/migrate.py", "migrate.py"),
    Rule("backend/migrations/", "the migrations"),
    Rule("backend/database.py", "database.py"),
    Rule("backend/cli.py", "the commands the package runs (migrate, set-password)"),
    Rule("backend/secret_key.py", "the data folder's layout (the session key kept beside the database)"),
    Rule("Dockerfile", "the image: its data folder, user, environment, entrypoint and base"),
    Rule("docker-entrypoint.sh", "the image's entrypoint"),
)


def reasons(changes: list[Change]) -> list[str]:
    """Each changed file on the backup path, with why: empty when none is.
    A file's first rule decides it, and so names why: the narrower rules come
    before startos/startos/'s own."""
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
    # -z: git quotes a name with other than plain ASCII in its list, which no
    # rule's path would match
    names = [name for name in git("diff", "--name-only", "-z", "--no-renames", before, after).split("\0") if name]
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
