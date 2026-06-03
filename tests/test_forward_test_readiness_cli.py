"""CLI smoke test for the secret-safe forward-test readiness checker."""

import subprocess
import sys


def test_forward_test_readiness_cli_help_loads():
    result = subprocess.run(
        [sys.executable, "scripts/check_forward_test_readiness.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--check-supabase" in result.stdout


def test_resolve_pending_review_cli_help_loads():
    result = subprocess.run(
        [sys.executable, "scripts/resolve_pending_review.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--thread-id" in result.stdout
    assert "--backend" in result.stdout


def test_wake_cycle_scripts_exist_and_target_cycle_runner():
    from pathlib import Path

    install_script = Path("scripts/install_4h_wake_cycle_task.ps1").read_text(encoding="utf-8")
    wake_runner = Path("scripts/run_forward_test_wake_cycle.ps1").read_text(encoding="utf-8")
    wake_probe = Path("scripts/check_wake_cycle_task.ps1").read_text(encoding="utf-8")

    assert "run_forward_test_wake_cycle.ps1" in install_script
    assert "run_trade_oracle_daemon.py\", \"--once" in wake_runner
    assert "WakeToRun" in wake_probe
