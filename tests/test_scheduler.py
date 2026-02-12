"""Tests for core/scheduler.py — slot computation and schedule generation."""

from datetime import date, time

from core.models import Profile, Task, TasksFile, TimeRange, State
from core.scheduler import compute_available_slots, compute_task_priority_score, generate_schedule


def _make_profile() -> Profile:
    return Profile(
        timezone="UTC",
        work_blocks=[
            TimeRange(time(9, 0), time(11, 0)),
            TimeRange(time(13, 0), time(17, 0)),
        ],
        fixed_routines={
            "lunch": type("R", (), {"window": TimeRange(time(12, 0), time(13, 0))})(),
        },
    )


def test_compute_available_slots_basic():
    """Work blocks minus fixed routines should yield available slots."""
    profile = Profile(
        work_blocks=[TimeRange(time(9, 0), time(17, 0))],
        fixed_routines={
            "lunch": type("R", (), {"window": TimeRange(time(12, 0), time(13, 0))})(),
        },
    )
    # Monday
    slots = compute_available_slots(profile, date(2026, 2, 9))
    assert len(slots) == 2
    assert slots[0].start == time(9, 0)
    assert slots[0].end == time(12, 0)
    assert slots[1].start == time(13, 0)
    assert slots[1].end == time(17, 0)


def test_compute_available_slots_with_weekly_event():
    """Weekly event on a matching weekday should be subtracted."""
    from core.models import WeeklyEvent
    profile = Profile(
        work_blocks=[TimeRange(time(13, 0), time(17, 0))],
        weekly_fixed_events=[
            WeeklyEvent(name="Class", day="tue", time=TimeRange(time(15, 0), time(16, 0)), commute_min_each_way=10),
        ],
    )
    # Tuesday
    slots = compute_available_slots(profile, date(2026, 2, 10))
    # Should have time before class (13:00-14:50) and after (16:10-17:00)
    assert len(slots) >= 1
    # First slot should end before 14:50
    assert slots[0].end <= time(14, 50)


def test_compute_task_priority_score_deadline():
    task = Task(
        id="urgent",
        type="deadline_project",
        priority=10,
        remaining_hours=10,
        deadline="2026-02-13",
    )
    score = compute_task_priority_score(task, date(2026, 2, 11))
    # Should be higher than base priority due to deadline urgency
    assert score > 10


def test_compute_task_priority_score_weekly_budget():
    task = Task(
        id="weekly",
        type="weekly_budget",
        priority=5,
        target_hours_per_week=8,
        hours_this_week=2,
    )
    score = compute_task_priority_score(task, date(2026, 2, 11))
    assert score > 5  # Budget gap should boost score


def test_generate_schedule_basic():
    profile = Profile(
        work_blocks=[TimeRange(time(9, 0), time(17, 0))],
    )
    tasks_file = TasksFile(tasks=[
        Task(id="task-a", title="Task A", type="deadline_project", priority=10,
             remaining_hours=4, min_chunk_minutes=60, max_chunk_minutes=120, status="active"),
        Task(id="task-b", title="Task B", type="daily_ritual", priority=5,
             estimated_minutes_per_day=15, min_chunk_minutes=10, max_chunk_minutes=30, status="active"),
    ])
    schedule = generate_schedule(profile, tasks_file, date(2026, 2, 11))
    assert schedule.date == "2026-02-11"
    assert len(schedule.blocks) >= 2
    assert schedule.total_work_minutes > 0


def test_generate_schedule_no_tasks():
    profile = Profile(work_blocks=[TimeRange(time(9, 0), time(17, 0))])
    tasks_file = TasksFile()
    schedule = generate_schedule(profile, tasks_file, date(2026, 2, 11))
    assert schedule.total_work_minutes == 0
    assert schedule.blocks == []
