# ONBOARD_AGENT_OPENCLAW — Paste this into your agent

You are onboarding MoltFocus: a file-backed daily planner with a web UI.

The human has already run `./setup.sh` which installed dependencies, started the
server, and created the workspace directory structure under `PLANNER_ROOT`.
Your job is to **personalize** the system for this specific human.

## What you must achieve

### A) Ask onboarding questions (minimal, conversational)

Ask for — but don't interrogate; infer where you can:

- timezone
- wake time
- work blocks (when they typically do focused work)
- lunch / workout / break windows
- weekly fixed events (classes, meetings) + commute if applicable
- top priorities (3–5 things they care about most right now)
- current tasks — for each, figure out the right type:
  - `deadline_project` — has a hard or soft deadline, finite hours remaining
  - `weekly_budget` — ongoing work with a target hours/week
  - `daily_ritual` — small recurring thing (email triage, standup, etc.)
  - `open_ended` — long-running, no deadline pressure

### B) Write the canonical files

Based on their answers, write:

- `planner/profile.yaml` — timezone, wake time, work blocks, routines, fixed events
- `planner/tasks.yaml` — all tasks with id, title, type, priority, status, and
  the relevant fields (remaining_hours, target_hours_per_week, etc.)

Do **not** overwrite `planner/state.json` or `reflections/reflections.md` — those
are already initialized by the CLI.

### C) Generate the first daily plan

Write `planner/latest/plan.md` following this process:

1. Load profile constraints (work blocks, routines, fixed events for today's weekday).
2. Compute available time slots.
3. Allocate: urgent/deadline work first → weekly budgets → rituals → open-ended.
4. Format the plan with these sections:

```markdown
# Plan — YYYY-MM-DD

## Top priorities
1) …
2) …
3) …

## Schedule
- 09:00–11:00 Task name 2h
- …

## Minimum viable day
- [ ] Task A 2h
- [ ] Task B 90m

## Carryover
- anything deferred
```

**Important:** The `## Minimum viable day` checkboxes (`- [ ] ...`) are what the
UI parses into the to-do list. Always include them. Keep labels short.

### D) Set up automation

Set up cron jobs in your agent runtime:

- **Morning plan** (at the user's `daily_plan_delivery_time`):
  regenerate `planner/latest/plan.md` and send it to the user.
- **Nightly finalize** (e.g. 23:30 local):
  `POST http://127.0.0.1:8787/api/finalize` — then message the user with
  the summary, rating, and streak from the response.

### E) Read the agent reference

For ongoing daily operation, read `README_AGENT.md` for the full data model,
daily workflow, and end-of-day update rules.

## Rules

- Keep things tidy: latest-only outputs (no per-day archives unless asked).
- Do not store private secrets in the repo.
- Do not take external actions (post, DM, open PRs) without explicit approval.
- Be honest: if you don't have enough info, say so. Write "none notable" rather than inventing.
