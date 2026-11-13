#!/bin/bash
# macOS: build "dist/mac/MarkItDown Studio.app" and a compressed .dmg to share.
#
#   macos/build_mac.sh              build for this Mac's CPU (arm64 = Apple Silicon, x86_64 = Intel)
#   MAC_ARCH=universal2 macos/build_mac.sh    one app for both CPUs (about twice the size; needs
#                                         universal2 wheels for every dependency)
#   SKIP_TEST=1 macos/build_mac.sh  skip the self-test
#   CODESIGN_IDENTITY="Developer ID Application: ..." macos/build_mac.sh    sign with your certificate
set -euo pipefail
cd "$(dirname "$0")/.."   # project root (this script lives in macos/)

[ "$(uname -s)" = "Darwin" ] || { echo "ERROR: this script must run on macOS." >&2; exit 1; }
[ -x .venv-mac/bin/python ] || bash macos/setup_mac.sh
PY=.venv-mac/bin/python

APP_NAME="MarkItDown Studio"
VERSION="$($PY -c 'import markitdown_app; print(markitdown_app.__version__)')"
ARCH="${MAC_ARCH:-$(uname -m)}"
APP="dist/mac/$APP_NAME.app"
DMG="dist/mac/MarkItDownStudio-$VERSION-mac-$ARCH.dmg"

if [ ! -f assets/app.icns ]; then
    echo "[1/4] Generating icon..."
    $PY tools/make_icon.py
else
    echo "[1/4] Icon present."
fi

echo "[2/4] Building $APP ($ARCH) with PyInstaller..."
rm -rf "$APP" dist/mac/MarkItDownStudio
MAC_ARCH="$ARCH" $PY -m PyInstaller --noconfirm --clean \
    --distpath dist/mac --workpath build/mac macos/MarkItDownStudio-mac.spec
rm -rf dist/mac/MarkItDownStudio   # intermediate folder; the .app holds its own copy

if [ "${SKIP_TEST:-0}" != "1" ]; then
    echo "[3/4] Self-test: converting one sample of each format with the built app..."
    rm -rf build/mac-test
    $PY tools/make_samples.py build/mac-test/samples
    # Run with a time limit: a hung app must fail the build, not stall it.
    "$APP/Contents/MacOS/MarkItDownStudio" --smoke-test "$PWD/build/mac-test/out" "$PWD"/build/mac-test/samples/* &
    TEST_PID=$!
    (
        sleep "${TEST_TIMEOUT:-600}"
        echo "ERROR: self-test still running after ${TEST_TIMEOUT:-600}s, stopping it." >&2
        mkdir -p build/mac-test/out
        # Record what every thread of the stuck app is doing, for diagnosis.
        sample $TEST_PID 3 -file build/mac-test/out/hang-sample.txt >/dev/null 2>&1 || true
        kill -9 $TEST_PID 2>/dev/null
    ) &
    WATCHDOG_PID=$!
    TEST_STATUS=0
    wait $TEST_PID || TEST_STATUS=$?
    kill $WATCHDOG_PID 2>/dev/null || true
    cp "$HOME/Library/Logs/MarkItDownStudio/app.log" build/mac-test/out/app.log 2>/dev/null || true
    if [ $TEST_STATUS -eq 0 ]; then
        echo "      Self-test passed (results and a screenshot are in build/mac-test/out)."
    else
        echo "ERROR: self-test failed. See build/mac-test/out/results.json" >&2
        exit 1
    fi
else
    echo "[3/4] Self-test skipped."
fi

echo "[4/4] Creating $DMG..."
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"
# ULMO = LZMA, the smallest disk image format (opens on macOS 10.15 and later).
hdiutil create -quiet -volname "$APP_NAME" -srcfolder "$STAGE" -fs HFS+ -format ULMO "$DMG"

echo
echo "Done."
echo "Largest items in the app (MB):"
du -sm "$APP"/Contents/Frameworks/* "$APP"/Contents/Frameworks/PySide6/* "$APP"/Contents/Frameworks/PySide6/Qt/lib/* "$APP"/Contents/Frameworks/onnxruntime/capi/* 2>/dev/null | sort -rn | head -40
echo "  App: $APP  ($(du -sh "$APP" | cut -f1) on disk)"
echo "  DMG: $DMG  ($(du -h "$DMG" | cut -f1) to share)"
