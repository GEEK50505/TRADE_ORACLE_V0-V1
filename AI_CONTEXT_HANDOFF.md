# TRADE_ORACLE AI Context Handoff

Last updated: 2026-04-30

This file is the canonical repo-native handoff for any new AI session. If you are a new model stepping into this codebase, read this file first, then read the referenced files in the order listed below.

## Mission

TRADE_ORACLE is a crypto swing-trading system that evolved from a scanner + risk + execution stack into a LangGraph-supervised decision engine with:

- pending-review interrupts
- Telegram-based human approval
- resume-on-same-thread execution
- benchmark/audit persistence
- a current migration away from `n8n` orchestration toward one Python runtime daemon
- a simultaneous migration toward a Supabase-backed unified data center

The practical operator setup is:

- one Windows laptop acting as the local server
- one phone acting as the Telegram operator device
- MT5 or Match-Trader as execution backend
- minimal cloud dependency

## Development Story So Far

The most important architectural decisions that came out of the prior development process are:

1. `n8n` was useful for proving the orchestration flow fast.
2. The `n8n` Telegram callback path worked, but public webhook/tunnel fragility made it a poor long-term fit for one-laptop deployment.
3. The repo now prefers a single Python runtime daemon that uses Telegram long polling instead of webhooks.
4. SQLite remains the safe local fallback, but the target direction is to unify audit, benchmark, pending-review state, and forward-journal state behind Supabase-capable storage.
5. The user wants the final system to behave like one platform and one data center, not a split between workflow tables and Python runtime state.

## Current Architecture State

### Already Working

- LangGraph evaluation and resume flow
- benchmark trail
- audit trail
- pending-review state model
- forward-test journal model
- Telegram polling client inside the daemon
- daemon-side cycle execution + resume execution logic

### Fallback / Legacy

- `n8n` workflows still exist and were previously validated end-to-end
- they should now be treated as fallback/reference, not the desired final orchestrator

## Canonical Files To Read

Read these in this order:

1. [AI_CONTEXT_HANDOFF.md](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/AI_CONTEXT_HANDOFF.md)
2. [README.md](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/README.md)
3. [trade_oracle_daemon.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/ai/trade_oracle_daemon.py)
4. [trade_oracle_runtime_state.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/ai/trade_oracle_runtime_state.py)
5. [trade_oracle_storage.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/ai/trade_oracle_storage.py)
6. [trade_oracle_supabase_storage.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/ai/trade_oracle_supabase_storage.py)
7. [supabase_client.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/journal/supabase_client.py)
8. [settings.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/config/settings.py)
9. [run_trade_oracle_daemon.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/scripts/run_trade_oracle_daemon.py)
10. [start_trade_oracle_daemon.ps1](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/scripts/start_trade_oracle_daemon.ps1)
11. [stop_trade_oracle_daemon.ps1](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/scripts/stop_trade_oracle_daemon.ps1)

## Current Single-Runtime Status

The daemon already exists in [trade_oracle_daemon.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/ai/trade_oracle_daemon.py).

Important daemon entry points:

