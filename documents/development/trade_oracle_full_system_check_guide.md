# TRADE_ORACLE Full System Check Guide

## Purpose

This guide is for any engineer or LLM that needs to perform a real top-to-bottom system check of the TRADE_ORACLE repo without assuming prior project context.

It is written to be usable by:

- a new human developer
- a future Codex session
- another LLM with local repo access

The goal is not just "run tests." The goal is to answer:

1. Is the codebase healthy?
2. Is the live daemon stack healthy?
3. Is Telegram long polling healthy?
4. Is Supabase reachable and usable?
5. Is MT5 reachable and usable?
6. Is the restart/recovery path healthy?
7. What has the system actually been doing in the market so far?
8. Is the system actually ready for supervised forward testing?

## Required assumptions

Assume only the following:

- you have local filesystem access to the repo
- you can run PowerShell commands
- the repo root is the current working directory
- secret values may exist in `.env.n8n.local`
- you must not print secrets back into logs or summaries

## High-level architecture to keep in mind

Current intended operating model:

- one Python daemon is the primary runtime path
- Telegram uses long polling
- Supabase is the unified active data center
- SQLite remains as fallback/reference until parity is no longer needed
- n8n is fallback/reference only
- MT5 is the execution backend for current forward testing

That means a full system check must cover both:

- code and storage correctness
- live operator/runtime behavior
- trading-journey behavior and current broker exposure

## Review template standard

Use a two-layer review template:

1. system-operations review
2. trading-journey review

The trading-journey review should be structured like a lightweight execution-quality and automated-trading supervision check:

- lifecycle coverage: idea -> review -> risk gate -> transmit -> live exposure
- execution-quality coverage: attempts, successes, and conversion rates
- control coverage: pending reviews, risk rejections, and error events
- exposure coverage: current open positions and pending orders

This structure is intentionally aligned with official guidance that emphasizes:

- "regular and rigorous" execution-quality review and documented exception reporting
- continuous supervision and monitoring of automated trading systems
- post-trade reporting and system safeguards

Source references:

- FINRA Best Execution overview and effective practices:
  https://www.finra.org/rules-guidance/guidance/reports/2024-finra-annual-regulatory-oversight-report/best-execution
- SEC order execution quality disclosure context:
  https://www.sec.gov/newsroom/speeches-statements/gensler-statement-order-execution-quality-030624
- CFTC automated trading risk controls and system safeguards:
  https://www.cftc.gov/PressRoom/PressReleases/6683-13
- NFA supervision expectations for electronic trading systems:
  https://www.nfa.futures.org/members/fcm/regulatory-obligations/supervision.html

## Files to read first

Read these before running anything:

1. `AI_CONTEXT_HANDOFF.md`
2. `README.md`
3. `ai/trade_oracle_daemon.py`
4. `ai/langgraph_orchestrator.py`
5. `ai/trade_oracle_runtime_state.py`
6. `ai/trade_oracle_supabase.py`
7. `ai/trade_oracle_supabase_storage.py`
8. `execution/mt5_bridge.py`
9. `config/settings.py`
10. `scripts/start_forward_testing_stack.ps1`
11. `scripts/run_local_server_watchdog.ps1`
12. `scripts/check_forward_test_readiness.py`

## Full system check procedure

Run the checks in this exact order.

### 1. Confirm repo and runtime artifact state

Commands:

```powershell
git status --short
Get-Content results\local_server_watchdog_heartbeat.json
Get-Content results\forward_testing_stack_status.json
Get-Process -Name python,powershell,terminal64 -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,StartTime | Sort-Object ProcessName,Id
```

What to look for:

- whether the repo is dirty
- whether the daemon appears healthy in the heartbeat
- whether the stack status file is current or stale
- whether MT5, daemon, and watchdog processes exist

Important interpretation note:

- `forward_testing_stack_status.json` can lag reality
- `local_server_watchdog_heartbeat.json` is the more important live health signal
- PID files can also be stale; always compare them against live processes

### 2. Run the full automated test suite

Command:

