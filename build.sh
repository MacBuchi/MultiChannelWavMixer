#!/usr/bin/env bash
# build.sh — build MultiChannelWavMixer.app with PyInstaller via uv
# Usage:
#   ./build.sh          — normal build
#   ./build.sh --clean  — remove dist/ and build/ first, then build
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Optional clean ──────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--clean" ]]; then
    echo "→ Cleaning previous build artefacts …"
    rm -rf dist build __pycache__
fi

# ── Build ───────────────────────────────────────────────────────────────────────
echo "→ Building MultiChannelWavMixer.app …"
uv run pyinstaller MultiChannelWavMixer.spec \
    --noconfirm \
    --log-level WARN

# ── Result ──────────────────────────────────────────────────────────────────────
APP="dist/MultiChannelWavMixer.app"
if [[ -d "$APP" ]]; then
    SIZE=$(du -sh "$APP" | cut -f1)
    echo ""
    echo "✓ Build successful: $APP  ($SIZE)"
    echo ""
    echo "  To run:    open $APP"
    echo "  To zip:    cd dist && zip -r MultiChannelWavMixer.zip MultiChannelWavMixer.app"
else
    echo "✗ Build failed — $APP not found." >&2
    exit 1
fi
