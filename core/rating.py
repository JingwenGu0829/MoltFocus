"""Rating computation, streak counting, and summary generation for MoltFocus."""

from __future__ import annotations


def compute_rating(done_count: int, total_items: int, reflection: str, any_time: bool) -> str:
    """Compute day rating: good, fair, or bad.

    Good: meaningful progress (>=50% done, or >=2 items, or any timed item done).
    Fair: some progress (>=1 item) or solid reflection (>=30 chars).
    Bad: nothing notable.
    """
    refl = (reflection or "").strip()
    if done_count >= max(1, total_items // 2) or (done_count >= 2) or (any_time and done_count >= 1):
        return "good"
    if done_count >= 1 or len(refl) >= 30:
        return "fair"
    return "bad"


def counts_for_streak(done_count: int, reflection: str, plan_changed: bool) -> bool:
    """Determine if a day counts toward the streak.

    Count if: >=1 item done, OR meaningful reflection, OR actively adjusted plan.
    """
    return done_count >= 1 or len((reflection or "").strip()) >= 30 or plan_changed


def summarize_paragraph(day: str, rating: str, done_items: list[str], minutes_total: int, reflection: str) -> str:
    """Build a one-line auto-summary for the day."""
    lead = {"good": "Good", "fair": "Fair", "bad": "Bad"}.get(rating, "Unknown")
    parts = []
    if done_items:
        top = done_items[:3]
        more = "" if len(done_items) <= 3 else f" (+{len(done_items) - 3} more)"
        parts.append(f"done: {', '.join(top)}{more}")
    if minutes_total > 0:
        parts.append(f"logged ~{minutes_total} min")
    refl = (reflection or "").strip()
    if refl:
        parts.append("reflection recorded")
    body = "; ".join(parts) if parts else "no notable progress logged"
    advice = {
        "good": "Keep the momentum; protect one deep block early tomorrow.",
        "fair": "Aim for one deeper block next; reduce context switching.",
        "bad": "Reset: pick one small win + one deep block tomorrow.",
    }.get(rating, "")
    return f"[{lead}] {day}: {body}. {advice}"
