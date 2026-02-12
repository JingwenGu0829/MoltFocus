from __future__ import annotations

import os
import re
import difflib
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

# ── Core library imports (replaces ~360 lines of duplicated utilities) ──
from core import (
    workspace_root as _workspace_root,
    get_user_timezone as _get_user_timezone,
    today_str as _today_str,
    now_local,
    read_text as _read_text,
    read_json as _read_json,
    read_yaml,
    write_text as _write_text,
    write_json_atomic as _write_json_atomic,
    write_text_atomic as _write_text_atomic,
    write_yaml_atomic as _write_yaml_atomic,
    extract_checkboxes as _extract_checkboxes,
    compute_rating as _compute_rating,
    counts_for_streak as _counts_for_streak,
    summarize_paragraph as _summarize_paragraph,
    prepend_reflection as _prepend_reflection,
    build_reflection_entry,
    validate_task as _validate_task,
    finalize_day,
    load_tasks,
    save_tasks,
    find_task,
    create_task,
    update_task as core_update_task,
    delete_task as core_delete_task,
    get_tasks_with_computed_fields,
    State,
    TasksFile,
    plan_path as _plan_path_fn,
    plan_prev_path as _plan_prev_path_fn,
    draft_path as _draft_path_fn,
    state_path as _state_path_fn,
    reflections_path as _reflections_path_fn,
    profile_path as _profile_path_fn,
    tasks_path as _tasks_path_fn,
)

ASSET_V = "20260201-01"
from fastapi import FastAPI, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi import Body
from fastapi.security import HTTPBasic, HTTPBasicCredentials


# ── HTML helpers ──────────────────────────────────────────────

def _escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

def _render_obj(x: Any) -> str:
    """Render a Python/YAML object into compact HTML (read-only)."""
    if x is None:
        return '<span class="muted">(null)</span>'
    if isinstance(x, bool):
        return '<span class="pill">true</span>' if x else '<span class="pill">false</span>'
    if isinstance(x, (int, float)):
        return f'<span class="pill">{x}</span>'
    if isinstance(x, str):
        s = _escape(x)
        if len(s) <= 80 and "\n" not in s:
            return f'<span>{s}</span>'
        return f'<pre class="mono">{s}</pre>'
    if isinstance(x, list):
        if not x:
            return '<span class="muted">(empty)</span>'
        items = ''.join([f'<li>{_render_obj(v)}</li>' for v in x])
        return f'<ol class="kv">{items}</ol>'
    if isinstance(x, dict):
        if not x:
            return '<span class="muted">(empty)</span>'
        rows = []
        for k, v in x.items():
            rows.append(f'<div class="kv-row"><div class="kv-key">{_escape(str(k))}</div><div class="kv-val">{_render_obj(v)}</div></div>')
        return '<div class="kv">' + ''.join(rows) + '</div>'
    return f'<span>{_escape(str(x))}</span>'


# ── Auth ──────────────────────────────────────────────────────

app = FastAPI(title="MoltFocus UI", version="0.3.0")

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

security = HTTPBasic(auto_error=False)


def get_current_user(credentials: HTTPBasicCredentials | None = Depends(security)) -> str:
    expected_username = os.environ.get("MOLTFOCUS_USERNAME", "")
    expected_password = os.environ.get("MOLTFOCUS_PASSWORD", "")

    if credentials is None:
        if not expected_username or not expected_password:
            return "guest"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Basic"},
        )

    if not expected_username or not expected_password:
        return "guest"

    correct_username = secrets.compare_digest(credentials.username.encode("utf-8"), expected_username.encode("utf-8"))
    correct_password = secrets.compare_digest(credentials.password.encode("utf-8"), expected_password.encode("utf-8"))

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    return credentials.username


# ── Existing endpoints ────────────────────────────────────────

@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"ok": "true"}


