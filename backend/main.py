#!/usr/bin/env python
"""
The BitcoinTX web app: FastAPI with the session login (or the AI key on the
routes open to it), the security middleware, the API routers, login and
logout, the health check, and the built frontend served from frontend/dist.
"""

import os
import logging
from typing import Optional
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)
from starlette.middleware.sessions import SessionMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

# Before the imports below read the environment.
load_dotenv()

# The Mac app bundles its own copy (BTCTX_FRONTEND_DIST).
frontend_dist = os.environ.get(
    "BTCTX_FRONTEND_DIST",
    os.path.join(os.path.dirname(__file__), "../frontend/dist")
)

from backend.database import DATABASE_FILE
from backend.secret_key import load_secret_key

# Signs the session cookie. Never a value from this repo — see secret_key.py
SECRET_KEY = load_secret_key(os.path.dirname(DATABASE_FILE))


def cors_origins(raw: str | None) -> list[str]:
    """
    Other origins whose pages may call the API with the login cookie
    (CORS_ALLOW_ORIGINS, comma-separated). None by default: the app serves
    its own pages, and the Vite dev server proxies /api (vite.config.ts).
    """
    return [origin.strip() for origin in (raw or "").split(",") if origin.strip()]


ALLOWED_ORIGINS = cors_origins(os.getenv("CORS_ALLOW_ORIGINS"))

from backend.database import init_db, get_db, SessionLocal
from backend.session_auth import require_login, session_user_id, start_session
from backend.security_headers import CrossSiteGuardMiddleware, SecurityHeadersMiddleware
from backend.services import ai_key


def _load_network_settings() -> None:
    """Privacy & network settings (live data, own mempool server, proxy)."""
    from backend.services import outbound

    db = SessionLocal()
    try:
        outbound.load(db)
    except Exception:
        logger.exception("Could not read the network settings; using the defaults")
    finally:
        db.close()


def _prepare_first_run() -> None:
    """The setup code while the account has the default login (first_run.py)."""
    from backend.services import first_run

    db = SessionLocal()
    try:
        first_run.prepare(db)
    except Exception:
        logger.exception("Could not prepare the first-run setup code")
    finally:
        db.close()


def _sync_ai_key_file() -> None:
    """Mac app: write mcp.json (the AI key) for this run."""
    if ai_key.mode() != "mac":
        return
    db = SessionLocal()
    try:
        ai_key.sync(db)
    except Exception:
        logger.exception("Could not write the AI key file")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """At startup: migrate the schema and seed the defaults, then the setup
    code, the network settings and (Mac app) the AI key file."""
    init_db()
    _prepare_first_run()
    _load_network_settings()
    _sync_ai_key_file()
    yield

app = FastAPI(
    title="BitcoinTX Portfolio Tracker API",
    description=(
        "API for managing Bitcoin transactions/accounts with a "
        "double-entry system and FIFO cost basis. Session-based auth."
    ),
    version="1.0",
    debug=os.getenv("DEBUG", "false").lower() == "true",
    redirect_slashes=True,
    lifespan=lifespan,
    # The interactive API docs describe every endpoint to anyone who asks;
    # only with DEBUG.
    docs_url="/docs" if os.getenv("DEBUG", "false").lower() == "true" else None,
    redoc_url="/redoc" if os.getenv("DEBUG", "false").lower() == "true" else None,
    openapi_url="/openapi.json" if os.getenv("DEBUG", "false").lower() == "true" else None,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="btc_session_id",
    same_site="lax",
    # Secure is added per request when it came over HTTPS (StartOS's proxy):
    # backend/security_headers.py. A fixed https_only would break the plain
    # HTTP installs (Mac app on 127.0.0.1, Docker on a LAN).
    https_only=False,
)
# A POST, PUT, PATCH or DELETE sent by another site's page (or another app on
# the same host) with the owner's cookie is refused (403).
app.add_middleware(CrossSiteGuardMiddleware, trusted_origins=ALLOWED_ORIGINS)
# Outside those, so it also sees the session cookie: CSP, no-referrer, nosniff,
# no framing, Secure cookie over HTTPS.
app.add_middleware(SecurityHeadersMiddleware)

if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

from starlette.responses import JSONResponse


@app.exception_handler(StarletteHTTPException)
async def spa_fallback_handler(request: Request, exc: StarletteHTTPException):
    """
    Handle 404 errors for SPA routing.

    When a user navigates directly to a client-side route (e.g., /dashboard),
    StaticFiles raises a 404 because no such file exists. This handler
    catches those 404s and serves index.html, allowing React Router to
    handle the route on the client side.

    API routes (/api/*) are excluded - they should return proper JSON errors.
    So are missing files (/favicon.ico, a stale /assets/*.js): a 404, not the
    page with 200 (none of the app's routes has a dot).
    """
    path = request.url.path
    is_api = path == "/api" or path.startswith("/api/")
    is_file = path.startswith("/assets/") or "." in path.rsplit("/", 1)[-1]
    if exc.status_code == 404 and not is_api and not is_file:
        index_path = os.path.join(frontend_dist, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path, media_type="text/html")

    # For API routes or non-404 errors, return JSON response (with the
    # exception's headers, e.g. Retry-After on a 429)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail or "Error"},
        headers=getattr(exc, "headers", None),
    )


