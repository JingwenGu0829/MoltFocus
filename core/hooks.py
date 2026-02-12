"""Plugin/hook system for MoltFocus.

Lifecycle hooks run shell commands at key points in the system.
Configured via planner/hooks.yaml.

Hook points:
- pre_finalize, post_finalize
- pre_plan_generate, post_plan_generate
- on_focus_start, on_focus_stop
- on_task_complete
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from core.fileio import read_yaml
from core.workspace import hooks_config_path, workspace_root


VALID_HOOK_POINTS = {
    "pre_finalize",
    "post_finalize",
    "pre_plan_generate",
    "post_plan_generate",
    "on_focus_start",
    "on_focus_stop",
    "on_task_complete",
}

DEFAULT_TIMEOUT = 30


def load_hooks_config(root: Path | None = None) -> dict[str, Any]:
    """Load hooks configuration from planner/hooks.yaml."""
    if root is None:
        root = workspace_root()
    path = hooks_config_path(root)
    if not path.exists():
        return {}
    return read_yaml(path)


def run_hooks(
    hook_point: str,
    context: dict[str, Any],
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Run all hooks registered for a given hook point.

    Context is passed as JSON via stdin to each hook subprocess.
    Returns list of results with stdout/stderr and exit codes.
    """
    if hook_point not in VALID_HOOK_POINTS:
        return []

    if root is None:
        root = workspace_root()

    config = load_hooks_config(root)
    hooks = config.get(hook_point, [])

    if not hooks or not isinstance(hooks, list):
        return []

    results = []
    context_json = json.dumps(context, ensure_ascii=False)

    for hook in hooks:
        if isinstance(hook, str):
            command = hook
            timeout = DEFAULT_TIMEOUT
        elif isinstance(hook, dict):
            command = hook.get("command", "")
            timeout = hook.get("timeout", DEFAULT_TIMEOUT)
        else:
            continue

        if not command:
            continue

        result: dict[str, Any] = {"command": command, "hook_point": hook_point}
        try:
            proc = subprocess.run(
                command,
                shell=True,
                input=context_json,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(root),
            )
            result["exit_code"] = proc.returncode
            result["stdout"] = proc.stdout[:4096]  # Cap output
            result["stderr"] = proc.stderr[:4096]
        except subprocess.TimeoutExpired:
            result["exit_code"] = -1
            result["error"] = f"Hook timed out after {timeout}s"
        except Exception as e:
            result["exit_code"] = -1
            result["error"] = str(e)

        results.append(result)

    return results
