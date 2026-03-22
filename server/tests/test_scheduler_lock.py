"""Tests for shared scheduler lock helpers."""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from scheduler_lock import acquire_scheduler_lock, release_scheduler_lock


def test_acquire_scheduler_lock_is_exclusive(tmp_path, monkeypatch):
    """Only one owner should acquire a lock file at a time."""
    monkeypatch.setenv("HOSTNAME", "test-container")
    lock_file = Path(tmp_path) / "scheduler.lock"

    acquired_first, details_first = acquire_scheduler_lock(lock_file, "card")
    acquired_second, details_second = acquire_scheduler_lock(lock_file, "card")

    assert acquired_first is True
    assert details_first["reason"] == "acquired"
    assert acquired_second is False
    assert details_second["reason"] == "active_lock"

    release_scheduler_lock(lock_file)


def test_stale_lock_with_dead_pid_is_reclaimed(tmp_path, monkeypatch):
    """A stale lock from a dead PID should be removed and reacquired."""
    monkeypatch.setenv("HOSTNAME", "test-container")
    lock_file = Path(tmp_path) / "scheduler.lock"

    stale_data = {
        "pid": 999999,
        "container_id": "test-container",
        "scheduler_type": "backup",
        "acquired_at": (datetime.now() - timedelta(hours=1)).isoformat(),
        "last_heartbeat": (datetime.now() - timedelta(hours=1)).isoformat(),
    }
    lock_file.write_text(json.dumps(stale_data), encoding="utf-8")

    acquired, details = acquire_scheduler_lock(lock_file, "backup")

    assert acquired is True
    assert details["reason"] == "acquired"

    release_scheduler_lock(lock_file)


def test_active_owner_not_reclaimed_on_old_heartbeat(tmp_path, monkeypatch):
    """A live owner process should keep the lock even with old heartbeat."""
    monkeypatch.setenv("HOSTNAME", "test-container")
    lock_file = Path(tmp_path) / "scheduler.lock"

    lock_data = {
        "pid": os.getpid(),
        "container_id": "test-container",
        "scheduler_type": "housekeeping",
        "acquired_at": (datetime.now() - timedelta(hours=2)).isoformat(),
        "last_heartbeat": (datetime.now() - timedelta(hours=2)).isoformat(),
    }
    lock_file.write_text(json.dumps(lock_data), encoding="utf-8")

    acquired, details = acquire_scheduler_lock(lock_file, "housekeeping")

    assert acquired is False
    assert details["reason"] == "active_lock"
