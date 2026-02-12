"""Tests for core/rating.py."""

from core.rating import compute_rating, counts_for_streak, summarize_paragraph


def test_compute_rating_good():
    assert compute_rating(3, 5, "", False) == "good"
    assert compute_rating(2, 10, "", False) == "good"


def test_compute_rating_fair():
    assert compute_rating(1, 5, "", False) == "fair"
    assert compute_rating(0, 5, "A long reflection that is meaningful.", False) == "fair"


def test_compute_rating_bad():
    assert compute_rating(0, 5, "", False) == "bad"
    assert compute_rating(0, 5, "short", False) == "bad"


def test_counts_for_streak():
    assert counts_for_streak(1, "", False) is True
    assert counts_for_streak(0, "A meaningful reflection of at least 30 chars.", False) is True
    assert counts_for_streak(0, "", True) is True
    assert counts_for_streak(0, "", False) is False


def test_summarize_paragraph():
    s = summarize_paragraph("2026-02-11", "good", ["Task A", "Task B"], 120, "Great day.")
    assert "[Good]" in s
    assert "2026-02-11" in s
    assert "Task A" in s


def test_summarize_paragraph_bad():
    s = summarize_paragraph("2026-02-11", "bad", [], 0, "")
    assert "[Bad]" in s
    assert "no notable progress" in s
