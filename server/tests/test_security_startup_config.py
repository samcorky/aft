"""Security startup configuration regression tests."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = [pytest.mark.unit, pytest.mark.security]


def test_app_import_fails_when_secret_key_missing():
    """Critical #1 regression: startup must fail fast if SECRET_KEY is not configured."""
    server_dir = Path(__file__).resolve().parents[1]

    env = os.environ.copy()
    env.pop("SECRET_KEY", None)

    # Keep this disabled so the test only validates SECRET_KEY enforcement.
    env["ENABLE_SERVER_SIDE_SESSIONS"] = "false"

    bootstrap_code = "\n".join([
        "import sys, types",
        "mod = types.ModuleType('flask_session')",
        "class _Session:",
        "    def __init__(self, *args, **kwargs):",
        "        pass",
        "mod.Session = _Session",
        "sys.modules['flask_session'] = mod",
        "import app",
    ])

    result = subprocess.run(
        [sys.executable, "-c", bootstrap_code],
        cwd=server_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    combined_output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0
    assert "SECRET_KEY environment variable is not set" in combined_output
