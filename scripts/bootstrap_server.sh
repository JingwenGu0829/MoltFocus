#!/usr/bin/env bash
set -euo pipefail

# MoltScheduler bootstrap (server side)
# - installs deps (git, curl)
# - installs tailscale (optional)
# - clones/updates repo
# - installs UI deps
# - creates systemd service
# - prints the UI URL (via tailscale IP)

REPO_URL_DEFAULT="https://github.com/JingwenGu0829/MoltFocus.git"
INSTALL_DIR_DEFAULT="$HOME/molt-scheduler"
PORT_DEFAULT="8787"

REPO_URL="${REPO_URL:-$REPO_URL_DEFAULT}"
INSTALL_DIR="${INSTALL_DIR:-$INSTALL_DIR_DEFAULT}"
PORT="${PORT:-$PORT_DEFAULT}"

if ! command -v git >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y git
fi

if ! command -v curl >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y curl
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "Missing 'uv'. Install uv first (https://docs.astral.sh/uv/)" >&2
  exit 1
fi

# Optional: install tailscale if missing
if ! command -v tailscale >/dev/null 2>&1; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi

# Clone or update repo
if [ -d "$INSTALL_DIR/.git" ]; then
  echo "Updating repo in $INSTALL_DIR"
  git -C "$INSTALL_DIR" pull --ff-only
else
  echo "Cloning repo to $INSTALL_DIR"
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# Install UI deps
./scripts/install_ui.sh

# Create systemd service
SERVICE=/etc/systemd/system/moltscheduler-ui.service
sudo tee "$SERVICE" >/dev/null <<UNIT
[Unit]
Description=MoltScheduler UI (FastAPI)
After=network.target tailscaled.service

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
Environment=PLANNER_ROOT=${PLANNER_ROOT:-$HOME/planner}
Environment=HOST=0.0.0.0
Environment=PORT=$PORT
ExecStart=$INSTALL_DIR/scripts/run_ui.sh
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now moltscheduler-ui

echo "\nService status:"
sudo systemctl status moltscheduler-ui --no-pager | sed -n '1,20p' || true

echo "\nTailscale:"
echo "- Run: sudo tailscale up"
echo "- Then open the auth URL on your laptop"

echo "\nAfter Tailscale is connected, open:"
if command -v tailscale >/dev/null 2>&1; then
  TSIP=$(tailscale ip -4 2>/dev/null || true)
  if [ -n "$TSIP" ]; then
    echo "http://$TSIP:$PORT"
  else
    echo "http://<SERVER_TAILSCALE_IP>:$PORT"
  fi
else
  echo "http://<SERVER_TAILSCALE_IP>:$PORT"
fi
