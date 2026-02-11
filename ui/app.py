from __future__ import annotations

import json
import os
import re
import difflib
import fcntl
import tempfile
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

ASSET_V = "20260201-01"
from fastapi import FastAPI, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi import Body
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets


def _workspace_root() -> Path:
    # PLANNER_ROOT should be the workspace root that contains planner/ and reflections/
    return Path(os.environ.get("PLANNER_ROOT", str(Path.home() / "planner"))).expanduser().resolve()


def _get_user_timezone() -> ZoneInfo:
    """Get user's timezone from profile.yaml, defaulting to system timezone."""
    root = _workspace_root()
    profile_path = root / "planner" / "profile.yaml"

    try:
        profile_txt = _read_text(profile_path)
        if profile_txt.strip():
            profile = yaml.safe_load(profile_txt)
            if isinstance(profile, dict) and "timezone" in profile:
                return ZoneInfo(profile["timezone"])
    except Exception:
        pass

    # Fallback to UTC if profile not found or invalid
    return ZoneInfo("UTC")


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    """Atomic write with file locking for safe concurrent access."""
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file first
    fd, temp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            # Acquire exclusive lock
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        # Atomic rename
        os.rename(temp_path, path)
    except Exception:
        # Clean up temp file on error
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def _write_text_atomic(path: Path, content: str) -> None:
    """Atomic write with file locking for safe concurrent access."""
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file first
    fd, temp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".txt")
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            # Acquire exclusive lock
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        # Atomic rename
        os.rename(temp_path, path)
    except Exception:
        # Clean up temp file on error
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def _write_yaml_atomic(path: Path, data: dict[str, Any]) -> None:
    """Atomic YAML write with file locking for safe concurrent access."""
    content = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    _write_text_atomic(path, content)


def _validate_task(task: dict[str, Any]) -> list[str]:
    """Validate task schema and return list of errors (empty if valid)."""
    errors = []

    # Required fields
    if "id" not in task:
        errors.append("Missing required field: id")
    if "title" not in task:
        errors.append("Missing required field: title")
    if "type" not in task:
        errors.append("Missing required field: type")
    elif task["type"] not in {"deadline_project", "weekly_budget", "daily_ritual", "open_ended"}:
        errors.append(f"Invalid task type: {task['type']}")

    # Type-specific validation
    if task.get("type") == "deadline_project":
        if "remaining_hours" in task and not isinstance(task["remaining_hours"], (int, float)):
            errors.append("remaining_hours must be numeric")
    elif task.get("type") == "weekly_budget":
        if "target_hours_per_week" in task and not isinstance(task["target_hours_per_week"], (int, float)):
            errors.append("target_hours_per_week must be numeric")

    # Status validation
    if "status" in task and task["status"] not in {"active", "paused", "complete"}:
        errors.append(f"Invalid status: {task['status']}")

    # Priority validation
    if "priority" in task:
        if not isinstance(task["priority"], int) or task["priority"] < 1 or task["priority"] > 10:
            errors.append("priority must be integer 1-10")

    return errors


def _prepend_reflection(ref_path: Path, entry_md: str) -> None:
    existing = _read_text(ref_path)
    if existing.strip() == "":
        existing = "# Reflections (rolling)\n\nAppend newest entries at the top.\n\n---\n\n"
    marker = "---\n\n"
    idx = existing.find(marker)
    if idx != -1:
        head = existing[: idx + len(marker)]
        tail = existing[idx + len(marker) :]
        new = head + "\n" + entry_md.strip() + "\n\n" + tail.lstrip()
    else:
        new = entry_md.strip() + "\n\n" + existing
    _write_text_atomic(ref_path, new)


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
        # short strings inline
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



def _extract_checkboxes(plan_md: str) -> list[dict[str, str]]:
    # Extract markdown tasks like:
    # - [ ] Task
    # - [x] Task
    out = []
    for i, line in enumerate(plan_md.splitlines()):
        m = re.match(r"^\s*[-*]\s*\[([ xX])\]\s+(.*)$", line)
        if not m:
            continue
        checked = m.group(1).strip().lower() == "x"
        label = m.group(2).strip()
        key = f"line-{i}"
        out.append({"key": key, "label": label, "checked": "1" if checked else "0"})
    return out


