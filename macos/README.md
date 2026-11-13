# MarkItDown Studio for macOS

Everything specific to the Mac version (Apple Silicon). Run these from the project root.

| Script | What it does |
|---|---|
| `bash macos/setup_mac.sh` | create `.venv-mac` and install dependencies |
| `bash macos/run_mac.sh` | run the app from source |
| `bash macos/build_mac.sh` | build `dist/mac/MarkItDown Studio.app`, self-test it, package a `.dmg` |

Without a Mac, run the **Build macOS app** workflow from the repository's Actions tab.
Details and differences from Windows are in the [main README](../README.md#macos-version).
