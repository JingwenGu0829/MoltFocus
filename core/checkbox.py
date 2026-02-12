"""Plan.md checkbox + duration parsing for MoltFocus."""

from __future__ import annotations

import re

from core.models import PlanCheckbox


def extract_checkboxes(plan_md: str) -> list[PlanCheckbox]:
    """Extract markdown checkboxes from plan text.

    Recognizes:
        - [ ] Task label
        - [x] Task label
        - [X] Task label
    """
    out = []
    for i, line in enumerate(plan_md.splitlines()):
        m = re.match(r"^\s*[-*]\s*\[([ xX])\]\s+(.*)$", line)
        if not m:
            continue
        checked = m.group(1).strip().lower() == "x"
        label = m.group(2).strip()
        key = f"line-{i}"
        out.append(PlanCheckbox(key=key, label=label, checked=checked))
    return out


def parse_duration_from_label(label: str) -> int:
    """Extract duration in minutes from a label like 'Task name 2h' or 'Task 90m'.

    Returns 0 if no duration found.
    """
    # Match patterns like "2h", "90m", "1.5h" at the end of the label
    m = re.search(r"(\d+(?:\.\d+)?)\s*([hm])\s*$", label, re.IGNORECASE)
    if not m:
        return 0
    val = float(m.group(1))
    unit = m.group(2).lower()
    if unit == "h":
        return int(val * 60)
    return int(val)


def parse_task_title_from_label(label: str) -> str:
    """Extract the task title prefix from a checkin label.

    'Deadline paper: experiment writeup 2h' -> 'Deadline paper'
    'Daily maintenance 20m' -> 'Daily maintenance'
    """
    # Remove trailing duration
    cleaned = re.sub(r"\s+\d+(?:\.\d+)?\s*[hm]\s*$", "", label, flags=re.IGNORECASE).strip()
    # If there's a colon, take the part before it (task title)
    if ":" in cleaned:
        return cleaned.split(":")[0].strip()
    return cleaned
