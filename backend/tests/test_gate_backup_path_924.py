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
VERSION = "export const current = VersionInfo.of({{\n  version: '{}',\n  releaseNotes: `{}`,\n" \
          "  migrations: {{\n    up: async ({{ effects }}) => {{{}}},\n    down: IMPOSSIBLE,\n  }},\n}})\n"
DOCKERFILE = "FROM python:3.13-slim@sha256:{}\nRUN useradd --uid 10001 btctx && mkdir -m 700 /data\n" \
             "ENV DATABASE_FILE={}\nENTRYPOINT [\"docker-entrypoint.sh\"]\n"
MOUNT = "export function mainMounts() {{\n  return sdk.Mounts.of().mountVolume({{\n    volumeId: 'main',\n" \
        "    mountpoint: '{}',\n  }})\n}}\nexport const uiPort = {}\n"
# A version file as the package writes it: its notes, a comment and the
# CHANGELOG's link change at every release; a helper above the migrations
# is part of them
RELEASE = "const CHANGELOG =\n  'https://github.com/DigiMonk73/BTCTX-MCP/blob/v{0}/docs/CHANGELOG.md'\n" \
          "const BEFORE =\n  'https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v{0}-beta.1'\n\n" \
          "/**\n * {0}:0, {1}\n */\nasync function forget(effects) {{\n  {2}\n}}\n\n" \
          "export const current = VersionInfo.of({{\n  version: '{0}:0',\n" \
          "  releaseNotes: {{\n    en_US: `{1} Run \\`btctx-mcp==${{CHANGELOG}}\\`.`,\n  }},\n" \
          "  // what the migration does\n  migrations: {{\n    up: async ({{ effects }}) => forget(effects),\n" \
          "    down: IMPOSSIBLE,\n  }},\n}})\n"
MANIFEST = "export const manifest = setupManifest({{\n  description: {{ short: '{}' }},\n  volumes: [\n{}  ],\n}})\n"


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
    # What a StartOS restore runs, and what the package's volumes hold (the review, #957)
    "restoreInit dropped": ("startos/startos/init/index.ts", "setupInit(restoreInit, versionGraph, seedStore)",
                            "setupInit(versionGraph, seedStore)"),
    "the login task on a restore": ("startos/startos/init/watchCredentials.ts",
                                    "if (kind === 'restore') return", "if (kind === 'restore') await raiseTask()"),
    "the store's shape": ("startos/startos/fileModels/store.json.ts", "loginSet: z.boolean()",
                          "loginWasSet: z.boolean()"),
    "how the service starts": ("startos/startos/main.ts", "sdk.useEntrypoint()", "['uvicorn', 'backend.main:app']"),
    "the version graph": ("startos/startos/versions/index.ts", "other: [v_1_2_9_0, v_1_2_8_0]",
                          "other: [v_1_2_9_0]"),
    "the Dockerfile's copy of the entrypoint": (
        "Dockerfile", "COPY --chmod=755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh\n",
        "COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh\n"),
    "the app's commands' entrypoint": ("startos/startos/utils.ts",
                                       "['docker-entrypoint.sh', 'python', '-m', 'backend.cli']",
                                       "['python', '-m', 'backend.cli']"),
    "a volume gone from a list across lines": ("startos/startos/manifest/index.ts",
                                               MANIFEST.format("A ledger", "    'main',\n    'startos',\n"),
                                               MANIFEST.format("A ledger", "    'main',\n")),
    "a version's helper above its migrations": ("startos/startos/versions/current.ts",
                                                RELEASE.format("2.0.1", "Notes.", "await forgetPassword(effects)"),
                                                RELEASE.format("2.0.2", "Notes.", "await forgetLogin(effects)")),
    # Code the release text's filter must never take for notes or a comment (the re-check, #957)
    "a path inside a migration's template string": (
        "startos/startos/versions/v2.0.2_0.ts", RELEASE.format("2.0.2", "Notes.", "await rm(`btctx.db-journal`)"),
        RELEASE.format("2.0.2", "Notes.", "await rm(`btctx.db`)")),
    "a glob string holding /*": (
        "startos/startos/versions/v2.0.2_0.ts", RELEASE.format("2.0.2", "Notes.", "await rm('/data/*.tmp')"),
        RELEASE.format("2.0.2", "Notes.", "await rm('/data/*.tmp'); await rm('/data/backups')")),
    "a comment holding one backtick, after code": (
        "startos/startos/versions/v2.0.2_0.ts",
        RELEASE.format("2.0.2", "Notes.", "await rm('a') // the ` file\n  await keep('b')"),
        RELEASE.format("2.0.2", "Notes.", "await rm('a') // the ` file\n  await rm('b')")),
    "a version inside a migration": (
        "startos/startos/versions/v2.0.2_0.ts",
        RELEASE.format("2.0.2", "Notes.", "await store.merge(effects, { version: '1' })"),
        RELEASE.format("2.0.2", "Notes.", "await store.merge(effects, { version: '2' })")),
    "an older version's own version": (
        "startos/startos/versions/v1.2.9_0.ts", RELEASE.format("1.2.9", "Notes.", "await x()"),
        RELEASE.format("1.2.8", "Notes.", "await x()")),
    "the package's entry point": ("startos/startos/index.ts", "export { init } from './init'",
                                  "export { init, uninit } from './init'"),
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
    "a release's version file: its notes, comment and links": (
        ("startos/startos/versions/current.ts", RELEASE.format("2.0.1", "Notes.", "await forgetPassword(effects)"),
         RELEASE.format("2.0.2", "Other notes, with \\`code\\`.", "await forgetPassword(effects)")),),
    "the manifest's other fields": (("startos/startos/manifest/index.ts",
                                     MANIFEST.format("A ledger", "    'main',\n    'startos',\n"),
                                     MANIFEST.format("A tax ledger", "    'main',\n    'startos',\n")),),
    "app code off the backup path": (("backend/services/calculation.py", "a", "b"),
                                     ("backend/routers/transaction.py", "a", "b")),
}