def _today_str() -> str:
    """Get today's date in user's timezone from profile.yaml."""
    user_tz = _get_user_timezone()
    return datetime.now(user_tz).date().isoformat()


def _compute_rating(done_count: int, total_items: int, reflection: str, any_time: bool) -> str:
    # Avoid punishing bad days too harshly.
    # Good: meaningful progress. Fair: some progress or solid reflection. Bad: nothing.
    refl = (reflection or "").strip()
    if done_count >= max(1, total_items // 2) or (done_count >= 2) or (any_time and done_count >= 1):
        return "good"
    if done_count >= 1 or len(refl) >= 30:
        return "fair"
    return "bad"


def _counts_for_streak(done_count: int, reflection: str, plan_changed: bool) -> bool:
    # New idea: streak shouldn’t punish honesty.
    # Count a day if you either did >=1 meaningful thing OR reflected OR actively adjusted plan.
    return done_count >= 1 or len((reflection or "").strip()) >= 30 or plan_changed


def _summarize_paragraph(day: str, rating: str, done_items: list[str], minutes_total: int, reflection: str) -> str:
    lead = {"good": "Good", "fair": "Fair", "bad": "Bad"}[rating]
    parts = []
    if done_items:
        top = done_items[:3]
        more = "" if len(done_items) <= 3 else f" (+{len(done_items)-3} more)"
        parts.append(f"done: {', '.join(top)}{more}")
    if minutes_total > 0:
        parts.append(f"logged ~{minutes_total} min")
    refl = (reflection or "").strip()
    if refl:
        parts.append("reflection recorded")
    body = "; ".join(parts) if parts else "no notable progress logged"
    advice = {
        "good": "Keep the momentum; protect one deep block early tomorrow.",
        "fair": "Aim for one deeper block next; reduce context switching.",
        "bad": "Reset: pick one small win + one deep block tomorrow.",
    }[rating]
    return f"[{lead}] {day}: {body}. {advice}"


app = FastAPI(title="MoltFocus UI", version="0.2.0")

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

security = HTTPBasic(auto_error=False)


def get_current_user(credentials: HTTPBasicCredentials | None = Depends(security)) -> str:
    """Verify HTTP Basic Auth credentials from environment variables."""
    expected_username = os.environ.get("MOLTFOCUS_USERNAME", "")
    expected_password = os.environ.get("MOLTFOCUS_PASSWORD", "")

    # If no Authorization header provided
    if credentials is None:
        # allow only if server is in guest mode
        expected_username = os.environ.get("MOLTFOCUS_USERNAME", "")
        expected_password = os.environ.get("MOLTFOCUS_PASSWORD", "")
        if not expected_username or not expected_password:
            return "guest"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Basic"},
        )

    # If no credentials configured, allow access (backward compatible)
    if not expected_username or not expected_password:
        return "guest"

    # Constant-time comparison to prevent timing attacks
    correct_username = secrets.compare_digest(credentials.username.encode("utf-8"), expected_username.encode("utf-8"))
    correct_password = secrets.compare_digest(credentials.password.encode("utf-8"), expected_password.encode("utf-8"))

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    return credentials.username


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"ok": "true"}


