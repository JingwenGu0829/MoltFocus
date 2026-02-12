"""Consolidated, idempotent finalization logic for MoltFocus.

The finalization pipeline:
1. Load & validate draft
2. Idempotency check (skip if already finalized today)
3. Compute rating/streak
4. Build & prepend reflection
5. Update state.json
6. Process checkin progress + update tasks
7. Refresh analytics
8. Generate agent_context.json
9. Run hooks
10. Clear draft
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from core.fileio import read_json, write_json_atomic
from core.models import CheckinDraft, State
from core.rating import compute_rating, counts_for_streak, summarize_paragraph
from core.reflections import build_reflection_entry, prepend_reflection
from core.tasks import (
    archive_completed_tasks,
    load_tasks,
    process_checkin_progress,
    reset_weekly_budgets,
    save_tasks,
)
from core.workspace import (
    draft_path,
    now_local,
    reflections_path,
    state_path,
    today_str,
    workspace_root,
    plan_path as _plan_path,
    plan_prev_path as _plan_prev_path,
)
from core.fileio import read_text


def finalize_day(root: Path | None = None) -> dict[str, Any]:
    """Finalize today's draft into reflections + update streak/summary.

    This is the consolidated finalization function used by both the API and CLI.
    It is idempotent: a second call on the same day returns already_finalized=True.
    """
    if root is None:
        root = workspace_root()

    dp = draft_path(root)
    sp = state_path(root)
    rp = reflections_path(root)

    today = today_str(root)
    now = now_local(root)

    # 1. Load & validate draft
    raw_draft = read_json(dp)
    if raw_draft.get("day") != today:
        return {"ok": False, "reason": "no-draft-for-today", "today": today}

    # 2. Idempotency guard
    raw_state = read_json(sp)
    state = State.from_dict(raw_state)
    if state.last_finalized_date == today:
        return {"ok": True, "day": today, "already_finalized": True}

    draft = CheckinDraft.from_dict(raw_draft)
    draft_mode = draft.mode
    if draft_mode not in {"commit", "recovery"}:
        draft_mode = "commit"

    items_raw = raw_draft.get("items", {}) or {}
    reflection = draft.reflection

    # Collect done items
    done_items = []
    for _k, item in draft.items.items():
        if item.done:
            done_items.append(item.label or "(item)")

    total_items = len(draft.items)
    done_count = len(done_items)

    # Plan changed detection
    pp = _plan_path(root)
    ppp = _plan_prev_path(root)
    plan_cur = read_text(pp).strip()
    if ppp.exists():
        plan_changed = read_text(ppp).strip() != plan_cur
    elif plan_cur:
        plan_changed = True
    else:
        plan_changed = False

    # 3. Compute rating/streak
    rating = compute_rating(done_count, total_items, reflection, False)
    if draft_mode == "recovery" and rating == "bad" and (done_count >= 1 or len(reflection.strip()) >= 30):
        rating = "fair"

    counts = counts_for_streak(done_count, reflection, plan_changed)
    if draft_mode == "recovery":
        counts = counts or (len(reflection.strip()) >= 30)

    streak = state.streak
    last_streak_date = state.last_streak_date

    if counts:
        if last_streak_date != today:
            if last_streak_date is not None:
                try:
                    last_date = date.fromisoformat(last_streak_date)
                    gap = (now.date() - last_date).days
                    if gap > 1:
                        streak = 1
                    else:
                        streak += 1
                except (ValueError, TypeError):
                    streak = 1
            else:
                streak = 1
            state.last_streak_date = today

    summary = summarize_paragraph(today, rating, done_items, 0, reflection)

    # History (keep last 30 days)
    from core.models import HistoryEntry

    hist_entry = HistoryEntry(
        day=today, rating=rating, mode=draft_mode,
        streak_counted=bool(counts), done_count=done_count, total=total_items,
    )
    # De-dup by day
    by_day = {e.day: e for e in state.history}
    by_day[today] = hist_entry
    state.history = sorted(by_day.values(), key=lambda x: x.day)[-30:]

    # 4. Build & prepend reflection
    entry_md = build_reflection_entry(
        today=today,
        now_iso=now.isoformat(timespec="minutes"),
        rating=rating,
        mode=draft_mode,
        done_items=done_items,
        items=items_raw,
        reflection=reflection,
        summary=summary,
    )
    prepend_reflection(rp, entry_md)

    # 5. Update state
    state.streak = streak
    state.last_rating = rating
    state.last_mode = draft_mode
    state.last_summary = summary
    state.last_finalized_date = today
    write_json_atomic(sp, state.to_dict())

    # 6. Process checkin progress + update tasks
    task_updates = []
    try:
        tasks_file = load_tasks(root)
        reset_weekly_budgets(tasks_file, state, today)
        task_updates = process_checkin_progress(draft, tasks_file)
        archived = archive_completed_tasks(tasks_file)
        if task_updates or archived:
            save_tasks(tasks_file, root)
            # Re-save state if week_start_date changed
            write_json_atomic(sp, state.to_dict())
    except Exception:
        pass  # Task processing is best-effort

    # 7. Refresh analytics (best-effort)
    try:
        from core.analytics import refresh_analytics
        refresh_analytics(root)
    except Exception:
        pass

    # 8. Generate agent_context.json (best-effort)
    try:
        from core.agent_context import generate_agent_context
        generate_agent_context(root)
    except Exception:
        pass

    # 9. Run hooks (best-effort)
    try:
        from core.hooks import run_hooks
        run_hooks("post_finalize", {
            "day": today, "rating": rating, "streak": streak,
            "done_count": done_count, "total": total_items,
        }, root)
    except Exception:
        pass

    # 10. Clear draft
    write_json_atomic(dp, {
        "day": today,
        "updatedAt": now.isoformat(timespec="seconds"),
        "items": {},
        "reflection": "",
    })

    return {
        "ok": True,
        "day": today,
        "rating": rating,
        "streak": streak,
        "task_updates": task_updates,
    }
