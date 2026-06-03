"""CLI smoke tests for the single-runtime daemon entrypoint."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_run_trade_oracle_daemon_help_loads_from_script_path():
    repo_root = Path(__file__).resolve().parents[1]  # .../TRADE_ORACLE
    script_path = repo_root / "scripts" / "run_trade_oracle_daemon.py"
    completed = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "--poll-once" in completed.stdout
