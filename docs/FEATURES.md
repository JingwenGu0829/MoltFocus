# Features

MoltFocus is a self-sufficient, agent-native daily planner. Everything below is implemented and working — no stubs, no "coming soon."

---

## Architecture

MoltFocus is built on a **shared core library** (`core/`) that powers both the Web UI and the Terminal UI. Every feature described here is available through all three interfaces: the TUI, the REST API, and programmatically via Python imports.

```
core/                     Shared library (zero duplication between UIs)
  models.py               Typed dataclasses for every data structure
  fileio.py               Atomic file I/O with flock locking
  workspace.py            Path resolution + timezone helpers
  checkbox.py             Plan.md checkbox + duration parsing
  rating.py               Day rating + streak logic
  reflections.py          Reflection entry builder
  finalize.py             Consolidated finalization pipeline
  tasks.py                Task CRUD + lifecycle + progress tracking
  scheduler.py            Constraint-based scheduling engine
  analytics.py            Pattern analytics from reflection history
  focus.py                Focus session management
  agent_context.py        Intelligence bridge for external agents
  hooks.py                Plugin/hook system
```

All data is stored in plain files (YAML, JSON, Markdown) under `PLANNER_ROOT/`. Nothing requires a database. Everything is inspectable, version-controllable, and owned by you.

---

## 1. Built-in Scheduling Engine

**The system can generate its own plans.** No external agent required.

The scheduler in [`core/scheduler.py`](../core/scheduler.py) reads your profile constraints and task database, then algorithmically produces a time-blocked daily plan:

- **Slot computation**: Starts from your `work_blocks`, subtracts `fixed_routines` and `weekly_fixed_events` (including commute buffers), yielding precise available windows for each day of the week.
- **Priority scoring**: Each task gets a composite score based on:
  - Base priority (1-10)
  - Deadline urgency: `remaining_hours / days_until_deadline`
  - Weekly budget gap: how far behind target you are
  - Analytics boost (optional, from historical patterns)
- **Greedy allocation**: Tasks are sorted by score and placed into the best-fitting slot, respecting `min_chunk_minutes` and `max_chunk_minutes`. Tasks can split across multiple slots. 5-minute buffers are inserted between blocks.
- **Plan rendering**: Outputs a complete `plan.md` with Top Priorities, Schedule (with routines and events), Minimum Viable Day (checkboxes), and Carryover sections.

**Access:**
- CLI: `moltfocus generate [--date YYYY-MM-DD]`
- TUI: press `g` to regenerate today's plan
- API: `POST /api/schedule/generate`

---

## 2. Task Lifecycle & Progress Tracking

Tasks are not static entries. They have a full lifecycle managed by [`core/tasks.py`](../core/tasks.py):

### CRUD operations
- Create, read, update, and delete tasks with schema validation
- Four task types: `deadline_project`, `weekly_budget`, `daily_ritual`, `open_ended`
- Priority 1-10, status `active` / `paused` / `complete`

### Automatic progress tracking
When you finalize a day, the system matches your completed checkin items back to tasks via title prefix matching:

- **Deadline projects**: `remaining_hours` decrements automatically. When it hits zero, the task auto-completes.
- **Weekly budgets**: `hours_this_week` increments. Resets to zero on the configured week start day.
- **Daily rituals**: Counted as done-for-today.

### Computed fields
Tasks are enriched with real-time computed fields:
- `urgency_score` — composite priority considering deadlines and budget gaps
- `weekly_progress_pct` — percentage of weekly hour target completed
- `days_until_deadline` — countdown for deadline projects

### Archiving
Completed tasks are automatically moved to an `archived:` section in `tasks.yaml`. No data loss, no clutter.

**Access:**
- CLI: `moltfocus tasks` (lists with urgency scores)
- API: `GET /api/tasks` (with computed fields), `POST /api/tasks`, `PUT /api/tasks/{id}`, `DELETE /api/tasks/{id}`
- Legacy: `POST /api/update_task` (still works, backward compatible)

---

## 3. Pattern Analytics

The analytics engine in [`core/analytics.py`](../core/analytics.py) parses your `reflections.md` history and extracts actionable patterns:

- **Completion by weekday** — average completion rate for each day of the week. Reveals your best and worst days.
- **Completion by task type** — are you better at timed deep work or daily rituals?
- **Rolling averages** — 7-day and 30-day trend indicators. Spot slumps early.
- **Most skipped tasks** — items that appear frequently but rarely get done (3+ appearances, <50% completion). Candidates for restructuring or removal.
- **Recovery success rate** — how effective recovery mode actually is for you.
- **Streak history** — start/end/length of every streak.

Analytics are cached in `planner/analytics.json` and refreshed on every finalization. The cache can be deleted without data loss — it regenerates from `reflections.md`.

**Access:**
- CLI: `moltfocus analytics`
- API: `GET /api/analytics`, `GET /api/analytics/patterns`

---

## 4. Focus Sessions

Pomodoro-style focus tracking implemented in [`core/focus.py`](../core/focus.py):

- **Start a session** with a task ID, label, and planned duration (default 25 min).
- **Record interruptions** — increment counter on the active session.
- **Stop the session** — calculates elapsed time, marks completion, and moves to history.
- **Auto-logs to task progress** — when you stop a focus session, the elapsed minutes are automatically applied to the task's progress (decrementing `remaining_hours` for deadline projects, incrementing `hours_this_week` for weekly budgets).
- **Stats** — total sessions, total minutes, average session length, interruption count, completion rate over configurable time windows.

Data stored in `planner/latest/focus.json`.

**Access:**
- CLI: `moltfocus focus`, `moltfocus focus start <id> [label] [minutes]`, `moltfocus focus stop [--completed]`, `moltfocus focus interrupt`
- API: `POST /api/focus/start`, `POST /api/focus/stop`, `GET /api/focus/current`

---

## 5. Co-Evolution Feedback Loop

The intelligence bridge in [`core/agent_context.py`](../core/agent_context.py) generates a single `planner/agent_context.json` after every finalization. This is the file an external agent reads instead of parsing everything manually.

### Contents
- **Analytics snapshot**: streak, 7-day average, completion by weekday
- **Top 5 urgent tasks** with composite priority scores
- **Weekly budget status**: target vs. actual hours for each budget task
- **Scheduling suggestions** — rule-based recommendations:
  - If 7-day average < 50%: suggest lighter day or recovery mode
  - Route hardest tasks to your historically best days
  - Warn about frequently skipped tasks (3+ skips)
  - Flag historically low-completion weekdays
  - Suggest recovery mode when it has a high success rate for you

The built-in scheduler also reads these suggestions to auto-adjust difficulty.

**Access:**
- API: `GET /api/schedule/suggestions`
- File: `planner/agent_context.json` (machine-readable, always fresh after finalization)

---

## 6. Finalization Pipeline

The finalization system in [`core/finalize.py`](../core/finalize.py) is the beating heart of the nightly cycle. It runs a 10-step pipeline:

1. **Load & validate** the checkin draft
2. **Idempotency check** — second call on the same day is a safe no-op
3. **Compute rating** (good/fair/bad) and streak eligibility
4. **Build & prepend** a structured reflection entry to `reflections.md`
5. **Update `state.json`** — streak, rating, summary, history (last 30 days, de-duped)
6. **Process checkin progress** — match done items to tasks, update hours
7. **Refresh analytics** — recompute from full reflection history
8. **Generate `agent_context.json`** — fresh intelligence for agents
9. **Run hooks** — execute any configured `post_finalize` hooks
10. **Clear draft** — reset for tomorrow

### Rating system
- **Good**: completed >= 50% of items, or >= 2 items, or any timed item done
- **Fair**: completed >= 1 item, or wrote a meaningful reflection (>= 30 characters)
- **Bad**: nothing notable
- Recovery mode is more forgiving: upgrades "bad" to "fair" if you did anything

### Streak logic
A day counts toward your streak if you: completed >= 1 item, OR wrote a meaningful reflection, OR actively adjusted your plan. Missing a day resets the streak.

**Access:**
- TUI: press `f`
- CLI: `moltfocus finalize`
- API: `POST /api/finalize`

---

## 7. Dual Interface

### Web UI (`ui/app.py`)
A FastAPI server serving a single-page HTML interface:
- **Plan editor** with live markdown preview (using marked.js)
- **Check-in panel** with auto-saving checkboxes, comments, and reflection textarea
- **Plan diff** showing changes since last save
- **Streak display** with 30-day history
- **Meta file viewer** for profile.yaml and tasks.yaml
- **Mode toggle** between Commit and Recovery

