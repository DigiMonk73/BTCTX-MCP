# The frontend is built on the build machine's own architecture: the output
# is static files, so a multi-arch build doesn't run npm under emulation.
FROM --platform=$BUILDPLATFORM node:24-slim@sha256:55fb5f5a527ea2c5c4a95f963e48ef90aa38c7b346054fdc8ee9957a2b55d205 AS frontend-builder

WORKDIR /app/frontend
# The manifests first, so a source-only change reuses the npm ci layer.
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# The page names its version on every request (vite.config.ts reads it)
COPY VERSION ../VERSION
RUN npm run build

FROM python:3.13-slim@sha256:2d44738ebf4ce5f63b9d9ea871e9c7cfdc0426f7b0c97cac915fd88ded1d86bb AS backend

# Unbuffered, so log lines reach `docker logs` (and StartOS) as they happen.
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
# Database (and the session key beside it) live on the /data volume.
# Without this the DB would land in /app/backend and vanish on update.
ENV DATABASE_FILE=/data/btctx.db

# No system packages added: IRS forms are filled in pure Python (pypdf).
# The base image's own CA bundle is only brought up to date (below).

WORKDIR /app
# The app's own user (#202): BitcoinTX never runs as root. A fixed uid and
# gid, the same in every release, so /data keeps its owner across updates.
RUN groupadd --system --gid 10001 btctx \
 && useradd --system --uid 10001 --gid btctx --no-create-home \
      --home-dir /nonexistent --shell /usr/sbin/nologin btctx
# The ledger is private: only the app's user can read /data.
RUN mkdir -p /data && chown btctx:btctx /data && chmod 700 /data

# The lock: every package, indirect ones too, at a fixed version whose hash
# must match, and only ready-built wheels, so nothing is built (with tools no
# lock pins) during the install.
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --require-hashes --only-binary :all: -r requirements.txt

# The system's CA bundle without the roots distrusted after the eMudhra
# compromise (#638, from Start9): trixie's ca-certificates 20250419+deb13u1
# drops emSign ECC Root CA - G3 and Comodo AAA Services root (Debian
# #1151413). The app's own connections verify with certifi, or a home
# Mempool's one root its owner trusts, never this store; only
# `cli install-draft-forms` (test installs, irs.gov) reads it. Each grep (G3's
# first PEM line) fails the build if the system's store or certifi's still
# holds it, and `test -s` first, so a missing or empty file can't pass.
RUN apt-get update \
 && apt-get install -y --no-install-recommends --only-upgrade ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && SYSTEM=/etc/ssl/certs/ca-certificates.crt && CERTIFI="$(python3 -m certifi)" \
 && test -s "$SYSTEM" && test -s "$CERTIFI" \
 && ! grep -q MIICTjCCAdOgAwIBAgIKPPYHqWhwDtqLhDAKBggqhkjOPQQDAzBr "$SYSTEM" \
 && ! grep -q MIICTjCCAdOgAwIBAgIKPPYHqWhwDtqLhDAKBggqhkjOPQQDAzBr "$CERTIFI"

# VERSION sits where backend/version.py reads it.
COPY backend/ ./backend
COPY VERSION ./VERSION
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist
# Compiled now: the code belongs to root, so the app can't cache it at run time.
RUN python -m compileall -q backend

# Starts as root only to give /data to btctx, then runs the command as btctx.
COPY --chmod=755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["docker-entrypoint.sh"]

EXPOSE 80

# No access log: request lines carry client addresses and dates (?date=...).
# No "server: uvicorn" header on the responses.
# No proxy headers: a client's address is its connection's, never an
# X-Forwarded-For header's (the login throttle counts by address).
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "80", "--no-access-log", "--no-server-header", "--no-proxy-headers"]
