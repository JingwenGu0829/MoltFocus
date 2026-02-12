"""Task CRUD, validation, lifecycle, and progress tracking for MoltFocus."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from core.checkbox import parse_duration_from_label, parse_task_title_from_label
from core.fileio import read_yaml, write_yaml_atomic
from core.models import CheckinDraft, Task, TasksFile, State
from core.workspace import tasks_path as _tasks_path


# ── Validation ────────────────────────────────────────────────


VALID_TYPES = {"deadline_project", "weekly_budget", "daily_ritual", "open_ended"}
VALID_STATUSES = {"active", "paused", "complete"}


def validate_task(task: dict[str, Any]) -> list[str]:
    """Validate task schema and return list of errors (empty if valid)."""
    errors = []
    if "id" not in task:
        errors.append("Missing required field: id")
    if "title" not in task:
        errors.append("Missing required field: title")
    if "type" not in task:
        errors.append("Missing required field: type")
    elif task["type"] not in VALID_TYPES:
        errors.append(f"Invalid task type: {task['type']}")

    if task.get("type") == "deadline_project":
        if "remaining_hours" in task and not isinstance(task["remaining_hours"], (int, float)):
            errors.append("remaining_hours must be numeric")
    elif task.get("type") == "weekly_budget":
        if "target_hours_per_week" in task and not isinstance(task["target_hours_per_week"], (int, float)):
            errors.append("target_hours_per_week must be numeric")

    if "status" in task and task["status"] not in VALID_STATUSES:
        errors.append(f"Invalid status: {task['status']}")

    if "priority" in task:
        if not isinstance(task["priority"], int) or task["priority"] < 1 or task["priority"] > 10:
            errors.append("priority must be integer 1-10")

    return errors


# ── CRUD ──────────────────────────────────────────────────────


def load_tasks(root: Path | None = None) -> TasksFile:
    """Load tasks.yaml into a TasksFile model."""
    path = _tasks_path(root)
    data = read_yaml(path)
    return TasksFile.from_dict(data)


def save_tasks(tasks_file: TasksFile, root: Path | None = None) -> None:
    """Save TasksFile back to tasks.yaml atomically."""
    path = _tasks_path(root)
    write_yaml_atomic(path, tasks_file.to_dict())


def find_task(tasks_file: TasksFile, task_id: str) -> Task | None:
    """Find a task by ID in the active task list."""
    for t in tasks_file.tasks:
        if t.id == task_id:
            return t
    return None


def create_task(tasks_file: TasksFile, task_data: dict[str, Any]) -> tuple[Task, list[str]]:
    """Create and add a new task. Returns (task, errors)."""
    errors = validate_task(task_data)
    if errors:
        return Task(), errors

    # Check for duplicate ID
    task_id = task_data["id"]
    if find_task(tasks_file, task_id):
        return Task(), [f"Task ID already exists: {task_id}"]

    task = Task.from_dict(task_data)
    tasks_file.tasks.append(task)
    return task, []


def update_task(tasks_file: TasksFile, task_id: str, updates: dict[str, Any]) -> tuple[Task | None, list[str]]:
    """Update a task by ID. Returns (updated_task, errors)."""
    task = find_task(tasks_file, task_id)
    if not task:
        return None, [f"Task not found: {task_id}"]

    # Apply updates
    task_dict = task.to_dict()
    task_dict.update(updates)

    errors = validate_task(task_dict)
    if errors:
        return None, errors

    # Apply to the actual task object
    updated = Task.from_dict(task_dict)
    for i, t in enumerate(tasks_file.tasks):
        if t.id == task_id:
            tasks_file.tasks[i] = updated
            break
    return updated, []


def delete_task(tasks_file: TasksFile, task_id: str, archive: bool = True) -> bool:
    """Remove a task from active list. If archive=True, move to archived list."""
    for i, t in enumerate(tasks_file.tasks):
        if t.id == task_id:
            task = tasks_file.tasks.pop(i)
            if archive:
                task.status = "complete"
                tasks_file.archived.append(task)
            return True
    return False


# ── Phase 2: Task Lifecycle & Progress Tracking ──────────────


def match_task_from_label(label: str, tasks: list[Task]) -> Task | None:
    """Match a checkin label to a task via title prefix matching.

    'Deadline paper: experiment writeup 2h' -> matches task with title 'Deadline paper'
    """
    title_prefix = parse_task_title_from_label(label)
    if not title_prefix:
        return None

    # Try exact title match first, then case-insensitive prefix
    prefix_lower = title_prefix.lower()
    for task in tasks:
        if task.title.lower() == prefix_lower:
            return task
    for task in tasks:
        if task.title.lower().startswith(prefix_lower) or prefix_lower.startswith(task.title.lower()):
            return task
    return None


def update_task_progress(task: Task, minutes_done: int) -> None:
    """Update a task's progress based on completed work.

    - deadline_project: decrement remaining_hours; auto-complete when <= 0
    - weekly_budget: increment hours_this_week
    - daily_ritual: (no numeric tracking, just counts as done-for-today)
    """
    if task.type == "deadline_project" and task.remaining_hours is not None:
        task.remaining_hours = max(0, task.remaining_hours - minutes_done / 60.0)
        if task.remaining_hours <= 0:
            task.status = "complete"
    elif task.type == "weekly_budget":
        task.hours_this_week += minutes_done / 60.0


def process_checkin_progress(draft: CheckinDraft, tasks_file: TasksFile) -> list[str]:
    """Process all done items in a checkin draft, updating task progress.

    Returns list of update descriptions.
    """
    updates = []
    for _key, item in draft.items.items():
        if not item.done:
            continue
        task = match_task_from_label(item.label, tasks_file.tasks)
        if not task:
            continue
        minutes = parse_duration_from_label(item.label)
        if minutes <= 0:
            # Default: estimate from task type
            if task.type == "daily_ritual" and task.estimated_minutes_per_day:
                minutes = task.estimated_minutes_per_day
            else:
                minutes = 30  # fallback
        update_task_progress(task, minutes)
        updates.append(f"{task.id}: +{minutes}min")
    return updates


def reset_weekly_budgets(tasks_file: TasksFile, state: State, today: str) -> bool:
    """Reset hours_this_week to 0 when a new week starts.

    Returns True if a reset was performed.
    """
    DAY_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
    week_start_day = DAY_MAP.get(tasks_file.week_start.lower(), 0)

    try:
        today_date = date.fromisoformat(today)
    except ValueError:
        return False

    current_weekday = today_date.weekday()

    # Check if we need to reset
    if state.week_start_date:
        try:
            last_start = date.fromisoformat(state.week_start_date)
            if (today_date - last_start).days < 7:
                return False
        except ValueError:
            pass

    # Check if today is the week start day
    if current_weekday == week_start_day:
        for task in tasks_file.tasks:
            if task.type == "weekly_budget":
                task.hours_this_week = 0.0
        state.week_start_date = today
        return True

    # If we've never tracked, set it to the most recent week start
    if not state.week_start_date:
        days_since = (current_weekday - week_start_day) % 7
        last_start = today_date.__class__.fromordinal(today_date.toordinal() - days_since)
        state.week_start_date = last_start.isoformat()

    return False


def archive_completed_tasks(tasks_file: TasksFile) -> list[str]:
    """Move completed tasks to the archived list. Returns IDs of archived tasks."""
    archived_ids = []
    remaining = []
    for task in tasks_file.tasks:
        if task.status == "complete":
            tasks_file.archived.append(task)
            archived_ids.append(task.id)
        else:
            remaining.append(task)
    tasks_file.tasks = remaining
    return archived_ids


def get_tasks_with_computed_fields(
    tasks_file: TasksFile, state: State, today: str
) -> list[dict[str, Any]]:
    """Return tasks with added computed fields: urgency_score, weekly_progress_pct, days_until_deadline."""
    result = []
    try:
        today_date = date.fromisoformat(today)
    except ValueError:
        today_date = date.today()

    for task in tasks_file.tasks:
        d = task.to_dict()

        # Urgency score
        urgency = float(task.priority)
        if task.type == "deadline_project" and task.deadline:
            try:
                deadline_date = date.fromisoformat(task.deadline)
                days_left = max(1, (deadline_date - today_date).days)
                d["days_until_deadline"] = days_left
                if task.remaining_hours is not None and task.remaining_hours > 0:
                    urgency += (task.remaining_hours / days_left) * 5
            except ValueError:
                pass

        if task.type == "weekly_budget" and task.target_hours_per_week:
            gap = max(0, task.target_hours_per_week - task.hours_this_week)
            d["weekly_progress_pct"] = round(
                (task.hours_this_week / task.target_hours_per_week) * 100, 1
            )
            urgency += (gap / task.target_hours_per_week) * 3

        d["urgency_score"] = round(urgency, 2)
        result.append(d)

    result.sort(key=lambda x: x.get("urgency_score", 0), reverse=True)
    return result
