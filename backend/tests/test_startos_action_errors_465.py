"""
StartOS actions that run a BitcoinTX command (#465): a failure shows the
user a translated alert, and the command has no time limit.

- Start9's Actions page, "Wrap User-Facing Strings in i18n()": what an
  action throws is its alert, so it is translated. What init throws stays
  a plain diagnostic (the same section), so runAppCli keeps the SDK's report
  and only the actions translate it, through utils.alertOnFailure.
- Start9's Main page, "Commands That Run Longer Than 30 Seconds": a command
  whose time grows with the data passes `timeout: null`.

The file checks run everywhere; the last test runs the error-reading code
itself with Node, where Node can run TypeScript (22.6 on).
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


def test_no_command_has_a_time_limit_in_minutes():
    # 1.2.8 gave every command 10 minutes (`timeout: 10 * 60_000`)
    body = UTILS.split("export async function runAppCli")[1].split("\n}\n")[0]
    assert "timeout: null" in body
    for name, text in _package_sources().items():
        assert not re.search(r"\btimeout:\s*\d", text), name


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


def test_init_keeps_the_sdks_plain_report():
    # A throw from init is a Service Launch Error, a diagnostic: never translated
    for name, text in _package_sources("init").items():
        assert "alertOnFailure" not in text, name


def _node_runs_typescript() -> bool:
    if not shutil.which("node"):
        return False
    # An older Node refuses the option ("bad option")
    probe = subprocess.run(["node", "--experimental-strip-types", "-e", ""], capture_output=True)
    return probe.returncode == 0


def _helpers() -> str:
    """alertOnFailure and lastWords, as utils.ts has them (they import nothing)."""
    start = UTILS.index("export async function alertOnFailure")
    lastWords = UTILS.index("function lastWords")
    return UTILS[start : UTILS.index("\n}\n", lastWords) + 3]


DRIVER = r"""
function exitError(stderr: string) {
  // As the SDK's ExitError: its message, and the result with stderr (a Buffer)
  return Object.assign(new Error(`python failed with exit code 1: ${stderr}`), {
    result: { exitCode: 1, stderr: Buffer.from(stderr) },
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
const cases = {
  cli: await alertFor(exitError(
    "INFO:alembic.runtime.migration:Context impl SQLiteImpl.\n" +
    "error: (sqlite3.OperationalError) attempt to write a readonly database\n" +
    "[SQL: UPDATE users SET password_hash=? WHERE users.id = ?]\n" +
    "[parameters: ('$2b$12$hash', 1)]\n" +
    "(Background on this error at: https://sqlalche.me/e/20/e3q8)\n")),
  cliThenNoise: await alertFor(exitError("error: first\nerror: database is locked\n\n")),
  traceback: await alertFor(exitError(
    "Traceback (most recent call last):\n  File \"x.py\", line 1\n" +
    "ModuleNotFoundError: No module named 'backend'\n")),
  silent: await alertFor(Object.assign(new Error('python terminated with signal SIGKILL: '), {
    result: { exitCode: null, stderr: '' } })),
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
        "cliThenNoise": "ALERT(database is locked)",
        "traceback": "ALERT(ModuleNotFoundError: No module named 'backend')",
        "silent": "ALERT(python terminated with signal SIGKILL: )",
        "other": "ALERT(no such image)",
        "passes": "Recalculated 3 transaction(s).",
    }
    # Nothing else is shown or logged: below cli.py's `error:` line, the
    # SQL's values (a password's hash, a transaction's figures)
    assert run.stderr == ""
