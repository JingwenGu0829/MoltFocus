"""Tests for core/analytics.py — reflection parsing and analytics computation."""

from core.analytics import parse_reflections, compute_analytics
from core.models import State, HistoryEntry


SAMPLE_REFLECTIONS = """# Reflections (rolling)

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
- [Good] 2026-02-10: done 3 items.

---

## 2026-02-09
- Time: 2026-02-09T22:00

**Rating:** FAIR

**Mode:** RECOVERY

**Done**
- Important project: API refactor 2h

**Notes**
- Deadline paper: skipped due to low energy

**Reflection**
Fair day. Got the API refactor done.

**Auto-summary**
- [Fair] 2026-02-09: done 1 item.

---
"""


def test_parse_reflections():
    records = parse_reflections(SAMPLE_REFLECTIONS)
    assert len(records) == 2
    assert records[0].date == "2026-02-10"
    assert records[0].rating == "good"
    assert records[0].mode == "commit"
    assert len(records[0].done_items) == 3
    assert records[1].date == "2026-02-09"
    assert records[1].rating == "fair"
    assert records[1].mode == "recovery"


def test_parse_reflections_empty():
    records = parse_reflections("")
    assert records == []


def test_compute_analytics():
    records = parse_reflections(SAMPLE_REFLECTIONS)
    state = State(history=[
        HistoryEntry(day="2026-02-09", streak_counted=True),
        HistoryEntry(day="2026-02-10", streak_counted=True),
    ])
    summary = compute_analytics(records, state)
    assert summary.total_days_tracked == 2
    assert summary.rolling_7day_avg > 0
    assert summary.recovery_success_rate > 0  # one recovery day that was fair = success


def test_compute_analytics_empty():
    summary = compute_analytics([])
    assert summary.total_days_tracked == 0
    assert summary.rolling_7day_avg == 0


def test_refresh_analytics(workspace):
    from core.analytics import refresh_analytics
    summary = refresh_analytics(workspace)
    assert summary.total_days_tracked >= 1
    # Should have written analytics.json
    from core.fileio import read_json
    data = read_json(workspace / "planner" / "analytics.json")
    assert "totalDaysTracked" in data
