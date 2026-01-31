# Features

This doc describes what MoltScheduler does today.

## Core concept
- Canonical truth lives in files under `PLANNER_ROOT/`.
- UI edits **latest-only** outputs.

## File layout (expected under PLANNER_ROOT)
- `planner/profile.yaml` — macro schedule constraints
- `planner/tasks.yaml` — task database
- `planner/state.json` — streak + last summary/rating + bookkeeping
- `planner/latest/plan.md` — today’s plan (editable)
- `planner/latest/checkin_draft.json` — auto-saved check-in draft
- `reflections/reflections.md` — rolling reflection log (nightly finalize appends)

## UI
### Plan editor
- Edits `planner/latest/plan.md`.
- Supports markdown checkboxes for tasks:
  - `- [ ] Thesis 2h`
  - `- [ ] Profiling 90m`

### Check-in (auto-save)
- Renders a tickable to-do list from the checkboxes in `plan.md`.
- Each row has:
  - done checkbox
  - minutes spent
  - optional comment
- Reflection textarea auto-saves.

### Modes (adaptive)
- **Commit mode** vs **Recovery mode** saved in the check-in draft.
- Nightly finalize uses the mode to rate the day and update streak.

### Focus (V1.2)
- Select a to-do item → Start focus.
- Tracks active focus session locally + writes to `planner/latest/focus.json`.

### Yesterday summary + streak
- UI shows the latest one-paragraph summary + rating + streak from `planner/state.json`.

## Nightly finalize
- API endpoint: `POST /api/finalize`
- Converts the draft into:
  - a compact entry appended to `reflections/reflections.md`
  - streak/rating/summary updates in `planner/state.json`
