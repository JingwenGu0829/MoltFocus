# MoltScheduler UI (V0)

A tiny web UI intended to run on a **headless server** and be viewed from your laptop/phone browser.

## What it edits
It edits the same file-backed storage as the agent:
- `planner/latest/plan.md` (editable)
- `planner/latest/sglang_issues.md` (read-only, optional)
- `reflections/reflections.md` (appends check-ins)

## Run

```bash
./scripts/install_ui.sh

# must contain planner/ and reflections/
export PLANNER_ROOT=/path/to/workspace_root

# server bind + port
export HOST=0.0.0.0
export PORT=8787

./scripts/run_ui.sh
```

Open:
- local test: `http://127.0.0.1:8787`
- via Tailscale: `http://<SERVER_TAILSCALE_IP>:8787`

## Notes
- V0 keeps logic simple: edit plan text + submit a check-in.
- V0 does **not** auto-update `tasks.yaml` based on check-ins (agent does bookkeeping).