@pytest.mark.parametrize("case", sorted(NEEDED))
def test_a_change_to_the_backup_path_makes_bak5_needed(case):
    path, before, after = NEEDED[case]
    lines = _report(("frontend/src/App.tsx", "a", "b"), (path, before, after))
    assert lines[-1] == "BAK-5 and UPG-5b: needed"
    assert [line for line in lines[:-1] if line.startswith(f"{path}: ")], lines
    assert not [line for line in lines if "App.tsx" in line]  # only what makes them needed


@pytest.mark.parametrize("case", sorted(NOT_NEEDED))
def test_a_change_off_the_backup_path_records_bak5_as_not_needed(case):
    changes = NOT_NEEDED[case]
    lines = _report(*changes)
    assert lines[-1] == "BAK-5 and UPG-5b: not needed"
    # The diff that shows it: every file the release changes
    assert lines[0] == f"{len(changes)} files changed, none on the backup path:"
    assert [line.strip() for line in lines[1:-1]] == [path for path, _, _ in changes]


def test_a_file_moved_off_the_backup_path_still_counts():
    """git compares without renames, so the old path shows as gone."""
    lines = _report(("backend/services/backup.py", "a", None), ("backend/services/old_backup.py", None, "a"))
    assert lines[-1] == "BAK-5 and UPG-5b: needed"


def _git(repo, *args):
    import os
    import subprocess

    # The machine's own git settings (signing, hooks) stay out of the test
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    return subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid", *args],
                          cwd=repo, env=env, capture_output=True, text=True)


def test_the_script_compares_two_commits_through_git(tmp_path):
    """git's own rename detection would show a file moved off the backup
    path by its new name only: the script asks git without it."""
    import os
    import subprocess
    import sys

    repo = tmp_path / "repo"
    (repo / "backend" / "services").mkdir(parents=True)
    (repo / "docs").mkdir()
    (repo / "backend" / "services" / "backup.py").write_text("def backup(): ...\n" * 20)
    (repo / "docs" / "guide.md").write_text("A guide.\n")
    _git(repo, "init", "-q")
    for step in (("add", "."), ("commit", "-qm", "first"), ("tag", "first"),
                 ("mv", "backend/services/backup.py", "backend/services/old_backup.py"),
                 ("commit", "-qm", "moved"), ("tag", "moved")):
        assert _git(repo, *step).returncode == 0
    (repo / "docs" / "guide.md").write_text("A longer guide.\n")
    assert _git(repo, "commit", "-qam", "docs").returncode == 0
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    script = str(ROOT / "scripts" / "gate" / "backup_path_changed.py")

    def run(*revs):
        return subprocess.run([sys.executable, script, *revs], cwd=repo, env=env, capture_output=True, text=True)

    moved = run("first", "moved")
    assert moved.returncode == 0 and moved.stdout.splitlines()[-1] == "BAK-5 and UPG-5b: needed", moved.stdout
    assert "backend/services/backup.py: backup.py (the service)" in moved.stdout
    docs = run("moved", "HEAD")
    assert docs.returncode == 0
    assert docs.stdout.splitlines() == ["1 files changed, none on the backup path:", "  docs/guide.md",
                                        "BAK-5 and UPG-5b: not needed"]
    unknown = run("nowhere", "HEAD")
    assert unknown.returncode == 2 and "nowhere" in unknown.stderr
