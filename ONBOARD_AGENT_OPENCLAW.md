# ONBOARD_AGENT_OPENCLAW — Paste this into your OpenClaw agent

You are onboarding MoltScheduler: a file-backed daily planner + headless-server web UI.

## What you must achieve

### A) Make it runnable (dependencies + UI)
1) Ask where the user is running the agent:
- headless server (recommended) + laptop browser

2) Tell the user to install Tailscale on their laptop:
- https://tailscale.com/download

3) On the server: install/run the UI (prefer the repo bootstrap):
- clone repo
- run `scripts/bootstrap_server.sh`
- run `sudo tailscale up` and have the user approve the auth URL

### B) Initialize the workspace structure
Create canonical files under the user’s chosen `PLANNER_ROOT`:
- `planner/profile.yaml`
- `planner/tasks.yaml`
- `planner/state.json`
- `reflections/reflections.md`
- ensure `planner/latest/` exists

### C) Guest mode (demo)
Offer a “guest mode” option:
- if user says yes, write a small example profile/tasks + a sample `planner/latest/plan.md` so they can see the UI working immediately.

### D) Ask onboarding questions (minimal)
Ask for:
- timezone
- wake time
- work blocks
- lunch/workout windows
- weekly fixed events (+ commute)
- top priorities order (3–5)
- current tasks (deadline projects + weekly budgets + daily rituals)

### E) Generate a usable plan
Write `planner/latest/plan.md` and ALWAYS include checkbox tasks using this exact format:
- `- [ ] Thesis 2h`
- `- [ ] Profiling 90m`

The UI builds the to-do list by parsing these lines.

### F) Automation
Set up cron jobs in OpenClaw:
- daily plan generation at the user’s chosen time
- nightly finalize: POST `http://127.0.0.1:8787/api/finalize` then message the user summary/rating/streak

## Rules
- Keep things tidy: latest-only outputs (no per-day archives unless asked).
- Do not store private secrets in the repo.
- Do not take external actions without explicit approval.
