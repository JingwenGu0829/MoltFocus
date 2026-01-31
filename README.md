# MoltScheduler

A **file-backed, agent-assisted daily planning system** with an optional **web UI**.

V1 is intentionally simple: the “product” is a clean data model + an operating procedure an agent can follow.

## What it does
- You maintain canonical files (`planner/profile.yaml`, `planner/tasks.yaml`).
- An agent reads them and pushes a daily plan (time-blocked, estimated durations, top priorities).
- Optionally, you edit the plan + submit check-ins via a browser UI.

## What it is not (yet)
- Not a calendar replacement.
- Not a full-featured GUI with drag-drop.

---

## Quick start (template only)

1) Copy `template/` to your private workspace.
2) Edit:
- `planner/profile.yaml`
- `planner/tasks.yaml`
3) Give your agent the instructions in **README_AGENT.md**.

---

## Run the UI on a headless server (recommended via Tailscale)

### Step 0 — Requirements
- A server (can be headless) that runs your agent + stores your planner files
- A personal laptop/desktop/phone where you open the UI in a browser

### Step 1 — Install Tailscale

**On your laptop:**
- Install from: https://tailscale.com/download

**On the server (Linux):**
```bash
curl -fsSL https://tailscale.com/install.sh | sh
```

### Step 2 — Join the same tailnet

**On the server:**
```bash
sudo tailscale up

# sanity check
sudo tailscale status
sudo tailscale ip -4
```

**On your laptop:**
- Open the Tailscale app → sign in to the **same account**
- Confirm the server shows up in the device list

### Step 3 — Clone the repo and install UI dependencies (server)

```bash
git clone https://github.com/JingwenGu0829/MoltScheduler.git
cd MoltScheduler

./scripts/install_ui.sh
```

### Step 4 — Start the UI server (server)

Set `PLANNER_ROOT` to the folder that contains:
- `planner/`
- `reflections/`

Example (OpenClaw default workspace layout):
```bash
export PLANNER_ROOT=/home/jig040/.openclaw/workspace/jing

export HOST=0.0.0.0
export PORT=8787
./scripts/run_ui.sh
```

### Step 5 — Open the UI (from your laptop)

1) Find the server’s Tailscale IP:
```bash
sudo tailscale ip -4
```

2) Open in your browser:
```
http://<SERVER_TAILSCALE_IP>:8787
```

UI notes: see `ui/README.md`.

---

## Troubleshooting

- Check the UI is running on the server:
  - `ss -lntp | grep 8787`
- Check the UI health endpoint:
  - `curl http://127.0.0.1:8787/healthz`
- If Tailscale connectivity is weird:
  - `tailscale status`

---

## Philosophy
- **Truth vs outputs**: keep one canonical source of truth, and regenerate outputs.
- **Tidy by default**: keep only `planner/latest/` artifacts unless you explicitly want history.

## License
MIT (see `LICENSE`).
