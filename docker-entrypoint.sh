#!/bin/sh
# BitcoinTX runs as the image's own user, btctx (uid 10001), never as root
# (#202). Docker starts this script as root: it gives the data folder to
# btctx when something in it isn't btctx's (a volume an image before 1.2.9
# made is root's, and so may be a host folder mounted there), then runs the
# command as btctx. It keeps one right, to open port 80: inside its own
# network a container lets any user open it, but not with --network host.
# Started with --user, the command runs as that user, unchanged: the data
# folder must then be theirs.
set -eu

if [ "$(id -u)" != 0 ]; then
    exec "$@"
fi

# The data folder: DATABASE_FILE's when that is a folder mounted on its own
# (a volume or a host folder; never a mounted file), written plainly (no ".", ".." or link on the way: those
# could name / or a folder the app chose), else /data. Never a folder of the
# image itself, nor the kernel's.
data=/data
dir=$(dirname -- "${DATABASE_FILE:-/data/btctx.db}")
case "$dir" in
    /dev | /dev/* | /proc | /proc/* | /sys | /sys/*) ;;
    /?*) if [ -d "$dir" ] && [ "$(readlink -f -- "$dir")" = "$dir" ] && mountpoint -q -- "$dir"; then data=$dir; fi ;;
esac

# Runs a command as btctx, keeping only the right to open port 80. It
# replaces the shell: run it in a subshell to come back.
as_btctx() {
    exec setpriv --reuid=btctx --regid=btctx --init-groups \
        --inh-caps=-all,+net_bind_service --ambient-caps=-all,+net_bind_service \
        --no-new-privs -- "$@"
}
refuse() {
    echo "BitcoinTX: $1" >&2
    echo "Started as root, it needs the capabilities CHOWN, DAC_OVERRIDE, SETUID, SETGID and" >&2
    echo "NET_BIND_SERVICE (Docker's defaults); or give $data to uid 10001 and start with --user 10001:10001." >&2
    exit 1
}

(as_btctx true) 2>/dev/null || refuse "it could not switch to its user btctx (uid 10001)."
# Handed over only when btctx finds something in it that isn't its own: a
# start after the first needs none of root's rights over the files, and root
# doesn't walk a folder the app controls.
others=$( (as_btctx find "$data" \( \! -user btctx -o \! -group btctx \) -print -quit) 2>/dev/null) || true
if [ -n "$others" ]; then
    chown -R btctx:btctx "$data" || refuse "it could not give $data to its user btctx (uid 10001)."
fi
as_btctx "$@"