@app.get("/", response_class=HTMLResponse)
def index(username: str = Depends(get_current_user)) -> HTMLResponse:
    root = _workspace_root()
    plan_md = _read_text(_plan_path_fn(root)) or "# Plan\n\n(no plan yet)\n"

    profile_txt = _read_text(_profile_path_fn(root))
    tasks_txt = _read_text(_tasks_path_fn(root))

    profile_parse_error = None
    try:
        yaml.safe_load(profile_txt) if profile_txt.strip() else {}
    except Exception as e:
        profile_parse_error = f"YAML parse error: {str(e)}"

    tasks_parse_error = None
    try:
        yaml.safe_load(tasks_txt) if tasks_txt.strip() else {}
    except Exception as e:
        tasks_parse_error = f"YAML parse error: {str(e)}"

    checkboxes = _extract_checkboxes(plan_md)

    draft = _read_json(_draft_path_fn(root)) if _draft_path_fn(root).exists() else {}
    if draft.get("day") != _today_str():
        draft = {"day": _today_str(), "mode": "commit", "items": {}, "reflection": ""}

    items_by_key: dict[str, Any] = draft.get("items", {}) or {}
    mode = (draft.get("mode", "commit") or "commit").strip().lower()
    if mode not in {"commit", "recovery"}:
        mode = "commit"
    reflection = draft.get("reflection", "") or ""

    state = _read_json(_state_path_fn(root)) if _state_path_fn(root).exists() else {}
    streak = int(state.get("streak", 0) or 0)
    last_summary = state.get("lastSummary", "") or ""
    last_rating = state.get("lastRating", "") or ""

    hist = state.get("history", []) or []
    hist = list(hist)[-30:][::-1]
    lines = []
    for e in hist:
        d = e.get("day", "?")
        r = (e.get("rating", "?") or "?").upper()
        m = (e.get("mode", "?") or "?").upper()
        lines.append(f"{d}  {r}  ({m})")
    history_txt = "\n".join(lines) if lines else "(no history yet)"

    diff_txt = ""
    pprev = _plan_prev_path_fn(root)
    if pprev.exists():
        prev = _read_text(pprev).splitlines()
        cur = plan_md.splitlines()
        diff = difflib.unified_diff(prev, cur, fromfile="plan_prev", tofile="plan", lineterm="")
        diff_txt = "\n".join(diff).strip()

    todo_rows = []
    for cb in checkboxes:
        key = cb.key
        label = cb.label
        title = label
        dur = ""
        m_dur = re.search(r"^(.*?)(?:\s*[\u2014-]\s*)(\d+\s*[mh])\s*$", label)
        if m_dur:
            title = m_dur.group(1).strip()
            dur = m_dur.group(2).strip()

        d = items_by_key.get(key, {})
        done = bool(d.get("done", False))
        comment = d.get("comment", "") or ""

        todo_rows.append(
            f"""
            <div class=\"todo\" data-item-row data-key=\"{_escape(key)}\">
              <input type=\"checkbox\" {'checked' if done else ''} />
              <div data-label>\n                <div class=\"todo-title\">{_escape(title)}</div>{f'<div class="todo-dur muted small">{_escape(dur)}</div>' if dur else ""}
              </div>
              <input data-comment type=\"text\" placeholder=\"comment\" value=\"{_escape(comment)}\" />
            </div>
            """
        )

    rating_badge = ""
    if last_rating in {"good", "fair", "bad"}:
        rating_badge = f"<span class=\"badge {last_rating}\">{last_rating.upper()}</span>"

    html = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>MoltFocus</title>
  <link rel=\"stylesheet\" href=\"/static/style.css?v={ASSET_V}\" />
  <script src="/static/marked.min.js?v={ASSET_V}"></script>
