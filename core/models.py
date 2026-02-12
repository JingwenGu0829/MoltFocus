"""Typed dataclasses for MoltFocus data model.

All models use from_dict/to_dict for JSON/YAML serialization.
camelCase in JSON is mapped to snake_case in Python.
Unknown keys are ignored; missing keys use defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any


# ── Primitives ────────────────────────────────────────────────


@dataclass
class TimeRange:
    """A start-end time range within a single day."""

    start: time
    end: time

    @classmethod
    def from_str(cls, s: str) -> TimeRange:
        """Parse '09:00-11:00' or '09:00\u201311:00'."""
        s = s.replace("\u2013", "-").replace("\u2014", "-")
        parts = s.split("-")
        if len(parts) != 2:
            raise ValueError(f"Invalid time range: {s!r}")
        return cls(
            start=time.fromisoformat(parts[0].strip()),
            end=time.fromisoformat(parts[1].strip()),
        )

    def duration_minutes(self) -> int:
        s = self.start.hour * 60 + self.start.minute
        e = self.end.hour * 60 + self.end.minute
        return max(0, e - s)

    def to_str(self) -> str:
        return f"{self.start.strftime('%H:%M')}-{self.end.strftime('%H:%M')}"

    def overlaps(self, other: TimeRange) -> bool:
        return self.start < other.end and other.start < self.end

    def subtract(self, other: TimeRange) -> list[TimeRange]:
        """Return remaining slots after removing *other* from *self*."""
        if not self.overlaps(other):
            return [TimeRange(self.start, self.end)]
        result = []
        if self.start < other.start:
            result.append(TimeRange(self.start, other.start))
        if other.end < self.end:
            result.append(TimeRange(other.end, self.end))
        return result


# ── Profile ───────────────────────────────────────────────────


@dataclass
class FixedRoutine:
    name: str
    window: TimeRange
    duration_min: int | None = None

    @classmethod
    def from_dict(cls, name: str, d: dict[str, Any]) -> FixedRoutine:
        window = TimeRange.from_str(d.get("window", "00:00-00:00"))
        return cls(name=name, window=window, duration_min=d.get("duration_min"))


@dataclass
class WeeklyEvent:
    name: str
    day: str  # mon, tue, wed, ...
    time: TimeRange
    location: str = ""
    commute_min_each_way: int = 0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WeeklyEvent:
        return cls(
            name=d.get("name", ""),
            day=d.get("day", "").lower(),
            time=TimeRange.from_str(d.get("time", "00:00-00:00")),
            location=d.get("location", ""),
            commute_min_each_way=int(d.get("commute_min_each_way", 0)),
        )


@dataclass
class Profile:
    timezone: str = "UTC"
    wake_time: str = "08:00"
    daily_plan_delivery_time: str = "08:30"
    work_blocks: list[TimeRange] = field(default_factory=list)
    fixed_routines: dict[str, FixedRoutine] = field(default_factory=dict)
    commute_typical_one_way_min: int = 0
    weekly_fixed_events: list[WeeklyEvent] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Profile:
        if not d or not isinstance(d, dict):
            return cls()
        work_blocks = [TimeRange.from_str(s) for s in (d.get("work_blocks") or [])]
        routines = {}
        for name, rd in (d.get("fixed_routines") or {}).items():
            if isinstance(rd, dict):
                routines[name] = FixedRoutine.from_dict(name, rd)
        events = [WeeklyEvent.from_dict(e) for e in (d.get("weekly_fixed_events") or [])]
        commute = d.get("commute", {})
        commute_min = int(commute.get("typical_one_way_min", 0)) if isinstance(commute, dict) else 0
        return cls(
            timezone=d.get("timezone", "UTC"),
            wake_time=d.get("wake_time", "08:00"),
            daily_plan_delivery_time=d.get("daily_plan_delivery_time", "08:30"),
            work_blocks=work_blocks,
            fixed_routines=routines,
            commute_typical_one_way_min=commute_min,
            weekly_fixed_events=events,
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "timezone": self.timezone,
            "wake_time": self.wake_time,
            "daily_plan_delivery_time": self.daily_plan_delivery_time,
            "work_blocks": [b.to_str() for b in self.work_blocks],
        }
        if self.fixed_routines:
            d["fixed_routines"] = {}
            for name, r in self.fixed_routines.items():
                rd: dict[str, Any] = {"window": r.window.to_str()}
                if r.duration_min is not None:
                    rd["duration_min"] = r.duration_min
                d["fixed_routines"][name] = rd
        if self.commute_typical_one_way_min:
            d["commute"] = {"typical_one_way_min": self.commute_typical_one_way_min}
        if self.weekly_fixed_events:
            d["weekly_fixed_events"] = []
            for e in self.weekly_fixed_events:
                ed: dict[str, Any] = {"name": e.name, "day": e.day, "time": e.time.to_str()}
                if e.location:
                    ed["location"] = e.location
                if e.commute_min_each_way:
                    ed["commute_min_each_way"] = e.commute_min_each_way
                d["weekly_fixed_events"].append(ed)
        return d


# ── Tasks ─────────────────────────────────────────────────────


@dataclass
class Task:
    id: str = ""
    title: str = ""
    type: str = ""  # deadline_project, weekly_budget, daily_ritual, open_ended
    priority: int = 5
    status: str = "active"  # active, paused, complete
    # deadline_project fields
    remaining_hours: float | None = None
    deadline: str | None = None  # ISO date
    # weekly_budget fields
    target_hours_per_week: float | None = None
    hours_this_week: float = 0.0
    # daily_ritual fields
    estimated_minutes_per_day: int | None = None
    # scheduling hints
    min_chunk_minutes: int = 25
    max_chunk_minutes: int = 180
    # extra
    notes: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Task:
        return cls(
            id=str(d.get("id", "")),
            title=str(d.get("title", "")),
            type=str(d.get("type", "")),
            priority=int(d.get("priority", 5)),
            status=str(d.get("status", "active")),
            remaining_hours=d.get("remaining_hours"),
            deadline=d.get("deadline"),
            target_hours_per_week=d.get("target_hours_per_week"),
            hours_this_week=float(d.get("hours_this_week", 0.0)),
            estimated_minutes_per_day=d.get("estimated_minutes_per_day"),
            min_chunk_minutes=int(d.get("min_chunk_minutes", 25)),
            max_chunk_minutes=int(d.get("max_chunk_minutes", 180)),
            notes=str(d.get("notes", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "type": self.type,
            "priority": self.priority,
            "status": self.status,
        }
        if self.type == "deadline_project":
            if self.remaining_hours is not None:
                d["remaining_hours"] = self.remaining_hours
            if self.deadline:
                d["deadline"] = self.deadline
        if self.type == "weekly_budget":
            if self.target_hours_per_week is not None:
                d["target_hours_per_week"] = self.target_hours_per_week
            d["hours_this_week"] = self.hours_this_week
        if self.type == "daily_ritual":
            if self.estimated_minutes_per_day is not None:
                d["estimated_minutes_per_day"] = self.estimated_minutes_per_day
        if self.min_chunk_minutes != 25:
            d["min_chunk_minutes"] = self.min_chunk_minutes
        if self.max_chunk_minutes != 180:
            d["max_chunk_minutes"] = self.max_chunk_minutes
        if self.notes:
            d["notes"] = self.notes
        return d


@dataclass
class TasksFile:
    week_start: str = "mon"
    tasks: list[Task] = field(default_factory=list)
    archived: list[Task] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TasksFile:
        if not d or not isinstance(d, dict):
            return cls()
        tasks = [Task.from_dict(t) for t in (d.get("tasks") or [])]
        archived = [Task.from_dict(t) for t in (d.get("archived") or [])]
        return cls(
            week_start=str(d.get("week_start", "mon")),
            tasks=tasks,
            archived=archived,
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "week_start": self.week_start,
            "tasks": [t.to_dict() for t in self.tasks],
        }
        if self.archived:
            d["archived"] = [t.to_dict() for t in self.archived]
        return d


# ── Check-in ──────────────────────────────────────────────────


@dataclass
class CheckinItem:
    label: str = ""
    done: bool = False
    comment: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CheckinItem:
        return cls(
            label=str(d.get("label", "")),
            done=bool(d.get("done", False)),
            comment=str(d.get("comment", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "done": self.done, "comment": self.comment}


@dataclass
class CheckinDraft:
    day: str = ""
    updated_at: str = ""
    mode: str = "commit"
    items: dict[str, CheckinItem] = field(default_factory=dict)
    reflection: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CheckinDraft:
        if not d or not isinstance(d, dict):
            return cls()
        items = {}
        for k, v in (d.get("items") or {}).items():
            if isinstance(v, dict):
                items[k] = CheckinItem.from_dict(v)
        return cls(
            day=str(d.get("day", "")),
            updated_at=str(d.get("updatedAt", "")),
            mode=str(d.get("mode", "commit")).strip().lower() or "commit",
            items=items,
            reflection=str(d.get("reflection", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "updatedAt": self.updated_at,
            "mode": self.mode,
            "items": {k: v.to_dict() for k, v in self.items.items()},
            "reflection": self.reflection,
        }


# ── State ─────────────────────────────────────────────────────


@dataclass
class HistoryEntry:
    day: str = ""
    rating: str = ""
    mode: str = ""
    streak_counted: bool = False
    done_count: int = 0
    total: int = 0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> HistoryEntry:
        return cls(
            day=str(d.get("day", "")),
            rating=str(d.get("rating", "")),
            mode=str(d.get("mode", "")),
            streak_counted=bool(d.get("streakCounted", False)),
            done_count=int(d.get("doneCount", 0)),
            total=int(d.get("total", 0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "rating": self.rating,
            "mode": self.mode,
            "streakCounted": self.streak_counted,
            "doneCount": self.done_count,
            "total": self.total,
        }


@dataclass
class State:
    streak: int = 0
    last_streak_date: str | None = None
    last_rating: str | None = None
    last_mode: str | None = None
    last_summary: str | None = None
    last_finalized_date: str | None = None
    history: list[HistoryEntry] = field(default_factory=list)
    weekly_budget_tracking: dict[str, Any] = field(default_factory=dict)
    week_start_date: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> State:
        if not d or not isinstance(d, dict):
            return cls()
        history = [HistoryEntry.from_dict(e) for e in (d.get("history") or [])]
        return cls(
            streak=int(d.get("streak", 0) or 0),
            last_streak_date=d.get("lastStreakDate"),
            last_rating=d.get("lastRating"),
            last_mode=d.get("lastMode"),
            last_summary=d.get("lastSummary"),
            last_finalized_date=d.get("lastFinalizedDate"),
            history=history,
            weekly_budget_tracking=d.get("weeklyBudgetTracking") or {},
            week_start_date=d.get("weekStartDate"),
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "streak": self.streak,
            "lastStreakDate": self.last_streak_date,
            "lastRating": self.last_rating,
            "lastMode": self.last_mode,
            "lastSummary": self.last_summary,
            "lastFinalizedDate": self.last_finalized_date,
            "history": [e.to_dict() for e in self.history],
        }
        if self.weekly_budget_tracking:
            d["weeklyBudgetTracking"] = self.weekly_budget_tracking
        if self.week_start_date:
            d["weekStartDate"] = self.week_start_date
        return d


# ── Plan Checkbox ─────────────────────────────────────────────


@dataclass
class PlanCheckbox:
    key: str = ""
    label: str = ""
    checked: bool = False


# ── Focus Session ─────────────────────────────────────────────


@dataclass
class FocusSession:
    task_id: str = ""
    task_label: str = ""
    started_at: str = ""
    planned_minutes: int = 25
    ended_at: str | None = None
    elapsed_minutes: float = 0.0
    completed: bool = False
    interruptions: int = 0
    notes: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FocusSession:
        if not d or not isinstance(d, dict):
            return cls()
        return cls(
            task_id=str(d.get("task_id", d.get("taskId", ""))),
            task_label=str(d.get("task_label", d.get("taskLabel", ""))),
            started_at=str(d.get("started_at", d.get("startedAt", ""))),
            planned_minutes=int(d.get("planned_minutes", d.get("plannedMinutes", 25))),
            ended_at=d.get("ended_at", d.get("endedAt")),
            elapsed_minutes=float(d.get("elapsed_minutes", d.get("elapsedMinutes", 0.0))),
            completed=bool(d.get("completed", False)),
            interruptions=int(d.get("interruptions", 0)),
            notes=str(d.get("notes", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "taskId": self.task_id,
            "taskLabel": self.task_label,
            "startedAt": self.started_at,
            "plannedMinutes": self.planned_minutes,
            "endedAt": self.ended_at,
            "elapsedMinutes": self.elapsed_minutes,
            "completed": self.completed,
            "interruptions": self.interruptions,
            "notes": self.notes,
        }


@dataclass
class FocusState:
    active_session: FocusSession | None = None
    history: list[FocusSession] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FocusState:
        if not d or not isinstance(d, dict):
            return cls()
        active = d.get("active_session", d.get("activeSession"))
        return cls(
            active_session=FocusSession.from_dict(active) if active else None,
            history=[FocusSession.from_dict(s) for s in (d.get("history") or [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "activeSession": self.active_session.to_dict() if self.active_session else None,
            "history": [s.to_dict() for s in self.history],
        }


# ── Scheduler ─────────────────────────────────────────────────


@dataclass
class ScheduledBlock:
    start: time | None = None
    end: time | None = None
    task_id: str = ""
    task_title: str = ""
    duration_minutes: int = 0
    block_type: str = "task"  # task, routine, event

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start.strftime("%H:%M") if self.start else "",
            "end": self.end.strftime("%H:%M") if self.end else "",
            "taskId": self.task_id,
            "taskTitle": self.task_title,
            "durationMinutes": self.duration_minutes,
            "blockType": self.block_type,
        }


@dataclass
class DaySchedule:
    date: str = ""
    blocks: list[ScheduledBlock] = field(default_factory=list)
    unscheduled_tasks: list[str] = field(default_factory=list)
    total_work_minutes: int = 0
    utilization_pct: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "blocks": [b.to_dict() for b in self.blocks],
            "unscheduledTasks": self.unscheduled_tasks,
            "totalWorkMinutes": self.total_work_minutes,
            "utilizationPct": round(self.utilization_pct, 1),
        }


# ── Analytics ─────────────────────────────────────────────────


@dataclass
class DayRecord:
    date: str = ""
    rating: str = ""
    mode: str = ""
    done_items: list[str] = field(default_factory=list)
    all_items: list[str] = field(default_factory=list)
    reflection_text: str = ""
    notes: list[str] = field(default_factory=list)

    def completion_rate(self) -> float:
        if not self.all_items:
            return 0.0
        return len(self.done_items) / len(self.all_items)


@dataclass
class AnalyticsSummary:
    completion_by_weekday: dict[str, float] = field(default_factory=dict)
    completion_by_task_type: dict[str, float] = field(default_factory=dict)
    best_time_blocks: list[str] = field(default_factory=list)
    most_skipped_tasks: list[str] = field(default_factory=list)
    streak_history: list[dict[str, Any]] = field(default_factory=list)
    rolling_7day_avg: float = 0.0
    rolling_30day_avg: float = 0.0
    recovery_success_rate: float = 0.0
    total_days_tracked: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "completionByWeekday": self.completion_by_weekday,
            "completionByTaskType": self.completion_by_task_type,
            "bestTimeBlocks": self.best_time_blocks,
            "mostSkippedTasks": self.most_skipped_tasks,
            "streakHistory": self.streak_history,
            "rolling7dayAvg": round(self.rolling_7day_avg, 3),
            "rolling30dayAvg": round(self.rolling_30day_avg, 3),
            "recoverySuccessRate": round(self.recovery_success_rate, 3),
            "totalDaysTracked": self.total_days_tracked,
        }
