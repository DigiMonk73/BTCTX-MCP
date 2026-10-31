#!/bin/bash
#
# Build script for BitcoinTX macOS Desktop App
#
# Prerequisites:
#   - Python 3.11+ with pip (brew install python@3.13)
#   - Node.js 22.13+ with npm (the README's minimum; CI and Docker use 24)
#
# Usage:
#   ./desktop/build-mac.sh
#   BTCTX_BUILD_PYTHON=/path/to/python3.13 ./desktop/build-mac.sh   (that Python)
#

set -e

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo ""
echo "========================================"
echo "  BitcoinTX macOS Desktop Build"
echo "========================================"
echo ""

cd "$PROJECT_ROOT"

# Step 1: Check prerequisites
echo "[1/6] Checking prerequisites..."

if ! command -v npm &> /dev/null; then
    echo "ERROR: npm not found"
    exit 1
fi

# Python 3.11+ (#546): the one BTCTX_BUILD_PYTHON names, which CI's macOS jobs set
# to the Python they set up (3.13, chosen and tested; the runner's newest was
# taken before, whatever it was, #284); else the newest found here. Set but
# empty, it's an error, never a quiet fall back to the search.
PYTHON_CMD=""
if [ -n "${BTCTX_BUILD_PYTHON+set}" ]; then
    CANDIDATES=("$BTCTX_BUILD_PYTHON")
else
    CANDIDATES=(python3.13 python3.12 python3.11 python3)
fi
for py in "${CANDIDATES[@]}"; do
    if command -v "$py" &> /dev/null; then
        PY_VER=$("$py" -c "import sys; print(sys.version_info.minor)" 2>/dev/null) || continue
        PY_MAJOR=$("$py" -c "import sys; print(sys.version_info.major)" 2>/dev/null) || continue
        if [ "$PY_MAJOR" -eq 3 ] && [ "$PY_VER" -ge 11 ]; then
            PYTHON_CMD="$py"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ] && [ -n "${BTCTX_BUILD_PYTHON+set}" ]; then
    echo "ERROR: BTCTX_BUILD_PYTHON ($BTCTX_BUILD_PYTHON) isn't a Python 3.11+"
    exit 1
fi
if [ -z "$PYTHON_CMD" ]; then
    echo "ERROR: Python 3.11+ is required but not found"
    echo ""
    echo "Install with Homebrew:"
    echo "  brew install python@3.13"
    echo ""
    echo "Then run this script again."
    exit 1
fi

