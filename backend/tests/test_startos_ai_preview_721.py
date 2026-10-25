"""
StartOS's Connect an AI Assistant on a 2.0 pre-release (#721): the server
name and the connector by the app's own rule (Settings, `aiSetup.ts`'s
`serverName` and `serverPackage`). An alpha or a beta names the server
"bitcointx-preview", so the AI app's entry for the tester's own BitcoinTX
("bitcointx") is never replaced, and pins its connector in PEP 440's form
(2.0.0aN, 2.0.0bN), as PyPI lists it and the release notes say it; a
release keeps "bitcointx" and btctx-mcp==X.Y.Z.

The file checks run everywhere; the helper itself runs with Node, where
Node can run TypeScript (22.6 on: CI's Python job sets one up).
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ACTION = (ROOT / "startos/startos/actions/connectAi.ts").read_text()
CURRENT = (ROOT / "startos/startos/versions/current.ts").read_text()
AI_SETUP = (ROOT / "frontend/src/utils/aiSetup.ts").read_text()


def test_the_action_names_no_server_of_its_own():
    # alpha.2's action wrote `bitcointx` and `claude mcp add --scope user
    # bitcointx` whatever the version
    assert not re.search(r"\bbitcointx\s*:", ACTION)
    assert "--scope user bitcointx" not in ACTION
    assert "aiConnector(" in ACTION


def test_the_names_are_the_apps():
    for name in ("bitcointx", "bitcointx-preview"):
        assert f'"{name}"' in AI_SETUP
        assert f"'{name}'" in ACTION


def _node_runs_typescript() -> bool:
    if not shutil.which("node"):
        return False
    # An older Node refuses the option ("bad option")
    probe = subprocess.run(["node", "--experimental-strip-types", "-e", ""], capture_output=True)
    return probe.returncode == 0


def _helper() -> str:
    """aiConnector and its pattern, as connectAi.ts has them (they import nothing)."""
    start = ACTION.index("const PRERELEASE")
    end = ACTION.index("\n}\n", ACTION.index("function aiConnector")) + 3
    return ACTION[start:end]


def _package_version() -> str:
    """The package's own version, current.ts's `version: 'X:revision'`, without its revision."""
    return re.search(r"version: '([^':]+):\d+'", CURRENT).group(1)


VERSIONS = ["2.0.0-alpha.2", "2.0.0-alpha.12", "2.0.0-beta.1", "2.0.0", "1.2.10", "2.1.0"]


@pytest.mark.skipif(not _node_runs_typescript(), reason="needs Node 22.6 or later")
def test_a_pre_release_names_its_server_apart_and_pins_its_connector_as_pypi_does(tmp_path):
    script = tmp_path / "connector.mts"
    versions = [*VERSIONS, _package_version()]
    script.write_text(_helper() + f"\nconsole.log(JSON.stringify({json.dumps(versions)}.map(aiConnector)))\n")
    run = subprocess.run(
        ["node", "--experimental-strip-types", "--no-warnings", str(script)],
        capture_output=True, text=True, timeout=60,
    )
    assert run.returncode == 0, run.stderr
    *named, this_package = json.loads(run.stdout)
    assert named == [
        {"name": "bitcointx-preview", "pkg": "btctx-mcp==2.0.0a2"},
        {"name": "bitcointx-preview", "pkg": "btctx-mcp==2.0.0a12"},
        {"name": "bitcointx-preview", "pkg": "btctx-mcp==2.0.0b1"},
        {"name": "bitcointx", "pkg": "btctx-mcp==2.0.0"},
        {"name": "bitcointx", "pkg": "btctx-mcp==1.2.10"},
        {"name": "bitcointx", "pkg": "btctx-mcp==2.1.0"},
    ]
    # This package's own: on a pre-release, never the tester's own BitcoinTX's name
    pre = re.fullmatch(r"(\d+\.\d+\.\d+)-(alpha|beta)\.(\d+)", _package_version())
    assert this_package == (
        {"name": "bitcointx-preview", "pkg": f"btctx-mcp=={pre[1]}{pre[2][0]}{pre[3]}"} if pre
        else {"name": "bitcointx", "pkg": f"btctx-mcp=={_package_version()}"})
