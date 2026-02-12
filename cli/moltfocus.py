#!/usr/bin/env python3
"""MoltFocus TUI — interactive terminal planner powered by Textual."""

from __future__ import annotations

import sys
from pathlib import Path

# ── Ensure project root is on sys.path so `from core import ...` works ──
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

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

# ── Core library imports (replaces ~280 lines of duplicated data layer) ──
from core import (
    workspace_root,
    get_user_timezone,
    today_str,
    now_local,
    read_text,
    read_json,
    write_json_atomic,
    write_text_atomic,
    extract_checkboxes,
    finalize_day,
    load_tasks,
)
from core.workspace import (
    plan_path,
    draft_path,
    state_path,
    plan_prev_path,
)


# ── Draft helpers ─────────────────────────────────────────────

def _load_draft() -> dict:
    root = workspace_root()
    draft = read_json(draft_path(root))
    if draft.get("day") != today_str():
        draft = {"day": today_str(), "mode": "commit", "items": {}, "reflection": ""}
    return draft


def _save_draft(draft: dict) -> None:
    root = workspace_root()
    draft["updatedAt"] = now_local().isoformat(timespec="seconds")
    write_json_atomic(draft_path(root), draft)


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
            placeholder="comment\u2026",
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

        try:
            tasks_file = load_tasks()
        except Exception:
            return

        for t in tasks_file.tasks:
            details = ""
            if t.type == "deadline_project":
                details = f"{t.remaining_hours or '?'}h remaining"
            elif t.type == "weekly_budget":
                details = f"{t.target_hours_per_week or '?'}h/week ({t.hours_this_week:.1f}h done)"
            elif t.type == "daily_ritual":
                details = f"{t.estimated_minutes_per_day or '?'}min/day"
            elif t.type == "open_ended":
                details = "open-ended"

            table.add_row(t.id, t.title, t.type, str(t.priority), t.status, details)


