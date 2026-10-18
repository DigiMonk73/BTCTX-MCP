"""
BitcoinTX runs as the image's own user, btctx, never as root (#202), in
Docker and in the StartOS package, which runs the same image through its
start-up script (test_startos_entrypoint_464.py), so the drop to btctx
exists once. These are the parts a file can show; CI's Docker job runs the
image itself (the app's uid, an update from 1.2.8's root-owned /data:
scripts/docker_update_check.sh), and the StartOS VM the package
(docs/STARTOS_COMPATIBILITY.md).
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = (ROOT / "Dockerfile").read_text()
ENTRYPOINT = (ROOT / "docker-entrypoint.sh").read_text()


def test_the_image_has_its_own_user_with_a_fixed_uid():
    assert "groupadd --system --gid 10001 btctx" in DOCKERFILE
    assert "useradd --system --uid 10001 --gid btctx" in DOCKERFILE
    assert "chown btctx:btctx /data && chmod 700 /data" in DOCKERFILE


def test_the_image_starts_through_the_entrypoint_that_drops_root():
    assert 'ENTRYPOINT ["docker-entrypoint.sh"]' in DOCKERFILE
    assert "COPY --chmod=755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh" in DOCKERFILE
    # No USER line: the entrypoint must start as root to take over a volume
    # an older image left root's; StartOS starts it as the image's user (#464)
    assert not re.search(r"^USER\b", DOCKERFILE, re.M)
    drop = "exec setpriv --reuid=btctx --regid=btctx --init-groups"
    assert drop in ENTRYPOINT and "--no-new-privs" in ENTRYPOINT
    # The data folder is /data, or DATABASE_FILE's when it's a mount of its
    # own: never a folder of the image (#446's review)
    assert 'dir=$(dirname -- "${DATABASE_FILE:-/data/btctx.db}")' in ENTRYPOINT
    # A folder written plainly, never /dev, /proc or /sys: "/./x.db",
    # "/data/../x.db", a link the app made or a mounted file such as
    # /etc/hosts could otherwise be handed over (#446's re-checks)
    assert "/dev | /dev/* | /proc | /proc/* | /sys | /sys/*) ;;" in ENTRYPOINT
    plainly = '[ -d "$dir" ] && [ "$(readlink -f -- "$dir")" = "$dir" ] && mountpoint -q -- "$dir"'
    assert plainly in ENTRYPOINT
    # Root runs only the chown, and only when btctx finds a file that isn't
    # its own; the command runs after the drop, or unchanged when Docker
    # started it as another user (--user)
    check = ENTRYPOINT.index("others=$( (as_btctx find \"$data\"")
    chown = ENTRYPOINT.index('chown -R btctx:btctx "$data"')
    assert ENTRYPOINT.index('if [ "$(id -u)" != 0 ]; then\n    exec "$@"') < check < chown
    assert ENTRYPOINT.rstrip().endswith('\nas_btctx "$@"')

