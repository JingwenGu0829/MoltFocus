"""Atomic file I/O utilities for MoltFocus."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml


def read_text(path: Path) -> str:
    """Read a text file, returning empty string if missing."""
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON file, returning empty dict if missing."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    return json.loads(text)


def read_yaml(path: Path) -> dict[str, Any]:
    """Read a YAML file, returning empty dict if missing or empty."""
    text = read_text(path)
    if not text.strip():
        return {}
    result = yaml.safe_load(text)
    return result if isinstance(result, dict) else {}


def write_text(path: Path, content: str) -> None:
    """Simple (non-atomic) text write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Simple (non-atomic) JSON write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _atomic_write(path: Path, content: str, suffix: str = ".tmp") -> None:
    """Atomic write with file locking: temp file + flock + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        os.rename(temp_path, path)
    except Exception:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def write_text_atomic(path: Path, content: str) -> None:
    """Atomic text file write."""
    _atomic_write(path, content, suffix=".txt")


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    """Atomic JSON write."""
    _atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n", suffix=".json")


def write_yaml_atomic(path: Path, data: dict[str, Any]) -> None:
    """Atomic YAML write."""
    content = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    _atomic_write(path, content, suffix=".yaml")