</head>
<body>
  <div class=\"container\">
    <header class=\"top\">
      <div>
        <h1>MoltFocus</h1>
        <div class=\"muted small\"><details><summary style=\"cursor:pointer\">\U0001f525 <b>{streak}</b> {rating_badge}</summary><pre class=\"mono\" style=\"margin-top:8px\">{_escape(history_txt)}</pre></details></div>
      </div>
      <div class=\"pill\"><code>{root}</code></div>
    </header>

    <section class=\"grid\">
      <div class=\"card\">
        <h2>Plan (edit directly)</h2>
        <form method=\"post\" action=\"/save_plan\">
          <div class=\"planbar\">
            <div class=\"muted small\">Click plan to edit; click outside to preview.</div>
            <div class=\"planbar-actions\">
              <button id=\"savePlan\" type=\"submit\">Save</button>
            </div>
          </div>

          <div id=\"planPane\">
            <div id=\"planPreview\" class=\"md\"></div>
            <textarea id=\"plan\" name=\"plan_md\" rows=\"20\" style=\"display:none\">{_escape(plan_md)}</textarea>
          </div>

          <div class=\"muted small\" style=\"margin-top:8px\">Tip: embed tasks as markdown checkboxes: <code>- [ ] Thesis 2h</code></div>
        </form>

        <details style=\"margin-top:10px\" {'open' if diff_txt else ''}>
          <summary><b>Plan diff (since last save)</b></summary>
          <pre class=\"mono\">{_escape(diff_txt or "(no changes captured yet)")}</pre>
        </details>
      </div>

      <div class=\"card\" data-checkin>
        <h2>Check-in (auto-saves)</h2>
        <div class="row" style="margin-top:8px">
          <div class="muted small">Mode:</div>
          <div>
            <label class="muted small" style="display:inline-flex; gap:6px; align-items:center; margin-right:10px">
              <input type="radio" name="mode" value="commit" {"checked" if mode=="commit" else ""} /> Commit
            </label>
            <label class="muted small" style="display:inline-flex; gap:6px; align-items:center">
              <input type="radio" name="mode" value="recovery" {"checked" if mode=="recovery" else ""} /> Recovery
            </label>
          </div>
        </div>
        <div class=\"muted small\">No submit needed. Status: <span id=\"saveStatus\">\u2026</span> <button id=\"manualSave\">Save now</button></div>

        <h3 style=\"margin-top:12px\">Today's to-do list</h3>
        {''.join(todo_rows) if todo_rows else '<div class="muted small">No checkboxes found in plan. Add tasks like <code>- [ ] ...</code> in the plan.</div>'}

        <label style=\"margin-top:14px\">Reflection</label>
        <textarea id=\"reflection\" rows=\"4\">{_escape(reflection)}</textarea>

      </div>
    </section>

    <section class=\"card\">
      <h2>Yesterday summary</h2>
      <div class=\"muted\">{_escape(last_summary or '(not generated yet)')}</div>
    </section>

    <section class="card">
      <details>
        <summary><b>Meta files</b> <span class="muted small">(profile/tasks)</span></summary>
        <div class="muted small" style="margin-top:8px">planner/profile.yaml</div>
        {f'<div style="color:#ff6b6b; background:rgba(255,107,107,0.1); padding:8px; border-radius:6px; margin:8px 0; font-size:13px"><b>\u26a0 {_escape(profile_parse_error)}</b></div>' if profile_parse_error else ''}
        <pre class="mono">{_escape(profile_txt or "(missing)")}</pre>
        <div class="muted small" style="margin-top:8px">planner/tasks.yaml</div>
        {f'<div style="color:#ff6b6b; background:rgba(255,107,107,0.1); padding:8px; border-radius:6px; margin:8px 0; font-size:13px"><b>\u26a0 {_escape(tasks_parse_error)}</b></div>' if tasks_parse_error else ''}
        <pre class="mono">{_escape(tasks_txt or "(missing)")}</pre>
      </details>
    </section>
<footer class=\"muted small\">v0.3 \u00b7 Draft auto-saves to <code>planner/latest/checkin_draft.json</code>. Nightly finalization updates streak + summary.</footer>
  </div>

  <script src=\"/static/app.js?v={ASSET_V}\"></script>
