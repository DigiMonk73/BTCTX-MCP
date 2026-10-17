#!/bin/sh
# BitcoinTX runs as the image's own user, btctx (uid 10001), never as root
# (#202). Docker starts this script as root: it gives /data to btctx (a
# volume an image before 1.2.9 made is root's, and so may be a host folder
# mounted there), then runs the command as btctx. It keeps one right, to
# open port 80: inside its own network a container lets any user open it,
# but not with --network host. Started with --user, the command runs as that
# user, unchanged: /data must then be theirs.
set -eu

if [ "$(id -u)" != 0 ]; then
    exec "$@"
fi

if ! chown -R btctx:btctx /data; then
    echo "BitcoinTX: could not give /data to its user btctx (uid 10001)." >&2
    echo "Give the folder or volume mounted at /data to uid 10001 yourself, or start with --user." >&2
    exit 1
fi
exec setpriv --reuid=btctx --regid=btctx --init-groups \
    --inh-caps=-all,+net_bind_service --ambient-caps=-all,+net_bind_service \
    --no-new-privs -- "$@"
