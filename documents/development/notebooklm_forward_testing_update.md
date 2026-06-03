# TRADE_ORACLE Forward Testing Update

Updated: 2026-05-02

This document is a compact narrative update for tools such as NotebookLM. The canonical technical source of truth is:

- `AI_CONTEXT_HANDOFF.md`
- `documents/development/trade_oracle_system_handbook.md`
- `documents/development/trade_oracle_final_pipeline_readiness_report.md`

## Current State

TRADE_ORACLE has completed the daemon-first cutover for supervised demo forward testing.

The active architecture is:

- one Python daemon as the main runtime
- Telegram long polling for human approval
- Supabase as the active unified data center
- SQLite retained as fallback until repeated parity is proven
- n8n retained as fallback/reference only
- MT5 demo execution as the current broker path
- VS Code one-click power-on/power-off tasks for local operation

## What Has Been Proven

- Supabase schema bootstrap through the session pooler.
- Supabase table reachability for the operational tables.
- SQLite runtime-state migration into Supabase.
- Supabase restart recovery for daemon checkpoint state.
- Telegram bot auth, outbound messaging, callback polling, and stale callback handling.
- MT5 demo auth, account-state read, symbol mapping, and live tick inspection.
- Full daemon-path `SOL/USDT` simulated cycle with Telegram review and MT5 broker acceptance.
- One-click operator stack startup with healthy watchdog heartbeat.
- Automated test suite: `91 passed, 1 xfailed, 1 warning`.

## Current Forward-Test Boundary

GO:

- supervised demo forward testing
- human Telegram approval
- daemon-first runtime
- Supabase-backed state
- MT5 demo execution
- operational reliability testing for up to two weeks

NO-GO:

- unattended live-money trading
- auto-approval for real forward testing
- removing SQLite fallback
- scaling position size
- claiming strategy profitability
- repo-wide refactor before the reliability window produces evidence

## Current Runtime Detail

The forward-testing stack has started successfully. A pending `TON/USDT` review may be open. That is not a startup blocker, but it intentionally prevents brand-new cycles until the human operator approves, rejects, or resolves the review.

## Two-Week Reliability Focus

The next phase should answer operational questions:

- Does the daemon stay alive?
- Does the watchdog accurately report daemon health?
- Does Supabase remain reachable and consistent?
- Does Telegram review work repeatedly?
- Are stale callbacks ignored safely?
- Are pending reviews preserved across restart?
- Are duplicate orders prevented?
- Are broker outcomes recorded in Supabase benchmark and forward journal?

Profitability is not proven by this phase. The two-week demo is about operational reliability. Strategy edge needs a longer and cleaner sample.

## Refactor Recommendation

Do not do a repo-wide refactor now. Continue forward testing with only small safety and diagnostic fixes.

After the reliability window, consider bounded refactors:

- typed config validation
- daemon decomposition
- LangGraph file decomposition
- script folder organization
- results artifact hygiene
- daily forward-test report generator
- CI and release tagging
