#!/bin/bash
# macOS: run MarkItDown Studio from source.
set -euo pipefail
cd "$(dirname "$0")"
[ -x .venv-mac/bin/python ] || bash setup_mac.sh
exec .venv-mac/bin/python main.py "$@"
