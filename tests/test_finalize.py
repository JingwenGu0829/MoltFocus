"""Tests for core/finalize.py — finalization logic and idempotency."""

import json
from unittest.mock import patch

from core.finalize import finalize_day
from core.fileio import read_json, read_text


def test_finalize_basic(workspace):
    """Basic finalization should succeed and update state."""
    # Patch today_str to match the draft's day
    with patch("core.finalize.today_str", return_value="2026-02-11"), \
         patch("core.finalize.now_local") as mock_now:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        mock_now.return_value = datetime(2026, 2, 11, 21, 30, tzinfo=ZoneInfo("UTC"))

        result = finalize_day(workspace)

    assert result["ok"] is True
    assert result["day"] == "2026-02-11"
    assert result["rating"] in ("good", "fair", "bad")
    assert isinstance(result["streak"], int)

    # State should be updated
    state = read_json(workspace / "planner" / "state.json")
    assert state["lastFinalizedDate"] == "2026-02-11"
    assert state["lastRating"] == result["rating"]

    # Reflections should have a new entry
    reflections = read_text(workspace / "reflections" / "reflections.md")
    assert "## 2026-02-11" in reflections


def test_finalize_idempotent(workspace):
    """Second finalization on the same day should be a no-op."""
    with patch("core.finalize.today_str", return_value="2026-02-11"), \
         patch("core.finalize.now_local") as mock_now:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        mock_now.return_value = datetime(2026, 2, 11, 21, 30, tzinfo=ZoneInfo("UTC"))

        result1 = finalize_day(workspace)
        assert result1["ok"] is True
        assert "already_finalized" not in result1

        result2 = finalize_day(workspace)
        assert result2["ok"] is True
        assert result2.get("already_finalized") is True


def test_finalize_no_draft(workspace):
    """Finalization should fail if there's no draft for today."""
    with patch("core.finalize.today_str", return_value="2026-02-12"):
        result = finalize_day(workspace)

    assert result["ok"] is False
    assert result["reason"] == "no-draft-for-today"


def test_finalize_clears_draft(workspace):
    """After finalization, the draft should be cleared."""
    with patch("core.finalize.today_str", return_value="2026-02-11"), \
         patch("core.finalize.now_local") as mock_now:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        mock_now.return_value = datetime(2026, 2, 11, 21, 30, tzinfo=ZoneInfo("UTC"))

        finalize_day(workspace)

    draft = read_json(workspace / "planner" / "latest" / "checkin_draft.json")
    assert draft.get("items") == {}
    assert draft.get("reflection") == ""
