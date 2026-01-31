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
git clone https://github.com/JingwenGu0829/MoltScheduler.git
cd MoltScheduler

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

## 3) Agent onboarding
Paste `ONBOARD_AGENT_OPENCLAW.md` into your OpenClaw agent.
It will:
- create the file structure
- create a guest template if you want
- ask onboarding questions and fill `profile.yaml` + `tasks.yaml`
- set up cron jobs (daily plan + nightly finalize)
