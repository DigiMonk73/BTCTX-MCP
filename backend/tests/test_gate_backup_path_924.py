"""
When the release gate runs BAK-5 and UPG-5b, the StartOS backup and its
restore: the steps that need the VM's StartOS password, a person's (#924).
scripts/gate/backup_path_changed.py says "needed" only when the release
changes the backup path, and otherwise "not needed" with every file the
release changes, the diff that shows it.
"""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

SDK = '{{\n  "dependencies": {{\n    "@start9labs/start-sdk": "{}",\n    "typescript": "{}"\n  }}\n}}\n'
VERSION = "export const current = VersionInfo.of({{\n  version: '{}',\n  releaseNotes: '{}',\n" \
          "  migrations: {{\n    up: async ({{ effects }}) => {{{}}},\n    down: IMPOSSIBLE,\n  }},\n}})\n"
DOCKERFILE = "FROM python:3.13-slim@sha256:{}\nRUN useradd --uid 10001 btctx && mkdir -m 700 /data\n" \
             "ENV DATABASE_FILE={}\nENTRYPOINT [\"docker-entrypoint.sh\"]\n"
MOUNT = "export function mainMounts() {{\n  return sdk.Mounts.of().mountVolume({{\n    volumeId: 'main',\n" \
        "    mountpoint: '{}',\n  }})\n}}\nexport const uiPort = {}\n"


def _rule():
    spec = importlib.util.spec_from_file_location("backup_path_changed",
                                                  ROOT / "scripts" / "gate" / "backup_path_changed.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(*changes):
    rule = _rule()
    return rule.report([rule.Change(*change) for change in changes]).splitlines()


NEEDED = {
    "the backup service": ("backend/services/backup.py", "def backup(): ...", "def backup(): return 1"),
    "the backup router": ("backend/routers/backup.py", "a", "b"),
    "a new migration": ("backend/migrations/versions/0102_new_table.py", None, "def upgrade(): ..."),
    "migrate.py": ("backend/migrate.py", "a", "b"),
    "database.py": ("backend/database.py", "a", "b"),
    "the package's backup settings": ("startos/startos/backups.ts", "ofVolumes('main', 'startos')",
                                      "ofVolumes('main')"),
    "the start-sdk version": ("startos/package.json", SDK.format("4.0.0", "5.9.3"), SDK.format("4.1.0", "5.9.3")),
    "the entrypoint script": ("docker-entrypoint.sh", "exec \"$@\"", "exec gosu btctx \"$@\""),
    "the Dockerfile's entrypoint": ("Dockerfile", DOCKERFILE.format("a1", "/data/btctx.db"),
                                    DOCKERFILE.format("a1", "/data/btctx.db").replace("ENTRYPOINT", "CMD")),
    "the Dockerfile's data folder": ("Dockerfile", DOCKERFILE.format("a1", "/data/btctx.db"),
                                     DOCKERFILE.format("a1", "/data/ledger/btctx.db")),
    "the volume's mount": ("startos/startos/utils.ts", MOUNT.format("/data", 80), MOUNT.format("/srv", 80)),
    "a package migration": ("startos/startos/versions/current.ts", VERSION.format("2.0.1:0", "Notes.", ""),
                            VERSION.format("2.0.2:0", "Notes.", " await makeRecalculationDue(effects) ")),
    "a new package version with its migration": ("startos/startos/versions/v2.0.2_0.ts", None,
                                                 VERSION.format("2.0.2:0", "Notes.", " await x() ")),
}

NOT_NEEDED = {
    "frontend only": (("frontend/src/App.tsx", "a", "b"), ("frontend/package.json", "{}", '{"x": 1}')),
    "docs only": (("docs/AGENT-TESTS.md", "a", "b"), ("README.md", "a", "b"), ("docs/CHANGELOG.md", "a", "b")),
    "the package's version and notes only": (
        ("startos/startos/versions/current.ts", VERSION.format("2.0.1:0", "Notes.", ""),
         VERSION.format("2.0.2:0", "Other notes.", "")),),
    "another tool in the package": (("startos/package.json", SDK.format("4.0.0", "5.9.3"),
                                     SDK.format("4.0.0", "5.9.4")),),
    "the Dockerfile's base image": (("Dockerfile", DOCKERFILE.format("a1", "/data/btctx.db"),
                                     DOCKERFILE.format("b2", "/data/btctx.db")),),
    "the package's port, not its mount": (("startos/startos/utils.ts", MOUNT.format("/data", 80),
                                           MOUNT.format("/data", 81)),),
    "app code off the backup path": (("backend/services/calculation.py", "a", "b"),
                                     ("backend/routers/transaction.py", "a", "b")),
}


@pytest.mark.xfail(strict=True, reason="for #924: the backup-path rule isn't written yet")
@pytest.mark.parametrize("case", sorted(NEEDED))
def test_a_change_to_the_backup_path_makes_bak5_needed(case):
    path, before, after = NEEDED[case]
    lines = _report(("frontend/src/App.tsx", "a", "b"), (path, before, after))
    assert lines[-1] == "BAK-5 and UPG-5b: needed"
    assert [line for line in lines[:-1] if line.startswith(f"{path}: ")], lines
    assert not [line for line in lines if "App.tsx" in line]  # only what makes them needed


@pytest.mark.xfail(strict=True, reason="for #924: the backup-path rule isn't written yet")
@pytest.mark.parametrize("case", sorted(NOT_NEEDED))
def test_a_change_off_the_backup_path_records_bak5_as_not_needed(case):
    changes = NOT_NEEDED[case]
    lines = _report(*changes)
    assert lines[-1] == "BAK-5 and UPG-5b: not needed"
    # The diff that shows it: every file the release changes
    assert lines[0] == f"{len(changes)} files changed, none on the backup path:"
    assert [line.strip() for line in lines[1:-1]] == [path for path, _, _ in changes]


@pytest.mark.xfail(strict=True, reason="for #924: the backup-path rule isn't written yet")
def test_a_file_moved_off_the_backup_path_still_counts():
    """git compares without renames, so the old path shows as gone."""
    lines = _report(("backend/services/backup.py", "a", None), ("backend/services/old_backup.py", None, "a"))
    assert lines[-1] == "BAK-5 and UPG-5b: needed"
