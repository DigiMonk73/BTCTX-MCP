#!/usr/bin/env python
"""
backend/main.py

Sets up the FastAPI application for BitcoinTX, a double-entry Bitcoin portfolio tracker.

Key Roles:
 - Loads environment variables & configures session-based authentication
 - Adds CORS middleware for frontend integration
 - Includes 'transaction', 'account', 'user', 'bitcoin', and calculation routers
 - Serves the built React/Vite frontend from 'frontend/dist'
"""

import os
import hmac
import logging
from typing import Optional
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)
from starlette.middleware.sessions import SessionMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

# Load environment variables from a .env file at the project root
load_dotenv()

# ---------------------------------------------------------
# Frontend dist path (needed early for SPA fallback handler)
# Supports BTCTX_FRONTEND_DIST env var for desktop app bundling
# ---------------------------------------------------------
frontend_dist = os.environ.get(
    "BTCTX_FRONTEND_DIST",
    os.path.join(os.path.dirname(__file__), "../frontend/dist")
)

# ---------------------------------------------------------
# Session Configuration
# ---------------------------------------------------------
from backend.database import DATABASE_FILE
from backend.secret_key import load_secret_key

# Signs the session cookie. Never a value from this repo — see secret_key.py
SECRET_KEY = load_secret_key(os.path.dirname(DATABASE_FILE))
API_KEY = os.getenv("API_KEY")

# Default CORS origins if none specified (dev environment)
default_origins = (
    "http://127.0.0.1:3000,"
    "http://localhost:3000,"
    "http://127.0.0.1:5173,"
    "http://localhost:5173,"
    "http://127.0.0.1:8000,"
    "http://localhost:8000"
)
raw_origins = os.getenv("CORS_ALLOW_ORIGINS", default_origins)
ALLOWED_ORIGINS = [origin.strip() for origin in raw_origins.split(",")]

# ---------------------------------------------------------
# Database import (needed before lifespan)
# ---------------------------------------------------------
from backend.database import init_db, get_db, SessionLocal
from backend.session_auth import require_login, session_user_id, start_session
from backend.security_headers import SecurityHeadersMiddleware
from backend.services import mcp_key


def _sync_mcp_key() -> None:
    """Mac app: write mcp.json (the AI assistant key) for this run."""
    if not mcp_key.enabled():
        return
    db = SessionLocal()
    try:
        mcp_key.sync(db)
    except Exception:
        logger.exception("Could not write the AI assistant key file")
    finally:
        db.close()

# ---------------------------------------------------------
# Lifespan context manager for startup/shutdown
# ---------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup/shutdown events.
    Migrates the database schema and seeds defaults when FastAPI starts.
    """
    # Startup
    init_db()
    _sync_mcp_key()
    yield
    # Shutdown (nothing needed currently)

# ---------------------------------------------------------
# Initialize the FastAPI application
# ---------------------------------------------------------
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

# ---------------------------------------------------------
# Add Session Middleware
# ---------------------------------------------------------
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
# Outermost, so it also sees the session cookie: CSP, no-referrer, nosniff,
# no framing, Secure cookie over HTTPS.
app.add_middleware(SecurityHeadersMiddleware)

# ---------------------------------------------------------
# CORS Middleware
# ---------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # Or ["*"] in dev if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# SPA Fallback Exception Handler
# ---------------------------------------------------------
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
    """
    path = request.url.path
    if exc.status_code == 404 and not (path == "/api" or path.startswith("/api/")):
        index_path = os.path.join(frontend_dist, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path, media_type="text/html")

    # For API routes or non-404 errors, return JSON response
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail or "Error"}
    )

