#!/usr/bin/env python3
"""MoltFocus TUI — interactive terminal planner powered by Textual."""

from __future__ import annotations

import fcntl
import json
import os
import re
import sys
import tempfile
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widgets import (
    Checkbox,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Markdown,
    Static,
    TextArea,
)


# ── Data layer (shared with ui/app.py) ────────────────────────


def _root() -> Path:
    return (
        Path(os.environ.get("PLANNER_ROOT", str(Path.home() / "planner")))
        .expanduser()
        .resolve()
    )


def _read(path: Path) -> str:
    return path.read_text("utf-8") if path.exists() else ""


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text("utf-8")) if path.exists() else {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        os.rename(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _write_text_atomic(path: Path, content: str) -> None:
    """Atomic text file write — temp file + flock + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        os.rename(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _tz() -> ZoneInfo:
    try:
        txt = _read(_root() / "planner" / "profile.yaml")
        if txt.strip():
            p = yaml.safe_load(txt)
            if isinstance(p, dict) and "timezone" in p:
                return ZoneInfo(p["timezone"])
    except Exception:
        pass
    return ZoneInfo("UTC")


def _today() -> str:
    return datetime.now(_tz()).date().isoformat()


def _checkboxes(plan_md: str) -> list[dict]:
    out = []
    for i, line in enumerate(plan_md.splitlines()):
        m = re.match(r"^\s*[-*]\s*\[([ xX])\]\s+(.*)$", line)
        if m:
            out.append(
                {
                    "key": f"line-{i}",
                    "label": m.group(2).strip(),
                    "checked": m.group(1).strip().lower() == "x",
                }
            )
    return out


def _load_draft() -> dict:
    draft = _read_json(_root() / "planner" / "latest" / "checkin_draft.json")
    if draft.get("day") != _today():
        draft = {"day": _today(), "mode": "commit", "items": {}, "reflection": ""}
    return draft


def _save_draft(draft: dict) -> None:
    draft["updatedAt"] = datetime.now(_tz()).isoformat(timespec="seconds")
    _write_json(_root() / "planner" / "latest" / "checkin_draft.json", draft)


def _compute_rating(done_count: int, total_items: int, reflection: str, any_time: bool) -> str:
    refl = (reflection or "").strip()
    if done_count >= max(1, total_items // 2) or (done_count >= 2) or (any_time and done_count >= 1):
        return "good"
    if done_count >= 1 or len(refl) >= 30:
        return "fair"
    return "bad"


def _counts_for_streak(done_count: int, reflection: str, plan_changed: bool) -> bool:
    return done_count >= 1 or len((reflection or "").strip()) >= 30 or plan_changed


def _summarize_paragraph(day: str, rating: str, done_items: list[str], minutes_total: int, reflection: str) -> str:
    lead = {"good": "Good", "fair": "Fair", "bad": "Bad"}[rating]
    parts = []
    if done_items:
        top = done_items[:3]
        more = "" if len(done_items) <= 3 else f" (+{len(done_items)-3} more)"
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
    }[rating]
    return f"[{lead}] {day}: {body}. {advice}"


def _prepend_reflection(ref_path: Path, entry_md: str) -> None:
    existing = _read(ref_path)
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
    _write_text_atomic(ref_path, new)


def _finalize() -> dict:
    """Finalize today's draft — mirrors ui/app.py api_finalize()."""
    root = _root()
    draft_path = root / "planner" / "latest" / "checkin_draft.json"
    state_path = root / "planner" / "state.json"
    ref_path = root / "reflections" / "reflections.md"

    today = _today()
    user_tz = _tz()
    draft = _read_json(draft_path) if draft_path.exists() else {}
    if draft.get("day") != today:
        return {"ok": False, "reason": "no-draft-for-today", "today": today}

    draft_mode = (draft.get("mode", "commit") or "commit").strip().lower()
    if draft_mode not in {"commit", "recovery"}:
        draft_mode = "commit"

    items = draft.get("items", {}) or {}
    reflection = draft.get("reflection", "") or ""

    done_items = []
    for k, v in items.items():
        if v.get("done"):
            done_items.append(str(v.get("label", "(item)")))

    total_items = len(items)
    done_count = len(done_items)

    # Plan changed detection (Issue #4 fix)
    plan_prev_path = root / "planner" / "latest" / "plan_prev.md"
    plan_path = root / "planner" / "latest" / "plan.md"
    plan_cur = _read(plan_path).strip()
    if plan_prev_path.exists():
        plan_changed = _read(plan_prev_path).strip() != plan_cur
    elif plan_cur:
        plan_changed = True
    else:
        plan_changed = False

    rating = _compute_rating(done_count, total_items, reflection, False)
    if draft_mode == "recovery" and rating == "bad" and (done_count >= 1 or len(reflection.strip()) >= 30):
        rating = "fair"
    counts = _counts_for_streak(done_count, reflection, plan_changed)
    if draft_mode == "recovery":
        counts = counts or (len(reflection.strip()) >= 30)

    state = _read_json(state_path) if state_path.exists() else {}
    last_streak_date = state.get("lastStreakDate")
    streak = int(state.get("streak", 0) or 0)

    # Streak gap detection (Issue #2 fix)
    if counts:
        if last_streak_date != today:
            if last_streak_date is not None:
                today_date = datetime.now(user_tz).date()
                try:
                    last_date = date.fromisoformat(last_streak_date)
                    gap = (today_date - last_date).days
                    if gap > 1:
                        streak = 1
                    else:
                        streak += 1
                except (ValueError, TypeError):
                    streak = 1
            else:
                streak = 1
            state["lastStreakDate"] = today

    summary = _summarize_paragraph(today, rating, done_items, 0, reflection)

    # history (keep last 30 days)
    hist = state.get("history", []) or []
    hist.append({"day": today, "rating": rating, "mode": draft_mode, "streakCounted": bool(counts), "doneCount": done_count, "total": total_items})
    by_day = {}
    for e in hist:
        by_day[e.get("day")] = e
    hist = list(by_day.values())
    hist.sort(key=lambda x: x.get("day", ""))
    hist = hist[-30:]
    state["history"] = hist

    # prepend reflection entry
    now = datetime.now(user_tz)
    entry_lines = [
        f"## {today}",
        f"- Time: {now.isoformat(timespec='minutes')}",
        "",
        f"**Rating:** {rating.upper()}",
        "",
        f"**Mode:** {draft_mode.upper()}",
        "",
        "**Done**",
    ]
    if done_items:
        for it in done_items:
            entry_lines.append(f"- {it}")
    else:
        entry_lines.append("- (none)")

    entry_lines += ["", "**Notes**"]
    notes_added = False
    for k, v in items.items():
        comment = str(v.get("comment", "")).strip()
        label = str(v.get("label", "(item)"))
        if comment:
            notes_added = True
            entry_lines.append(f"- {label}: {comment}")
    if not notes_added:
        entry_lines.append("- (none)")

    entry_lines += [
        "",
        "**Reflection**",
        (reflection.strip() if reflection.strip() else "- (none)"),
        "",
        "**Auto-summary**",
        f"- {summary}",
    ]

    _prepend_reflection(ref_path, "\n".join(entry_lines))

    # update state
    state["streak"] = streak
    state["lastRating"] = rating
    state["lastMode"] = draft_mode
    state["lastSummary"] = summary
    state["lastFinalizedDate"] = today
    _write_json(state_path, state)

    # clear draft after finalize
    _write_json(draft_path, {"day": today, "updatedAt": now.isoformat(timespec="seconds"), "items": {}, "reflection": ""})

    return {"ok": True, "day": today, "rating": rating, "streak": streak}


# ── Stylesheet ─────────────────────────────────────────────────

CSS = """
Screen {
    background: $surface;
}

#header-bar {
    dock: top;
    height: 3;
    background: $primary-background;
    color: $text;
    content-align: center middle;
    padding: 0 2;
}

#header-bar .streak {
    color: $warning;
    text-style: bold;
}

#main-layout {
    height: 1fr;
}

#left-pane {
    width: 1fr;
    min-width: 30;
    border-right: tall $primary-background-darken-2;
    padding: 0 1;
}

#right-pane {
    width: 1fr;
    min-width: 30;
    padding: 0 1;
}

#plan-viewer {
    height: 1fr;
    padding: 0 1;
}

#checkin-section {
    height: auto;
    max-height: 60%;
    padding: 0 1;
}

#reflection-section {
    height: auto;
    min-height: 8;
    padding: 0 1;
}

.section-title {
    text-style: bold;
    color: $text;
    margin: 1 0 0 0;
    padding: 0 1;
}

.todo-row {
    height: auto;
    padding: 0 0;
    margin: 0 0;
}

.todo-row Checkbox {
    width: auto;
    min-width: 4;
    height: auto;
    padding: 0 1 0 0;
}

.todo-done {
    opacity: 50%;
}

.todo-done Checkbox {
    text-style: strike;
}

.todo-label {
    width: 1fr;
    height: auto;
}

.comment-input {
    width: 1fr;
    height: 3;
    margin: 0 0 0 1;
}

#reflection-area {
    height: 6;
    min-height: 4;
}

#plan-editor { height: 1fr; padding: 0 1; display: none; }

.todo-header-row { height: auto; padding: 0 0; margin: 0 0 0 0; }

.todo-col-header { width: 1fr; height: auto; text-style: bold; color: $text-muted; padding: 0 1; }

#status-bar {
    dock: bottom;
    height: 1;
    background: $primary-background;
    color: $text-muted;
    padding: 0 2;
}

#yesterday-summary {
    height: auto;
    max-height: 4;
    padding: 0 1;
    color: $text-muted;
    margin: 1 0 0 0;
}

#tasks-screen {
    padding: 1 2;
}

#tasks-table {
    height: 1fr;
}

#status-screen {
    padding: 1 2;
}

#status-info {
    height: auto;
    padding: 1 2;
    margin: 0 0 1 0;
    border: tall $primary-background-darken-2;
}

#history-table {
    height: 1fr;
}
"""


# ── Custom widgets ─────────────────────────────────────────────


class TodoItem(Horizontal):
    """A single check-in item: checkbox + label + comment."""

    def __init__(
        self, key: str, label: str, done: bool, comment: str, **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.item_key = key
        self.item_label = label
        self.item_done = done
        self.item_comment = comment

    def compose(self) -> ComposeResult:
        yield Checkbox(self.item_label, value=self.item_done, id=f"cb-{self.item_key}")
        yield Input(
            value=self.item_comment,
            placeholder="comment…",
            id=f"cmt-{self.item_key}",
            classes="comment-input",
        )

    def on_mount(self) -> None:
        self.add_class("todo-row")
        cb = self.query_one(Checkbox)
        cb.can_focus = False
        if self.item_done:
            self.add_class("todo-done")


# ── Screens ────────────────────────────────────────────────────


class TasksScreen(Vertical):
    """Tasks view as a data table."""

    def compose(self) -> ComposeResult:
        yield Label("Tasks", classes="section-title")
        yield DataTable(id="tasks-table")

    def on_mount(self) -> None:
        table: DataTable = self.query_one("#tasks-table", DataTable)
        table.add_columns("ID", "Title", "Type", "Pri", "Status", "Details")

        root = _root()
        txt = _read(root / "planner" / "tasks.yaml")
        if not txt.strip():
            return

        try:
            data = yaml.safe_load(txt)
        except Exception:
            return

        tasks = data.get("tasks", []) if isinstance(data, dict) else []
        for t in tasks:
            ttype = str(t.get("type", "?"))
            details = ""
            if ttype == "deadline_project":
                details = f"{t.get('remaining_hours', '?')}h remaining"
            elif ttype == "weekly_budget":
                details = f"{t.get('target_hours_per_week', '?')}h/week"
            elif ttype == "daily_ritual":
                details = f"{t.get('estimated_minutes_per_day', '?')}min/day"
            elif ttype == "open_ended":
                details = "open-ended"

            table.add_row(
                str(t.get("id", "?")),
                str(t.get("title", "?")),
                ttype,
                str(t.get("priority", "")),
                str(t.get("status", "?")),
                details,
            )


class StatusScreen(Vertical):
    """Status view: streak info + history table."""

    def compose(self) -> ComposeResult:
        yield Label("Status", classes="section-title")
        yield Static(id="status-info")
        yield DataTable(id="history-table")

    def on_mount(self) -> None:
        state = _read_json(_root() / "planner" / "state.json")
        streak = state.get("streak", 0)
        last_rating = (state.get("lastRating", "") or "").upper()
        last_mode = (state.get("lastMode", "") or "").upper()
        last_summary = state.get("lastSummary", "")
        last_date = state.get("lastFinalizedDate", "")

        info_parts = [f"Streak: {streak} days"]
        if last_rating:
            info_parts.append(f"Last rating: {last_rating} ({last_mode})")
        if last_date:
            info_parts.append(f"Last finalized: {last_date}")
        if last_summary:
            info_parts.append(f"\n{last_summary}")

        self.query_one("#status-info", Static).update("\n".join(info_parts))

        table: DataTable = self.query_one("#history-table", DataTable)
        table.add_columns("Date", "Rating", "Mode", "Done", "Total")

        hist = state.get("history", []) or []
        for e in reversed(hist[-30:]):
            table.add_row(
                str(e.get("day", "?")),
                (str(e.get("rating", "?")) or "?").upper(),
                (str(e.get("mode", "?")) or "?").upper(),
                str(e.get("doneCount", "?")),
                str(e.get("total", "?")),
            )


# ── Main app ───────────────────────────────────────────────────


class MoltFocusApp(App):
    """MoltFocus — interactive terminal planner."""

    TITLE = "MoltFocus"
    CSS = CSS
    AUTO_FOCUS = None

    BINDINGS = [
        Binding("d", "show_dashboard", "Dashboard"),
        Binding("t", "show_tasks", "Tasks"),
        Binding("s", "show_status", "Status"),
        Binding("r", "focus_reflection", "Reflect"),
        Binding("m", "toggle_mode", "Mode"),
        Binding("e", "edit_plan", "Edit Plan"),
        Binding("escape", "blur_focus", "Back"),
        Binding("ctrl+s", "save_plan", "Save Plan"),
        Binding("f", "finalize_day", "Finalize"),
        Binding("q", "quit_app", "Quit"),
    ]

    current_view: reactive[str] = reactive("dashboard")

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Control which bindings appear in the footer based on context."""
        if action == "save_plan":
            return True if self._plan_editing else None
        if action == "blur_focus":
            return True if self._plan_editing or self.focused is not None else None
        return True

    def __init__(self) -> None:
        super().__init__()
        self._draft = _load_draft()
        self._plan_md = ""
        self._checkboxes: list[dict] = []
        self._plan_editing = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Horizontal(
            VerticalScroll(
                Label("Plan", classes="section-title"),
                Markdown(id="plan-viewer"),
                TextArea(id="plan-editor"),
                id="left-pane",
                can_focus=False,
            ),
            Vertical(
                VerticalScroll(
                    Label("Check-in", classes="section-title"),
                    Horizontal(
                        Label("Task", classes="todo-col-header"),
                        Label("Comment", classes="todo-col-header"),
                        classes="todo-header-row",
                    ),
                    Vertical(id="checkin-list"),
                    id="checkin-section",
                    can_focus=False,
                ),
                Vertical(
                    Label("Reflection", classes="section-title"),
                    TextArea(id="reflection-area"),
                    id="reflection-section",
                ),
                Static(id="yesterday-summary"),
                id="right-pane",
            ),
            id="main-layout",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._load_data()

    def _load_data(self) -> None:
        """Load plan, draft, state and populate widgets."""
        root = _root()

        # Plan
        self._plan_md = _read(root / "planner" / "latest" / "plan.md")
        plan_widget = self.query_one("#plan-viewer", Markdown)
        if self._plan_md.strip():
            plan_widget.update(self._plan_md)
        else:
            plan_widget.update("*(no plan yet)*")

        # Checkboxes from plan
        self._checkboxes = _checkboxes(self._plan_md)
        self._draft = _load_draft()
        self._rebuild_checkin_list()

        # Reflection
        reflection_area = self.query_one("#reflection-area", TextArea)
        reflection = self._draft.get("reflection", "")
        reflection_area.load_text(reflection)

        # Yesterday summary
        summary_widget = self.query_one("#yesterday-summary", Static)
        state = _read_json(root / "planner" / "state.json")
        last_summary = state.get("lastSummary", "")
        if last_summary:
            summary_widget.update(f"Yesterday: {last_summary}")
        else:
            summary_widget.update("")

        self._update_mode_display()

    def _rebuild_checkin_list(self) -> None:
        """(Re)build the checkin todo items from current checkboxes + draft."""
        items = self._draft.get("items", {})
        checkin_list = self.query_one("#checkin-list", Vertical)
        checkin_list.remove_children()

        for cb in self._checkboxes:
            d = items.get(cb["key"], {})
            done = d.get("done", cb["checked"])
            comment = d.get("comment", "")
            checkin_list.mount(
                TodoItem(
                    key=cb["key"],
                    label=cb["label"],
                    done=done,
                    comment=comment,
                )
            )

    def _update_mode_display(self) -> None:
        """Update sub_title with streak + rating + mode."""
        state = _read_json(_root() / "planner" / "state.json")
        streak = state.get("streak", 0)
        last_rating = (state.get("lastRating", "") or "").upper()
        mode = (self._draft.get("mode", "commit") or "commit").upper()

        parts = [f"🔥 {streak}"]
        if last_rating:
            parts.append(last_rating)
        parts.append(f"[{mode}]")
        self.sub_title = "  ".join(parts)

    # ── Auto-save draft on every change ────────────────────────

    @on(Checkbox.Changed)
    def _on_checkbox_toggle(self, event: Checkbox.Changed) -> None:
        widget_id = event.checkbox.id or ""
        key = widget_id.removeprefix("cb-")
        items = self._draft.setdefault("items", {})
        if key not in items:
            items[key] = {"label": event.checkbox.label, "done": False, "comment": ""}
        items[key]["done"] = event.value
        # Update visual styling on the parent row
        parent = event.checkbox.parent
        if parent and isinstance(parent, TodoItem):
            if event.value:
                parent.add_class("todo-done")
            else:
                parent.remove_class("todo-done")
        self._auto_save()

    @on(Input.Changed)
    def _on_comment_change(self, event: Input.Changed) -> None:
        widget_id = event.input.id or ""
        key = widget_id.removeprefix("cmt-")
        items = self._draft.setdefault("items", {})
        if key not in items:
            items[key] = {"label": "", "done": False, "comment": ""}
        items[key]["comment"] = event.value
        self._auto_save()

    @on(TextArea.Changed, "#reflection-area")
    def _on_reflection_change(self, event: TextArea.Changed) -> None:
        self._draft["reflection"] = event.text_area.text
        self._auto_save()

    @work(thread=True)
    def _auto_save(self) -> None:
        try:
            _save_draft(self._draft)
        except Exception:
            pass

    # ── Screen switching via overlay ───────────────────────────

    def action_show_tasks(self) -> None:
        if self.current_view == "tasks":
            self.action_show_dashboard()
            return
        self._switch_to("tasks")

    def action_show_status(self) -> None:
        if self.current_view == "status":
            self.action_show_dashboard()
            return
        self._switch_to("status")

    def action_show_dashboard(self) -> None:
        self._switch_to("dashboard")

    def action_focus_reflection(self) -> None:
        if self.current_view != "dashboard":
            self._switch_to("dashboard")
        try:
            self.query_one("#reflection-area", TextArea).focus()
        except Exception:
            pass
        self.refresh_bindings()

    def action_blur_focus(self) -> None:
        """Escape handler — unfocus current widget or exit plan edit."""
        if self._plan_editing:
            self._exit_plan_edit(save=False)
        self.set_focus(None)
        self.refresh_bindings()

    def action_toggle_mode(self) -> None:
        """Toggle between commit and recovery mode."""
        current = (self._draft.get("mode", "commit") or "commit").lower()
        self._draft["mode"] = "recovery" if current == "commit" else "commit"
        self._update_mode_display()
        self._auto_save()

    def action_edit_plan(self) -> None:
        """Toggle between plan preview and plan editor."""
        if self._plan_editing:
            self._exit_plan_edit(save=False)
        else:
            self._enter_plan_edit()

    def _enter_plan_edit(self) -> None:
        """Show the plan TextArea editor, hide Markdown preview."""
        self._plan_editing = True
        editor = self.query_one("#plan-editor", TextArea)
        editor.load_text(self._plan_md)
        self.query_one("#plan-viewer", Markdown).display = False
        editor.display = True
        editor.focus()
        self.refresh_bindings()

    def _exit_plan_edit(self, save: bool = False) -> None:
        """Return to Markdown preview, optionally saving the plan."""
        self._plan_editing = False
        editor = self.query_one("#plan-editor", TextArea)
        viewer = self.query_one("#plan-viewer", Markdown)

        if save:
            new_text = editor.text
            root = _root()
            plan_path = root / "planner" / "latest" / "plan.md"
            prev_path = root / "planner" / "latest" / "plan_prev.md"

            # Preserve previous plan
            if plan_path.exists():
                _write_text_atomic(prev_path, _read(plan_path))

            _write_text_atomic(plan_path, new_text.rstrip() + "\n")

            # Reload plan and rebuild checkin
            self._plan_md = new_text.rstrip() + "\n"
            viewer.update(self._plan_md if self._plan_md.strip() else "*(no plan yet)*")
            self._checkboxes = _checkboxes(self._plan_md)
            self._rebuild_checkin_list()

        editor.display = False
        viewer.display = True
        self.refresh_bindings()

    def action_save_plan(self) -> None:
        """Ctrl+S handler — save plan if editing."""
        if self._plan_editing:
            self._exit_plan_edit(save=True)

    def action_finalize_day(self) -> None:
        """Save draft, then finalize in background thread."""
        try:
            _save_draft(self._draft)
        except Exception:
            pass
        self._do_finalize()

    @work(thread=True)
    def _do_finalize(self) -> None:
        """Run finalize in worker thread, show notification with result."""
        try:
            result = _finalize()
            if result.get("ok"):
                rating = result["rating"].upper()
                streak = result["streak"]
                self.call_from_thread(self.notify,
                    f"Finalized! Rating: {rating}, Streak: {streak}",
                    title="Day Finalized", severity="information")
                self.call_from_thread(self._load_data)
            else:
                self.call_from_thread(self.notify,
                    f"Cannot finalize: {result.get('reason', 'unknown')}",
                    title="Finalize Failed", severity="warning")
        except Exception as e:
            self.call_from_thread(self.notify,
                f"Error: {e}", title="Error", severity="error")

    def action_quit_app(self) -> None:
        # Final save before exit
        try:
            _save_draft(self._draft)
        except Exception:
            pass
        self.exit()

    def _switch_to(self, view: str) -> None:
        main = self.query_one("#main-layout", Horizontal)

        # Remove overlay screens if present
        for old in self.query(".overlay-screen"):
            old.remove()

        if view == "dashboard":
            # Show the main layout panes
            try:
                self.query_one("#left-pane").display = True
                self.query_one("#right-pane").display = True
            except Exception:
                pass
            self.current_view = "dashboard"
        else:
            # Hide dashboard panes, mount overlay
            try:
                self.query_one("#left-pane").display = False
                self.query_one("#right-pane").display = False
            except Exception:
                pass

            if view == "tasks":
                screen = TasksScreen(classes="overlay-screen")
                main.mount(screen)
            elif view == "status":
                screen = StatusScreen(classes="overlay-screen")
                main.mount(screen)

            self.current_view = view


# ── Entry point ────────────────────────────────────────────────


def main() -> None:
    root = _root()
    if not root.exists():
        print(f"Workspace not found: {root}")
        print("Set PLANNER_ROOT or run setup.sh first.")
        sys.exit(1)

    app = MoltFocusApp()
    app.run()


if __name__ == "__main__":
    main()
