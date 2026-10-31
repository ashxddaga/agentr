"""
agentr.store: Unified storage layer for AgentR, providing canonical directory discovery,
atomic file writes, and cross-process file locking (fcntl) for concurrent multi-agent safety.
"""
from __future__ import annotations

import os
import json
import fcntl
import tempfile
from typing import Optional, Any, Dict


def find_agentr_dir(project_dir: Optional[str] = None) -> str:
    """Canonical resolver for the .agentr directory.

    Walks up from project_dir (or CWD) to locate an existing .agentr folder.
    If inside ~/Work, falls back to ~/Work/.agentr if present.
    Defaults to <project_dir>/.agentr.
    """
    curr = os.path.abspath(project_dir or os.getcwd())

    # Walk up to find an existing .agentr directory
    probe = curr
    while True:
        cand = os.path.join(probe, ".agentr")
        if os.path.isdir(cand):
            return cand
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent

    # If inside ~/Work, fall back to ~/Work/.agentr if it exists
    work_dir = os.path.expanduser("~/Work")
    if curr.startswith(work_dir):
        work_cand = os.path.join(work_dir, ".agentr")
        if os.path.isdir(work_cand):
            return work_cand

    return os.path.join(curr, ".agentr")


def read_json_locked(filepath: str, default: Any = None) -> Any:
    """Reads a JSON file with a shared lock (LOCK_SH) to prevent reading during concurrent writes."""
    if not os.path.exists(filepath):
        return default

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                return json.load(f)
            finally:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
    except Exception:
        return default


def write_json_locked(filepath: str, data: Any, indent: int = 2) -> None:
    """Writes JSON data atomically with exclusive locking (LOCK_EX) and fsync.

    Writes to a temporary file in the same directory first, then renames to avoid partial writes.
    """
    dir_name = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(dir_name, exist_ok=True)

    temp_fd, temp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp_", suffix=".json")
    try:
        with open(temp_fd, "w", encoding="utf-8") as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                json.dump(data, f, indent=indent, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            finally:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
        os.replace(temp_path, filepath)
    except Exception:
        if os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass
        raise


def append_text_locked(filepath: str, text: str) -> None:
    """Appends text to a file with an exclusive lock (LOCK_EX)."""
    dir_name = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(dir_name, exist_ok=True)

    with open(filepath, "a", encoding="utf-8") as f:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        finally:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
