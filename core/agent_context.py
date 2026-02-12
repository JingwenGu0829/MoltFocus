"""Agent context generation — the bridge between analytics and external agents.

After each finalization, generates planner/agent_context.json that aggregates
recent analytics, urgent tasks, weekly budget status, and scheduling suggestions
into a single file for agent consumption.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from core.fileio import read_json, write_json_atomic
from core.models import State
from core.tasks import load_tasks, get_tasks_with_computed_fields
from core.workspace import (
    agent_context_path,
    analytics_path,
    state_path,
    workspace_root,
    get_user_timezone,
)


def get_scheduling_suggestions(
    analytics: dict[str, Any],
    state: State,
    tasks_computed: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Generate rule-based scheduling suggestions.

    Rules:
    - If rolling_7day_avg < 0.5 -> suggest lighter day or recovery mode
    - Route hardest tasks to best_time_blocks[0]
    - Warn about frequently skipped tasks (>=3 skips)
    - Weekday awareness: flag historically low-completion days
    """
    suggestions = []

    # Check 7-day trend
    avg_7 = analytics.get("rolling7dayAvg", 0)
    if avg_7 > 0 and avg_7 < 0.5:
        suggestions.append({
            "type": "difficulty_adjustment",
            "message": f"7-day completion average is low ({avg_7:.0%}). Consider a lighter plan or recovery mode.",
            "priority": "high",
        })

    # Best time blocks
    best_blocks = analytics.get("bestTimeBlocks", [])
    if best_blocks and tasks_computed:
        top_task = tasks_computed[0] if tasks_computed else None
        if top_task:
            suggestions.append({
                "type": "scheduling",
                "message": f"Schedule '{top_task.get('title', '')}' during your best day(s): {', '.join(best_blocks[:2])}.",
                "priority": "medium",
            })

    # Skipped tasks warning
    skipped = analytics.get("mostSkippedTasks", [])
    for task_name in skipped[:3]:
        suggestions.append({
            "type": "skip_warning",
            "message": f"'{task_name}' is frequently skipped. Consider breaking it into smaller chunks or re-prioritizing.",
            "priority": "medium",
        })

    # Weekday awareness
    weekday_rates = analytics.get("completionByWeekday", {})
    if weekday_rates:
        today_name = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][
            date.today().weekday()
        ]
        today_rate = weekday_rates.get(today_name)
        if today_rate is not None and today_rate < 0.4:
            suggestions.append({
                "type": "weekday_warning",
                "message": f"Historically, {today_name.title()} has a low completion rate ({today_rate:.0%}). Plan conservatively.",
                "priority": "medium",
            })

    # Recovery effectiveness
    recovery_rate = analytics.get("recoverySuccessRate", 0)
    if state.last_rating == "bad" and recovery_rate > 0.6:
        suggestions.append({
            "type": "recovery_suggestion",
            "message": f"Recovery mode has worked well ({recovery_rate:.0%} success rate). Consider using it today.",
            "priority": "high",
        })

    return suggestions


def generate_agent_context(root: Path | None = None) -> dict[str, Any]:
    """Generate agent_context.json with aggregated intelligence for agents.

    Contents:
    - Recent analytics snapshot
    - Top urgent tasks with scores
    - Weekly budget status
    - Scheduling suggestions
    """
    if root is None:
        root = workspace_root()

    # Load state
    state_data = read_json(state_path(root))
    state = State.from_dict(state_data)

    # Load analytics
    analytics = read_json(analytics_path(root))

    # Load tasks with computed fields
    tasks_file = load_tasks(root)
    tz = get_user_timezone(root)
    today = datetime.now(tz).date().isoformat()
    tasks_computed = get_tasks_with_computed_fields(tasks_file, state, today)

    # Top 5 urgent tasks
    top_tasks = tasks_computed[:5]

    # Weekly budget status
    budget_status = []
    for task in tasks_file.tasks:
        if task.type == "weekly_budget" and task.target_hours_per_week:
            budget_status.append({
                "task_id": task.id,
                "title": task.title,
                "target_hours": task.target_hours_per_week,
                "actual_hours": round(task.hours_this_week, 1),
                "remaining_hours": round(max(0, task.target_hours_per_week - task.hours_this_week), 1),
                "progress_pct": round((task.hours_this_week / task.target_hours_per_week) * 100, 1),
            })

    # Scheduling suggestions
    suggestions = get_scheduling_suggestions(analytics, state, tasks_computed)

    context = {
        "generatedAt": datetime.now(tz).isoformat(timespec="seconds"),
        "analytics": {
            "streak": state.streak,
            "lastRating": state.last_rating,
            "rolling7dayAvg": analytics.get("rolling7dayAvg", 0),
            "rolling30dayAvg": analytics.get("rolling30dayAvg", 0),
            "completionByWeekday": analytics.get("completionByWeekday", {}),
            "totalDaysTracked": analytics.get("totalDaysTracked", 0),
        },
        "topUrgentTasks": top_tasks,
        "weeklyBudgetStatus": budget_status,
        "suggestions": suggestions,
    }

    write_json_atomic(agent_context_path(root), context)
    return context