```powershell
.\.venv-langgraph\Scripts\python.exe -m pytest -p no:cacheprovider
```

Pass criteria:

- all tests pass except any intentional `xfailed` cases

Current known healthy result reference:

```text
95 passed, 1 xfailed, 1 warning
```

If this regresses, stop and report the exact failing tests first.

### 3. Run the live readiness check

Command:

```powershell
.\.venv-langgraph\Scripts\python.exe scripts\check_forward_test_readiness.py --env-file .env.n8n.local --check-supabase
```

Pass criteria:

- `missing_required_env` is empty
- `runtime_state.ok` is `true`
- `supabase.ok` is `true`
- `blockers` is empty
- `ready_for_forward_testing_start` is `true`

Interpretation:

- this check is the main truth source for operator readiness
- it is secret-safe by design
- it does not place broker trades

### 4. Validate MT5 live profile reachability

Command:

```powershell
.\.venv-langgraph\Scripts\python.exe scripts\validate_mt5_demo_profile.py --env-file .env.n8n.local
```

Pass criteria:

- authenticated account state
- expected server present
- intended symbols resolve
- each intended symbol has a live tick
- `can_open_new_trade` is `true`

Warnings that matter:

- missing tick data
- wrong server
- wrong symbol mapping
- Python API blocked by terminal settings

### 5. Generate the trading-health report

Command:

```powershell
.\.venv-langgraph\Scripts\python.exe scripts\generate_trade_oracle_trading_health_report.py --env-file .env.n8n.local --json-output results\trade_oracle_trading_health_report.json --markdown-output documents\development\trade_oracle_trading_health_report.md
```

Pass criteria:

- report generates successfully
- benchmark summary is populated
- recent cycle data is populated
- forward-journal outcome counts are populated
- MT5 broker state loads if MT5 is the active execution backend

What to inspect in the report:

- total cycles, runs, symbols, and benchmark events
- transmit attempts vs transmit successes
- broker acceptance rate
- pending-review frequency and resume conversion
- dominant recent outcomes such as `risk_rejected`, `no_trade`, or `resume_execution_result`
- current open broker exposure and unrealized PnL snapshot
- whether the system is actively trading, over-rejecting, or stuck operationally

Important interpretation rules:

- this is a trading-process health check, not yet a full profitability proof
- if closed-trade realized PnL is not present in the canonical report, say that clearly
- recent `risk_rejected` concentration can mean healthy conservatism, bad symbol fit, or mis-tuned constraints; do not overclaim
- a proven broker transmit path matters more than a high raw cycle count

### 6. Check daemon and watchdog live runtime

Commands:

```powershell
Get-Content results\local_server_watchdog_heartbeat.json
Get-Content results\trade_oracle_daemon.err.log -Tail 60
Get-Content results\trade_oracle_daemon.log -Tail 60
```

Pass criteria:

- heartbeat status is `healthy`
- `daemon_healthy` is `true`
- daemon log does not show unrecovered crash loops

Known acceptable noise:

- transient Telegram polling retries
- transient `409 Conflict` events if another poller briefly overlaps

Unacceptable:

- daemon process exiting repeatedly
- persistent Supabase probe failure
- repeated MT5 auth failures

### 7. Verify restart/logon recovery path

Commands:

```powershell
Get-Content "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\TRADE_ORACLE Local Server Watchdog.cmd"
Start-Process -FilePath powershell.exe -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File','scripts\run_local_server_watchdog.ps1','-EnvFile','.env.n8n.local','-RuntimeMode','daemon' -WorkingDirectory . -PassThru | Select-Object Id,ProcessName
Start-Sleep -Seconds 5
Get-Content results\trade_oracle_watchdog.pid
Get-Content results\local_server_watchdog_heartbeat.json
```

Pass criteria:

- Startup launcher exists
- watchdog starts
- watchdog writes its own PID file
- heartbeat becomes healthy

Interpretation:

- this proves logon-time restart behavior reasonably well
- it is not identical to a literal cold reboot, but it is the best safe in-session validation

### 8. Verify wake/sleep recovery path

Commands:

