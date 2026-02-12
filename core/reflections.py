"""Reflection entry building and prepending for MoltFocus."""

from __future__ import annotations

from pathlib import Path

from core.fileio import read_text, write_text_atomic


def prepend_reflection(ref_path: Path, entry_md: str) -> None:
    """Prepend a reflection entry to reflections.md.

    Inserts after the '---' marker that separates the header from entries.
    """
    existing = read_text(ref_path)
    if existing.strip() == "":
        existing = "# Reflections (rolling)\n\nAppend newest entries at the top.\n\n---\n\n"
    marker = "---\n\n"
    idx = existing.find(marker)
    if idx != -1:
        head = existing[: idx + len(marker)]
        tail = existing[idx + len(marker) :]
        new = head + "\n" + entry_md.strip() + "\n\n" + tail.lstrip()
    else:
        new = entry_md.strip() + "\n\n" + existing
    write_text_atomic(ref_path, new)


def build_reflection_entry(
    today: str,
    now_iso: str,
    rating: str,
    mode: str,
    done_items: list[str],
    items: dict,
    reflection: str,
    summary: str,
) -> str:
    """Build the markdown text for a single reflection entry."""
    lines = [
        f"## {today}",
        f"- Time: {now_iso}",
        "",
        f"**Rating:** {rating.upper()}",
        "",
        f"**Mode:** {mode.upper()}",
        "",
        "**Done**",
    ]
    if done_items:
        for it in done_items:
            lines.append(f"- {it}")
    else:
        lines.append("- (none)")

    lines += ["", "**Notes**"]
    notes_added = False
    for _k, v in items.items():
        comment = str(v.get("comment", "") if isinstance(v, dict) else "").strip()
        label = str(v.get("label", "(item)") if isinstance(v, dict) else "(item)")
        if comment:
            notes_added = True
            lines.append(f"- {label}: {comment}")
    if not notes_added:
        lines.append("- (none)")

    lines += [
        "",
        "**Reflection**",
        (reflection.strip() if reflection.strip() else "- (none)"),
        "",
        "**Auto-summary**",
        f"- {summary}",
    ]
    return "\n".join(lines)
