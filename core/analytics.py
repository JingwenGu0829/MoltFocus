"""Pattern analytics engine for MoltFocus.

Parses reflections.md to extract structured records, then computes
analytics like completion rates, trends, and patterns.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from core.fileio import read_text, read_json, write_json_atomic
from core.models import AnalyticsSummary, DayRecord, State
from core.workspace import (
    analytics_path,
    reflections_path,
    state_path,
    workspace_root,
)


# ── Reflection Parser ─────────────────────────────────────────


def parse_reflections(md_text: str) -> list[DayRecord]:
    """Parse reflections.md into structured DayRecord entries.

    Splits on '## YYYY-MM-DD' headers, extracts structured sections.
    """
    records = []
    # Split on date headers
    sections = re.split(r"(?=^## \d{4}-\d{2}-\d{2})", md_text, flags=re.MULTILINE)

    for section in sections:
        section = section.strip()
        if not section:
            continue

        # Extract date
        date_match = re.match(r"^## (\d{4}-\d{2}-\d{2})", section)
        if not date_match:
            continue

        record = DayRecord(date=date_match.group(1))

        # Extract rating
        rating_match = re.search(r"\*\*Rating:\*\*\s*(\w+)", section)
        if rating_match:
            record.rating = rating_match.group(1).lower()

        # Extract mode
        mode_match = re.search(r"\*\*Mode:\*\*\s*(\w+)", section)
        if mode_match:
            record.mode = mode_match.group(1).lower()

        # Extract done items
        done_section = re.search(
            r"\*\*Done\*\*\s*\n(.*?)(?=\n\*\*|\Z)",
            section,
            re.DOTALL,
        )
        if done_section:
            for line in done_section.group(1).strip().splitlines():
                line = line.strip()
                if line.startswith("- ") and line != "- (none)":
                    record.done_items.append(line[2:].strip())
                    record.all_items.append(line[2:].strip())

        # Extract notes for items that weren't done
        notes_section = re.search(
            r"\*\*Notes\*\*\s*\n(.*?)(?=\n\*\*|\Z)",
            section,
            re.DOTALL,
        )
        if notes_section:
            for line in notes_section.group(1).strip().splitlines():
                line = line.strip()
                if line.startswith("- ") and line != "- (none)":
                    record.notes.append(line[2:].strip())
                    # Notes items are all items that aren't in done
                    item_name = line[2:].split(":")[0].strip()
                    if item_name not in [d.split(":")[0].strip() for d in record.done_items]:
                        record.all_items.append(item_name)

        # Extract reflection text
        refl_section = re.search(
            r"\*\*Reflection\*\*\s*\n(.*?)(?=\n\*\*|\Z)",
            section,
            re.DOTALL,
        )
        if refl_section:
            text = refl_section.group(1).strip()
            if text != "- (none)":
                record.reflection_text = text

        records.append(record)

    return records


# ── Analytics Computation ─────────────────────────────────────

DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def compute_analytics(
    records: list[DayRecord],
    state: State | None = None,
    tasks: list | None = None,
) -> AnalyticsSummary:
    """Compute analytics summary from parsed reflection records."""
    summary = AnalyticsSummary()
    summary.total_days_tracked = len(records)

    if not records:
        return summary

    # Completion by weekday
    weekday_rates: dict[str, list[float]] = defaultdict(list)
    for rec in records:
        try:
            d = date.fromisoformat(rec.date)
            day_name = DAY_NAMES[d.weekday()]
            weekday_rates[day_name].append(rec.completion_rate())
        except ValueError:
            pass

    summary.completion_by_weekday = {
        day: round(sum(rates) / len(rates), 3)
        for day, rates in weekday_rates.items()
        if rates
    }

    # Completion by task type (infer from item labels)
    type_done: dict[str, int] = defaultdict(int)
    type_total: dict[str, int] = defaultdict(int)
    for rec in records:
        for item in rec.all_items:
            # Simple heuristic: if it has duration, it's a project-type task
            ttype = "other"
            item_lower = item.lower()
            if re.search(r"\d+\s*[hm]", item):
                ttype = "timed_task"
            elif "maintenance" in item_lower or "ritual" in item_lower:
                ttype = "daily_ritual"
            type_total[ttype] += 1
            if item in rec.done_items:
                type_done[ttype] += 1

    summary.completion_by_task_type = {
        ttype: round(type_done.get(ttype, 0) / total, 3)
        for ttype, total in type_total.items()
        if total > 0
    }

    # Best time blocks (from schedule patterns in done items — heuristic)
    # We check which items get done most often
    if summary.completion_by_weekday:
        best_days = sorted(summary.completion_by_weekday.items(), key=lambda x: x[1], reverse=True)
        summary.best_time_blocks = [d[0] for d in best_days[:3]]

    # Most skipped tasks (appear often but rarely done)
    task_appear: dict[str, int] = defaultdict(int)
    task_done: dict[str, int] = defaultdict(int)
    for rec in records:
        for item in rec.all_items:
            # Normalize: take prefix before duration
            name = re.sub(r"\s+\d+(?:\.\d+)?\s*[hm]\s*$", "", item).strip()
            if ":" in name:
                name = name.split(":")[0].strip()
            task_appear[name] += 1
            if item in rec.done_items:
                task_done[name] += 1

    skipped = []
    for name, appearances in task_appear.items():
        if appearances >= 3:
            done = task_done.get(name, 0)
            skip_rate = 1 - (done / appearances)
            if skip_rate >= 0.5:
                skipped.append((name, skip_rate))
    skipped.sort(key=lambda x: x[1], reverse=True)
    summary.most_skipped_tasks = [s[0] for s in skipped[:5]]

    # Streak history from state
    if state:
        streaks = []
        current_streak_len = 0
        current_streak_start = None
        sorted_hist = sorted(state.history, key=lambda e: e.day)
        for entry in sorted_hist:
            if entry.streak_counted:
                if current_streak_start is None:
                    current_streak_start = entry.day
                current_streak_len += 1
            else:
                if current_streak_len > 0:
                    streaks.append({
                        "start": current_streak_start,
                        "end": entry.day,
                        "length": current_streak_len,
                    })
                current_streak_len = 0
                current_streak_start = None
        if current_streak_len > 0:
            streaks.append({
                "start": current_streak_start,
                "end": sorted_hist[-1].day if sorted_hist else "",
                "length": current_streak_len,
            })
        summary.streak_history = streaks

    # Rolling averages
    sorted_records = sorted(records, key=lambda r: r.date, reverse=True)
    if len(sorted_records) >= 7:
        rates_7 = [r.completion_rate() for r in sorted_records[:7]]
        summary.rolling_7day_avg = sum(rates_7) / len(rates_7)
    elif sorted_records:
        rates_all = [r.completion_rate() for r in sorted_records]
        summary.rolling_7day_avg = sum(rates_all) / len(rates_all)

    if len(sorted_records) >= 30:
        rates_30 = [r.completion_rate() for r in sorted_records[:30]]
        summary.rolling_30day_avg = sum(rates_30) / len(rates_30)
    elif sorted_records:
        rates_all = [r.completion_rate() for r in sorted_records]
        summary.rolling_30day_avg = sum(rates_all) / len(rates_all)

    # Recovery success rate
    recovery_days = [r for r in records if r.mode == "recovery"]
    if recovery_days:
        recovery_good = sum(1 for r in recovery_days if r.rating in ("good", "fair"))
        summary.recovery_success_rate = recovery_good / len(recovery_days)

    return summary


# ── Storage & Refresh ─────────────────────────────────────────


def refresh_analytics(root: Path | None = None) -> AnalyticsSummary:
    """Recompute analytics from reflections.md and save to analytics.json."""
    if root is None:
        root = workspace_root()

    ref_text = read_text(reflections_path(root))
    records = parse_reflections(ref_text)

    state_data = read_json(state_path(root))
    state = State.from_dict(state_data)

    summary = compute_analytics(records, state)
    write_json_atomic(analytics_path(root), summary.to_dict())
    return summary


def load_analytics(root: Path | None = None) -> AnalyticsSummary | None:
    """Load cached analytics from analytics.json."""
    if root is None:
        root = workspace_root()
    data = read_json(analytics_path(root))
    if not data:
        return None
    s = AnalyticsSummary()
    s.completion_by_weekday = data.get("completionByWeekday", {})
    s.completion_by_task_type = data.get("completionByTaskType", {})
    s.best_time_blocks = data.get("bestTimeBlocks", [])
    s.most_skipped_tasks = data.get("mostSkippedTasks", [])
    s.streak_history = data.get("streakHistory", [])
    s.rolling_7day_avg = data.get("rolling7dayAvg", 0.0)
    s.rolling_30day_avg = data.get("rolling30dayAvg", 0.0)
    s.recovery_success_rate = data.get("recoverySuccessRate", 0.0)
    s.total_days_tracked = data.get("totalDaysTracked", 0)
    return s