@app.get("/", response_class=HTMLResponse)
def index(username: str = Depends(get_current_user)) -> HTMLResponse:
    root = _workspace_root()
    plan_path = root / "planner" / "latest" / "plan.md"
    plan_prev_path = root / "planner" / "latest" / "plan_prev.md"

    ref_path = root / "reflections" / "reflections.md"
    draft_path = root / "planner" / "latest" / "checkin_draft.json"
    state_path = root / "planner" / "state.json"

    plan_md = _read_text(plan_path) or "# Plan\n\n(no plan yet)\n"

    profile_path = root / "planner" / "profile.yaml"
    tasks_path = root / "planner" / "tasks.yaml"

    profile_txt = _read_text(profile_path)
    tasks_txt = _read_text(tasks_path)

    profile_parse_error = None
    try:
        profile_obj = yaml.safe_load(profile_txt) if profile_txt.strip() else {}
    except Exception as e:
        profile_obj = {}
        profile_parse_error = f"YAML parse error: {str(e)}"

    tasks_parse_error = None
    try:
        tasks_obj = yaml.safe_load(tasks_txt) if tasks_txt.strip() else {}
    except Exception as e:
        tasks_obj = {}
        tasks_parse_error = f"YAML parse error: {str(e)}"

    checkboxes = _extract_checkboxes(plan_md)

    draft = _read_json(draft_path) if draft_path.exists() else {}
    draft_day = draft.get("day")
    if draft_day != _today_str():
        draft = {"day": _today_str(), "mode": "commit", "items": {}, "reflection": ""}

    # map draft items
    items_by_key: dict[str, Any] = draft.get("items", {}) or {}
    mode = (draft.get("mode", "commit") or "commit").strip().lower()
    if mode not in {"commit","recovery"}:
        mode = "commit"
    reflection = draft.get("reflection", "") or ""

    # show last summary/rating
    state = _read_json(state_path) if state_path.exists() else {}
    streak = int(state.get("streak", 0) or 0)
    last_summary = state.get("lastSummary", "") or ""
    last_rating = state.get("lastRating", "") or ""

    # streak history (last 30 days)
    hist = state.get("history", []) or []
    # show newest first
    hist = list(hist)[-30:][::-1]
    lines=[]
    for e in hist:
        d=e.get("day","?")
        r=(e.get("rating","?") or "?").upper()
        m=(e.get("mode","?") or "?").upper()
        lines.append(f"{d}  {r}  ({m})")
    history_txt = "\n".join(lines) if lines else "(no history yet)"

    # plan diff (prev vs current)
    diff_txt = ""
    if plan_prev_path.exists():
        prev = _read_text(plan_prev_path).splitlines()
        cur = plan_md.splitlines()
        diff = difflib.unified_diff(prev, cur, fromfile="plan_prev", tofile="plan", lineterm="")
        diff_txt = "\n".join(diff).strip()

    # Build check-in list HTML
    todo_rows = []
    for cb in checkboxes:
        key = cb["key"]
        label = cb["label"]
        title = label
        dur = ""
        m = re.search(r"^(.*?)(?:\s*[—-]\s*)(\d+\s*[mh])\s*$", label)
        if m:
            title = m.group(1).strip()
            dur = m.group(2).strip()

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
        <div class=\"muted small\"><details><summary style=\"cursor:pointer\">🔥 <b>{streak}</b> {rating_badge}</summary><pre class=\"mono\" style=\"margin-top:8px\">{_escape(history_txt)}</pre></details></div>
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
        <div class=\"muted small\">No submit needed. Status: <span id=\"saveStatus\">…</span> <button id=\"manualSave\">Save now</button></div>

        <h3 style=\"margin-top:12px\">Today’s to-do list</h3>
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
        {f'<div style="color:#ff6b6b; background:rgba(255,107,107,0.1); padding:8px; border-radius:6px; margin:8px 0; font-size:13px"><b>⚠ {_escape(profile_parse_error)}</b></div>' if profile_parse_error else ''}
        <pre class="mono">{_escape(profile_txt or "(missing)")}</pre>
        <div class="muted small" style="margin-top:8px">planner/tasks.yaml</div>
        {f'<div style="color:#ff6b6b; background:rgba(255,107,107,0.1); padding:8px; border-radius:6px; margin:8px 0; font-size:13px"><b>⚠ {_escape(tasks_parse_error)}</b></div>' if tasks_parse_error else ''}
        <pre class="mono">{_escape(tasks_txt or "(missing)")}</pre>
      </details>
    </section>
<footer class=\"muted small\">v0.2 · Draft auto-saves to <code>planner/latest/checkin_draft.json</code>. Nightly finalization updates streak + summary.</footer>
  </div>

  <script src=\"/static/app.js?v={ASSET_V}\"></script>