```powershell
powercfg /a
powershell -ExecutionPolicy Bypass -File scripts\install_4h_wake_cycle_task.ps1 -RuntimeMode daemon
```

Then, if allowed:

```powershell
Start-ScheduledTask -TaskName 'TRADE_ORACLE 4H Wake Cycle'
Get-ScheduledTaskInfo -TaskName 'TRADE_ORACLE 4H Wake Cycle' | Select-Object LastRunTime,NextRunTime,LastTaskResult
```

Interpretation rules:

- if the machine only supports `S0 Low Power Idle`, do not assume true continuous operation during sleep
- wake-task installation proves recovery intent, not live trading continuity during sleep
- the safest operational recommendation is still: keep the machine awake on AC power during forward testing

### 9. Verify idempotent startup behavior

Command:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File .\scripts\start_forward_testing_stack.ps1 -EnvFile .env.n8n.local -SkipWatchdog
```

Pass criteria:

- if the stack is already running, it should exit cleanly
- expected output now includes:

```text
FORWARD_TESTING_ALREADY_RUNNING=True
```

Interpretation:

- this confirms the startup lock and overlap-safe behavior are working
- important for wake tasks, watchdog restart, and manual power-on overlap

## Final verdict template

At the end of the check, produce a verdict in this exact structure:

### Repo Health

- test suite result
- major failures or none

### Live Runtime

- daemon healthy: yes/no
- watchdog healthy: yes/no
- MT5 reachable: yes/no
- Supabase reachable: yes/no
- Telegram polling healthy: yes/no

### Trading Journey

- total cycles reviewed
- broker acceptance rate
- dominant recent outcomes
- open broker exposure summary
- whether the current evidence shows:
  - operational reliability only
  - early execution proof
  - or actual live strategy-performance evidence

### Recovery Paths

- restart/logon recovery: proven / partially proven / not proven
- wake/sleep recovery: proven / partially proven / not proven

### Forward-Testing Verdict

One of:

- `GO for supervised forward testing`
- `GO with caveats`
- `NO-GO`

### Open Risks

List only the real remaining issues.

## Current reference result as of 2026-05-05

This was the observed healthy reference state when this guide was last updated:

- full tests: `95 passed, 1 xfailed, 1 warning`
- live readiness: green
- Supabase: green
- runtime-state: green
- open pending reviews: `0`
- daemon heartbeat: healthy
- daemon-first startup idempotency: verified
- watchdog PID self-registration after startup/logon launch: verified
- wake task installed in daemon mode: verified

Important nuance from the latest check:

- restart/logon recovery is in good shape
- sleep continuity is still not something to trust for trading on this laptop
- wake/recovery is better than before, but the recommended operating mode is still awake + AC power

## Common failure patterns and what they usually mean

### `ModuleNotFoundError: dotenv`

Usually means the wrong Python interpreter was used. Use:

```powershell
.\.venv-langgraph\Scripts\python.exe
```

### `Telegram getUpdates 409 Conflict`

Usually means another poller overlapped briefly. This should now be recoverable and non-fatal.

### `runtime_state_probe_failed` or `supabase_table_probe_failed`

Usually means:

- wrong interpreter
- network problem
- Supabase temporary connectivity issue
- sandbox or permission boundary, if running inside a restricted agent

### heartbeat says degraded but daemon is actually running

Usually means:

- stale PID file
- stale heartbeat
- watchdog had not yet refreshed its status

Always compare:

- live process list
- watchdog PID file
- heartbeat timestamp

## Deliverables another LLM should produce

A good full-system-check run should leave behind:

- a concise written verdict
- the exact commands used
- pass/fail results
- any noteworthy logs
- any blockers or caveats
- a current trading-health report in both JSON and Markdown form

If asked to document the process for future runs, it should also produce:

- an updated handoff note if reality changed
- an updated README if operator behavior changed
- a standalone prompt for the next LLM

## Companion prompt

Use the companion file:

- `documents/development/trade_oracle_full_system_check_prompt.md`

That prompt is designed for another LLM with zero prior context.
