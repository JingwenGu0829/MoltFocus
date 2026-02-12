"""Tests for core/tasks.py — CRUD, validation, lifecycle."""

import pytest
from core.models import Task, TasksFile, CheckinDraft, CheckinItem, State
from core.tasks import (
    validate_task,
    find_task,
    create_task,
    update_task,
    delete_task,
    match_task_from_label,
    update_task_progress,
    process_checkin_progress,
    reset_weekly_budgets,
    archive_completed_tasks,
    get_tasks_with_computed_fields,
    load_tasks,
    save_tasks,
)


def test_validate_task_valid():
    errors = validate_task({"id": "t1", "title": "Task", "type": "open_ended"})
    assert errors == []


def test_validate_task_missing_id():
    errors = validate_task({"title": "Task", "type": "open_ended"})
    assert any("id" in e for e in errors)


def test_validate_task_invalid_type():
    errors = validate_task({"id": "t1", "title": "Task", "type": "invalid"})
    assert any("type" in e for e in errors)


def test_validate_task_invalid_priority():
    errors = validate_task({"id": "t1", "title": "Task", "type": "open_ended", "priority": 11})
    assert any("priority" in e for e in errors)


def test_find_task():
    tf = TasksFile(tasks=[Task(id="a", title="A"), Task(id="b", title="B")])
    assert find_task(tf, "a").title == "A"
    assert find_task(tf, "c") is None


def test_create_task():
    tf = TasksFile()
    task, errors = create_task(tf, {"id": "new", "title": "New Task", "type": "open_ended"})
    assert errors == []
    assert task.id == "new"
    assert len(tf.tasks) == 1


def test_create_task_duplicate():
    tf = TasksFile(tasks=[Task(id="existing", title="X", type="open_ended")])
    _, errors = create_task(tf, {"id": "existing", "title": "Y", "type": "open_ended"})
    assert any("already exists" in e for e in errors)


def test_update_task():
    tf = TasksFile(tasks=[Task(id="a", title="A", type="open_ended", priority=5)])
    updated, errors = update_task(tf, "a", {"priority": 8})
    assert errors == []
    assert updated.priority == 8


def test_update_task_not_found():
    tf = TasksFile()
    _, errors = update_task(tf, "missing", {"priority": 8})
    assert any("not found" in e for e in errors)


def test_delete_task_with_archive():
    tf = TasksFile(tasks=[Task(id="a", title="A", type="open_ended")])
    assert delete_task(tf, "a", archive=True) is True
    assert len(tf.tasks) == 0
    assert len(tf.archived) == 1
    assert tf.archived[0].status == "complete"


def test_delete_task_without_archive():
    tf = TasksFile(tasks=[Task(id="a", title="A", type="open_ended")])
    assert delete_task(tf, "a", archive=False) is True
    assert len(tf.tasks) == 0
    assert len(tf.archived) == 0


def test_match_task_from_label():
    tasks = [
        Task(id="paper", title="Deadline paper", type="deadline_project"),
        Task(id="proj", title="Important project", type="weekly_budget"),
        Task(id="maint", title="Daily maintenance", type="daily_ritual"),
    ]
    assert match_task_from_label("Deadline paper: experiment writeup 2h", tasks).id == "paper"
    assert match_task_from_label("Daily maintenance 20m", tasks).id == "maint"
    assert match_task_from_label("Unknown task 1h", tasks) is None


def test_update_task_progress_deadline():
    task = Task(id="p", type="deadline_project", remaining_hours=10)
    update_task_progress(task, 120)  # 2 hours
    assert task.remaining_hours == 8.0


def test_update_task_progress_deadline_auto_complete():
    task = Task(id="p", type="deadline_project", remaining_hours=0.5, status="active")
    update_task_progress(task, 60)  # 1 hour
    assert task.remaining_hours == 0
    assert task.status == "complete"


def test_update_task_progress_weekly_budget():
    task = Task(id="p", type="weekly_budget", hours_this_week=2.0)
    update_task_progress(task, 90)  # 1.5 hours
    assert task.hours_this_week == 3.5


def test_process_checkin_progress():
    tasks_file = TasksFile(tasks=[
        Task(id="paper", title="Deadline paper", type="deadline_project", remaining_hours=10),
        Task(id="maint", title="Daily maintenance", type="daily_ritual", estimated_minutes_per_day=15),
    ])
    draft = CheckinDraft(items={
        "line-1": CheckinItem(label="Deadline paper: writeup 2h", done=True),
        "line-2": CheckinItem(label="Daily maintenance 20m", done=True),
        "line-3": CheckinItem(label="Something else", done=False),
    })
    updates = process_checkin_progress(draft, tasks_file)
    assert len(updates) == 2
    assert tasks_file.tasks[0].remaining_hours == 8.0  # 10 - 2h


def test_archive_completed_tasks():
    tf = TasksFile(tasks=[
        Task(id="a", status="active"),
        Task(id="b", status="complete"),
        Task(id="c", status="active"),
    ])
    archived_ids = archive_completed_tasks(tf)
    assert archived_ids == ["b"]
    assert len(tf.tasks) == 2
    assert len(tf.archived) == 1


def test_get_tasks_with_computed_fields():
    tf = TasksFile(tasks=[
        Task(id="a", title="A", type="deadline_project", priority=10, remaining_hours=5, deadline="2026-02-15"),
        Task(id="b", title="B", type="weekly_budget", priority=5, target_hours_per_week=8, hours_this_week=2),
    ])
    state = State()
    result = get_tasks_with_computed_fields(tf, state, "2026-02-11")
    assert len(result) == 2
    # Should be sorted by urgency_score descending
    assert result[0]["id"] == "a"  # higher urgency
    assert "urgency_score" in result[0]
    assert "weekly_progress_pct" in result[1]


def test_load_save_tasks_round_trip(workspace):
    tf = load_tasks(workspace)
    assert len(tf.tasks) == 3
    tf.tasks[0].remaining_hours = 5
    save_tasks(tf, workspace)
    tf2 = load_tasks(workspace)
    assert tf2.tasks[0].remaining_hours == 5
