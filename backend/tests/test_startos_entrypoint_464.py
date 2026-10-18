"""
The StartOS package runs the image's own start-up script, docker-entrypoint.sh,
for every step (#464; Start9's main.md, "Using Upstream Entrypoint", and
recipe-prebuilt-image.md, step 4): the migrate oneshot, the web server and
every backend.cli command an action or init runs. The script hands /data to
btctx when needed and drops to it (test_container_user.py), so the package
keeps no copy of that: no chown step, no setpriv, no command of its own for
the web server. The StartOS VM runs it (docs/STARTOS_COMPATIBILITY.md).
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = (ROOT / "Dockerfile").read_text()
PKG = ROOT / "startos/startos"
MAIN = (PKG / "main.ts").read_text()
UTILS = (PKG / "utils.ts").read_text()


def _dockerfile_list(instruction: str) -> list[str]:
    return json.loads(re.search(rf"^{instruction} (\[.*\])$", DOCKERFILE, re.M).group(1))


def test_main_runs_the_migration_then_the_web_server_through_the_script():
    migrate = MAIN.index(".addOneshot('migrate'")
    webui = MAIN.index(".addDaemon('webui'")
    assert migrate < webui
    assert MAIN.count(".addOneshot(") == 1 and MAIN.count(".addDaemon(") == 1
    override = re.search(r"command: sdk\.useEntrypoint\(\[([^\]]*)\]\),", MAIN[migrate:webui]).group(1)
    assert re.findall(r"'([^']+)'", override) == ["python", "-m", "backend.cli", "migrate"]
    assert "requires: []," in MAIN[migrate:webui]
    # The image's CMD, unchanged: uvicorn's flags live in the Dockerfile only
    assert "exec: { command: sdk.useEntrypoint(), env }," in MAIN[webui:]
    assert "requires: ['migrate']," in MAIN[webui:]
    assert "uvicorn" not in MAIN


def test_main_runs_each_step_as_the_image_user_in_its_folder():
    # No user or cwd: the script starts as root, the image's user (no USER
    # line), in its WORKDIR, as `docker run` starts it
    steps = MAIN[MAIN.index("sdk.Daemons.of(effects)"):]
    assert not re.search(r"^\s*(user|cwd):", steps, re.M)
    assert not re.search(r"^USER\b", DOCKERFILE, re.M)
    assert re.findall(r"^WORKDIR (\S+)$", DOCKERFILE, re.M)[-1] == "/app"


def test_every_cli_command_runs_through_the_image_entrypoint():
    # backend.cli runs in exactly two places: main's migrate step and
    # runAppCli (Set Login Credentials, Recalculate Ledger, the init's
    # default-login check)
    runs = sorted(p.name for p in PKG.rglob("*.ts") if "'backend.cli'" in p.read_text())
    assert runs == ["main.ts", "utils.ts"]
    cli = UTILS.split("export async function runAppCli")[1].split("\n}\n")[0]
    assert cli.count("sub.execFail(") == 1
    command = re.search(r"sub\.execFail\(\s*\[([^\]]*)\]", cli).group(1)
    words = re.findall(r"'([^']+)'", command)
    assert words[: len(_dockerfile_list("ENTRYPOINT"))] == _dockerfile_list("ENTRYPOINT")
    assert words[len(_dockerfile_list("ENTRYPOINT")):] == ["python", "-m", "backend.cli"]
    assert "...args" in command
    options = cli.split("sub.execFail(")[1]
    assert not re.search(r"\b(user|cwd):", options)
    # The price variables (Recalculate Ledger) and the password on stdin
    assert re.search(r"[{,]\s*env\b", options) and "input: opts.input" in options


def test_the_package_keeps_no_copy_of_the_drop_to_btctx():
    for f in PKG.rglob("*.ts"):
        text = f.read_text()
        for gone in ("setpriv", "chown", "OWN_DATA", "asAppUser", "APP_USER", "net_bind_service"):
            assert gone not in text, f"{gone} in {f.relative_to(ROOT)}"
    assert _dockerfile_list("ENTRYPOINT") == ["docker-entrypoint.sh"]
    assert _dockerfile_list("CMD")[:2] == ["uvicorn", "backend.main:app"]


def test_the_image_command_listens_where_the_package_looks():
    # The interface and the health check use uiPort; the image's CMD names
    # the port the web server opens
    assert "export const uiPort = 80\n" in UTILS
    cmd = _dockerfile_list("CMD")
    assert cmd[cmd.index("--port") + 1] == "80" and cmd[cmd.index("--host") + 1] == "0.0.0.0"
