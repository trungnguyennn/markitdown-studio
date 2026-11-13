#!/bin/bash
# macOS: create .venv-mac and install the Full edition's dependencies.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
if ! "$PYTHON" -c 'import sys; raise SystemExit(not ((3, 10) <= sys.version_info[:2] <= (3, 13)))' 2>/dev/null; then
    echo "ERROR: Python 3.10-3.13 is required (python.org or 'brew install python@3.12')." >&2
    echo "       Use another interpreter with:  PYTHON=/path/to/python3.12 ./setup_mac.sh" >&2
    exit 1
fi

echo "[1/2] Creating virtual environment (.venv-mac)..."
"$PYTHON" -m venv .venv-mac

echo "[2/2] Installing dependencies..."
.venv-mac/bin/python -m pip install --upgrade pip
.venv-mac/bin/python -m pip install --prefer-binary -r requirements.txt

echo
echo "Setup complete. Run with:  ./run_mac.sh      Build the app with:  ./build_mac.sh"