</body>
</html>"""

    ref_path = _reflections_path_fn(root)
    if not ref_path.exists():
        _write_text(ref_path, "# Reflections (rolling)\n\nAppend newest entries at the top.\n\n---\n\n")

    return HTMLResponse(html)


@app.post("/save_plan")
def save_plan(plan_md: str = Form(...), username: str = Depends(get_current_user)) -> RedirectResponse:
    root = _workspace_root()
    pp = _plan_path_fn(root)
    prev = _plan_prev_path_fn(root)

    if pp.exists():
        _write_text(prev, _read_text(pp))

    _write_text(pp, plan_md.rstrip() + "\n")
    return RedirectResponse(url="/", status_code=303)


@app.post("/api/checkin_draft")
def api_checkin_draft(payload: dict[str, Any] = Body(...), username: str = Depends(get_current_user)) -> dict[str, Any]:
    root = _workspace_root()
    dp = _draft_path_fn(root)

    day = _today_str()
    mode_in = (payload.get("mode", "commit") or "commit").strip().lower()
    if mode_in not in {"commit", "recovery"}:
        mode_in = "commit"

    items_in = payload.get("items", []) or []
    reflection = payload.get("reflection", "") or ""

    items: dict[str, Any] = {}
    for it in items_in:
        key = str(it.get("key", ""))
        if not key:
            continue
        items[key] = {
            "label": str(it.get("label", "")),
            "done": bool(it.get("done", False)),
            "comment": str(it.get("comment", "")),
        }

    user_tz = _get_user_timezone()
    draft = {
        "day": day,
        "updatedAt": datetime.now(user_tz).isoformat(timespec="seconds"),
        "mode": mode_in,
        "items": items,
        "reflection": reflection,
    }

    _write_json_atomic(dp, draft)
    return {"ok": True, "day": day}


@app.post("/api/finalize")
def api_finalize(username: str = Depends(get_current_user)) -> dict[str, Any]:
    """Finalize today's draft — delegates to core.finalize_day()."""
    return finalize_day()


@app.get("/raw/plan")
def raw_plan(username: str = Depends(get_current_user)) -> PlainTextResponse:
    root = _workspace_root()
    return PlainTextResponse(_read_text(_plan_path_fn(root)) or "")


# ── Legacy task update endpoint (backward compatible) ─────────

@app.post("/api/update_task")
def api_update_task(payload: dict[str, Any] = Body(...), username: str = Depends(get_current_user)) -> dict[str, Any]:
    """Update a task in tasks.yaml (legacy endpoint, kept for backward compatibility)."""
    root = _workspace_root()
    task_id = payload.get("task_id")
    updates = payload.get("updates", {})

    if not task_id:
        raise HTTPException(status_code=400, detail="Missing task_id")
    if not updates:
        raise HTTPException(status_code=400, detail="Missing updates")

    tasks_file = load_tasks(root)
    updated, errors = core_update_task(tasks_file, task_id, updates)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    save_tasks(tasks_file, root)
    return {"ok": True, "task": updated.to_dict() if updated else None}


# ══════════════════════════════════════════════════════════════
# Phase 6: Enhanced API Surface — new RESTful endpoints
# ══════════════════════════════════════════════════════════════

@app.get("/api/profile")
def api_get_profile(username: str = Depends(get_current_user)) -> dict[str, Any]:
    """Read profile constraints as JSON."""
    root = _workspace_root()
    data = read_yaml(_profile_path_fn(root))
    return data or {}


@app.get("/api/tasks")
def api_list_tasks(username: str = Depends(get_current_user)) -> dict[str, Any]:
    """List tasks with computed fields (urgency, weekly progress)."""
    root = _workspace_root()
    tasks_file = load_tasks(root)
    state_data = _read_json(_state_path_fn(root))
    state = State.from_dict(state_data)
    today = _today_str()
    computed = get_tasks_with_computed_fields(tasks_file, state, today)
    return {"tasks": computed, "week_start": tasks_file.week_start}


@app.post("/api/tasks")
def api_create_task(payload: dict[str, Any] = Body(...), username: str = Depends(get_current_user)) -> dict[str, Any]:
    """Create a new task."""
    root = _workspace_root()
    tasks_file = load_tasks(root)
    task, errors = create_task(tasks_file, payload)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    save_tasks(tasks_file, root)
    return {"ok": True, "task": task.to_dict()}


@app.put("/api/tasks/{task_id}")
def api_update_task_rest(task_id: str, payload: dict[str, Any] = Body(...), username: str = Depends(get_current_user)) -> dict[str, Any]:
    """Update a task (RESTful)."""
    root = _workspace_root()
    tasks_file = load_tasks(root)
    updated, errors = core_update_task(tasks_file, task_id, payload)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    save_tasks(tasks_file, root)
    return {"ok": True, "task": updated.to_dict() if updated else None}