- `run_cycle_once` at [trade_oracle_daemon.py:496](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/ai/trade_oracle_daemon.py#L496)
- `process_callback_query` at [trade_oracle_daemon.py:840](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/ai/trade_oracle_daemon.py#L840)
- `run_forever` at [trade_oracle_daemon.py:919](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/ai/trade_oracle_daemon.py#L919)
- `build_default_trade_oracle_daemon` at [trade_oracle_daemon.py:935](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/ai/trade_oracle_daemon.py#L935)

Operationally, the daemon is intended to replace:

- n8n schedule trigger
- n8n Telegram review webhook
- n8n pending-review table
- n8n forward-journal table

## Current Unified Data-Center Status

### Done

- Audit store supports `sqlite|supabase`
- Benchmark store supports `sqlite|supabase`
- Runtime-state store now supports `sqlite|supabase`
  - pending reviews
  - forward journal
  - daemon checkpoints, including Telegram polling cursor

Relevant files:

- [trade_oracle_supabase_storage.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/ai/trade_oracle_supabase_storage.py)
- [trade_oracle_runtime_state.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/ai/trade_oracle_runtime_state.py)
- [trade_oracle_storage.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/ai/trade_oracle_storage.py)

### Not Done Yet

- proof that Supabase-only runtime state can recover after restart with no n8n dependency
- full supervised parity run between SQLite and Supabase backends over multiple real cycles

## Important Settings

Read these in [settings.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/config/settings.py):

- benchmark backend:
  - `TRADE_ORACLE_BENCHMARK_BACKEND`
- runtime state backend:
  - `TRADE_ORACLE_RUNTIME_STATE_BACKEND`
  - `TRADE_ORACLE_RUNTIME_STATE_DB_PATH`
- Supabase tables:
  - `TRADE_ORACLE_SUPABASE_AUDIT_TABLE`
  - `TRADE_ORACLE_SUPABASE_BENCHMARK_TABLE`
  - `TRADE_ORACLE_SUPABASE_PENDING_REVIEW_TABLE`
  - `TRADE_ORACLE_SUPABASE_FORWARD_JOURNAL_TABLE`
  - `TRADE_ORACLE_SUPABASE_DAEMON_CHECKPOINT_TABLE`
- Telegram daemon settings:
  - `TRADE_ORACLE_TELEGRAM_BOT_TOKEN`
  - `TRADE_ORACLE_TELEGRAM_CHAT_ID`
  - `TRADE_ORACLE_DAEMON_CYCLE_INTERVAL_SECONDS`
  - `TRADE_ORACLE_DAEMON_TELEGRAM_POLL_TIMEOUT_SECONDS`
  - `TRADE_ORACLE_DAEMON_IDLE_SLEEP_SECONDS`
  - `TRADE_ORACLE_DAEMON_START_IMMEDIATELY`
  - `TRADE_ORACLE_DAEMON_SEND_CYCLE_SUMMARY`

## Current Local Operating Model

Right now the user is operating from one Windows PC and wants the PC to act like the server.

Practical implications:

- avoid solutions that require stable paid cloud infrastructure
- prefer long polling over public webhook tunnels
- keep local fallbacks available
- keep the phone as the approval surface, not the compute host
- treat MT5/Windows execution realities honestly

## Test State

The most recent important validation state before this handoff:

- runtime-state + storage tests passed
- platform / super-brain / ops service tests passed
- earlier development also validated the n8n review/resume loop end-to-end

The exact counts are less important than the current invariant:

- storage seam is working
- daemon exists
- daemon-first watchdog startup exists
- next risk is Supabase restart/parity proof, not missing core architecture

## Recommended Next Steps

These are the next highest-value steps in order:

1. Prove Supabase-only daemon recovery after restart.
   The Telegram polling cursor now persists through the runtime-state backend; the remaining proof is a real restart run against Supabase.
2. Add more targeted daemon tests.
   Focus on:
   - pending-review handoff
   - callback resume
   - restart reconstruction from runtime-state store
3. Run the daemon in supervised `--once` / `--poll-once` modes first.
4. Switch runtime-state backend to Supabase during parity testing.
5. Only after parity and restart recovery are solid, retire n8n from active orchestration.

## What Not To Do

- Do not re-expand n8n unless there is a strong short-term reason.
- Do not rely on Telegram webhooks if long polling can solve the same problem.
- Do not assume cloud infrastructure is available.
- Do not silently remove SQLite fallback until Supabase parity is proven.

## Best Resume Prompt Pattern

When starting a new AI thread, do not try to restate the whole history manually. Point the new model at this file and give it one concrete next objective.

Use the starter prompt in the next section.

## Starter Prompt For A New AI Thread

Copy this into the next chat:

```text
We are continuing work on the TRADE_ORACLE repo.

First, read these files in order:
1. AI_CONTEXT_HANDOFF.md
2. README.md
3. ai/trade_oracle_daemon.py
4. ai/trade_oracle_runtime_state.py
5. ai/trade_oracle_storage.py
6. ai/trade_oracle_supabase_storage.py
7. journal/supabase_client.py
8. config/settings.py

Current direction:
- move fully toward one Python runtime daemon instead of n8n orchestration
- keep Supabase as the target unified data center
- keep SQLite fallback until parity is proven
- use Telegram long polling, not webhook tunnels, for the main production path

Current known status:
- audit, benchmark, pending-review state, forward-journal state, and daemon checkpoint state are backend-selectable
- the daemon already exists
- local-server automation now defaults to daemon startup, with n8n retained as an explicit fallback mode
- the next major gap is proving Supabase restart recovery and supervised parity over real cycles

Please inspect the current daemon implementation, summarize the exact remaining gaps, then implement the next highest-value production-hardening step without asking me to repeat repo history.
```
