"""Shared test fixtures for MoltFocus tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace with standard structure."""
    root = tmp_path / "workspace"
    (root / "planner" / "latest").mkdir(parents=True)
    (root / "reflections").mkdir(parents=True)

    # Profile
    profile = {
        "timezone": "UTC",
        "wake_time": "08:00",
        "daily_plan_delivery_time": "08:30",
        "work_blocks": ["09:00-11:00", "13:00-17:00", "18:00-20:00"],
        "fixed_routines": {
            "workout": {"window": "11:10-11:50", "duration_min": 40},
            "lunch": {"window": "11:50-12:30"},
        },
        "commute": {"typical_one_way_min": 20},
        "weekly_fixed_events": [
            {
                "name": "Example class",
                "day": "tue",
                "time": "15:30-16:50",
                "location": "campus",
                "commute_min_each_way": 20,
            }
        ],
    }
    (root / "planner" / "profile.yaml").write_text(
        yaml.dump(profile, default_flow_style=False), encoding="utf-8"
    )

    # Tasks
    tasks = {
        "week_start": "mon",
        "tasks": [
            {
                "id": "deadline-paper",
                "title": "Deadline paper",
                "type": "deadline_project",
                "priority": 10,
                "status": "active",
                "remaining_hours": 12,
                "min_chunk_minutes": 60,
                "max_chunk_minutes": 180,
            },
            {
                "id": "important-project",
                "title": "Important project",
                "type": "weekly_budget",
                "priority": 8,
                "status": "active",
                "target_hours_per_week": 8,
                "min_chunk_minutes": 60,
            },
            {
                "id": "maintenance",
                "title": "Daily maintenance",
                "type": "daily_ritual",
                "priority": 5,
                "status": "active",
                "estimated_minutes_per_day": 10,
            },
        ],
    }
    (root / "planner" / "tasks.yaml").write_text(
        yaml.dump(tasks, default_flow_style=False), encoding="utf-8"
    )

    # State
    state = {
        "streak": 3,
        "lastStreakDate": "2026-02-10",
        "lastRating": "good",
        "lastMode": "commit",
        "lastSummary": "[Good] 2026-02-10: done: task1. Keep the momentum.",
        "lastFinalizedDate": "2026-02-10",
        "history": [
            {"day": "2026-02-10", "rating": "good", "mode": "commit", "streakCounted": True, "doneCount": 3, "total": 4},
        ],
    }
    (root / "planner" / "state.json").write_text(
        json.dumps(state, indent=2), encoding="utf-8"
    )

    # Reflections
    reflections = """# Reflections (rolling)

Append newest entries at the top.

---

## 2026-02-10
- Time: 2026-02-10T21:30

**Rating:** GOOD

**Mode:** COMMIT

**Done**
- Deadline paper: experiment writeup 2h
- Important project: code review 90m
- Daily maintenance 20m

**Notes**
- (none)

**Reflection**
Good productive day.

**Auto-summary**
- [Good] 2026-02-10: done: Deadline paper, Important project, Daily maintenance. Keep the momentum.

---

## 2026-02-09
- Time: 2026-02-09T22:00

**Rating:** FAIR

**Mode:** COMMIT

**Done**
- Important project: API refactor 2h

**Notes**
- Deadline paper: skipped due to low energy

**Reflection**
Fair day. Got the API refactor done.

**Auto-summary**
- [Fair] 2026-02-09: done: Important project. Aim for one deeper block next.

---
"""
    (root / "reflections" / "reflections.md").write_text(reflections, encoding="utf-8")

    # Plan
    plan = """# Plan — 2026-02-11

## Top priorities
1) Deadline paper — finish experiment section

## Schedule
- 09:00–11:00 Deadline paper: experiment writeup 2h
- 13:00–14:30 Important project: code review 90m

## Minimum viable day
- [ ] Deadline paper: experiment writeup 2h
- [ ] Important project: code review 90m
- [ ] Daily maintenance 20m
"""
    (root / "planner" / "latest" / "plan.md").write_text(plan, encoding="utf-8")

    # Checkin draft
    draft = {
        "day": "2026-02-11",
        "updatedAt": "2026-02-11T17:00:00",
        "mode": "commit",
        "items": {
            "line-11": {"label": "Deadline paper: experiment writeup 2h", "done": True, "comment": "done"},
            "line-12": {"label": "Important project: code review 90m", "done": True, "comment": ""},
            "line-13": {"label": "Daily maintenance 20m", "done": False, "comment": ""},
        },
        "reflection": "Good day overall.",
    }
    (root / "planner" / "latest" / "checkin_draft.json").write_text(
        json.dumps(draft, indent=2), encoding="utf-8"
    )

    # Set env var
    os.environ["PLANNER_ROOT"] = str(root)
    yield root
    # Cleanup
    if "PLANNER_ROOT" in os.environ:
        del os.environ["PLANNER_ROOT"]
