# TRADE_ORACLE AI Context Handoff

Last updated: 2026-06-02

This is the canonical entrypoint for a fresh AI or developer session.

Read in this order:

1. [trade_oracle_ai_agent_handoff_packet.md](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/documents/development/trade_oracle_ai_agent_handoff_packet.md)
2. [current_trade_oracle_trading_health_report.md](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/documents/development/current_trade_oracle_trading_health_report.md)
3. [trade_oracle_system_handbook.md](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/documents/development/trade_oracle_system_handbook.md)
4. [trade_oracle_final_pipeline_readiness_report.md](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/documents/development/trade_oracle_final_pipeline_readiness_report.md)
5. [README.md](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/README.md)

## Current Direction

- one Python daemon is the primary runtime path
- Telegram uses long polling, not webhooks
- Supabase is the active unified data center
- SQLite fallback stays until repeated parity is proven
- n8n is fallback/reference only
- MT5 demo is the active execution target
- operator workflow is built around a one-click VS Code power-on path plus watchdog recovery

## Current Reality Snapshot

As of 2026-06-02 recovery session:

- the project is operationally real, with demo broker-accepted orders proven
- the daemon was recovered and is running healthy after an env-inheritance fix (see below)
- the watchdog is running and correctly detects daemon health via runtime lock + pid
- **daemon logs write to stderr** (results/trade_oracle_daemon.err.log) — stdout is always empty by design
- the FTMO demo account balance is approximately $50,000 (appears to have been replenished/reset by FTMO)
- Supabase account_state high_watermark (~$50,002) is CORRECT — it reflects live MT5 equity
- account_state.current_balance (shows 5000) is a stale static field — all risk calcs use live MT5 equity, not this field
- 70 total cycles observed, 28 transmit successes, broker acceptance rate ~58%, 0 error events
- at last check: 3 open DOGEUSD SELL positions placed during today's recovery testing

## Key Bug Fixed 2026-06-02

**Windows `Start-Process` env-inheritance gap**: When `start_trade_oracle_daemon.ps1` launched
Python via `Start-Process` with file-redirection handles, Windows did NOT reliably forward the
parent process's env vars (set via `Import-DotEnvFile`) to the child. This caused the daemon to
start, write the runtime lock, then immediately crash silently with "Missing MT5 connection fields"
because it had no credentials. The log files stayed empty (0 bytes) making this very hard to trace.

**Fix applied to** [scripts/start_trade_oracle_daemon.ps1](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/scripts/start_trade_oracle_daemon.ps1):
Now generates a self-contained PowerShell launcher wrapper (`results/trade_oracle_daemon_launcher.ps1`)
that independently reads `.env.n8n.local` before calling python. The watchdog auto-restart path
calls `start_forward_testing_stack.ps1 → start_trade_oracle_daemon.ps1`, so all recovery paths
benefit from this fix.

## Immediate Safety Rules

- do not print secrets from `.env.n8n.local`
- do not wipe or clean the repo automatically
- do not revert unrelated local changes
- do not perform a broad refactor before the supervised reliability window is complete
- prefer small operational, diagnostics, reporting, and runtime-hardening fixes

## Important Nuance

The code and docs are not perfectly aligned on cycle cadence:

- [config/settings.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/config/settings.py) currently defaults `TRADE_ORACLE_DAEMON_CYCLE_INTERVAL_SECONDS` to `3600`
- several documents and workflow names still refer to historical `4H` orchestration

Treat the code/default runtime setting as the live truth unless a human explicitly says otherwise.

## Most Important Files

1. [documents/development/trade_oracle_ai_agent_handoff_packet.md](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/documents/development/trade_oracle_ai_agent_handoff_packet.md)
2. [documents/development/current_trade_oracle_trading_health_report.md](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/documents/development/current_trade_oracle_trading_health_report.md)
3. [ai/trade_oracle_daemon.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/ai/trade_oracle_daemon.py)
4. [ai/trade_oracle_runtime_state.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/ai/trade_oracle_runtime_state.py)
5. [ai/trade_oracle_supabase_storage.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/ai/trade_oracle_supabase_storage.py)
6. [execution/mt5_bridge.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/execution/mt5_bridge.py)
7. [config/settings.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/config/settings.py)
8. [scripts/start_forward_testing_stack.ps1](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/scripts/start_forward_testing_stack.ps1)
9. [scripts/run_trade_oracle_daemon.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/scripts/run_trade_oracle_daemon.py)
10. [scripts/run_local_server_watchdog.ps1](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/scripts/run_local_server_watchdog.ps1)
11. [scripts/check_forward_test_readiness.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/scripts/check_forward_test_readiness.py)
12. [scripts/generate_trade_oracle_trading_health_report.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/scripts/generate_trade_oracle_trading_health_report.py)
13. [scripts/start_trade_oracle_daemon.ps1](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/scripts/start_trade_oracle_daemon.ps1)

## Starter Prompt

Use the tailored prompt here:

[google_ai_ide_handoff_prompt.md](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/documents/development/google_ai_ide_handoff_prompt.md)
