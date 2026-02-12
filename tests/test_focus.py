"""Tests for core/focus.py — focus session lifecycle."""

import pytest
from core.focus import (
    start_session,
    stop_session,
    record_interruption,
    get_active_session,
    get_focus_state,
    get_focus_stats,
)


def test_start_session(workspace):
    session = start_session("task-1", "My Task", planned_minutes=25, root=workspace)
    assert session.task_id == "task-1"
    assert session.task_label == "My Task"
    assert session.planned_minutes == 25


def test_start_session_already_active(workspace):
    start_session("task-1", "Task 1", root=workspace)
    with pytest.raises(ValueError, match="already active"):
        start_session("task-2", "Task 2", root=workspace)


def test_stop_session(workspace):
    start_session("task-1", "Task 1", root=workspace)
    session = stop_session(completed=True, notes="Done!", root=workspace)
    assert session.completed is True
    assert session.notes == "Done!"
    assert session.elapsed_minutes >= 0


def test_stop_session_no_active(workspace):
    with pytest.raises(ValueError, match="No active"):
        stop_session(root=workspace)


def test_record_interruption(workspace):
    start_session("task-1", "Task 1", root=workspace)
    session = record_interruption(root=workspace)
    assert session.interruptions == 1
    session = record_interruption(root=workspace)
    assert session.interruptions == 2


def test_record_interruption_no_active(workspace):
    result = record_interruption(root=workspace)
    assert result is None


def test_get_active_session(workspace):
    assert get_active_session(root=workspace) is None
    start_session("task-1", "Task 1", root=workspace)
    session = get_active_session(root=workspace)
    assert session is not None
    assert session.task_id == "task-1"


def test_focus_stats_empty(workspace):
    stats = get_focus_stats(days=7, root=workspace)
    assert stats["total_sessions"] == 0


def test_full_focus_lifecycle(workspace):
    """Start -> interrupt -> stop -> check stats."""
    start_session("task-1", "Task 1", 25, root=workspace)
    record_interruption(root=workspace)
    stop_session(completed=True, root=workspace)

    state = get_focus_state(root=workspace)
    assert state.active_session is None
    assert len(state.history) == 1
    assert state.history[0].interruptions == 1
    assert state.history[0].completed is True
