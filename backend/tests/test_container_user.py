"""
BitcoinTX runs as the image's own user, btctx, never as root (#202), in
Docker and in the StartOS package that runs the same image. These are the
parts a file can show; CI's Docker job runs the image itself (the app's
uid, an update from 1.2.8's root-owned /data: scripts/docker_update_check.sh),
and the StartOS VM the package (docs/STARTOS_COMPATIBILITY.md).
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = (ROOT / "Dockerfile").read_text()
ENTRYPOINT = (ROOT / "docker-entrypoint.sh").read_text()
PKG = ROOT / "startos/startos"
MAIN = (PKG / "main.ts").read_text()
UTILS = (PKG / "utils.ts").read_text()


def test_the_image_has_its_own_user_with_a_fixed_uid():
    assert "groupadd --system --gid 10001 btctx" in DOCKERFILE
    assert "useradd --system --uid 10001 --gid btctx" in DOCKERFILE
    assert "chown btctx:btctx /data && chmod 700 /data" in DOCKERFILE


def test_the_image_starts_through_the_entrypoint_that_drops_root():
    assert 'ENTRYPOINT ["docker-entrypoint.sh"]' in DOCKERFILE
    assert "COPY --chmod=755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh" in DOCKERFILE
    # No USER line: the entrypoint must start as root to take over a volume
    # an older image left root's, and StartOS runs every step as named.
    assert not re.search(r"^USER\b", DOCKERFILE, re.M)
    assert "chown -R btctx:btctx /data" in ENTRYPOINT
    drop = "exec setpriv --reuid=btctx --regid=btctx --init-groups"
    assert drop in ENTRYPOINT and "--no-new-privs" in ENTRYPOINT
    # Root runs only the chown: the command itself only after the drop, or
    # unchanged when Docker started it as another user (--user)
    assert ENTRYPOINT.index('if [ "$(id -u)" != 0 ]; then\n    exec "$@"') < ENTRYPOINT.index("chown -R")
    assert ENTRYPOINT.rstrip().endswith('--no-new-privs -- "$@"')


def test_startos_drops_to_the_same_user_keeping_only_port_80():
    assert "export const APP_USER = 'btctx'" in UTILS
    body = UTILS.split("export function asAppUser")[1].split("\n}\n")[0]
    keep = "-all,+net_bind_service"
    assert re.findall(r"['`]([^'`]+)['`]", body) == [
        "setpriv",
        "--reuid=${APP_USER}",
        "--regid=${APP_USER}",
        "--init-groups",
        f"--inh-caps={keep}",
        f"--ambient-caps={keep}",
        "--no-new-privs",
        "--",
    ]
    # The image drops the same way
    assert f"--inh-caps={keep} --ambient-caps={keep}" in ENTRYPOINT


def test_startos_gives_the_volume_to_the_app_at_every_start_as_root():
    # Start9's main.md, "Oneshots": chown as root, before anything else
    assert "export const OWN_DATA: [string, ...string[]] = [\n  'chown',\n  '-R',\n  `${APP_USER}:${APP_USER}`,\n  '/data',\n]" in UTILS
    chown = MAIN.index(".addOneshot('chown'")
    migrate = MAIN.index(".addOneshot('migrate'")
    webui = MAIN.index(".addDaemon('webui'")
    assert chown < migrate < webui
    assert "exec: { command: OWN_DATA, user: 'root' },\n        requires: []," in MAIN[chown:migrate]
    assert "user: APP_USER,\n        },\n        requires: ['chown']," in MAIN[migrate:webui]
    assert "command: asAppUser([" in MAIN[webui:] and "user: 'root'," in MAIN[webui:]


def test_every_cli_command_runs_as_the_app_user_after_the_chown():
    # backend.cli is run in exactly two places: main's migrate step and
    # runAppCli (Set Login Credentials, Recalculate Ledger, the init's
    # default-login check)
    runs = [p for p in PKG.rglob("*.ts") if "'backend.cli'" in p.read_text()]
    assert sorted(p.name for p in runs) == ["main.ts", "utils.ts"]
    cli = UTILS.split("export async function runAppCli")[1].split("\n}\n")[0]
    assert cli.index("sub.execFail(OWN_DATA, { user: 'root'") < cli.index("'backend.cli'")
    assert "user: APP_USER," in cli.split("'backend.cli'")[1]
