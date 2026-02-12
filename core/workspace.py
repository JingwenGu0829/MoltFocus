"""Workspace root, timezone, path helpers for MoltFocus."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.fileio import read_yaml


def workspace_root() -> Path:
    """Get the workspace root directory (contains planner/ and reflections/)."""
    return Path(
        os.environ.get("PLANNER_ROOT", str(Path.home() / "planner"))
    ).expanduser().resolve()


def get_user_timezone(root: Path | None = None) -> ZoneInfo:
    """Get user's timezone from profile.yaml, defaulting to UTC."""
    if root is None:
        root = workspace_root()
    try:
        profile = read_yaml(root / "planner" / "profile.yaml")
        if profile and "timezone" in profile:
            return ZoneInfo(profile["timezone"])
    except Exception:
        pass
    return ZoneInfo("UTC")


def today_str(root: Path | None = None) -> str:
    """Get today's date string (YYYY-MM-DD) in user's timezone."""
    tz = get_user_timezone(root)
    return datetime.now(tz).date().isoformat()


def now_local(root: Path | None = None) -> datetime:
    """Get current datetime in user's timezone."""
    tz = get_user_timezone(root)
    return datetime.now(tz)


# ── Path helpers ──────────────────────────────────────────────

def plan_path(root: Path | None = None) -> Path:
    if root is None:
        root = workspace_root()
    return root / "planner" / "latest" / "plan.md"


def plan_prev_path(root: Path | None = None) -> Path:
    if root is None:
        root = workspace_root()
    return root / "planner" / "latest" / "plan_prev.md"


def draft_path(root: Path | None = None) -> Path:
    if root is None:
        root = workspace_root()
    return root / "planner" / "latest" / "checkin_draft.json"


def state_path(root: Path | None = None) -> Path:
    if root is None:
        root = workspace_root()
    return root / "planner" / "state.json"


def reflections_path(root: Path | None = None) -> Path:
    if root is None:
        root = workspace_root()
    return root / "reflections" / "reflections.md"


def profile_path(root: Path | None = None) -> Path:
    if root is None:
        root = workspace_root()
    return root / "planner" / "profile.yaml"


def tasks_path(root: Path | None = None) -> Path:
    if root is None:
        root = workspace_root()
    return root / "planner" / "tasks.yaml"


def focus_path(root: Path | None = None) -> Path:
    if root is None:
        root = workspace_root()
    return root / "planner" / "latest" / "focus.json"


def analytics_path(root: Path | None = None) -> Path:
    if root is None:
        root = workspace_root()
    return root / "planner" / "analytics.json"


def agent_context_path(root: Path | None = None) -> Path:
    if root is None:
        root = workspace_root()
    return root / "planner" / "agent_context.json"


def hooks_config_path(root: Path | None = None) -> Path:
    if root is None:
        root = workspace_root()
    return root / "planner" / "hooks.yaml"
