#!/usr/bin/env python3
"""
The release gate's sign-in and password page checks, in one command (#935,
for #924): docs/AGENT-TESTS.md's AUTH-1 to AUTH-3, BAK-2, BAK-3, SEC-8 and
END-2, driven in a browser (scripts/gate/pages.mjs), PASS or FAIL per step
with what it saw.

    scripts/gate/pages.py IMAGE [OUT_DIR]
    scripts/gate/pages.py btctx:ci

The candidate's own image, as the StartOS package runs it: a new volume; the
login made while the app is stopped by Set Login Credentials' own command
(INS-3: `admin` and a new random password); the schema step; then the server,
with the package's settings and the price source left to the app (INS-4's
"Decide in BitcoinTX instead"). On 127.0.0.1 only, port $PORT (9553): these
are test logins, typed only into a page on this computer, never into the test
VM's `.local` address. The owner's BitcoinTX (8765) and Preview (8767) are
checked before and after and must answer the same. The container and its
volume are removed at the end; what each step saw, a screenshot of each FAIL
and the server's log stay in OUT_DIR (a new temp folder by default).

Needs Docker, the repository's .venv (for the golden loader) and the
frontend's Playwright with Chromium (`cd frontend && npm ci && npx playwright
install chromium`). Only ever a throwaway install: never a real ledger.
"""

import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# The steps, in the order pages.mjs runs them: each one docs/AGENT-TESTS.md's
STEPS = ("AUTH-1", "AUTH-2", "AUTH-3", "BAK-2", "BAK-3", "SEC-8", "END-2")
OWNER_PORTS = (8765, 8767)  # the owner's BitcoinTX and BitcoinTX Preview
THIS_COMPUTER = ("127.0.0.1", "localhost")
# What the StartOS package gives the app (startos/startos/utils.ts, appEnv),
# with no price settings: INS-4 leaves the choice to the app
STARTOS_ENV = {"DATABASE_FILE": "/data/btctx.db", "LOG_LEVEL": "INFO", "BTCTX_HOST": "startos"}
WAIT_LIMIT = 300  # seconds for the server to answer; it usually takes under 30


def say(text):
    print(time.strftime("%H:%M:%SZ", time.gmtime()), text, flush=True)


def local_url(url):
    """The URL without its last slash, if it's a page on this computer; else refused.
    A test login goes only to 127.0.0.1 or localhost (#924), never the VM's name."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or parts.hostname not in THIS_COMPUTER or "@" in parts.netloc:
        raise SystemExit(f"refused: {url}: test logins go only to a page on this computer, "
                         f"{' or '.join(THIS_COMPUTER)}")
    return url.rstrip("/")


def health(port):
    """What /api/health answers on 127.0.0.1:port, or "none"."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}/api/health", timeout=2) as answer:
            return answer.read().decode()
    except (urllib.error.URLError, OSError):
        return "none"


def owners():
    return " ".join(f"{port}={health(port)}" for port in OWNER_PORTS)


