"""CLI smoke tests for the single-runtime daemon entrypoint."""

from __future__ import annotations

import subprocess
import sys


def test_run_trade_oracle_daemon_help_loads_from_script_path():
    completed = subprocess.run(
        [sys.executable, "scripts/run_trade_oracle_daemon.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "--poll-once" in completed.stdout
