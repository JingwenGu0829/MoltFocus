"""Tests for core/models.py — dataclass serialization round-trips."""

from core.models import (
    TimeRange,
    Profile,
    Task,
    TasksFile,
    CheckinDraft,
    CheckinItem,
    State,
    HistoryEntry,
    FocusSession,
    FocusState,
)
from datetime import time


def test_time_range_from_str():
    tr = TimeRange.from_str("09:00-11:00")
    assert tr.start == time(9, 0)
    assert tr.end == time(11, 0)
    assert tr.duration_minutes() == 120


def test_time_range_with_en_dash():
    tr = TimeRange.from_str("09:00\u201311:00")
    assert tr.start == time(9, 0)
    assert tr.end == time(11, 0)


def test_time_range_overlaps():
    a = TimeRange(time(9, 0), time(11, 0))
    b = TimeRange(time(10, 0), time(12, 0))
    c = TimeRange(time(12, 0), time(13, 0))
    assert a.overlaps(b) is True
    assert a.overlaps(c) is False


def test_time_range_subtract():
    a = TimeRange(time(9, 0), time(17, 0))
    b = TimeRange(time(12, 0), time(13, 0))
    result = a.subtract(b)
    assert len(result) == 2
    assert result[0].start == time(9, 0)
    assert result[0].end == time(12, 0)
    assert result[1].start == time(13, 0)
    assert result[1].end == time(17, 0)


def test_profile_from_dict():
    data = {
        "timezone": "America/Los_Angeles",
        "wake_time": "08:30",
        "work_blocks": ["09:00-11:00", "13:00-17:00"],
        "fixed_routines": {
            "lunch": {"window": "12:00-13:00", "duration_min": 60},
        },
        "commute": {"typical_one_way_min": 20},
        "weekly_fixed_events": [
            {"name": "Class", "day": "tue", "time": "15:00-16:00", "commute_min_each_way": 10},
        ],
    }
    p = Profile.from_dict(data)
    assert p.timezone == "America/Los_Angeles"
    assert len(p.work_blocks) == 2
    assert "lunch" in p.fixed_routines
    assert p.commute_typical_one_way_min == 20
    assert len(p.weekly_fixed_events) == 1


def test_profile_from_empty():
    p = Profile.from_dict({})
    assert p.timezone == "UTC"
    assert p.work_blocks == []


def test_task_round_trip():
    data = {
        "id": "my-task",
        "title": "My Task",
        "type": "deadline_project",
        "priority": 8,
        "status": "active",
        "remaining_hours": 10,
    }
    t = Task.from_dict(data)
    assert t.id == "my-task"
    assert t.remaining_hours == 10
    d = t.to_dict()
    assert d["id"] == "my-task"
    assert d["remaining_hours"] == 10


def test_task_weekly_budget_round_trip():
    data = {
        "id": "proj",
        "title": "Project",
        "type": "weekly_budget",
        "target_hours_per_week": 8,
        "hours_this_week": 3.5,
    }
    t = Task.from_dict(data)
    assert t.hours_this_week == 3.5
    d = t.to_dict()
    assert d["hours_this_week"] == 3.5


def test_tasks_file_with_archived():
    data = {
        "week_start": "mon",
        "tasks": [{"id": "a", "title": "A", "type": "open_ended"}],
        "archived": [{"id": "b", "title": "B", "type": "open_ended", "status": "complete"}],
    }
    tf = TasksFile.from_dict(data)
    assert len(tf.tasks) == 1
    assert len(tf.archived) == 1
    d = tf.to_dict()
    assert len(d["archived"]) == 1


def test_checkin_draft_from_dict():
    data = {
        "day": "2026-02-11",
        "updatedAt": "2026-02-11T17:00:00",
        "mode": "commit",
        "items": {
            "line-1": {"label": "Task 1", "done": True, "comment": "done"},
            "line-2": {"label": "Task 2", "done": False, "comment": ""},
        },
        "reflection": "Good day.",
    }
    draft = CheckinDraft.from_dict(data)
    assert draft.day == "2026-02-11"
    assert len(draft.items) == 2
    assert draft.items["line-1"].done is True
    assert draft.reflection == "Good day."


def test_state_round_trip():
    data = {
        "streak": 5,
        "lastStreakDate": "2026-02-10",
        "lastRating": "good",
        "history": [
            {"day": "2026-02-10", "rating": "good", "streakCounted": True, "doneCount": 3, "total": 4},
        ],
    }
    s = State.from_dict(data)
    assert s.streak == 5
    assert len(s.history) == 1
    d = s.to_dict()
    assert d["streak"] == 5
    assert d["lastStreakDate"] == "2026-02-10"


def test_focus_session_round_trip():
    data = {
        "taskId": "my-task",
        "taskLabel": "My Task",
        "startedAt": "2026-02-11T10:00:00",
        "plannedMinutes": 25,
        "interruptions": 2,
    }
    s = FocusSession.from_dict(data)
    assert s.task_id == "my-task"
    assert s.interruptions == 2
    d = s.to_dict()
    assert d["taskId"] == "my-task"
    assert d["interruptions"] == 2
