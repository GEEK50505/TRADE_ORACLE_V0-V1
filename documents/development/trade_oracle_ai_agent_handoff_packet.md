# TRADE_ORACLE AI Agent Handoff Packet

Last updated: 2026-05-22

This document is written for a new AI coding agent taking over the repo mid-stream.

## What This Project Is

TRADE_ORACLE is a daemon-first crypto forward-testing system that:

- scans a watchlist
- evaluates trade setups through the TRADE_ORACLE decision pipeline
- routes approval flow through Telegram long polling
- persists runtime, benchmark, and review state
- transmits approved demo orders through MT5

The current operational emphasis is reliability and evidence collection, not aggressive new feature work.

## Current Operating Model

- primary runtime: Python daemon
- review path: Telegram long polling callbacks, no webhook dependency required for the daemon path
- primary data center: Supabase
- fallback persistence: SQLite
- primary execution target: MT5 demo
- operator model: supervised forward testing

## Read These Files First

1. [AI_CONTEXT_HANDOFF.md](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/AI_CONTEXT_HANDOFF.md)
2. [current_trade_oracle_trading_health_report.md](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/documents/development/current_trade_oracle_trading_health_report.md)
3. [README.md](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/README.md)
4. [ai/trade_oracle_daemon.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/ai/trade_oracle_daemon.py)
5. [config/settings.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/config/settings.py)
6. [scripts/start_forward_testing_stack.ps1](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/scripts/start_forward_testing_stack.ps1)
7. [scripts/check_forward_test_readiness.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/scripts/check_forward_test_readiness.py)

## Current Known State

Based on the latest local health report and repo inspection:

- the project has already achieved broker-accepted demo execution
- the active architecture is daemon-first, not n8n-first
- the repo has many local modifications and untracked artifacts
- the latest health report says the watchdog was alive while the daemon itself was down because of a stale runtime lock
- the latest health snapshot reported no open positions and no pending orders
- the latest health report also says the live LLM path should not yet be the active executor

## Dirty Worktree Warning

This repository is not clean.

Observed during handoff:

- many tracked files are modified
- many documentation files are untracked
- many result artifacts and sqlite databases are present
- there are active runtime artifacts like PID files and state files in `results/`

Working rule:

- assume local changes may matter
- do not mass-delete artifacts unless explicitly asked
- do not use reset-style cleanup
- if a change looks surprising, inspect it before touching it

## Runtime Truth Versus Doc Drift

There is historical 4H wording throughout the repo, but runtime defaults have moved.

Important detail:

- [config/settings.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/config/settings.py) currently defaults `TRADE_ORACLE_DAEMON_CYCLE_INTERVAL_SECONDS` to `3600`
- many filenames, workflow names, and old docs still say `4H`

If asked about the live daemon cadence, verify the code and env first.

## What To Verify First

1. Confirm which repo root is active.
   Use `TRADE_ORACLE/TRADE_ORACLE`, not the parent folder.
2. Check the worktree before editing.
   Inspect `git status --short`.
3. Reconfirm secrets are present without printing them.
   Check `.env.n8n.local` existence and required keys only.
4. Run the readiness check.
   Use [scripts/check_forward_test_readiness.py](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/scripts/check_forward_test_readiness.py).
5. Inspect runtime lock and daemon status before starting anything.
   Cross-check PID files with the actual process table.

## Safe Startup / Inspection Commands

Use these from the repo root `TRADE_ORACLE/TRADE_ORACLE`.

Readiness:

```powershell
python scripts\check_forward_test_readiness.py --env-file .env.n8n.local --check-supabase
```

Generate a fresh health report:

```powershell
python scripts\generate_trade_oracle_trading_health_report.py --env-file .env.n8n.local --json-output results\trade_oracle_trading_health_report.json --markdown-output documents\development\trade_oracle_trading_health_report.md
```

Poll Telegram once without launching a full cycle:

```powershell
python scripts\run_trade_oracle_daemon.py --poll-once
```

Start the forward-testing stack:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_forward_testing_stack.ps1
```

## Highest-Value Near-Term Work

- fix runtime and lock robustness
- keep daemon/watchdog/MT5 startup reliable
- keep Supabase and SQLite parity observable
- improve health reporting and operator visibility
- preserve evidence for each supervised cycle

## Things Not To Do Yet

- do not do a repo-wide refactor
- do not switch to unattended live-money trading
- do not remove SQLite fallback
- do not promote the live LLM path to active executor without shadow validation
- do not assume document labels like `4H` always reflect current runtime behavior

## Handoff Goal For The Next Agent

The next agent should behave like an operator-aware senior engineer:

- validate current runtime truth
- protect existing local work
- fix the smallest thing that restores reliability
- leave behind cleaner evidence and better docs than it found
