# README_AGENT — Instructions for an agent replicating this system

Goal: provide daily planning for a human by maintaining a **file-backed task database** and generating a daily plan.

## 0) Principles

1) **Separate canonical truth from generated outputs**
- Canonical truth: `planner/profile.yaml`, `planner/tasks.yaml`, `planner/state.json`, `reflections/reflections.md`
- Generated output: `planner/latest/plan.md` (and optional other `latest/*.md`)

2) **Keep it tidy**
- Default mode: overwrite files in `planner/latest/`.
- Do not accumulate daily archives unless the human asks.

3) **Be honest**
- If you don’t have enough info to schedule precisely, say so.
- If nothing notable happened (e.g., no actionable issues), write “none notable” rather than inventing.

4) **No external actions without approval**
- Don’t post, DM, or open PRs unless explicitly approved.

## 1) Data model

### `planner/profile.yaml`
Contains constraints:
- timezone
- wake time
- work blocks
- fixed events (class, commute)
- recurring routines (workout, lunch)

### `planner/tasks.yaml`
Each task must have:
- `id` (stable)
- `type`: `deadline_project` | `weekly_budget` | `daily_ritual` | `open_ended`
- `priority` (integer)
- `status`: `active` | `paused` | `complete`

Recommended fields:
- `remaining_hours` for deadline projects
- `target_hours_per_week` for weekly budgets
- `min_chunk_minutes`

### `reflections/reflections.md`
Rolling compressed log.
- Append newest at the top.
- Include: what was done, blockers, schedule changes, energy/mood.

## 2) Daily workflow (08:50 local time recommended)

1) Load canonical truth files.
2) Determine today’s available time blocks (subtract fixed events + commute + routines).
3) Allocate work blocks:
- First allocate urgent/deadline work.
- Then allocate weekly budgets (keep them on track).
- Add 1 small “maintenance”/ritual slot.

4) Write output plan:
- `planner/latest/plan.md`

Plan format:
- Top 3 priorities
- Time-blocked schedule
- Estimated durations
- Minimum viable day
- Carryover/backlog

5) Send the plan to the human.

## 3) End-of-day update workflow

The nightly finalize step (`POST /api/finalize` or TUI `f` key) automatically:
1) Appends a structured entry to `reflections/reflections.md`.
2) Updates streak, rating, and summary in `planner/state.json`.
3) Clears the draft (`planner/latest/checkin_draft.json`).

**Task updates are the agent's responsibility** (not automated by finalize):
- Decrement `remaining_hours` for deadline projects based on time spent.
- Track weekly budget hours.
- Mark tasks complete when the user confirms.

Use `POST /api/update_task` with `{"task_id": "...", "updates": {...}}` or edit `planner/tasks.yaml` directly.

## 4) Optional modules
- “Repo issue scan” (e.g., SGLang): write to `planner/latest/sglang_issues.md` and send as a file.