class StatusScreen(Vertical):
    """Status view: streak info + history table."""

    def compose(self) -> ComposeResult:
        yield Label("Status", classes="section-title")
        yield Static(id="status-info")
        yield DataTable(id="history-table")

    def on_mount(self) -> None:
        root = workspace_root()
        state = read_json(state_path(root))
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
    """MoltFocus \u2014 interactive terminal planner."""

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
        Binding("g", "generate_plan", "Generate"),
        Binding("q", "quit_app", "Quit"),
    ]

    current_view: reactive[str] = reactive("dashboard")

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "save_plan":
            return True if self._plan_editing else None
        if action == "blur_focus":
            return True if self._plan_editing or self.focused is not None else None
        return True

    def __init__(self) -> None:
        super().__init__()
        self._draft = _load_draft()
        self._plan_md = ""
        self._checkboxes: list = []
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
        root = workspace_root()

        self._plan_md = read_text(plan_path(root))
        plan_widget = self.query_one("#plan-viewer", Markdown)
        if self._plan_md.strip():
            plan_widget.update(self._plan_md)
        else:
            plan_widget.update("*(no plan yet)*")

        self._checkboxes = extract_checkboxes(self._plan_md)
        self._draft = _load_draft()
        self._rebuild_checkin_list()

        reflection_area = self.query_one("#reflection-area", TextArea)
        reflection = self._draft.get("reflection", "")
        reflection_area.load_text(reflection)

        summary_widget = self.query_one("#yesterday-summary", Static)
        state = read_json(state_path(root))
        last_summary = state.get("lastSummary", "")
        if last_summary:
            summary_widget.update(f"Yesterday: {last_summary}")
        else:
            summary_widget.update("")

        self._update_mode_display()

    def _rebuild_checkin_list(self) -> None:
        items = self._draft.get("items", {})
        checkin_list = self.query_one("#checkin-list", Vertical)
        checkin_list.remove_children()

        for cb in self._checkboxes:
            key = cb.key
            d = items.get(key, {})
            done = d.get("done", cb.checked)
            comment = d.get("comment", "")
            checkin_list.mount(
                TodoItem(key=key, label=cb.label, done=done, comment=comment)
            )

    def _update_mode_display(self) -> None:
        root = workspace_root()
        state = read_json(state_path(root))
        streak = state.get("streak", 0)
        last_rating = (state.get("lastRating", "") or "").upper()
        mode = (self._draft.get("mode", "commit") or "commit").upper()

        parts = [f"\U0001f525 {streak}"]
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
        if self._plan_editing:
            self._exit_plan_edit(save=False)
        self.set_focus(None)
        self.refresh_bindings()

    def action_toggle_mode(self) -> None:
        current = (self._draft.get("mode", "commit") or "commit").lower()
        self._draft["mode"] = "recovery" if current == "commit" else "commit"
        self._update_mode_display()
        self._auto_save()

    def action_edit_plan(self) -> None:
        if self._plan_editing:
            self._exit_plan_edit(save=False)
        else:
            self._enter_plan_edit()

    def _enter_plan_edit(self) -> None:
        self._plan_editing = True
        editor = self.query_one("#plan-editor", TextArea)
        editor.load_text(self._plan_md)
        self.query_one("#plan-viewer", Markdown).display = False
        editor.display = True
        editor.focus()
        self.refresh_bindings()

    def _exit_plan_edit(self, save: bool = False) -> None:
        self._plan_editing = False
        editor = self.query_one("#plan-editor", TextArea)
        viewer = self.query_one("#plan-viewer", Markdown)

        if save:
            new_text = editor.text
            root = workspace_root()
            pp = plan_path(root)
            pprev = plan_prev_path(root)

            if pp.exists():
                write_text_atomic(pprev, read_text(pp))

            write_text_atomic(pp, new_text.rstrip() + "\n")

            self._plan_md = new_text.rstrip() + "\n"
            viewer.update(self._plan_md if self._plan_md.strip() else "*(no plan yet)*")
            self._checkboxes = extract_checkboxes(self._plan_md)
            self._rebuild_checkin_list()

        editor.display = False
        viewer.display = True
        self.refresh_bindings()

    def action_save_plan(self) -> None:
        if self._plan_editing:
            self._exit_plan_edit(save=True)

    def action_finalize_day(self) -> None:
        try:
            _save_draft(self._draft)
        except Exception:
            pass
        self._do_finalize()

    @work(thread=True)
    def _do_finalize(self) -> None:
        try:
            result = finalize_day()
            if result.get("ok"):
                if result.get("already_finalized"):
                    self.call_from_thread(self.notify,
                        "Already finalized today.",
                        title="Day Finalized", severity="information")
                else:
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

    def action_generate_plan(self) -> None:
        """Generate a new plan using the built-in scheduler."""
        self._do_generate()

    @work(thread=True)
    def _do_generate(self) -> None:
        try:
            from core.scheduler import generate_plan
            plan_md = generate_plan()
            self.call_from_thread(self.notify,
                "Plan generated!",
                title="Plan Generated", severity="information")
            self.call_from_thread(self._load_data)
        except Exception as e:
            self.call_from_thread(self.notify,
                f"Error: {e}", title="Error", severity="error")

    def action_quit_app(self) -> None:
        try:
            _save_draft(self._draft)
        except Exception:
            pass
        self.exit()

    def _switch_to(self, view: str) -> None:
        main = self.query_one("#main-layout", Horizontal)

        for old in self.query(".overlay-screen"):
            old.remove()

        if view == "dashboard":
            try:
                self.query_one("#left-pane").display = True
                self.query_one("#right-pane").display = True
            except Exception:
                pass
            self.current_view = "dashboard"
        else:
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


# ── CLI subcommands ────────────────────────────────────────────


def _cli_generate(args: list[str]) -> None:
    """Generate a daily plan using the built-in scheduler."""
    from core.scheduler import generate_plan
    from datetime import date as date_type

    target_date = None
    if "--date" in args:
        idx = args.index("--date")
        if idx + 1 < len(args):
            try:
                target_date = date_type.fromisoformat(args[idx + 1])
            except ValueError:
                print(f"Invalid date: {args[idx + 1]}")
                sys.exit(1)

    plan_md = generate_plan(target_date=target_date)
    print(plan_md)


def _cli_finalize() -> None:
    """Run finalization from CLI."""
    result = finalize_day()
    if result.get("ok"):
        if result.get("already_finalized"):
            print(f"Already finalized for {result['day']}.")
        else:
            print(f"Finalized! Rating: {result['rating'].upper()}, Streak: {result['streak']}")
            if result.get("task_updates"):
                print(f"Task updates: {', '.join(result['task_updates'])}")
    else:
        print(f"Cannot finalize: {result.get('reason', 'unknown')}")
        sys.exit(1)