def port_taken(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def docker(*args, stdin=None, check=True):
    """A docker command's result; with check, a failure stops the run saying what docker said."""
    done = subprocess.run(["docker", *args], input=stdin, capture_output=True, text=True)
    if check and done.returncode:
        raise SystemExit(f"FAIL docker {args[0]}: {(done.stderr or done.stdout).strip()[-600:]}")
    return done


def env_args(env):
    return [arg for name, value in env.items() for arg in ("-e", f"{name}={value}")]


def app_command(image, volume, *command, stdin=None):
    """A BitcoinTX command in a container of its own on the volume, as the
    package's actions run one while the service is stopped."""
    docker("run", "--rm", "-i", "-v", f"{volume}:/data", *env_args(STARTOS_ENV), image, *command, stdin=stdin)


def wait_for(url):
    began, report = time.monotonic(), 30
    while health_at(url) == "none":
        waited = time.monotonic() - began
        if waited >= WAIT_LIMIT:
            raise SystemExit(f"FAIL the candidate didn't answer in {WAIT_LIMIT // 60} minutes")
        if waited >= report:
            say(f"still waiting for the candidate ({int(waited)} s; it usually takes under 30)")
            report += 30
        time.sleep(1)


def health_at(url):
    return health(urllib.parse.urlsplit(url).port)


def start(image, run, port, password):
    """The volume and the running candidate, set up as StartOS sets it up."""
    docker("volume", "create", run)
    say("Set Login Credentials' own command, while the app is stopped (INS-3)")
    app_command(image, run, "python", "-m", "backend.cli", "set-password", "--username", "admin",
                "--password-stdin", stdin=password + "\n")
    app_command(image, run, "python", "-m", "backend.cli", "migrate")
    docker("run", "-d", "--name", run, "-p", f"127.0.0.1:{port}:80", "-v", f"{run}:/data",
           *env_args(STARTOS_ENV), image)


def remove(run):
    docker("rm", "-fv", run, check=False)
    docker("volume", "rm", run, check=False)


def browser_steps(url, out, run, password):
    """pages.mjs's run: its exit code, and what it reported per step."""
    python = ROOT / ".venv" / "bin" / "python"
    env = {**os.environ, "GATE_PASSWORD": password, "GATE_CONTAINER": run,
           "GATE_PY": str(python if python.exists() else sys.executable)}
    code = subprocess.run(["node", str(ROOT / "scripts" / "gate" / "pages.mjs"), url, str(out)], env=env).returncode
    results = out / "results.json"
    return code, json.loads(results.read_text()) if results.exists() else []


def verdict(reported):
    """PASS only when every step ran once and passed; a missing step fails."""
    seen = [r["id"] for r in reported]
    failed = [r["id"] for r in reported if r["verdict"] != "PASS"]
    missing = [step for step in STEPS if step not in seen]
    unknown = [step for step in seen if step not in STEPS]
    for step in missing:
        say(f"FAIL {step}: never reported")
    for step in unknown:
        say(f"FAIL {step}: not one of this script's steps")
    ok = not (failed or missing or unknown) and len(seen) == len(STEPS)
    say(f"{'PASS' if ok else 'FAIL'} {len(STEPS) - len(set(failed + missing))} of {len(STEPS)} steps passed")
    return ok


def main(argv):
    if len(argv) not in (2, 3):
        print(__doc__.split("\n\n")[1])
        return 2
    image = argv[1]
    out = Path(argv[2]) if len(argv) == 3 else Path(tempfile.mkdtemp(prefix="btctx-pages."))
    out.mkdir(parents=True, exist_ok=True)
    port = int(os.environ.get("PORT", "9553"))
    url = local_url(f"http://127.0.0.1:{port}")
    if port in OWNER_PORTS:
        raise SystemExit(f"FAIL port {port} is the owner's: choose another")
    if port_taken(port):
        raise SystemExit(f"FAIL port {port} is in use: stop what runs there, or set PORT")
    before = owners()
    say("needs from you: nothing (Docker and a browser on this computer; under a minute)")
    say(f"the owner's ports before: {before}")
    run = f"btctx-pages-{os.getpid()}"
    password = secrets.token_urlsafe(18)  # 24 characters, as Set Login Credentials makes
    try:
        start(image, run, port, password)
        wait_for(url)
        say(f"{image} answers on {url}: {health_at(url)} (container and volume {run})")
        code, reported = browser_steps(url, out, run, password)
        log = docker("logs", run, check=False)
        (out / "server.log").write_text((log.stdout + log.stderr).replace(password, "<the test login>"))
    finally:
        remove(run)
    after = owners()
    say(f"the owner's ports after: {after}")
    if after != before:
        say(f"FAIL the owner's ports changed: {before} -> {after}")
        return 1
    say(f"what each step saw, the screenshots and the server's log: {out}")
    return 0 if code == 0 and verdict(reported) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
