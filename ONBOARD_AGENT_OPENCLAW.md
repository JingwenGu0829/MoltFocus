# ONBOARD_AGENT_OPENCLAW — Paste this into your OpenClaw agent

You are onboarding a **file-backed daily planner** (MoltScheduler).

## Goals
1) Create the canonical planner files in the user's workspace (portable, tidy):
   - `planner/profile.yaml`
   - `planner/tasks.yaml`
   - `planner/state.json`
   - `reflections/reflections.md`
2) Keep outputs **latest-only**:
   - `planner/latest/plan.md`
   - `planner/latest/sglang_issues.md` (optional)
   - `planner/latest/checkin_draft.json` (UI auto-saves)
3) Ask the user the minimum questions needed to schedule their day realistically.
4) Set up cron jobs:
   - Daily plan push at user’s chosen time (default 08:50 local)
   - Optional repo-issues scan
   - Nightly finalize (POST UI /api/finalize) + send streak/summary

## Procedure

### Step 1 — Ask onboarding questions (keep it short)
Ask for:
- Timezone
- Wake time
- Work blocks (2–4 blocks)
- Fixed routines (lunch/workout) + times
- Weekly fixed events (day + start/end + commute)
- Top priorities order (3–5)
- Current tasks (deadline projects + weekly budgets + daily rituals)

### Step 2 — Write canonical files
Write/update these files in the workspace:
- `planner/profile.yaml`
- `planner/tasks.yaml`
- `planner/state.json` (initialize streak=0, lastSummary="")
- `reflections/reflections.md` (initialize if missing)
- Ensure `planner/latest/` exists.

### Step 3 — Generate today’s plan
Create/overwrite `planner/latest/plan.md`.
- Include checkboxes for tasks in the plan using markdown:
  IMPORTANT: use the exact format `- [ ] Task 120m` (or `- [ ] Thesis 2h`) so the UI can render a tickable to-do list.
  - `- [ ] Task (duration)`

### Step 4 — Set up cron jobs
Create cron jobs in the OpenClaw gateway:
- Daily plan generation
- Optional SGLang issue scan
- Nightly finalize: POST `http://127.0.0.1:8787/api/finalize`, then read `planner/state.json` and message the user the summary + rating + streak.

### Step 5 — Explain usage to the user (2–3 bullets)
- Edit plan in UI anytime.
- Check off items + add minutes/comments; it auto-saves.
- Nightly finalize creates the reflection entry + updates streak.

## Rules
- Default to tidy: do not create per-day archives.
- Do not store private secrets in this repo.
- Do not take external actions (PRs/messages to others) without explicit approval.
