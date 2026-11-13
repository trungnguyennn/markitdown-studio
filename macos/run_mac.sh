#!/bin/bash
# macOS: run MarkItDown Studio from source.
set -euo pipefail
cd "$(dirname "$0")/.."   # project root (this script lives in macos/)
[ -x .venv-mac/bin/python ] || bash macos/setup_mac.sh
exec .venv-mac/bin/python main.py "$@"