### Terminal UI (`cli/moltfocus.py`)
A full Textual TUI with equivalent functionality:
- Split-pane layout: plan viewer + check-in panel
- Keyboard-driven: `d` dashboard, `t` tasks, `s` status, `e` edit, `r` reflect, `m` mode, `f` finalize, `g` generate, `q` quit
- Data tables for tasks and history
- Background auto-save on every keystroke

Both UIs share the same `core/` library — zero code duplication.

---

## 8. REST API (22 endpoints)

The full API surface for agent and programmatic integration:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/healthz` | Health check |
| GET | `/` | Web UI (HTML) |
| POST | `/save_plan` | Save plan.md |
| GET | `/raw/plan` | Raw plan.md text |
| POST | `/api/checkin_draft` | Auto-save check-in |
| POST | `/api/finalize` | Run finalization pipeline |
| POST | `/api/update_task` | Legacy task update |
| GET | `/api/profile` | Profile constraints as JSON |
| GET | `/api/tasks` | Tasks with computed fields |
| POST | `/api/tasks` | Create task |
| PUT | `/api/tasks/{id}` | Update task (RESTful) |
| DELETE | `/api/tasks/{id}` | Archive/delete task |
| GET | `/api/analytics` | Analytics summary |
| GET | `/api/analytics/patterns` | Detailed patterns |
| POST | `/api/schedule/generate` | Generate plan via scheduler |
| GET | `/api/schedule/suggestions` | Scheduling suggestions |
| POST | `/api/focus/start` | Start focus session |
| POST | `/api/focus/stop` | Stop focus session |
| GET | `/api/focus/current` | Active session + 7-day stats |
| GET | `/api/state` | Full state dump |
| GET | `/api/reflections/recent` | Last N parsed reflections |

All endpoints support HTTP Basic Auth (configurable via `MOLTFOCUS_USERNAME` / `MOLTFOCUS_PASSWORD` env vars). Guest mode when no credentials are set.

---

## 9. Plugin/Hook System

Extensibility via [`core/hooks.py`](../core/hooks.py). Configure shell commands in `planner/hooks.yaml` that run at lifecycle points:

**Hook points:**
- `pre_finalize` / `post_finalize`
- `pre_plan_generate` / `post_plan_generate`
- `on_focus_start` / `on_focus_stop`
- `on_task_complete`

Hooks receive context as JSON via stdin. Each hook has configurable timeout protection (default 30s) with stdout/stderr capture.

Example `hooks.yaml`:
```yaml
post_finalize:
  - "curl -X POST https://my-webhook.example.com/finalized"
  - command: "python /path/to/my_script.py"
    timeout: 10
```

---

## 10. File-backed Data Model

Everything is a plain file. No database, no proprietary format.

| File | Format | Purpose |
|------|--------|---------|
| `planner/profile.yaml` | YAML | Schedule constraints, timezone, work blocks, routines, events |
| `planner/tasks.yaml` | YAML | Task database with lifecycle state |
| `planner/state.json` | JSON | Streak, rating, summary, 30-day history |
| `planner/latest/plan.md` | Markdown | Today's generated plan with checkboxes |
| `planner/latest/checkin_draft.json` | JSON | Auto-saved check-in progress |
| `planner/latest/focus.json` | JSON | Active focus session + session history |
| `planner/analytics.json` | JSON | Computed analytics cache (regenerable) |
| `planner/agent_context.json` | JSON | Aggregated intelligence for agents |
| `planner/hooks.yaml` | YAML | Hook configuration |
| `reflections/reflections.md` | Markdown | Rolling reflection log (newest first) |

All new files are additive — old workspaces load without changes. Missing keys default gracefully.

---

## Backward Compatibility

- **Zero migration**: `from_dict` methods on every model handle missing keys with sensible defaults. Old workspace files load without changes.
- **New files are additive**: `analytics.json`, `agent_context.json`, `focus.json`, `hooks.yaml` are only created when their features are first used.
- **Legacy API preserved**: `POST /api/update_task` continues to work alongside the new RESTful `PUT /api/tasks/{id}`.
- **CLI backward compatible**: `./moltfocus` with no args still launches the TUI.
