"""Tests for core/hooks.py — hook system."""

import json
from core.hooks import run_hooks, load_hooks_config
from core.fileio import write_text


def test_run_hooks_no_config(workspace):
    """No hooks.yaml -> no hooks run."""
    results = run_hooks("post_finalize", {"day": "2026-02-11"}, workspace)
    assert results == []


def test_run_hooks_with_echo(workspace):
    """Test hook that echoes context via stdin."""
    import yaml
    config = {
        "post_finalize": [
            "cat"  # echo back stdin
        ]
    }
    config_path = workspace / "planner" / "hooks.yaml"
    config_path.write_text(yaml.dump(config), encoding="utf-8")

    results = run_hooks("post_finalize", {"day": "2026-02-11"}, workspace)
    assert len(results) == 1
    assert results[0]["exit_code"] == 0
    # stdout should contain our context JSON
    output = json.loads(results[0]["stdout"])
    assert output["day"] == "2026-02-11"


def test_run_hooks_invalid_hook_point(workspace):
    results = run_hooks("invalid_point", {}, workspace)
    assert results == []


def test_run_hooks_timeout(workspace):
    """Test hook timeout protection."""
    import yaml
    config = {
        "post_finalize": [
            {"command": "sleep 10", "timeout": 1}
        ]
    }
    config_path = workspace / "planner" / "hooks.yaml"
    config_path.write_text(yaml.dump(config), encoding="utf-8")

    results = run_hooks("post_finalize", {"day": "2026-02-11"}, workspace)
    assert len(results) == 1
    assert results[0]["exit_code"] == -1
    assert "timed out" in results[0].get("error", "").lower()
