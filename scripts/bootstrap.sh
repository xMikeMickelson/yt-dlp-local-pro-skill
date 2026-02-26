#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   scripts/bootstrap.sh /opt/yt-dlp-local

TARGET_DIR="${1:-/opt/yt-dlp-local}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

mkdir -p "$TARGET_DIR"/{cookies,downloads,logs}
cd "$TARGET_DIR"

if [ ! -d venv ]; then
  "$PYTHON_BIN" -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip
pip install flask yt-dlp

echo "Bootstrap complete at: $TARGET_DIR"
echo "Next: copy app.py/config.py/.env + install systemd unit"
