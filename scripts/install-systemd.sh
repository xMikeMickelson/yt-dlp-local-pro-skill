#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   sudo scripts/install-systemd.sh /opt/yt-dlp-local <service-user>

TARGET_DIR="${1:-/opt/yt-dlp-local}"
SERVICE_USER="${2:-$USER}"
UNIT_PATH="/etc/systemd/system/yt-dlp-local.service"

sudo tee "$UNIT_PATH" >/dev/null <<EOF
[Unit]
Description=yt-dlp-local API Service
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${TARGET_DIR}
Environment=PATH=${TARGET_DIR}/venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=${TARGET_DIR}/venv/bin/python app.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now yt-dlp-local
sudo systemctl status yt-dlp-local --no-pager