# ---------------------------------------------------------
# Auth Dependency (must be defined before router includes)
# ---------------------------------------------------------
def get_current_user(
    request: Request,
    x_api_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> str:
    """
    Auth dependency: session cookie, API key, or (Mac app only) the AI
    assistant key.
    - Browser/frontend: session cookie (user_id in session)
    - Programmatic access (e.g., Telegram bot): X-API-Key header
    - The local MCP server: Authorization: Bearer <key from mcp.json>
      (backend/services/mcp_key.py; this computer only)
    """
    # Session auth (browser/frontend); a session from before a password
    # change is cleared (backend/session_auth.py)
    user_id = session_user_id(request, db)
    if user_id:
        return user_id
    # API key auth (programmatic access)
    if API_KEY and x_api_key and hmac.compare_digest(x_api_key, API_KEY):
        return "api_key_user"
    if mcp_key.request_has_valid_key(request, db):
        return "mcp_key"
    detail = getattr(request.state, "mcp_key_refusal", None) or "Not authenticated"
    raise HTTPException(status_code=401, detail=detail)

def require_login_dependency(request: Request, db: Session = Depends(get_db)) -> int:
    """A logged-in session only: no API key, no AI assistant key (debug routes)."""
    return require_login(request, db)


# ---------------------------------------------------------
# Routers (Transaction, User, Account, Calculation, Bitcoin, Reports, Debug)
# ---------------------------------------------------------
# (Mandatory) Routers (Transaction, User, Account, Calculation, Bitcoin, Reports)
from backend.routers import transaction, user, account, calculation, bitcoin, reports, backup, csv_import, river_import, entry_import, settings, review

# Mandatory routers
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

# (Optional) Debug Router
try:
    from backend.routers import debug
    app.include_router(debug.router, prefix="/api/debug", tags=["debug"], dependencies=[Depends(require_login_dependency)])
except ImportError:
    print(
        "WARNING: Could not import 'debug' router. If you need debug features, "
        "ensure 'backend/routers/debug.py' exists."
    )

# ---------------------------------------------------------
# Protected Route Example
# ---------------------------------------------------------
@app.get("/api/protected")
def read_protected_route(current_user: str = Depends(get_current_user)):
    """
    Demonstration of a session-protected endpoint.
    If 'user_id' isn't in the session, we raise 401.
    Otherwise, we greet the logged-in user.
    """
    return {"message": f"Hello, user {current_user}. You have access to this route!"}

# ---------------------------------------------------------
# LoginRequest Pydantic Model
# ---------------------------------------------------------
class LoginRequest(BaseModel):
    """
    Schema for login JSON:
      { "username": "someName", "password": "somePass" }
    """
    username: str
    password: str

# ---------------------------------------------------------
# Production-Ready Login / Logout Endpoints
# ---------------------------------------------------------
from backend.services.user import get_user_by_username  # for verifying credentials

@app.post("/api/login")
def login(
    login_req: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Production-level session-based login:
      1) Accepts JSON { "username": "...", "password": "..." }
      2) Look up the user in the DB, check hashed password
      3) If valid, store user.id in session
      4) Return success message
    """
    user = get_user_by_username(login_req.username, db)
    if not user:
        # For security, don't reveal which part is invalid
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    if not user.verify_password(login_req.password):
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    start_session(request, user)
    return {"detail": f"Logged in as {user.username}"}

@app.post("/api/logout")
def logout(request: Request, response: Response):
    """
    Clear the session to log out the user.
    """
    request.session.clear()
    return {"detail": "Logged out successfully"}

# ---------------------------------------------------------
# Health check (public: used by StartOS and container probes)
# ---------------------------------------------------------
from backend.migrate import current_revision, head_revision
from backend.version import app_version

@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    """
    200 when the database answers and its schema is at the version this code
    expects; 503 otherwise. Reveals nothing about the ledger.
    """
    head = head_revision()
    try:
        schema = current_revision(db.connection())
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

# ---------------------------------------------------------
# Production: Serve React/Vite frontend from dist/ at "/"
# ---------------------------------------------------------
from fastapi.staticfiles import StaticFiles

# Mount static files from dist/ at root ("/")
# Note: html=True serves index.html for root and directories only.
# The SPA fallback for client-side routes is handled by spa_fallback_handler above.
app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

# ---------------------------------------------------------
# Local Testing
# ---------------------------------------------------------
if __name__ == "__main__":
    import sys
    sys.path.append(os.getenv("PYTHONPATH", "."))
    # e.g. run: uvicorn main:app --reload
