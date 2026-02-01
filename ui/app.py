from __future__ import annotations

import json
import os
import re
import difflib
from datetime import datetime, date
from pathlib import Path
from typing import Any

import yaml

ASSET_V = "20260201-01"
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi import Body


def _workspace_root() -> Path:
    # PLANNER_ROOT should be the workspace root that contains planner/ and reflections/
    return Path(os.environ.get("PLANNER_ROOT", str(Path.home() / "planner"))).expanduser().resolve()


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
    _write_text(ref_path, new)


def _escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


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
    return date.today().isoformat()


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


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"ok": "true"}


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    root = _workspace_root()
    plan_path = root / "planner" / "latest" / "plan.md"
    plan_prev_path = root / "planner" / "latest" / "plan_prev.md"
    issues_path = root / "planner" / "latest" / "sglang_issues.md"

    ref_path = root / "reflections" / "reflections.md"
    draft_path = root / "planner" / "latest" / "checkin_draft.json"
    focus_path = root / "planner" / "latest" / "focus.json"
    state_path = root / "planner" / "state.json"

    plan_md = _read_text(plan_path) or "# Plan\n\n(no plan yet)\n"
    issues_md = _read_text(issues_path)

    profile_path = root / "planner" / "profile.yaml"
    tasks_path = root / "planner" / "tasks.yaml"

    profile_txt = _read_text(profile_path)
    tasks_txt = _read_text(tasks_path)

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
              <div data-label>\n                <div class=\"todo-title\">{_escape(title)}</div>{f"<div class=\"todo-dur muted small\">{_escape(dur)}</div>" if dur else ""}
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
              <button id=\"planToggle\" type=\"button\">Edit</button>
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
def save_plan(plan_md: str = Form(...)) -> RedirectResponse:
    root = _workspace_root()
    plan_path = root / "planner" / "latest" / "plan.md"
    prev_path = root / "planner" / "latest" / "plan_prev.md"

    # store prev for diff
    if plan_path.exists():
        _write_text(prev_path, _read_text(plan_path))

    _write_text(plan_path, plan_md.rstrip() + "\n")
    return RedirectResponse(url="/", status_code=303)


@app.post("/api/checkin_draft")
def api_checkin_draft(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    root = _workspace_root()
    draft_path = root / "planner" / "latest" / "checkin_draft.json"
    focus_path = root / "planner" / "latest" / "focus.json"

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

    draft = {
        "day": day,
        "updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": mode_in,
            "items": items,
        "reflection": reflection,
    }

    _write_json(draft_path, draft)
    return {"ok": True, "day": day}


@app.post("/api/finalize")
def api_finalize() -> dict[str, Any]:
    """Finalize today's draft into reflections + update streak/summary.

    Intended to be called by a nightly cron/job.
    """
    root = _workspace_root()
    draft_path = root / "planner" / "latest" / "checkin_draft.json"
    focus_path = root / "planner" / "latest" / "focus.json"
    state_path = root / "planner" / "state.json"
    ref_path = root / "reflections" / "reflections.md"

    today = _today_str()
    draft = _read_json(draft_path) if draft_path.exists() else {}
    if draft.get("day") != today:
        return {"ok": False, "reason": "no-draft-for-today", "today": today}

    draft_mode = (draft.get("mode", "commit") or "commit").strip().lower()
    if draft_mode not in {"commit","recovery"}:
        draft_mode = "commit"

    items = draft.get("items", {}) or {}
    mode = (draft.get("mode", "commit") or "commit").strip().lower()
    if mode not in {"commit","recovery"}:
        mode = "commit"
    reflection = draft.get("reflection", "") or ""

    done_items = []
    minutes_total = 0
    any_time = False
    for k, v in items.items():
        if v.get("done"):
            done_items.append(str(v.get("label", "(item)")))

    total_items = len(items)
    done_count = len(done_items)

    # Plan changed heuristic: if plan_prev exists and differs.
    plan_prev_path = root / "planner" / "latest" / "plan_prev.md"
    plan_changed = plan_prev_path.exists() and _read_text(plan_prev_path).strip() != ""

    rating = _compute_rating(done_count, total_items, reflection, any_time)
    # recovery mode is more forgiving
    if draft_mode == "recovery" and rating == "bad" and (done_count >= 1 or len(reflection.strip()) >= 30 or any_time):
        rating = "fair"
    counts = _counts_for_streak(done_count, reflection, plan_changed)
    if draft_mode == "recovery":
        counts = counts or (len(reflection.strip()) >= 30)

    state = _read_json(state_path) if state_path.exists() else {}
    last_streak_date = state.get("lastStreakDate")
    streak = int(state.get("streak", 0) or 0)

    if counts:
        if last_streak_date != today:
            # naive streak increment (doesn't check gaps for v0)
            streak += 1
            state["lastStreakDate"] = today

    summary = _summarize_paragraph(today, rating, done_items, minutes_total, reflection)

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
    now = datetime.now().astimezone()
    entry_lines = [
        f"## {today}",
        f"- Time: {now.isoformat(timespec='minutes')}",
        "",
        f"**Rating:** {rating.upper()}"
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
    _write_json(state_path, state)

    # clear draft after finalize
    _write_json(draft_path, {"day": today, "updatedAt": now.isoformat(timespec="seconds"), "items": {}, "reflection": ""})

    return {"ok": True, "day": today, "rating": rating, "streak": streak}


@app.get("/raw/plan")
def raw_plan() -> PlainTextResponse:
    root = _workspace_root()
    plan_path = root / "planner" / "latest" / "plan.md"
    return PlainTextResponse(_read_text(plan_path) or "")


@app.post("/api/focus")
def api_focus(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    root = _workspace_root()
    focus_path = root / "planner" / "latest" / "focus.json"
    payload["updatedAt"] = datetime.now().astimezone().isoformat(timespec="seconds")
    _write_json(focus_path, payload)
    return {"ok": True}
