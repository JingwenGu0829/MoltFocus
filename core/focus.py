"""Focus session management for MoltFocus.

Implements Pomodoro-style focus sessions with interruption tracking
and automatic task progress logging.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from core.fileio import read_json, write_json_atomic
from core.models import FocusSession, FocusState
from core.workspace import focus_path, get_user_timezone, workspace_root


def _load_focus_state(root: Path | None = None) -> FocusState:
    if root is None:
        root = workspace_root()
    data = read_json(focus_path(root))
    return FocusState.from_dict(data)


def _save_focus_state(state: FocusState, root: Path | None = None) -> None:
    if root is None:
        root = workspace_root()
    write_json_atomic(focus_path(root), state.to_dict())


def start_session(
    task_id: str,
    task_label: str,
    planned_minutes: int = 25,
    root: Path | None = None,
) -> FocusSession:
    """Start a new focus session. Raises if a session is already active."""
    if root is None:
        root = workspace_root()

    state = _load_focus_state(root)
    if state.active_session is not None:
        raise ValueError("A focus session is already active. Stop it first.")

    tz = get_user_timezone(root)
    now = datetime.now(tz)

    session = FocusSession(
        task_id=task_id,
        task_label=task_label,
        started_at=now.isoformat(timespec="seconds"),
        planned_minutes=planned_minutes,
    )
    state.active_session = session
    _save_focus_state(state, root)
    return session


def stop_session(
    completed: bool = False,
    notes: str = "",
    root: Path | None = None,
) -> FocusSession:
    """Stop the active focus session. Returns the completed session."""
    if root is None:
        root = workspace_root()

    state = _load_focus_state(root)
    if state.active_session is None:
        raise ValueError("No active focus session to stop.")

    session = state.active_session
    tz = get_user_timezone(root)
    now = datetime.now(tz)

    session.ended_at = now.isoformat(timespec="seconds")
    session.completed = completed
    session.notes = notes

    # Calculate elapsed time
    try:
        start = datetime.fromisoformat(session.started_at)
        elapsed = (now - start).total_seconds() / 60
        session.elapsed_minutes = round(elapsed, 1)
    except (ValueError, TypeError):
        session.elapsed_minutes = 0.0

    # Move to history
    state.history.append(session)
    state.active_session = None
    _save_focus_state(state, root)

    # Auto-log to task progress (best-effort)
    if session.elapsed_minutes > 0:
        try:
            from core.tasks import load_tasks, find_task, update_task_progress, save_tasks
            tasks_file = load_tasks(root)
            task = find_task(tasks_file, session.task_id)
            if task:
                update_task_progress(task, int(session.elapsed_minutes))
                save_tasks(tasks_file, root)
        except Exception:
            pass

    return session


def record_interruption(root: Path | None = None) -> FocusSession | None:
    """Increment the interruption counter on the active session."""
    if root is None:
        root = workspace_root()

    state = _load_focus_state(root)
    if state.active_session is None:
        return None

    state.active_session.interruptions += 1
    _save_focus_state(state, root)
    return state.active_session


def get_active_session(root: Path | None = None) -> FocusSession | None:
    """Get the current active focus session, or None."""
    state = _load_focus_state(root)
    return state.active_session


def get_focus_state(root: Path | None = None) -> FocusState:
    """Get the full focus state (active session + history)."""
    return _load_focus_state(root)


def get_focus_stats(days: int = 7, root: Path | None = None) -> dict[str, Any]:
    """Get focus session statistics for the last N days."""
    state = _load_focus_state(root)

    if not state.history:
        return {
            "total_sessions": 0,
            "total_minutes": 0,
            "avg_session_minutes": 0,
            "total_interruptions": 0,
            "completion_rate": 0,
        }

    # Filter to last N days
    from datetime import timedelta
    tz = get_user_timezone(root)
    cutoff = datetime.now(tz) - timedelta(days=days)
    cutoff_str = cutoff.isoformat()

    recent = [s for s in state.history if s.started_at >= cutoff_str]

    if not recent:
        return {
            "total_sessions": 0,
            "total_minutes": 0,
            "avg_session_minutes": 0,
            "total_interruptions": 0,
            "completion_rate": 0,
        }

    total_minutes = sum(s.elapsed_minutes for s in recent)
    completed = sum(1 for s in recent if s.completed)

    return {
        "total_sessions": len(recent),
        "total_minutes": round(total_minutes, 1),
        "avg_session_minutes": round(total_minutes / len(recent), 1),
        "total_interruptions": sum(s.interruptions for s in recent),
        "completion_rate": round(completed / len(recent), 3),
    }
