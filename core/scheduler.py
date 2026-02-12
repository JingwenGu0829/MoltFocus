"""Constraint-based scheduling engine for MoltFocus.

Generates time-blocked daily plans algorithmically using profile constraints,
task priorities, and optional analytics data.
"""

from __future__ import annotations

from datetime import date, time
from pathlib import Path
from typing import Any

from core.fileio import read_text, read_yaml, write_text_atomic
from core.models import (
    DaySchedule,
    Profile,
    ScheduledBlock,
    Task,
    TasksFile,
    TimeRange,
    State,
)
from core.tasks import load_tasks
from core.workspace import (
    plan_path,
    profile_path,
    state_path,
    tasks_path,
    workspace_root,
)
from core.fileio import read_json


# ── Constants ─────────────────────────────────────────────────

BUFFER_MINUTES = 5
DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


# ── Slot Computation ──────────────────────────────────────────


def _time_add_minutes(t: time, minutes: int) -> time:
    """Add minutes to a time object, clamping at 23:59."""
    total = t.hour * 60 + t.minute + minutes
    total = max(0, min(total, 23 * 60 + 59))
    return time(total // 60, total % 60)


def compute_available_slots(profile: Profile, target_date: date) -> list[TimeRange]:
    """Compute available work slots for a given date.

    Starts from work_blocks, then subtracts fixed_routines and weekly_fixed_events
    (with commute buffers) for that day of the week.
    """
    weekday = DAY_NAMES[target_date.weekday()]

    # Start with work blocks
    slots = [TimeRange(b.start, b.end) for b in profile.work_blocks]

    # Subtract fixed routines (apply every day)
    blocked: list[TimeRange] = []
    for routine in profile.fixed_routines.values():
        blocked.append(routine.window)

    # Subtract weekly events for this weekday
    for event in profile.weekly_fixed_events:
        if event.day.lower() == weekday:
            # Add commute time before and after
            commute = event.commute_min_each_way
            start = _time_add_minutes(event.time.start, -commute)
            end = _time_add_minutes(event.time.end, commute)
            blocked.append(TimeRange(start, end))

    # Remove blocked ranges from slots
    for block in blocked:
        new_slots = []
        for slot in slots:
            new_slots.extend(slot.subtract(block))
        slots = new_slots

    # Filter out tiny slots (< 10 minutes)
    slots = [s for s in slots if s.duration_minutes() >= 10]

    # Sort by start time
    slots.sort(key=lambda s: (s.start.hour, s.start.minute))
    return slots


# ── Priority Scoring ──────────────────────────────────────────


def compute_task_priority_score(
    task: Task, today: date, state: State | None = None, analytics: dict[str, Any] | None = None
) -> float:
    """Compute composite priority score for scheduling.

    Components:
    - Base priority (1-10 normalized)
    - Deadline urgency: remaining_hours / max(1, days_until_deadline)
    - Weekly budget gap: (target - actual) / target
    - Analytics boost (optional)
    """
    score = float(task.priority)

    # Deadline urgency
    if task.type == "deadline_project" and task.deadline:
        try:
            deadline_date = date.fromisoformat(task.deadline)
            days_left = max(1, (deadline_date - today).days)
            if task.remaining_hours is not None and task.remaining_hours > 0:
                score += (task.remaining_hours / days_left) * 5
        except ValueError:
            pass
    elif task.type == "deadline_project" and task.remaining_hours is not None:
        # No deadline set but has remaining hours - moderate urgency
        if task.remaining_hours > 0:
            score += 2

    # Weekly budget gap
    if task.type == "weekly_budget" and task.target_hours_per_week:
        gap = max(0, task.target_hours_per_week - task.hours_this_week)
        if task.target_hours_per_week > 0:
            score += (gap / task.target_hours_per_week) * 3

    # Daily ritual - small constant boost to ensure they get scheduled
    if task.type == "daily_ritual":
        score += 1

    return score


# ── Schedule Generation ──────────────────────────────────────


def generate_schedule(
    profile: Profile,
    tasks_file: TasksFile,
    target_date: date,
    state: State | None = None,
    analytics: dict[str, Any] | None = None,
) -> DaySchedule:
    """Generate a day schedule using greedy allocation.

    - Score all active tasks, sort descending
    - For each task, find best-fitting slot respecting min_chunk/max_chunk
    - Split tasks across slots if needed
    - Leave 5-min buffers between blocks
    - Unscheduled overflow goes to carryover
    """
    slots = compute_available_slots(profile, target_date)
    total_available = sum(s.duration_minutes() for s in slots)

    # Score and sort tasks
    active_tasks = [t for t in tasks_file.tasks if t.status == "active"]
    scored = [(compute_task_priority_score(t, target_date, state, analytics), t) for t in active_tasks]
    scored.sort(key=lambda x: x[0], reverse=True)

    # Determine how much time each task needs today
    task_needs: list[tuple[float, Task, int]] = []  # (score, task, minutes_needed)
    for score, task in scored:
        if task.type == "daily_ritual":
            needed = task.estimated_minutes_per_day or 15
        elif task.type == "deadline_project":
            needed = task.max_chunk_minutes
        elif task.type == "weekly_budget":
            if task.target_hours_per_week:
                # Distribute remaining budget across remaining weekdays (assume 5 workdays)
                remaining_hours = max(0, task.target_hours_per_week - task.hours_this_week)
                needed = min(task.max_chunk_minutes, int(remaining_hours * 60 / 3))
                needed = max(needed, task.min_chunk_minutes)
            else:
                needed = task.min_chunk_minutes
        else:
            needed = task.min_chunk_minutes

        if needed > 0:
            task_needs.append((score, task, needed))

    # Track remaining capacity in each slot
    slot_cursors = [(s.start, s.end) for s in slots]
    blocks: list[ScheduledBlock] = []
    unscheduled: list[str] = []

    for _score, task, minutes_needed in task_needs:
        remaining = minutes_needed
        allocated = False

        for i, (cursor_start, slot_end) in enumerate(slot_cursors):
            if remaining <= 0:
                break

            available = (slot_end.hour * 60 + slot_end.minute) - (cursor_start.hour * 60 + cursor_start.minute)
            if available < task.min_chunk_minutes:
                continue

            # Allocate time
            chunk = min(remaining, available, task.max_chunk_minutes)
            if chunk < task.min_chunk_minutes:
                continue

            block_end = _time_add_minutes(cursor_start, chunk)
            blocks.append(ScheduledBlock(
                start=cursor_start,
                end=block_end,
                task_id=task.id,
                task_title=task.title,
                duration_minutes=chunk,
                block_type="task",
            ))

            # Advance cursor with buffer
            new_cursor = _time_add_minutes(block_end, BUFFER_MINUTES)
            slot_cursors[i] = (new_cursor, slot_end)
            remaining -= chunk
            allocated = True

        if not allocated:
            unscheduled.append(task.id)

    # Add fixed routines and events as informational blocks
    routine_blocks: list[ScheduledBlock] = []
    for name, routine in profile.fixed_routines.items():
        routine_blocks.append(ScheduledBlock(
            start=routine.window.start,
            end=routine.window.end,
            task_id=name,
            task_title=name.replace("_", " ").title(),
            duration_minutes=routine.window.duration_minutes(),
            block_type="routine",
        ))

    weekday = DAY_NAMES[target_date.weekday()]
    for event in profile.weekly_fixed_events:
        if event.day.lower() == weekday:
            routine_blocks.append(ScheduledBlock(
                start=event.time.start,
                end=event.time.end,
                task_id=event.name.lower().replace(" ", "-"),
                task_title=event.name,
                duration_minutes=event.time.duration_minutes(),
                block_type="event",
            ))

    # Merge and sort all blocks by start time
    all_blocks = blocks + routine_blocks
    all_blocks.sort(key=lambda b: (b.start.hour if b.start else 0, b.start.minute if b.start else 0))

    total_work = sum(b.duration_minutes for b in blocks)

    return DaySchedule(
        date=target_date.isoformat(),
        blocks=all_blocks,
        unscheduled_tasks=unscheduled,
        total_work_minutes=total_work,
        utilization_pct=(total_work / total_available * 100) if total_available > 0 else 0,
    )


# ── Plan.md Rendering ─────────────────────────────────────────


def schedule_to_plan_md(schedule: DaySchedule, tasks_file: TasksFile) -> str:
    """Render a DaySchedule to the expected plan.md format."""
    lines = [f"# Plan \u2014 {schedule.date}", ""]

    # Top priorities - task blocks sorted by priority
    task_blocks = [b for b in schedule.blocks if b.block_type == "task"]
    seen_tasks: set[str] = set()
    priorities = []
    for b in task_blocks:
        if b.task_id not in seen_tasks:
            seen_tasks.add(b.task_id)
            priorities.append(b)

    if priorities:
        lines.append("## Top priorities")
        for i, b in enumerate(priorities[:5], 1):
            lines.append(f"{i}) {b.task_title}")
        lines.append("")

    # Schedule
    lines.append("## Schedule")
    for b in schedule.blocks:
        start = b.start.strftime("%H:%M") if b.start else "?"
        end = b.end.strftime("%H:%M") if b.end else "?"
        dur_str = ""
        if b.block_type == "task":
            if b.duration_minutes >= 60:
                h = b.duration_minutes // 60
                m = b.duration_minutes % 60
                dur_str = f" {h}h" if m == 0 else f" {h}h{m:02d}m"
            else:
                dur_str = f" {b.duration_minutes}m"
        lines.append(f"- {start}\u2013{end} {b.task_title}{dur_str}")
    lines.append("")

    # Minimum viable day (checkboxes for task blocks)
    lines.append("## Minimum viable day")
    seen_labels: set[str] = set()
    for b in task_blocks:
        # Build label: "Task title: sub-description Xm/Xh"
        dur = ""
        if b.duration_minutes >= 60:
            h = b.duration_minutes // 60
            m = b.duration_minutes % 60
            dur = f" {h}h" if m == 0 else f" {h}h{m:02d}m"
        else:
            dur = f" {b.duration_minutes}m"

        label = f"{b.task_title}{dur}"
        if label not in seen_labels:
            seen_labels.add(label)
            lines.append(f"- [ ] {label}")
    lines.append("")

    # Carryover
    if schedule.unscheduled_tasks:
        lines.append("## Carryover")
        for task_id in schedule.unscheduled_tasks:
            from core.tasks import find_task
            task = find_task(tasks_file, task_id)
            title = task.title if task else task_id
            lines.append(f"- {title} (deferred \u2014 insufficient time slots)")
        lines.append("")

    return "\n".join(lines)


# ── High-level API ────────────────────────────────────────────


def generate_plan(target_date: date | None = None, root: Path | None = None) -> str:
    """High-level: load all data, generate schedule, write plan.md, return content."""
    if root is None:
        root = workspace_root()

    # Load profile
    profile_data = read_yaml(profile_path(root))
    profile = Profile.from_dict(profile_data)

    # Load tasks
    tasks_file = load_tasks(root)

    # Load state
    state_data = read_json(state_path(root))
    state = State.from_dict(state_data)

    # Target date
    if target_date is None:
        from core.workspace import get_user_timezone
        from datetime import datetime
        tz = get_user_timezone(root)
        target_date = datetime.now(tz).date()

    # Load analytics if available
    analytics = None
    from core.workspace import analytics_path
    analytics_data = read_json(analytics_path(root))
    if analytics_data:
        analytics = analytics_data

    # Generate schedule
    schedule = generate_schedule(profile, tasks_file, target_date, state, analytics)

    # Render to markdown
    plan_md = schedule_to_plan_md(schedule, tasks_file)

    # Write plan.md (preserve previous)
    pp = plan_path(root)
    from core.workspace import plan_prev_path
    ppp = plan_prev_path(root)
    existing = read_text(pp)
    if existing.strip():
        write_text_atomic(ppp, existing)

    write_text_atomic(pp, plan_md)

    return plan_md