</body>
</html>"""

    # ensure reflections file exists
    if not ref_path.exists():
        _write_text(ref_path, "# Reflections (rolling)\n\nAppend newest entries at the top.\n\n---\n\n")

    return HTMLResponse(html)


@app.post("/save_plan")
def save_plan(plan_md: str = Form(...), username: str = Depends(get_current_user)) -> RedirectResponse:
    root = _workspace_root()
    plan_path = root / "planner" / "latest" / "plan.md"
    prev_path = root / "planner" / "latest" / "plan_prev.md"

    # store prev for diff
    if plan_path.exists():
        _write_text(prev_path, _read_text(plan_path))

    _write_text(plan_path, plan_md.rstrip() + "\n")
    return RedirectResponse(url="/", status_code=303)


@app.post("/api/checkin_draft")
def api_checkin_draft(payload: dict[str, Any] = Body(...), username: str = Depends(get_current_user)) -> dict[str, Any]:
    root = _workspace_root()
    draft_path = root / "planner" / "latest" / "checkin_draft.json"

    day = _today_str()
    mode_in = (payload.get("mode", "commit") or "commit").strip().lower()
    if mode_in not in {"commit","recovery"}:
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

    _write_json_atomic(draft_path, draft)
    return {"ok": True, "day": day}


@app.post("/api/finalize")
def api_finalize(username: str = Depends(get_current_user)) -> dict[str, Any]:
    """Finalize today's draft into reflections + update streak/summary.

    Intended to be called by a nightly cron/job.
    """
    root = _workspace_root()
    draft_path = root / "planner" / "latest" / "checkin_draft.json"
    state_path = root / "planner" / "state.json"
    ref_path = root / "reflections" / "reflections.md"

    today = _today_str()
    user_tz = _get_user_timezone()
    draft = _read_json(draft_path) if draft_path.exists() else {}
    if draft.get("day") != today:
        return {"ok": False, "reason": "no-draft-for-today", "today": today}

    draft_mode = (draft.get("mode", "commit") or "commit").strip().lower()
    if draft_mode not in {"commit","recovery"}:
        draft_mode = "commit"

    items = draft.get("items", {}) or {}
    reflection = draft.get("reflection", "") or ""

    done_items = []
    for k, v in items.items():
        if v.get("done"):
            done_items.append(str(v.get("label", "(item)")))

    total_items = len(items)
    done_count = len(done_items)

    plan_prev_path = root / "planner" / "latest" / "plan_prev.md"
    plan_path = root / "planner" / "latest" / "plan.md"
    plan_cur = _read_text(plan_path).strip()
    if plan_prev_path.exists():
        plan_changed = _read_text(plan_prev_path).strip() != plan_cur
    elif plan_cur:
        plan_changed = True   # no prev but plan exists — first plan of day
    else:
        plan_changed = False

    rating = _compute_rating(done_count, total_items, reflection, False)
    # recovery mode is more forgiving
    if draft_mode == "recovery" and rating == "bad" and (done_count >= 1 or len(reflection.strip()) >= 30):
        rating = "fair"
    counts = _counts_for_streak(done_count, reflection, plan_changed)
    if draft_mode == "recovery":
        counts = counts or (len(reflection.strip()) >= 30)

    state = _read_json(state_path) if state_path.exists() else {}
    last_streak_date = state.get("lastStreakDate")
    streak = int(state.get("streak", 0) or 0)

    if counts:
        if last_streak_date != today:
            if last_streak_date is not None:
                today_date = datetime.now(user_tz).date()
                try:
                    last_date = date.fromisoformat(last_streak_date)
                    gap = (today_date - last_date).days
                    if gap > 1:
                        streak = 1  # reset — missed day(s)
                    else:
                        streak += 1  # consecutive
                except (ValueError, TypeError):
                    streak = 1
            else:
                streak = 1  # first ever finalize
            state["lastStreakDate"] = today

    summary = _summarize_paragraph(today, rating, done_items, 0, reflection)

    # history (keep last 30 days)
    hist = state.get("history", []) or []
    hist.append({"day": today, "rating": rating, "mode": draft_mode, "streakCounted": bool(counts), "doneCount": done_count, "total": total_items})
    # de-dup by day (keep last entry)
    by_day = {}
    for e in hist:
        by_day[e.get("day")] = e
    hist = list(by_day.values())
    hist.sort(key=lambda x: x.get("day", ""))
    hist = hist[-30:]
    state["history"] = hist


    # prepend reflection entry
    now = datetime.now(user_tz)
    entry_lines = [
        f"## {today}",
        f"- Time: {now.isoformat(timespec='minutes')}",
        "",
        f"**Rating:** {rating.upper()}",
        "",
        f"**Mode:** {draft_mode.upper()}",
        "",
        "**Done**",
    ]
    if done_items:
        for it in done_items:
            entry_lines.append(f"- {it}")
    else:
        entry_lines.append("- (none)")

    entry_lines += [
        "",
        "**Notes**",
    ]

    # include non-done items with comments/time
    notes_added = False
    for k, v in items.items():
        comment = str(v.get("comment", "")).strip()
        label = str(v.get("label", "(item)"))
        if comment:
            notes_added = True
            entry_lines.append(f"- {label}: {comment}")
    if not notes_added:
        entry_lines.append("- (none)")

    entry_lines += [
        "",
        "**Reflection**",
        (reflection.strip() if reflection.strip() else "- (none)"),
        "",
        "**Auto-summary**",
        f"- {summary}",
    ]

    _prepend_reflection(ref_path, "\n".join(entry_lines))

    # update state
    state["streak"] = streak
    state["lastRating"] = rating
    state["lastMode"] = draft_mode
    state["lastSummary"] = summary
    state["lastFinalizedDate"] = today
    _write_json_atomic(state_path, state)

    # clear draft after finalize
    _write_json_atomic(draft_path, {"day": today, "updatedAt": now.isoformat(timespec="seconds"), "items": {}, "reflection": ""})

    return {"ok": True, "day": today, "rating": rating, "streak": streak}


@app.get("/raw/plan")
def raw_plan(username: str = Depends(get_current_user)) -> PlainTextResponse:
    root = _workspace_root()
    plan_path = root / "planner" / "latest" / "plan.md"
    return PlainTextResponse(_read_text(plan_path) or "")


@app.post("/api/update_task")
def api_update_task(payload: dict[str, Any] = Body(...), username: str = Depends(get_current_user)) -> dict[str, Any]:
    """Update a task in tasks.yaml with validation and atomic writes.

    Payload format:
    {
        "task_id": "task-id-here",
        "updates": {
            "remaining_hours": 10,
            "status": "active",
            ...
        }
    }
    """
    root = _workspace_root()
    tasks_path = root / "planner" / "tasks.yaml"

    task_id = payload.get("task_id")
    updates = payload.get("updates", {})

    if not task_id:
        raise HTTPException(status_code=400, detail="Missing task_id")

    if not updates:
        raise HTTPException(status_code=400, detail="Missing updates")

    # Read current tasks
    tasks_txt = _read_text(tasks_path)
    if not tasks_txt.strip():
        raise HTTPException(status_code=404, detail="tasks.yaml is empty or missing")

    try:
        tasks_data = yaml.safe_load(tasks_txt)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse tasks.yaml: {str(e)}")

    if not isinstance(tasks_data, dict) or "tasks" not in tasks_data:
        raise HTTPException(status_code=400, detail="tasks.yaml must contain 'tasks' key")

    tasks_list = tasks_data.get("tasks", [])
    if not isinstance(tasks_list, list):
        raise HTTPException(status_code=400, detail="'tasks' must be a list")

    # Find and update task
    task_found = False
    updated_task = None
    for i, task in enumerate(tasks_list):
        if task.get("id") == task_id:
            task_found = True
            # Apply updates
            for key, value in updates.items():
                task[key] = value

            # Validate updated task
            validation_errors = _validate_task(task)
            if validation_errors:
                raise HTTPException(
                    status_code=400,
                    detail=f"Task validation failed: {'; '.join(validation_errors)}"
                )

            tasks_list[i] = task
            updated_task = task
            break

    if not task_found:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    # Write atomically
    tasks_data["tasks"] = tasks_list
    try:
        _write_yaml_atomic(tasks_path, tasks_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write tasks.yaml: {str(e)}")

    return {"ok": True, "task": updated_task}