@app.delete("/api/tasks/{task_id}")
def api_delete_task(task_id: str, username: str = Depends(get_current_user)) -> dict[str, Any]:
    """Archive/delete a task."""
    root = _workspace_root()
    tasks_file = load_tasks(root)
    deleted = core_delete_task(tasks_file, task_id, archive=True)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    save_tasks(tasks_file, root)
    return {"ok": True, "task_id": task_id}


@app.get("/api/analytics")
def api_get_analytics(username: str = Depends(get_current_user)) -> dict[str, Any]:
    """Analytics summary."""
    root = _workspace_root()
    from core.analytics import load_analytics, refresh_analytics
    analytics = load_analytics(root)
    if analytics is None:
        analytics = refresh_analytics(root)
    return analytics.to_dict()


@app.get("/api/analytics/patterns")
def api_get_analytics_patterns(username: str = Depends(get_current_user)) -> dict[str, Any]:
    """Detailed patterns for agent consumption."""
    root = _workspace_root()
    from core.analytics import refresh_analytics
    analytics = refresh_analytics(root)
    return analytics.to_dict()


@app.post("/api/schedule/generate")
def api_generate_schedule(
    payload: dict[str, Any] = Body(default={}),
    username: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Trigger plan generation via the built-in scheduler."""
    from core.scheduler import generate_plan
    from datetime import date as date_type
    root = _workspace_root()

    target_date = None
    date_str = payload.get("date")
    if date_str:
        try:
            target_date = date_type.fromisoformat(date_str)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid date: {date_str}")

    plan_md = generate_plan(target_date=target_date, root=root)
    return {"ok": True, "plan_md": plan_md}


@app.get("/api/schedule/suggestions")
def api_schedule_suggestions(username: str = Depends(get_current_user)) -> dict[str, Any]:
    """Scheduling suggestions from analytics."""
    root = _workspace_root()
    from core.agent_context import generate_agent_context
    context = generate_agent_context(root)
    return {"suggestions": context.get("suggestions", [])}


@app.post("/api/focus/start")
def api_focus_start(payload: dict[str, Any] = Body(...), username: str = Depends(get_current_user)) -> dict[str, Any]:
    """Start a focus session."""
    from core.focus import start_session
    task_id = payload.get("task_id", "")
    task_label = payload.get("task_label", "")
    planned_minutes = int(payload.get("planned_minutes", 25))
    try:
        session = start_session(task_id, task_label, planned_minutes)
        return {"ok": True, "session": session.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/api/focus/stop")
def api_focus_stop(payload: dict[str, Any] = Body(default={}), username: str = Depends(get_current_user)) -> dict[str, Any]:
    """Stop the active focus session."""
    from core.focus import stop_session
    completed = bool(payload.get("completed", False))
    notes = str(payload.get("notes", ""))
    try:
        session = stop_session(completed=completed, notes=notes)
        return {"ok": True, "session": session.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/api/focus/current")
def api_focus_current(username: str = Depends(get_current_user)) -> dict[str, Any]:
    """Current focus state."""
    from core.focus import get_focus_state, get_focus_stats
    state = get_focus_state()
    stats = get_focus_stats(days=7)
    return {
        "active_session": state.active_session.to_dict() if state.active_session else None,
        "recent_sessions": len(state.history),
        "stats_7day": stats,
    }


@app.get("/api/state")
def api_get_state(username: str = Depends(get_current_user)) -> dict[str, Any]:
    """Full state dump."""
    root = _workspace_root()
    return _read_json(_state_path_fn(root))


@app.get("/api/reflections/recent")
def api_recent_reflections(n: int = 7, username: str = Depends(get_current_user)) -> dict[str, Any]:
    """Last N days of parsed reflections."""
    root = _workspace_root()
    from core.analytics import parse_reflections
    text = _read_text(_reflections_path_fn(root))
    records = parse_reflections(text)
    recent = records[:n]
    return {
        "count": len(recent),
        "records": [
            {
                "date": r.date,
                "rating": r.rating,
                "mode": r.mode,
                "done_items": r.done_items,
                "completion_rate": r.completion_rate(),
                "reflection": r.reflection_text,
            }
            for r in recent
        ],
    }
