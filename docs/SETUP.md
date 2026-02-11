# Setup (step-by-step)

This is the detailed setup guide.

## 1) Server (headless)

### Install Tailscale
On Linux server:
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```
Open the printed auth URL on your laptop.

### Install MoltScheduler UI
```bash
git clone https://github.com/JingwenGu0829/MoltFocus.git
cd MoltFocus

# PLANNER_ROOT must contain planner/ and reflections/
export PLANNER_ROOT=/path/to/workspace_root

./scripts/install_ui.sh
export HOST=0.0.0.0
export PORT=8787
./scripts/run_ui.sh
```

(Optional) systemd: see `scripts/bootstrap_server.sh`.

## 2) Laptop
- Install Tailscale: https://tailscale.com/download
- Join same account
- Open UI:
  `http://<SERVER_TAILSCALE_IP>:8787`

### If you only have SSH access (no Tailscale)
From your laptop:
```bash
ssh -N -L 8787:127.0.0.1:8787 <user>@<server-ip-or-hostname>
```
Then open:
`http://localhost:8787`

Notes:
- `0.0.0.0` means "listen on all server interfaces"; it is not a URL to open in a browser.
- `localhost` always means "this machine", so on your laptop it refers to your laptop unless tunneled.

## 3) Agent onboarding
Paste `ONBOARD_AGENT_OPENCLAW.md` into your OpenClaw agent.
It will:
- create the file structure
- create a guest template if you want
- ask onboarding questions and fill `profile.yaml` + `tasks.yaml`
- set up cron jobs (daily plan + nightly finalize)
