"""
StartOS actions that run a BitcoinTX command (#465): a failure shows the
user a translated alert, and the command has no time limit.

- Start9's Actions page, "Wrap User-Facing Strings in i18n()": what an
  action throws is its alert, so it is translated. What init throws stays
  a plain diagnostic (the same section), so runAppCli keeps the SDK's report
  and only the actions translate it, through utils.alertOnFailure. Neither
  shows or logs that whole report, whose SQL can carry a password's hash or
  a transaction's figures: only the command's own line (utils.lastWords).
- Start9's Main page, "Commands That Run Longer Than 30 Seconds": a command
  whose time grows with the data passes `timeout: null`.

The file checks run everywhere; the last test runs the error-reading code
itself with Node, where Node can run TypeScript (22.6 on: CI's Python job
sets one up).
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "startos/startos"
UTILS = (PKG / "utils.ts").read_text()
DEFAULT_DICT = (PKG / "i18n/dictionaries/default.ts").read_text()

# The utils.ts helpers that run `python -m backend.cli`
COMMANDS = ("runAppCli", "setAppCredentials", "replaceDefaultLogin")


def _package_sources(folder: str = "") -> dict[str, str]:
    return {p.name: p.read_text() for p in sorted((PKG / folder).rglob("*.ts"))}


def test_the_command_has_no_time_limit():
    # 1.2.8 gave it 10 minutes (`timeout: 10 * 60_000`). Another command, one
    # that should answer promptly, may keep a limit (main.md).
    body = UTILS.split("export async function runAppCli")[1].split("\n}\n")[0]
    assert "timeout: null" in body
    assert not re.search(r"\btimeout:\s*\d", body)


def test_every_action_command_is_turned_into_a_translated_alert():
    seen = 0
    for name, text in _package_sources("actions").items():
        calls = len(re.findall(rf"\b(?:{'|'.join(COMMANDS)})\(", text))
        wrapped = re.findall(
            rf"alertOnFailure\(\s*(?:{'|'.join(COMMANDS)})\([\s\S]*?i18n\(\s*'([^']+)'",
            text,
        )
        assert len(wrapped) == calls, f"{name}: a command's failure isn't translated"
        for key in wrapped:
            assert f"'{key}':" in DEFAULT_DICT, f"{name}: {key!r} isn't in the dictionary"
            assert "${detail}" in key, f"{name}: {key!r} doesn't show the command's words"
        seen += calls
    assert seen >= 2  # Set Login Credentials and Recalculate Ledger


def test_init_logs_a_plain_line_without_the_sqls_values():
    # A throw from init is a Service Launch Error, a diagnostic: never
    # translated. A failed command is logged by its own words only.
    logged = 0
    for name, text in _package_sources("init").items():
        assert "alertOnFailure" not in text, name
        if not re.search(rf"\b(?:{'|'.join(COMMANDS)})\(", text):
            continue
        for call in re.findall(r"console\.error\(([\s\S]*?)\)\n", text):
            assert "lastWords(e)" in call, f"{name} logs the SDK's whole report"
            logged += 1
    assert logged >= 1  # init/defaultLogin.ts


def _node_runs_typescript() -> bool:
    if not shutil.which("node"):
        return False
    # An older Node refuses the option ("bad option")
    probe = subprocess.run(["node", "--experimental-strip-types", "-e", ""], capture_output=True)
    return probe.returncode == 0


def _helpers() -> str:
    """alertOnFailure and lastWords, as utils.ts has them (they import nothing)."""
    start = UTILS.index("export async function alertOnFailure")
    lastWords = UTILS.index("export function lastWords")
    return UTILS[start : UTILS.index("\n}\n", lastWords) + 3]


DRIVER = r"""
function exitError(stderr: string | Buffer, exitSignal: string | null = null) {
  // As the SDK's ExitError: its message, and the result with stderr
  return Object.assign(new Error(`docker-entrypoint.sh failed: ${stderr}`), {
    result: { exitCode: exitSignal ? null : 1, exitSignal, stderr },
  })
}
async function alertFor(e: unknown): Promise<string> {
  try {
    await alertOnFailure(Promise.reject(e), (detail) => `ALERT(${detail})`)
    return 'no alert'
  } catch (thrown) {
    return (thrown as Error).message
  }
}
// What every command prints first, LOG_LEVEL being INFO
const LOG =
  'INFO:alembic.runtime.migration:Context impl SQLiteImpl.\n' +
  'INFO:backend.database:Database ready (schema 0012).\n'
const cases = {
  cli: await alertFor(exitError(LOG +
    'error: (sqlite3.OperationalError) attempt to write a readonly database\n' +
    '[SQL: UPDATE users SET password_hash=? WHERE users.id = ?]\n' +
    "[parameters: ('$2b$12$hash', 1)]\n" +
    '(Background on this error at: https://sqlalche.me/e/20/e3q8)\n')),
  lastError: await alertFor(exitError(Buffer.from(
    'note: no price lookups\nerror: first\nerror: database is locked\n\n'))),
  emptyError: await alertFor(exitError(LOG + 'error: \n')),
  refused: await alertFor(exitError(
    'BitcoinTX: it could not switch to its user btctx (uid 10001).\n' +
    'Started as root, it needs the capabilities CHOWN, DAC_OVERRIDE, SETUID, SETGID and\n' +
    "NET_BIND_SERVICE (Docker's defaults); or give /data to uid 10001 and start with --user 10001:10001.\n")),
  killed: await alertFor(exitError(LOG, 'SIGKILL')),
  traceback: await alertFor(exitError(LOG +
    'Traceback (most recent call last):\n  File "x.py", line 1\n' +
    "ModuleNotFoundError: No module named 'backend'\n")),
  other: await alertFor(new Error('no such image')),
  passes: await alertOnFailure(Promise.resolve('Recalculated 3 transaction(s).'), () => 'never'),
}
console.log(JSON.stringify(cases))
"""


@pytest.mark.skipif(not _node_runs_typescript(), reason="needs Node 22.6 or later")
def test_the_alert_says_what_the_command_said(tmp_path):
    script = tmp_path / "alert.mts"
    script.write_text(_helpers() + DRIVER)
    run = subprocess.run(
        ["node", "--experimental-strip-types", "--no-warnings", str(script)],
        capture_output=True, text=True, timeout=60,
    )
    assert run.returncode == 0, run.stderr
    cases = json.loads(run.stdout)
    assert cases == {
        "cli": "ALERT((sqlite3.OperationalError) attempt to write a readonly database)",
        "lastError": "ALERT(database is locked)",
        "emptyError": "ALERT(error:)",
        # The start-up script's cause, not its advice for Docker
        "refused": "ALERT(it could not switch to its user btctx (uid 10001).)",
        # Never a log line: a killed command's stderr ends with them
        "killed": "ALERT(terminated with signal SIGKILL)",
        "traceback": "ALERT(ModuleNotFoundError: No module named 'backend')",
        "other": "ALERT(no such image)",
        "passes": "Recalculated 3 transaction(s).",
    }
    # Nothing else is shown or logged: below cli.py's `error:` line, the
    # SQL's values (a password's hash, a transaction's figures)
    assert run.stderr == ""
