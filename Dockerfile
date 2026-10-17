# The frontend is built on the build machine's own architecture: the output
# is static files, so a multi-arch build doesn't run npm under emulation.
FROM --platform=$BUILDPLATFORM node:24-slim@sha256:a5f4366e834695d5f363b920c104953a535d3a9864d1bdf74566a0ebe01daee5 AS frontend-builder

WORKDIR /app/frontend
# The manifests first, so a source-only change reuses the npm ci layer.
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce AS backend

# Unbuffered, so log lines reach `docker logs` (and StartOS) as they happen.
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
# Database (and the session key beside it) live on the /data volume.
# Without this the DB would land in /app/backend and vanish on update.
ENV DATABASE_FILE=/data/btctx.db

# No system packages needed: IRS forms are filled in pure Python (pypdf)

WORKDIR /app
# The ledger is private: only the app's user (root here) can read /data.
RUN mkdir -p /data && chmod 700 /data

# The lock: every package, indirect ones too, at a fixed version whose hash
# must match, and only ready-built wheels, so nothing is built (with tools no
# lock pins) during the install.
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --require-hashes --only-binary :all: -r requirements.txt

# VERSION sits where backend/version.py reads it.
COPY backend/ ./backend
COPY VERSION ./VERSION
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

EXPOSE 80

# No access log: request lines carry client addresses and dates (?date=...).
# No "server: uvicorn" header on the responses.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "80", "--no-access-log", "--no-server-header"]