def _cli_tasks() -> None:
    """List tasks from CLI."""
    from core import State
    tasks_file = load_tasks()
    state_data = read_json(state_path(workspace_root()))
    state = State.from_dict(state_data)
    computed = get_tasks_with_computed_fields(tasks_file, state, today_str())
    for t in computed:
        urgency = t.get("urgency_score", 0)
        print(f"  [{t['status']:>8}] {t['id']:<25} {t['title']:<30} pri={t['priority']} urgency={urgency:.1f}")


def _cli_analytics() -> None:
    """Show analytics from CLI."""
    from core.analytics import refresh_analytics
    summary = refresh_analytics()
    print(f"Days tracked: {summary.total_days_tracked}")
    print(f"7-day avg: {summary.rolling_7day_avg:.1%}")
    print(f"30-day avg: {summary.rolling_30day_avg:.1%}")
    print(f"Recovery success rate: {summary.recovery_success_rate:.1%}")
    if summary.completion_by_weekday:
        print("\nCompletion by weekday:")
        for day, rate in sorted(summary.completion_by_weekday.items()):
            print(f"  {day}: {rate:.1%}")
    if summary.most_skipped_tasks:
        print(f"\nMost skipped: {', '.join(summary.most_skipped_tasks)}")


def _cli_focus(args: list[str]) -> None:
    """Focus session management from CLI."""
    from core.focus import start_session, stop_session, get_active_session, get_focus_stats

    if not args:
        # Show current state
        session = get_active_session()
        if session:
            print(f"Active focus: {session.task_label} (started {session.started_at})")
            print(f"  Planned: {session.planned_minutes}min, Interruptions: {session.interruptions}")
        else:
            print("No active focus session.")
        stats = get_focus_stats(days=7)
        print(f"\n7-day stats: {stats['total_sessions']} sessions, {stats['total_minutes']:.0f}min total")
        return

    subcmd = args[0]
    if subcmd == "start":
        task_id = args[1] if len(args) > 1 else "manual"
        label = args[2] if len(args) > 2 else task_id
        minutes = int(args[3]) if len(args) > 3 else 25
        session = start_session(task_id, label, minutes)
        print(f"Focus started: {label} ({minutes}min)")
    elif subcmd == "stop":
        completed = "--completed" in args
        session = stop_session(completed=completed)
        print(f"Focus stopped: {session.elapsed_minutes:.1f}min elapsed")
    elif subcmd == "interrupt":
        from core.focus import record_interruption
        session = record_interruption()
        if session:
            print(f"Interruption recorded ({session.interruptions} total)")
        else:
            print("No active session.")


# ── Entry point ────────────────────────────────────────────────


def main() -> None:
    root = workspace_root()
    if not root.exists():
        print(f"Workspace not found: {root}")
        print("Set PLANNER_ROOT or run setup.sh first.")
        sys.exit(1)

    args = sys.argv[1:]

    # Subcommand dispatch
    if args:
        cmd = args[0]
        if cmd == "generate":
            _cli_generate(args[1:])
        elif cmd == "finalize":
            _cli_finalize()
        elif cmd == "tasks":
            _cli_tasks()
        elif cmd == "analytics":
            _cli_analytics()
        elif cmd == "focus":
            _cli_focus(args[1:])
        elif cmd == "--help" or cmd == "-h":
            print("MoltFocus — interactive terminal planner")
            print()
            print("Usage:")
            print("  moltfocus                  Launch TUI (default)")
            print("  moltfocus generate         Generate plan using scheduler")
            print("    --date YYYY-MM-DD        Generate for specific date")
            print("  moltfocus finalize         Run nightly finalization")
            print("  moltfocus tasks            List tasks with urgency scores")
            print("  moltfocus analytics        Show analytics summary")
            print("  moltfocus focus            Show focus session state")
            print("    start <id> [label] [min] Start focus session")
            print("    stop [--completed]       Stop focus session")
            print("    interrupt                Record interruption")
        else:
            print(f"Unknown command: {cmd}")
            print("Run 'moltfocus --help' for usage.")
            sys.exit(1)
        return

    # Default: launch TUI
    tui_app = MoltFocusApp()
    tui_app.run()


if __name__ == "__main__":
    main()
