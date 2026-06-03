import importlib
import subprocess
import sys


def test_trading_health_report_cli_help_loads():
    result = subprocess.run(
        [sys.executable, "scripts/generate_trade_oracle_trading_health_report.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--markdown-output" in result.stdout


def test_type_name_handles_zero_type_code():
    report_script = importlib.import_module("scripts.generate_trade_oracle_trading_health_report")

    assert report_script._type_name(report_script._int_value(0)) == "BUY"
    assert report_script._type_name(report_script._int_value(1)) == "SELL"
    assert report_script._type_name(report_script._int_value(None)) == "TYPE_-1"