def get_current_user(request: Request, db: Session = Depends(get_db)):
    """
    Auth dependency: a logged-in session, or the AI key
    (Authorization: Bearer <key>, backend/services/ai_key.py) on the routes
    it may use. A valid key anywhere else is 403.
    """
    # Session auth (browser/frontend); a session from before a password
    # change is cleared (backend/session_auth.py)
    user_id = session_user_id(request, db)
    if user_id:
        return user_id
    token = ai_key.bearer_token(request.headers.get("authorization"))
    if token is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        ai_key.check_key(token, request.client.host if request.client else None, db)
    except ai_key.KeyRefused as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    if not ai_key.key_may_use(request.method, request.url.path):
        logger.info("AI key refused: %s %s isn't open to it", request.method, request.url.path)
        raise HTTPException(status_code=403, detail=ai_key.NOT_ALLOWED)
    return "ai_key"


def require_login_dependency(request: Request, db: Session = Depends(get_db)) -> int:
    """A logged-in session only, never the AI key (debug routes)."""
    return require_login(request, db)


from backend.routers import transaction, user, account, calculation, bitcoin, reports, backup, csv_import, river_import, entry_import, settings, review

app.include_router(transaction.router, prefix="/api/transactions", tags=["transactions"], dependencies=[Depends(get_current_user)])
app.include_router(user.router, prefix="/api/users", tags=["users"])  # No auth — register must work
app.include_router(account.router, prefix="/api/accounts", tags=["accounts"], dependencies=[Depends(get_current_user)])
app.include_router(calculation.router, prefix="/api/calculations", tags=["calculations"], dependencies=[Depends(get_current_user)])
app.include_router(bitcoin.router, prefix="/api/bitcoin", tags=["Bitcoin"], dependencies=[Depends(get_current_user)])
app.include_router(reports.reports_router, prefix="/api/reports", tags=["reports"], dependencies=[Depends(get_current_user)])
app.include_router(backup.router, prefix="/api/backup", tags=["backup"], dependencies=[Depends(get_current_user)])
app.include_router(csv_import.router, prefix="/api/import", tags=["import"], dependencies=[Depends(get_current_user)])
app.include_router(river_import.router, prefix="/api/import/river", tags=["import"], dependencies=[Depends(get_current_user)])
app.include_router(entry_import.router, prefix="/api/import/entries", tags=["import"], dependencies=[Depends(get_current_user)])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"], dependencies=[Depends(get_current_user)])
app.include_router(review.router, prefix="/api/review", tags=["review"], dependencies=[Depends(get_current_user)])

# Debug routes: a logged-in session only, never the AI key.
try:
    from backend.routers import debug
    app.include_router(debug.router, prefix="/api/debug", tags=["debug"], dependencies=[Depends(require_login_dependency)])
except ImportError:
    print(
        "WARNING: Could not import 'debug' router. If you need debug features, "
        "ensure 'backend/routers/debug.py' exists."
    )


@app.get("/api/protected")
def read_protected_route(current_user: str = Depends(get_current_user)):
    """200 when logged in (or with the AI key), 401 otherwise: the frontend
    asks it whether to show the login page."""
    return {"message": f"Hello, user {current_user}. You have access to this route!"}


class LoginRequest(BaseModel):
    """
    Schema for login JSON:
      { "username": "someName", "password": "somePass" }
    plus setup_code while an install still has the default login.
    """
    username: str
    password: str
    setup_code: Optional[str] = None

from backend.services.user import get_user_by_username
from backend.services import first_run, login_throttle


@app.post("/api/login")
def login(
    login_req: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Start a session for a correct username and password.
    Repeated failures are answered 429 for a while (login_throttle.py).
    The default admin/password login also needs the setup code (Docker and
    source installs before they're claimed; first_run.py): anyone who can
    reach a fresh install knows that login.
    """
    login_throttle.check(request)
    user = get_user_by_username(login_req.username, db)
    # For security, don't reveal which part is invalid
    if not user or not user.verify_password(login_req.password):
        login_throttle.failed(request)
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    if first_run.needs_code(user) and not first_run.check_code(login_req.setup_code):
        login_throttle.failed(request)
        raise HTTPException(status_code=403, detail=first_run.DEFAULT_LOGIN_REFUSED)

    login_throttle.succeeded(request)
    start_session(request, user)
    return {"detail": f"Logged in as {user.username}"}


@app.post("/api/logout")
def logout(request: Request, response: Response):
    """End the session."""
    request.session.clear()
    return {"detail": "Logged out successfully"}

# Health check (public: used by StartOS and container probes)
from backend.migrate import head_revision, stamped_revision
from backend.version import app_version


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    """
    200 when the database answers and its schema is at the version this code
    expects; 503 otherwise. Reveals nothing about the ledger.
    """
    head = head_revision()
    try:
        schema = stamped_revision(db.connection())
    except Exception as e:
        logger.warning("Health check: database unreachable: %s", e)
        return JSONResponse(
            status_code=503,
            content={"status": "error", "detail": "database unreachable", "version": app_version()},
        )
    ok = schema == head
    return JSONResponse(
        status_code=200 if ok else 503,
        content={
            "status": "ok" if ok else "error",
            "version": app_version(),
            "schema": schema,
            **({} if ok else {"detail": f"database schema is {schema}, expected {head}"}),
        },
    )

from fastapi.staticfiles import StaticFiles

# html=True serves index.html for "/" and folders only; spa_fallback_handler
# serves it for the frontend's own routes.
app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
