# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for BitcoinTX macOS Desktop App

Build with: pyinstaller BitcoinTX.spec
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

# Get the project root (parent of desktop/)
SPEC_DIR = Path(SPECPATH)
PROJECT_ROOT = SPEC_DIR.parent

# Verify paths exist
assert (PROJECT_ROOT / "backend").exists(), "backend/ not found"
assert (PROJECT_ROOT / "frontend" / "dist").exists(), "frontend/dist/ not found - run npm build first"

block_cipher = None

# Collect all backend Python files and assets
backend_datas = [
    # Backend Python packages
    (str(PROJECT_ROOT / "backend"), "backend"),
]

# Frontend dist
frontend_datas = [
    (str(PROJECT_ROOT / "frontend" / "dist"), "frontend/dist"),
]

# VERSION beside backend/, where backend/version.py looks for it
version_datas = [
    (str(PROJECT_ROOT / "VERSION"), "."),
]

# Hidden imports for all dependencies
hidden_imports = [
    # FastAPI and dependencies
    "fastapi",
    "starlette",
    "starlette.middleware.sessions",
    "starlette.middleware.cors",
    "starlette.staticfiles",
    "starlette.responses",
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",

    # Pydantic
    "pydantic",
    "pydantic.deprecated",
    "pydantic.deprecated.decorator",
    "pydantic_core",

    # Schema migrations: migration scripts under backend/migrations/ ship as
    # data (backend_datas) and are loaded at runtime, so PyInstaller can't see
    # what they import (alembic.op, alembic.context, ...).
    *collect_submodules("alembic"),
    "mako",
    "mako.template",

    # SQLAlchemy
    "sqlalchemy",
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.sql.default_comparator",

    # HTTP clients
    "httpx",
    "httpx._transports",
    "httpx._transports.default",
    "httpcore",

    # Auth & crypto
    "bcrypt",
    "cryptography",
    "cryptography.hazmat.primitives.kdf.pbkdf2",

    # PDF
    "pypdf",
    "reportlab",
    "reportlab.graphics",
    "reportlab.lib",
    "reportlab.platypus",

    # PIL (required by reportlab)
    "PIL",
    "PIL.Image",

    # Utilities
    "dotenv",
    "python_dateutil",
    "dateutil",
    "itsdangerous",
    "multipart",

    # Backend modules
    "backend",
    "backend.main",
    "backend.database",
    "backend.migrate",
    "backend.constants",
    "backend.models",
    "backend.models.user",
    "backend.models.account",
    "backend.models.transaction",
    "backend.routers",
    "backend.routers.user",
    "backend.routers.account",
    "backend.routers.transaction",
    "backend.routers.calculation",
    "backend.routers.bitcoin",
    "backend.routers.reports",
    "backend.routers.backup",
    "backend.routers.csv_import",
    "backend.routers.river_import",
    "backend.routers.entry_import",
    "backend.routers.settings",
    "backend.schemas",
    "backend.schemas.user",
    "backend.schemas.account",
    "backend.schemas.transaction",
    "backend.schemas.csv_import",
    "backend.schemas.river_import",
    "backend.schemas.entry_import",
    "backend.services",
    "backend.services.user",
    "backend.services.account",
    "backend.services.calculation",
    "backend.services.transaction",
    "backend.services.bitcoin",
    "backend.services.backup",
    "backend.services.csv_import",
    "backend.services.river_import",
    "backend.services.entry_import",
    "backend.services.tax_time",
    "backend.services.desktop",
    "backend.secret_key",
    "backend.version",
    "backend.cli",
    "backend.models.app_setting",
    "tzdata",
    "backend.services.reports",
    "backend.services.reports.form_8949",
    "backend.services.reports.complete_tax_report",
    "backend.services.reports.transaction_history",
    "backend.services.reports.reporting_core",
    "backend.services.reports.pdf_form_filler",

    # Desktop entrypoint helpers (desktop/)
    "desktop_ports",

    # WebView
    "webview",
]

a = Analysis(
    [str(SPEC_DIR / "entrypoint.py")],
    pathex=[str(PROJECT_ROOT), str(SPEC_DIR)],
    binaries=[],
    datas=backend_datas + frontend_datas + version_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "tkinter",
        "matplotlib",
        "numpy",
        "scipy",
        "pandas",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BitcoinTX",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window on macOS
    disable_windowed_traceback=False,
    argv_emulation=True,  # macOS: handle file drops etc
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="BitcoinTX",
)

app = BUNDLE(
    coll,
    name="BitcoinTX.app",
    icon=str(SPEC_DIR / "resources" / "icon.icns") if (SPEC_DIR / "resources" / "icon.icns").exists() else None,
    bundle_identifier="org.bitcointx.desktop",
    info_plist={
        "CFBundleName": "BitcoinTX",
        "CFBundleDisplayName": "BitcoinTX",
        "CFBundleIdentifier": "org.bitcointx.desktop",
        "CFBundleVersion": "0.9.1",
        "CFBundleShortVersionString": "0.9.1",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "10.15",
        "NSRequiresAquaSystemAppearance": False,  # Support dark mode
    },
)
