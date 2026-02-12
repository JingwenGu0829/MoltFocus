"""Tests for core/checkbox.py."""

from core.checkbox import extract_checkboxes, parse_duration_from_label, parse_task_title_from_label


def test_extract_checkboxes_basic():
    plan = """# Plan
## Minimum viable day
- [ ] Task one 2h
- [x] Task two 90m
- [ ] Task three
"""
    cbs = extract_checkboxes(plan)
    assert len(cbs) == 3
    assert cbs[0].label == "Task one 2h"
    assert cbs[0].checked is False
    assert cbs[1].label == "Task two 90m"
    assert cbs[1].checked is True
    assert cbs[2].label == "Task three"
    assert cbs[2].checked is False


def test_extract_checkboxes_empty():
    assert extract_checkboxes("") == []
    assert extract_checkboxes("# Just a heading\nSome text.") == []


def test_parse_duration_hours():
    assert parse_duration_from_label("Thesis writeup 2h") == 120
    assert parse_duration_from_label("Code review 1.5h") == 90


def test_parse_duration_minutes():
    assert parse_duration_from_label("Quick task 30m") == 30
    assert parse_duration_from_label("Standup 15m") == 15


def test_parse_duration_none():
    assert parse_duration_from_label("Task without duration") == 0
    assert parse_duration_from_label("") == 0


def test_parse_task_title_with_colon():
    assert parse_task_title_from_label("Deadline paper: experiment writeup 2h") == "Deadline paper"


def test_parse_task_title_without_colon():
    assert parse_task_title_from_label("Daily maintenance 20m") == "Daily maintenance"


def test_parse_task_title_no_duration():
    assert parse_task_title_from_label("Simple task") == "Simple task"
