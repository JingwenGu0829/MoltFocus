"""MoltFocus core library — shared data layer and engines.

Public API re-exports for convenient imports:
    from core import workspace_root, today_str, finalize_day, ...
"""

# Workspace & paths
from core.workspace import (
    workspace_root,
    get_user_timezone,
    today_str,
    now_local,
    plan_path,
    plan_prev_path,
    draft_path,
    state_path,
    reflections_path,
    profile_path,
    tasks_path,
    focus_path,
    analytics_path,
    agent_context_path,
    hooks_config_path,
)

# File I/O
from core.fileio import (
    read_text,
    read_json,
    read_yaml,
    write_text,
    write_json,
    write_text_atomic,
    write_json_atomic,
    write_yaml_atomic,
)

# Checkbox parsing
from core.checkbox import (
    extract_checkboxes,
    parse_duration_from_label,
    parse_task_title_from_label,
)

# Rating
from core.rating import (
    compute_rating,
    counts_for_streak,
    summarize_paragraph,
)

# Reflections
from core.reflections import (
    prepend_reflection,
    build_reflection_entry,
)

# Tasks
from core.tasks import (
    validate_task,
    load_tasks,
    save_tasks,
    find_task,
    create_task,
    update_task,
    delete_task,
    match_task_from_label,
    update_task_progress,
    process_checkin_progress,
    reset_weekly_budgets,
    archive_completed_tasks,
    get_tasks_with_computed_fields,
)

# Finalization
from core.finalize import finalize_day

# Models
from core.models import (
    TimeRange,
    Profile,
    Task,
    TasksFile,
    CheckinItem,
    CheckinDraft,
    HistoryEntry,
    State,
    PlanCheckbox,
    FocusSession,
    FocusState,
    ScheduledBlock,
    DaySchedule,
    DayRecord,
    AnalyticsSummary,
    FixedRoutine,
    WeeklyEvent,
)
