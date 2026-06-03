# TRADE_ORACLE Final Pipeline Readiness Report

Generated: 2026-05-02

## Verdict

TRADE_ORACLE is ready for supervised demo forward testing focused on operational reliability.

It is not yet proven profitable, and it is not approved for unattended live-money operation. The next phase should be a short, disciplined reliability window of up to two weeks.

## Current Production Direction

- one Python daemon is the main runtime path
- Telegram uses long polling, not webhooks
- Supabase is the active unified data center
- SQLite fallback remains until parity is proven
- n8n is fallback/reference only
- MT5 demo is the current execution backend
- VS Code now provides one-click power-on/power-off operator tasks

## Latest Automated Test Result

Command:

```powershell
python -m pytest -p no:cacheprovider
```

Result:

```text
91 passed, 1 xfailed, 1 warning
```

Coverage includes:

- data pipeline
- inference parsing
- LangGraph graph and orchestrator
- daemon cycle and Telegram callback behavior
- daemon CLI
- runtime-state storage
- audit and benchmark storage
- Supabase-selectable storage factories
- MT5 bridge
- Match-Trader bridge
- FastAPI platform, brain, ops, MCP, and super-brain services
- forward-test readiness reporting

## Live Bring-Up Result

The local forward-testing stack was started successfully using:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_forward_testing_stack.ps1
```

The VS Code task `TRADE_ORACLE: Power On Forward Testing` calls the same path.

Startup path validated:

- MT5 terminal launch/reuse
- live Supabase readiness probe
- MT5 preflight
- daemon `--poll-once` sanity check
- long-running daemon startup
- watchdog startup
- status file generation

Current status files:

- `results/forward_testing_stack_status.json`
- `results/local_server_watchdog_heartbeat.json`
- `results/forward_testing_mt5_preflight.json`

Latest heartbeat status:

```text
status=healthy
daemon_healthy=True
runtime_mode=daemon
```

## Current Readiness State

The active readiness report shows:

- required Telegram env present
- required Supabase env present
- required MT5 env present
- audit backend: Supabase
- benchmark backend: Supabase
- runtime-state backend: Supabase
- Supabase tables reachable
- Telegram update-offset checkpoint present
- startup blockers: none
- forward-testing startup ready: true

One open `TON/USDT` pending review may be present. That is not a startup blocker, but it intentionally blocks brand-new cycles until the human operator approves, rejects, or resolves it.

## MT5 Demo Preflight

Latest MT5 preflight confirms:

- execution backend: `mt5`
- server: `FTMO-Demo`
- terminal path configured
- authentication succeeds
- account state can be read
- high-watermark source is Supabase
- drawdown buffer is healthy enough for demo operation
- `SOL/USDT` resolves to `SOLUSD`
- live bid/ask ticks are present
- account can open a new trade under current risk state

Earlier broader preflight also validated:

- `AVAX/USDT`
- `DOGE/USDT`
- `BTC/USDT`
- `ETH/USDT`
- `SOL/USDT`
- `XRP/USDT`

## Broker-Accepted Demo Proof

A full daemon-path `SOL/USDT` simulated cycle reached broker acceptance on MT5 demo:

- scanner setup injected
- Super Brain produced pending review
- Telegram review message sent
- review resumed with `APPROVE`
- risk recheck passed
- MT5 accepted a pending `BUY_STOP` on `SOLUSD`
- Supabase persisted resolved review and forward journal
- benchmark recorded transmitted order result

This proves the mechanical path from daemon to broker. It does not prove strategy profitability.

## Fixes Completed During Final Bring-Up

Operator layer:

- added one-click startup script
- added one-click stop script
- added VS Code power-on/power-off tasks
- integrated MT5 startup
- integrated readiness, MT5 preflight, daemon poll sanity, daemon runtime, and watchdog

Reliability:

- fixed PowerShell PID handling bug caused by case-insensitive `$pid` collision with built-in `$PID`
- tightened readiness checker so runtime-state and Supabase failures block startup
- allowed startup when the only issue is an open pending review
- hardened Telegram stale callback-answer handling
- kept duplicate MT5 order protection active
- kept SQLite fallback intact

Documentation:

- rebuilt system handbook from scratch
- updated README
- updated AI handoff
- refreshed this readiness report

## Go/No-Go Matrix

| Area | Status | Notes |
| --- | --- | --- |
| Python daemon runtime | GO | Main path |
| Telegram long polling | GO | Webhooks not required |
| Supabase active state | GO | Tables reachable |
| SQLite fallback | KEEP | Do not remove yet |
| MT5 demo execution | GO | Broker acceptance proven |
| n8n | FALLBACK | Reference only |
| one-click operator start | GO | VS Code task available |
| supervised demo forward testing | GO | Start/continue now |
| unattended real-money trading | NO-GO | Not enough evidence |
| repo-wide refactor | WAIT | Use forward-test evidence first |
| profitability claim | NO-GO | Needs forward performance data |

## Recommended Two-Week Reliability Window

Use the next two weeks or less to answer operational questions:

- Does the daemon stay alive?
- Does the watchdog report accurately?
- Does Supabase remain the active source of truth?
- Does Telegram review work repeatedly?
- Are old callbacks safely ignored?
- Are pending reviews never lost?
- Are duplicate orders prevented?
- Are broker outcomes recorded in benchmark and forward journal?
- Can the system recover after stop/start without dangerous replay?

Success criteria:

- no unapproved trade is transmitted
- no duplicate order is sent
- no review is lost
- no restart causes an accidental execution
- every broker action has a matching Supabase trail
- every operator decision is visible in Telegram/runtime state

Pause criteria:

- unapproved order
- duplicate order
- missing review state
- unclear circuit-breaker behavior
- Supabase/runtime-state mismatch
- MT5 account state cannot be trusted

## Recommended Next Actions

1. Resolve or decide the current `TON/USDT` pending review in Telegram.
2. Keep the daemon stack running under the watchdog.
3. Use human approval only during demo forward testing.
4. Pull a daily report from Supabase, benchmark events, daemon logs, Telegram behavior, and MT5 state.
5. Do not run a repo-wide refactor until the reliability window produces evidence.
6. After the window, perform a bounded cleanup around config validation, daemon decomposition, results hygiene, and reporting.

## Main Commands

Power on:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_forward_testing_stack.ps1
```

Power off:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop_forward_testing_stack.ps1
```

Readiness:

```powershell
python scripts\check_forward_test_readiness.py --env-file .env.n8n.local --check-supabase
```

Poll once:

```powershell
python scripts\run_trade_oracle_daemon.py --poll-once
```

Run one supervised cycle:

```powershell
python scripts\run_trade_oracle_daemon.py --once
```

Resolve stale review:

```powershell
python scripts\resolve_pending_review.py --env-file .env.n8n.local --thread-id <thread_id> --backend both
```

## Final Note

The system is ready to test reliability. That is a big milestone. The next job is not to make the code more impressive. The next job is to let the system operate under supervision and collect clean evidence.