PYTHON_VERSION=$("$PYTHON_CMD" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  Python: $PYTHON_VERSION ($PYTHON_CMD)"

NODE_VERSION=$(node --version)
echo "  Node: $NODE_VERSION"

# Step 2: Create/update virtual environment
echo ""
echo "[2/6] Setting up Python virtual environment..."

VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    echo "  Created virtual environment"
else
    VENV_VERSION=$("$VENV_DIR/bin/python" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "?")
    echo "  Using existing virtual environment (Python $VENV_VERSION)"
    if [ "$VENV_VERSION" != "$PYTHON_VERSION" ]; then
        echo "  It keeps its Python, not $PYTHON_VERSION: delete desktop/.venv to build with $PYTHON_VERSION"
    fi
fi

source "$VENV_DIR/bin/activate"

# Install dependencies from the locks, every package checked against its
# hash. proxy-tools (under pywebview) is published only as source: it is
# built with the locked setuptools, installed first, not with whatever
# setuptools pip would fetch for the build (that fetch has no hash check).
export PIP_DISABLE_PIP_VERSION_CHECK=1
awk '/^setuptools==/ { on = 1; print; next } on && /^ / { print; next } { on = 0 }' \
    "$SCRIPT_DIR/requirements.txt" > "$VENV_DIR/setuptools.txt"
if [ ! -s "$VENV_DIR/setuptools.txt" ]; then
    echo "ERROR: no setuptools in desktop/requirements.txt (run make lock)"
    exit 1
fi
pip install -q --require-hashes --no-deps -r "$VENV_DIR/setuptools.txt"
pip install -q --require-hashes --no-build-isolation \
    -r "$PROJECT_ROOT/backend/requirements.txt" -r "$SCRIPT_DIR/requirements.txt"
echo "  Dependencies installed"

# Step 3: Build frontend
echo ""
echo "[3/6] Building frontend..."

cd "$PROJECT_ROOT/frontend"
npm ci --silent 2>/dev/null || npm ci
npm run build
cd "$PROJECT_ROOT"
echo "  Frontend built to frontend/dist/"

# Step 4: Verify resources
echo ""
echo "[4/6] Verifying resources..."

# BitcoinTX's icon, and BitcoinTX Preview's with its band (#670): the spec takes one
for icon in icon.icns icon-preview.icns; do
    if [ ! -f "$SCRIPT_DIR/resources/$icon" ]; then
        echo "  ERROR: $icon not found at $SCRIPT_DIR/resources/ (docs/MACOS_DESKTOP_APP.md, \"App icon\")"
        exit 1
    fi
done

if [ ! -d "$PROJECT_ROOT/backend/assets/irs_templates" ]; then
    echo "  ERROR: IRS templates not found at backend/assets/irs_templates/"
    exit 1
fi

echo "  Resources verified"

# Step 5: Run PyInstaller
echo ""
echo "[5/6] Building application bundle..."

cd "$SCRIPT_DIR"
# Only this build's app in dist/: BitcoinTX.app, or BitcoinTX Preview.app for a
# 2.0 pre-release (the spec takes its name from VERSION)
rm -rf "$SCRIPT_DIR/dist"
pyinstaller --clean --noconfirm BitcoinTX.spec

# Step 6: Report results
echo ""
echo "[6/6] Build complete!"

APPS=("$SCRIPT_DIR"/dist/*.app)
APP_PATH="${APPS[0]}"
APP_NAME="$(basename "$APP_PATH" .app)"
if [ "${#APPS[@]}" = 1 ] && [ -d "$APP_PATH" ]; then
    APP_SIZE=$(du -sh "$APP_PATH" | cut -f1)
    echo ""
    echo "  Application: $APP_PATH"
    echo "  Size: $APP_SIZE"
    echo ""
    # Never "open" it: that runs it on the installed app's data folder, a real ledger (#679)
    echo "To test, on its own data folder and port, never the installed app's ledger:"
    printf '  %q\n' "$SCRIPT_DIR/run-test-build.sh"
    echo ""

    # Create DMG if create-dmg is available
    if command -v create-dmg &> /dev/null; then
        echo "Creating DMG installer..."
        DMG_PATH="$SCRIPT_DIR/dist/${APP_NAME// /-}.dmg"
        rm -f "$DMG_PATH"
        create-dmg \
            --volname "$APP_NAME" \
            --window-pos 200 120 \
            --window-size 600 400 \
            --icon-size 100 \
            --icon "$APP_NAME.app" 150 190 \
            --app-drop-link 450 190 \
            "$DMG_PATH" \
            "$APP_PATH"

        if [ -f "$DMG_PATH" ]; then
            DMG_SIZE=$(du -sh "$DMG_PATH" | cut -f1)
            echo ""
            echo "  DMG created: $DMG_PATH"
            echo "  DMG size: $DMG_SIZE"
        fi
    else
        echo "To create DMG for distribution, install create-dmg:"
        echo "  brew install create-dmg"
        echo ""
        echo "Then run:"
        echo "  create-dmg --volname \"$APP_NAME\" --app-drop-link 450 190 \"${APP_NAME// /-}.dmg\" \"$APP_PATH\""
    fi
else
    echo "  ERROR: Application bundle not created"
    deactivate
    exit 1
fi

# Deactivate virtual environment
deactivate
