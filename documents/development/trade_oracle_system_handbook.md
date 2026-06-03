# TRADE_ORACLE System Handbook

Generated: 2026-05-02

This is the canonical technical and operating handbook for TRADE_ORACLE. It was rewritten from scratch after the daemon-first forward-testing bring-up so a senior developer, operator, or new AI assistant can understand the whole system without piecing together older phase documents.

No secrets are included here. Environment files, Supabase keys, Telegram bot tokens, broker passwords, and MT5 credentials must stay out of documentation and source control.

## 1. Executive Verdict

TRADE_ORACLE has made real progress. It is no longer just a scanner, a backtest collection, or a notebook-style experiment. It is now a local-first trading platform with:

- a single Python daemon as the primary runtime
- Telegram long polling for human approval
- Supabase as the active unified data center
- SQLite retained as a fallback
- MT5 demo execution proven through broker acceptance
- n8n retained only as fallback/reference
- VS Code one-click operator controls
- automated tests covering the core runtime, storage, services, and execution adapters

The system is ready for supervised demo forward testing focused on operational reliability.

It is not yet proven as a profit engine. Operational readiness and trading edge are different questions. The system can now answer the operational question during forward testing. The profitability question requires live-style sample size, clean benchmark records, slippage/spread tracking, invalidation analysis, and repeated trade outcomes.

## 2. Money And Refactor Judgment

### 2.1 Can this make serious money?

It has a chance, but not because it uses AI, Supabase, LangGraph, Telegram, or MT5. Those make it operable. Money comes from:

- durable strategy edge
- strict risk discipline
- execution quality
- avoiding overtrading
- surviving bad regimes
- collecting enough clean forward-test evidence to improve the system
- keeping emotional and automation risk under control

The codebase is now strong enough to test the machine. It is not yet strong enough to claim the machine has an edge. That is normal. This is exactly what forward testing is for.

My honest view:

- **Engineering progress:** strong
- **Operational readiness:** good enough for supervised demo forward testing
- **Profitability proof:** not yet established
- **Three-year potential:** meaningful if you keep the same pace, keep risk tiny, measure everything, and improve from evidence instead of hype
- **Chance of "a lot of money":** possible, but not forecastable from the code alone

Crypto and leveraged trading remain high risk. The CFTC warns that virtual currency markets can be volatile, cash markets can lack safeguards, and leverage can amplify losses. The CFTC also warns that no trading strategy is guaranteed. Use that as a grounding principle, not as a reason to quit.

### 2.2 Should we do a repo-wide refactor now?

No. Not before the first operational reliability window.

The better move is:

1. Freeze major architecture changes.
2. Run the 1 to 2 week supervised demo forward test.
3. Record every failure, hesitation, rejected trade, broker mismatch, Telegram issue, Supabase issue, and operator action.
4. Refactor after the reliability data tells us where the real friction is.

A repo-wide refactor right now would feel productive, but it would reset the validation surface just as the system became testable. The right refactor is not "clean everything." The right refactor is "tighten the parts proven noisy by forward testing."

Recommended refactor timing:

- **Now:** only small safety fixes, documentation, diagnostics, and operator ergonomics.
- **After the 2 week demo window:** bounded refactor around configuration validation, script organization, result artifact hygiene, daemon modularization, and reporting.
- **After repeated profitable or at least stable cycles:** production-grade packaging, CI, release tagging, migrations, and deployment hardening.

## 3. Current Operating State

Current state as of the latest validated bring-up:

- Forward-testing stack has started from the VS Code one-click path.
- MT5 terminal is running.
- Python daemon is running.
- Watchdog is running.
- Watchdog heartbeat is healthy.
- Supabase runtime state is reachable.
- Telegram long polling is the active approval path.
- n8n is not the main runtime path.
- One pending `TON/USDT` review is currently open in Supabase runtime state.

The open review is not a startup blocker. It is a fresh-cycle blocker. That means the daemon can run and poll Telegram, but it should not start a new cycle until the pending human review is approved, rejected, or intentionally resolved.

Latest local automated suite:

```text
91 passed, 1 xfailed, 1 warning
```

Latest operator status files:

- `results/forward_testing_stack_status.json`
- `results/local_server_watchdog_heartbeat.json`
- `results/forward_testing_mt5_preflight.json`
- `results/trade_oracle_daemon.log`
- `results/trade_oracle_daemon.err.log`

## 4. System In One Page

TRADE_ORACLE is a crypto swing-trading platform. It scans a watchlist, builds setup payloads, sends them through a LangGraph decision graph, applies hard risk controls, asks the human operator for approval over Telegram when needed, and transmits approved orders to an execution backend.

The current production-intent path is:

```text
VS Code Power On
  -> start_forward_testing_stack.ps1
  -> MT5 terminal
  -> readiness check
  -> MT5 preflight
  -> daemon poll-once sanity check
  -> long-running Python daemon
  -> watchdog

Python daemon
  -> scanner
  -> LangGraph Super Brain
  -> risk guardrails
  -> pending review in Supabase
  -> Telegram review message
  -> Telegram long polling callback
  -> resume same LangGraph thread
  -> risk recheck
  -> MT5 demo execution
  -> Supabase audit, benchmark, runtime state, forward journal
```

The governing principle is simple: the daemon owns runtime orchestration, Supabase owns active shared state, SQLite stays as fallback, Telegram is the approval surface, and MT5 is the current demo execution backend.

## 5. Full Project Structure Diagram

This diagram shows the practical structure of the repo. It intentionally focuses on source, contracts, scripts, and docs. Generated SQLite files, market data chunks, and backtest result files live mostly under `results/` and should be treated as artifacts, not core source.

```text
TRADE_ORACLE/
|-- AI_CONTEXT_HANDOFF.md
|-- README.md
|-- pytest.ini
|-- conftest.py
|-- requirements.txt
|-- requirements.trading.txt
|-- requirements.langgraph.txt
|-- requirements.optimization.txt
|-- Dockerfile.langgraph
|-- docker-compose.n8n.local.yml
|-- docker-compose.n8n.production.yml
|
|-- ai/
|   |-- trade_oracle_daemon.py
|   |-- langgraph_orchestrator.py
|   |-- trade_oracle_langgraph_phase1.py
|   |-- trade_oracle_audit.py
|   |-- trade_oracle_benchmark.py
|   |-- trade_oracle_storage.py
|   |-- trade_oracle_runtime_state.py
|   |-- trade_oracle_supabase.py
|   |-- trade_oracle_supabase_storage.py
|   |-- inference.py
|
|-- api/
|   |-- trade_oracle_platform_service.py
|   |-- trade_oracle_super_brain_service.py
|   |-- trade_oracle_brain_service.py
|   |-- trade_oracle_ops_service.py
|   |-- trade_oracle_mcp_service.py
|
|-- config/
|   |-- settings.py
|
|-- data/
|   |-- scanner.py
|   |-- data_pipeline.py
|   |-- market_data_*.parquet
|
|-- risk/
|   |-- manager.py
|
|-- execution/
|   |-- runtime.py
|   |-- mt5_bridge.py
|   |-- match_trader.py
|   |-- test_maven_connection.py
|
|-- journal/
|   |-- supabase_client.py
|   |-- trade_oracle_forward_test_review_template.md
|
|-- scripts/
|   |-- start_forward_testing_stack.ps1
|   |-- stop_forward_testing_stack.ps1
|   |-- start_trade_oracle_daemon.ps1
|   |-- stop_trade_oracle_daemon.ps1
|   |-- run_trade_oracle_daemon.py
|   |-- run_local_server_watchdog.ps1
|   |-- check_forward_test_readiness.py
|   |-- validate_mt5_demo_profile.py
|   |-- simulate_full_pipeline.py
|   |-- resolve_pending_review.py
|   |-- bootstrap_supabase_schema.py
|   |-- migrate_sqlite_state_to_supabase.py
|   |-- trade_oracle_supabase_schema.sql
|   |-- start_windows365_phone_stack.ps1
|   |-- stop_windows365_phone_stack.ps1
|   |-- install_local_server_automation.ps1
|   |-- install_4h_wake_cycle_task.ps1
|   |-- backtrader_*.py
|   |-- vectorbt_*.py
|   |-- build_*_shortlist.py
|   |-- fetch_*.py
|   |-- check_*.py
|
|-- contracts/
|   |-- trade_oracle_n8n_workflow_contract.json
|   |-- n8n_4h_master_orchestrator_platform.workflow.json
|   |-- n8n_4h_master_orchestrator_platform.telegram.workflow.json
|   |-- n8n_4h_master_orchestrator_platform.manual_validation.workflow.json
|   |-- n8n_telegram_review_webhook.workflow.json
|   |-- n8n_openclaw_review_resume.manual_validation.workflow.json
|
|-- tests/
|   |-- test_trade_oracle_daemon.py
|   |-- test_trade_oracle_daemon_cli.py
|   |-- test_forward_test_readiness_cli.py
|   |-- test_forward_test_readiness_report.py
|   |-- test_mt5_bridge.py
|   |-- test_execution_runtime.py
|   |-- test_trade_oracle_runtime_state.py
|   |-- test_trade_oracle_storage.py
|   |-- test_trade_oracle_audit.py
|   |-- test_trade_oracle_benchmark.py
|   |-- test_trade_oracle_platform_service.py
|   |-- test_trade_oracle_ops_service.py
|   |-- test_trade_oracle_mcp_service.py
|   |-- test_trade_oracle_super_brain_service.py
|   |-- test_trade_oracle_brain_service.py
|   |-- test_langgraph_orchestrator.py
|   |-- test_trade_oracle_langgraph_phase1.py
|   |-- test_data_pipeline.py
|   |-- test_inference.py
|   |-- test_inference_deepseek.py
|   |-- test_match_trader.py
|   |-- test_db.py
|
|-- documents/
|   |-- development/
|   |   |-- trade_oracle_system_handbook.md
|   |   |-- trade_oracle_final_pipeline_readiness_report.md
|   |   |-- notebooklm_forward_testing_update.md
|   |   |-- historical phase and architecture documents
|   |-- runbooks and historical notes
|
|-- results/
|   |-- forward_testing_stack_status.json
|   |-- forward_testing_mt5_preflight.json
|   |-- local_server_watchdog_heartbeat.json
|   |-- trade_oracle_daemon.log
|   |-- trade_oracle_daemon.err.log
|   |-- trade_oracle_audit.sqlite
|   |-- trade_oracle_benchmark.sqlite
|   |-- trade_oracle_runtime_state.sqlite
|   |-- backtest reports, optimization CSVs, generated test DBs
|
|-- .vscode/
|   |-- tasks.json
|   |-- settings.json
```

## 6. Component Inventory

### 6.1 Root Files

`README.md`

Main user-facing repo entrypoint. It contains setup commands, daemon commands, FastAPI service commands, n8n fallback notes, Supabase migration notes, and the current operator path.

`AI_CONTEXT_HANDOFF.md`

Canonical handoff for a new AI or developer session. It should stay short enough to read quickly but complete enough to prevent history loss.

`pytest.ini`

Limits test discovery to `tests/` so generated artifacts do not become accidental test inputs.

`conftest.py` and `tests/conftest.py`

Test configuration and path bootstrapping.

`requirements*.txt`

Separate dependency tracks exist because the trading stack, LangGraph stack, and optimization stack do not all want the same versions.

`Dockerfile.langgraph`

Container surface for the FastAPI/LangGraph deployment path.

`docker-compose.n8n.*.yml`

Legacy/fallback n8n deployment configurations.

### 6.2 `config/`

`config/settings.py`

Central configuration module. It reads env vars and sets system defaults.

Important categories:

- watchlist and strategy parameters
- risk constants
- MCP and provider settings
- audit/benchmark/runtime-state storage backends
- Supabase table names
- Telegram daemon settings
- Match-Trader credentials
- MT5 credentials and symbol mapping
- live take-profit policy

The current key defaults are conservative: MT5 is the preferred execution backend, risk per trade is fixed at `$10`, max concurrent trades is `4`, and SQLite remains a fallback even while Supabase is active.

### 6.3 `data/`

`data/scanner.py`

Market scanner. It uses `ccxt` to fetch OHLCV data and pandas to compute baseline indicators:

- EMA 20
- SMA 50
- ATR 14
- Fibonacci proximity
- setup quality
- narrative tags
- structural regime

It produces payloads consumed by the LangGraph bridge. It also contains a Windows DNS resolver patch for `aiohttp`/`aiodns` reliability.

`data/data_pipeline.py`

Historical data and indicator support used by tests and research workflows.

`data/market_data_*.parquet`

Local cached market datasets. These are artifacts used by research/backtesting, not runtime source code.

### 6.4 `risk/`

`risk/manager.py`

Hard risk gatekeeper.

Rules currently enforced:

- hard 2.5 percent drawdown circuit breaker
- 3.0 percent trailing drawdown trade gate
- `$15` warning/failure buffer
- max `4` concurrent trades
- fixed `$10` risk per trade
- max 1:2 crypto leverage
- ATR-based stop loss and take-profit sizing

The circuit breaker is intentionally hardcoded and non-overridable by environment variables. That is good. Risk rules should be harder to accidentally weaken than ordinary configuration.

### 6.5 `execution/`

`execution/runtime.py`

Factory layer that chooses `mt5` or `match_trader` from config or explicit arguments. It keeps services and daemon code from knowing how to instantiate each backend.

`execution/mt5_bridge.py`

Async wrapper around the synchronous MetaTrader5 package. It:

- initializes/attaches to the MT5 terminal
- authenticates or attaches to the active session
- resolves symbols through `MT5_SYMBOL_MAP`
- fetches account equity and active positions
- validates symbol availability and ticks
- converts strategy units to broker volume
- validates entry, stop, target geometry
- chooses market, stop, or limit order shape from live bid/ask
- prevents duplicate pending orders when a matching order already exists
- transmits orders to the MT5 demo terminal

This is currently the most important execution adapter.

`execution/match_trader.py`

Asynchronous REST bridge for the Match-Trader path. It remains useful but is not the current primary execution path.

`execution/test_maven_connection.py`

Legacy connectivity/probing helper.

### 6.6 `ai/`

`ai/trade_oracle_daemon.py`

Primary runtime orchestrator. This file is the current heart of forward testing.

Responsibilities:

- load Telegram cursor from runtime-state checkpoint
- run scanner cycles
- hydrate account state
- enforce circuit breaker before evaluation
- send scanner rows to LangGraph orchestrator
- persist pending reviews
- send Telegram review messages
- poll Telegram callback buttons through long polling
- resume LangGraph thread after approval/rejection
- recheck risk before execution
- transmit approved orders
- write forward journal and benchmark events
- send cycle summaries
- halt on circuit breaker

Important behavior:

- if open reviews exist, new cycles are skipped
- already resolved callbacks are ignored instead of re-executed
- stale Telegram `answerCallbackQuery` 400 responses are ignored
- Telegram update offsets are persisted so restart replay risk is reduced

`ai/langgraph_orchestrator.py`

Bridge from scanner payloads into the LangGraph graph. It normalizes scanner rows, starts graph threads, detects pending review interrupts, resumes human review, and extracts execution candidates.

`ai/trade_oracle_langgraph_phase1.py`

The graph definition and specialist model. It includes:

- raw setup schemas
- account state schemas
- intent router
- macro liquidity analyst
- fundamental narrative specialist
- tokenomics auditor
- technical confluence validator
- devil's advocate
- final Pydantic gatekeeper
- human interrupt/resume payload
- deterministic fallback logic
- MCP tool stub integration

This file is powerful but large. It is a prime future refactor target, but not before the forward-test reliability window.

`ai/trade_oracle_audit.py`

SQLite audit event store. It records general operational and graph events.

`ai/trade_oracle_benchmark.py`

SQLite benchmark event store. It records cycle events, decisions, risk checks, and transmit outcomes.

`ai/trade_oracle_storage.py`

Storage factory and protocol layer. It lets the system choose `sqlite` or `supabase` for audit, benchmark, and runtime-state stores.

`ai/trade_oracle_runtime_state.py`

Runtime-state models and store implementations for:

- pending reviews
- forward journal entries
- daemon checkpoints

It contains SQLite logic and the Supabase runtime-state adapter.

`ai/trade_oracle_supabase.py`

Shared Supabase client helpers, including a compatibility patch for gotrue proxy args and retry wrapping for transient transport failures.

`ai/trade_oracle_supabase_storage.py`

Supabase audit and benchmark store implementations.

`ai/inference.py`

Older inference helper. Tests still cover response parsing, but the daemon-first runtime mainly routes through the LangGraph stack.

### 6.7 `api/`

The API layer exists for service decomposition, local testing, n8n compatibility, and possible container deployment.

`api/trade_oracle_platform_service.py`

Single FastAPI deployment surface that mounts the Super Brain, brain, ops, and MCP services. It also exposes system health, audit, benchmark, and capability routes.

`api/trade_oracle_super_brain_service.py`

Top-level Super Brain run-once service.

`api/trade_oracle_brain_service.py`

n8n-compatible LangGraph brain service for evaluate/resume behavior.

`api/trade_oracle_ops_service.py`

Operational service for scanner, account state, risk evaluation, symbol status, and execution calls.

`api/trade_oracle_mcp_service.py`

MCP-style provider/tool boundary for macro, fundamental, tokenomics, technical, and risk guardrail snapshots.

### 6.8 `journal/`

`journal/supabase_client.py`

State manager for high-watermark persistence in Supabase.

`journal/trade_oracle_forward_test_review_template.md`

Human review template for forward testing.

### 6.9 `scripts/`

Operational scripts:

- `start_forward_testing_stack.ps1`: one-click forward-testing power-on path
- `stop_forward_testing_stack.ps1`: stop daemon/watchdog, optionally MT5
- `start_trade_oracle_daemon.ps1`: starts daemon in background
- `stop_trade_oracle_daemon.ps1`: stops daemon by PID file
- `run_trade_oracle_daemon.py`: daemon CLI
- `run_local_server_watchdog.ps1`: health loop and auto-restart helper
- `check_forward_test_readiness.py`: secret-safe readiness report
- `validate_mt5_demo_profile.py`: safe MT5 account/symbol probe
- `simulate_full_pipeline.py`: supervised demo simulator that can exercise the daemon path
- `resolve_pending_review.py`: resolves stale reviews in SQLite/Supabase/both
- `bootstrap_supabase_schema.py`: creates Supabase tables over Postgres connection
- `migrate_sqlite_state_to_supabase.py`: migrates local runtime state to Supabase
- `trade_oracle_supabase_schema.sql`: schema source for Supabase tables

Fallback/local server scripts:

- `start_windows365_phone_stack.ps1`
- `stop_windows365_phone_stack.ps1`
- `setup_cloudflare_named_tunnel.ps1`
- `install_local_server_automation.ps1`
- `install_4h_wake_cycle_task.ps1`

Research scripts:

- `backtrader_*.py`
- `vectorbt_*.py`
- `build_*_shortlist.py`
- `fetch_data.py`
- `fetch_watchlist.py`
- `analyze_*`
- `prepare_backtrader_shortlist.py`

Diagnostics:

- `check_telegram_daemon_path.py`
- `test_live_telegram_review_flow.py`
- `check_parquet.py`
- `check_market_parquets.py`
- `validate_daemon_restart_recovery.py`
- `prove_daemon_restart_recovery.py`

### 6.10 `contracts/`

Contracts preserve the n8n-era workflows and webhook schemas.

These are no longer the main production path, but they are valuable for:

- reference behavior
- fallback testing
- comparing old orchestration to daemon orchestration
- future migration notes

### 6.11 `tests/`

The test suite covers:

- scanner/data pipeline
- risk and execution runtime
- MT5 bridge behavior
- Match-Trader bridge behavior
- audit storage
- benchmark storage
- runtime-state storage
- Supabase-selectable storage factories
- daemon cycle behavior
- Telegram callback replay/cursor behavior
- daemon CLI
- readiness checker
- FastAPI platform/ops/MCP/brain/super-brain routes
- LangGraph graph and orchestrator behavior
- inference response parsing

Current result:

```text
91 passed, 1 xfailed, 1 warning
```

The xfail is a legacy execution test. The warning is a pandas frequency deprecation in a data pipeline test.

### 6.12 `documents/`

This folder contains both canonical current docs and historical phase docs.

Canonical current docs:

- `AI_CONTEXT_HANDOFF.md`
- `README.md`
- `documents/development/trade_oracle_system_handbook.md`
- `documents/development/trade_oracle_final_pipeline_readiness_report.md`
- `documents/development/notebooklm_forward_testing_update.md`

Historical docs should be treated as context, not current truth, unless they agree with the canonical docs.

### 6.13 `results/`

Generated artifacts:

- daemon logs
- status files
- preflight reports
- SQLite audit/benchmark/runtime-state DBs
- generated test DBs
- backtesting reports
- optimization CSVs
- market data chunks

Do not treat this folder as clean source. It is operational evidence and generated state.

## 7. Runtime Architecture

### 7.1 Primary Daemon Path

The daemon is built by `build_default_trade_oracle_daemon()` in `ai/trade_oracle_daemon.py`.

Default dependencies:

- runtime-state store from `build_trade_oracle_runtime_state_store`
- benchmark store from `build_trade_oracle_benchmark_store`
- LangGraph orchestrator from `LangGraphSupervisorOrchestrator`
- scanner runner from `MarketScanner`
- execution client from `build_execution_client_from_settings`
- Telegram client from `HttpxTelegramBotClient`

The daemon has three main modes:

- long-running: `python scripts/run_trade_oracle_daemon.py`
- one cycle: `python scripts/run_trade_oracle_daemon.py --once`
- callback-only poll: `python scripts/run_trade_oracle_daemon.py --poll-once`

### 7.2 Startup Path

The VS Code default task calls:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_forward_testing_stack.ps1
```

That script:

1. loads `.env.n8n.local`
2. starts MT5 terminal if it is not already running
3. runs `check_forward_test_readiness.py --check-supabase`
4. blocks on missing env, runtime-state failure, or Supabase failure
5. allows startup if the only blocker is an open pending review
6. runs MT5 preflight
7. runs daemon `--poll-once`
8. starts the long-running daemon
9. starts the watchdog
10. writes `results/forward_testing_stack_status.json`

### 7.3 Watchdog Path

`scripts/run_local_server_watchdog.ps1` checks whether the daemon PID file points to a running process. In daemon mode it does not require n8n, platform service, or webhook tunnel health.

It writes:

- `results/local_server_watchdog_state.json`
- `results/local_server_watchdog_heartbeat.json`
- `results/local_server_watchdog.log`

It can auto-start the daemon if missing.

### 7.4 Telegram Path

Telegram is long-polling only for the main path.

The daemon calls Telegram `getUpdates` with:

- callback-only allowed updates
- stored offset
- configured poll timeout

When a callback arrives:

1. parse `approve:<thread_id>` or `reject:<thread_id>`
2. load pending review from runtime state
3. ignore if missing or already resolved
4. answer callback if possible
5. resume LangGraph thread
6. recheck risk before execution
7. resolve review
8. edit Telegram message
9. write journal and benchmark events
10. persist next Telegram update offset

### 7.5 Supabase Path

Supabase stores the active operational state:

- `trade_oracle_audit_events`
- `trade_oracle_benchmark_events`
- `trade_oracle_pending_reviews`
- `trade_oracle_forward_journal`
- `trade_oracle_daemon_checkpoints`
- `account_state`

The Python Supabase client uses `SUPABASE_URL` and `SUPABASE_KEY`. Schema bootstrap uses `SUPABASE_DB_URL` through the session pooler when IPv4 is needed.

### 7.6 SQLite Fallback

SQLite remains important because it gives:

- local testability
- local debugging
- backup state shape
- parity comparison
- lower dependence on network uptime

Do not remove SQLite until repeated supervised Supabase cycles prove parity.

## 8. Trading Decision Flow

### 8.1 Scanner

The scanner pulls market data and computes technical structure. It emits one setup payload per qualifying asset.

Example fields:

- `symbol`
- `regime`
- `current_price`
- `atr`
- `timeframe`
- `fibonacci_convergence_proximity`
- `ema_cluster_distance`
- `setup_quality`
- `rationale`
- `narrative_tags`
- `scanner_metadata`

### 8.2 LangGraph Super Brain

The graph reads a raw setup and builds a structured decision through deterministic and optional model-backed specialists.

Specialist roles:

- intent router
- macro liquidity analyst
- fundamental narrative specialist
- tokenomics auditor
- technical confluence validator
- devil's advocate
- Pydantic JSON gatekeeper
- optional reserved specialist placeholder

### 8.3 Human Review

If the graph produces an execution-ready setup, the gatekeeper can interrupt for human review. The daemon persists the review and sends Telegram buttons.

Human actions:

- `APPROVE`
- `REJECT`

Review state is durable. Restarting the daemon should not lose the pending review.

### 8.4 Risk Recheck

Risk is checked before cycle evaluation and again after human approval. This is important because account equity can change during the review window.

If the circuit breaker trips during review, the daemon resolves the review as halted and does not transmit.

### 8.5 Broker Transmit

The current live demo path uses MT5.

The MT5 bridge chooses order type from current bid/ask:

- near-market BUY/SELL can route as market
- BUY above market can route as `BUY_STOP`
- BUY below market can route as `BUY_LIMIT`
- SELL below market can route as `SELL_STOP`
- SELL above market can route as `SELL_LIMIT`

Duplicate guard checks existing pending orders before sending another.

## 9. Data Model

### 9.1 Audit Event

Purpose: general traceability.

Fields:

- `event_id`
- `created_at_utc`
- `event_type`
- `source`
- `run_id`
- `thread_id`
- `status`
- `payload`

### 9.2 Benchmark Event

Purpose: measure trading workflow performance and decisions.

Fields:

- `event_id`
- `created_at_utc`
- `event_type`
- `source`
- `cycle_id`
- `run_id`
- `thread_id`
- `symbol`
- `execution_backend`
- `benchmark_variant`
- `status`
- `decision`
- `payload`

### 9.3 Pending Review

Purpose: durable human gate.

Fields:

- `thread_id`
- `cycle_id`
- `run_id`
- `benchmark_variant`
- `review_status`
- `review_action`
- `telegram_chat_id`
- `telegram_message_id`
- `symbol`
- `direction`
- `candidate`
- `review_context`
- `account_state`
- `created_at_utc`
- `updated_at_utc`
- `reviewer`
- `review_notes`
- `cycle_outcome`

### 9.4 Forward Journal

Purpose: one row per cycle outcome.

Fields:

- `cycle_id`
- `run_id`
- `benchmark_variant`
- `thread_id`
- `workflow_name`
- `stage`
- `outcome`
- `symbol`
- `direction`
- `pending_review`
- `transmit_succeeded`
- `benchmark_event_count`
- `thread_ids`
- `summary`
- `updated_at_utc`

### 9.5 Daemon Checkpoint

Purpose: restart-safe daemon state.

Current key:

- `telegram_update_offset`

Fields:

- `checkpoint_key`
- `checkpoint_value`
- `updated_at_utc`

### 9.6 Account State

Purpose: high-watermark tracking.

Fields:

- `id`
- `high_watermark`

## 10. Risk Specification

Current risk policy:

```text
Initial reference balance:        5000
Runtime balance/env default:      configurable
Risk per trade:                   10 USD
Max concurrent trades:            4
Max crypto leverage:              2x
Trade gate drawdown limit:        3.0 percent
Hard circuit breaker:             2.5 percent
Failure buffer:                   15 USD
Stop distance:                    ATR * 1.5
TP1:                              ATR * 2.0
TP2:                              ATR * 3.5
Live TP mode default:             tp1_only
```

The circuit breaker being lower than the 3.0 percent gate is intentional. It halts the system before the broader trailing drawdown line is reached.

## 11. Operational Reliability Mechanisms

Already implemented:

- daemon process PID file
- watchdog heartbeat
- Telegram offset checkpoint
- Supabase retries for transient transport failures
- pending-review replay protection
- stale Telegram callback answer handling
- duplicate MT5 pending-order guard
- MT5 level validation
- MT5 Python API permission checks through preflight
- readiness checker that does not print secrets
- VS Code one-click power-on path
- SQLite fallback

Still worth adding after the demo window:

- structured daemon log events instead of mostly text logs
- startup lock file to prevent overlapping startup scripts
- explicit daily forward-test report generator
- cleanup policy for generated test SQLite files
- CI workflow that excludes local secrets/results
- config validation object instead of module-level loose env parsing
- automatic MT5 pending-order reconciliation report

## 12. Current Readiness

### 12.1 Ready For Demo Forward Testing

Yes.

The system is ready for supervised demo forward testing focused on operational reliability.

The forward test should measure:

- does the daemon stay alive?
- does the watchdog report correctly?
- does Supabase remain reachable?
- does Telegram review flow work repeatedly?
- does the queue prevent accidental stacked reviews?
- does MT5 execution behave as expected?
- do failures leave enough evidence to diagnose?
- do restarts recover without duplicate orders?

### 12.2 Not Yet Ready For

Not yet ready for:

- unattended real-money trading
- removing SQLite fallback
- assuming strategy profitability
- scaling trade size
- repo-wide refactor that touches core runtime behavior
- auto-approval in real supervised forward testing

## 13. Two-Week Demo Forward-Test Plan

The user wants the demo forward test to be short, likely two weeks or less, because the goal is operational reliability, not statistical proof of edge. That is reasonable.

### Day 0

- Confirm MT5 demo account is connected.
- Confirm Algo Trading and Python API trading are enabled.
- Run VS Code `TRADE_ORACLE: Power On Forward Testing`.
- Confirm watchdog heartbeat is healthy.
- Resolve any pending review that is intentionally old.

### Days 1-3

- Let the daemon run supervised.
- Approve or reject Telegram reviews manually.
- Do not use auto-approval.
- Record every operator action.
- Verify Supabase rows after every review.

### Days 4-7

- Introduce controlled restarts.
- Stop/start daemon from VS Code.
- Confirm Telegram cursor does not replay old decisions dangerously.
- Confirm duplicate guard prevents repeat pending orders.

### Days 8-14

- Continue supervised operation.
- Collect metrics:
  - uptime
  - review count
  - approval count
  - rejection count
  - transmit count
  - broker acceptance count
  - broker rejection count
  - duplicate prevented count
  - restart count
  - recovery success count
  - Supabase error count
  - Telegram error count
  - MT5 error count

### Pass Criteria

Operational reliability pass if:

- no unapproved trade is transmitted
- no duplicate order is transmitted after restart/retry
- no review is lost
- daemon restart preserves Telegram offset and pending review state
- watchdog accurately reflects daemon health
- Supabase remains the active source of truth
- every broker transmit has a matching benchmark/journal trail

### Fail Criteria

Pause forward testing if:

- an order transmits without human approval
- a duplicate order is sent
- circuit breaker behavior is unclear
- MT5 account state cannot be trusted
- Supabase and local fallback disagree in a way that affects execution
- Telegram callback handling becomes ambiguous

## 14. Refactor Plan After Forward Testing

Recommended bounded refactors after the reliability window:

### 14.1 Configuration Refactor

Move from module-level env parsing to a typed settings object with validation and secret masking.

Why:

- fewer stale import surprises
- easier CLI testing
- clearer missing/env-invalid errors

### 14.2 Daemon Decomposition

Split `trade_oracle_daemon.py` into:

- Telegram client
- daemon loop
- review service
- execution service
- account state service
- summary/journal writer

Why:

- easier tests
- lower merge risk
- easier future operator dashboard

### 14.3 LangGraph File Decomposition

Split `trade_oracle_langgraph_phase1.py` into:

- schemas
- prompts
- deterministic specialists
- model registry
- tool adapters
- graph builder

Why:

- current file is too large for fast reasoning
- specialist changes should not risk graph plumbing

### 14.4 Script Organization

Create script subfolders:

```text
scripts/
|-- ops/
|-- forward_test/
|-- supabase/
|-- research/
|-- diagnostics/
```

Why:

- current scripts folder mixes production start/stop with research sweeps
- operator commands should be visually obvious

### 14.5 Results Hygiene

Keep `results/` but separate:

```text
results/
|-- runtime/
|-- forward_test/
|-- tests/
|-- backtests/
|-- logs/
```

Why:

- generated test DBs currently swamp git status
- operational reports should be easy to find

### 14.6 Reporting Layer

Add a report generator that pulls:

- Supabase pending reviews
- Supabase forward journal
- benchmark summaries
- MT5 open orders/positions
- daemon logs
- watchdog heartbeat

Why:

- forward testing needs clean daily evidence

## 15. Top-Down Codebase Analysis

### 15.1 What Is Strong

- The system has a clear runtime direction now.
- The daemon replaces fragile webhook orchestration.
- Human review is durable and restart-aware.
- Supabase integration is real, not placeholder-only.
- SQLite fallback keeps local safety.
- MT5 execution has moved beyond naive order sending.
- Tests cover the important control-flow surfaces.
- VS Code startup makes the system operable by a human, not just runnable by a developer.

### 15.2 What Is Risky

- Some source files are too large.
- The repo has many generated artifacts in `results/`.
- Historical docs conflict with current reality.
- Secrets have been manually handled in chat before and must be rotated/managed carefully.
- Strategy edge is not proven by system readiness.
- Live callback timing can produce stale Telegram events.
- MT5 terminal state is external and can change outside Python.
- n8n artifacts can confuse future operators if they do not read the current docs.

### 15.3 What Is Missing

- daily forward-test report generator
- broker reconciliation report
- typed config validation
- explicit release/run IDs for operator sessions
- reliable cleanup for generated test DBs
- CI workflow
- long-run daemon soak-test report
- repeated Supabase/SQLite parity report
- quantified strategy-edge forward-test summary

### 15.4 What Should Not Be Changed Yet

Do not change these during the first forward-test window unless a bug forces it:

- risk constants
- daemon review behavior
- MT5 order routing logic
- Supabase table schema
- Telegram callback format
- storage backend selection
- human approval requirement

## 16. Profitability Evidence Needed

To decide whether the system has serious money potential, collect:

- number of valid setups found
- number rejected by graph
- number rejected by human
- number approved
- number risk-rejected
- number broker-accepted
- entry, stop, target, spread, slippage
- time in trade
- realized PnL
- unrealized drawdown
- whether outcome matched original thesis
- what the graph/human missed
- market regime during each trade

After 2 weeks, operational reliability can be assessed. Profitability cannot be fully proven in 2 weeks unless trade frequency is high and conditions are unusually representative. The short demo should answer: "Can we safely operate this?" not "Is this a money printer?"

## 17. Operating Commands

### 17.1 Power On

From VS Code:

```text
TRADE_ORACLE: Power On Forward Testing
```

Or from terminal:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_forward_testing_stack.ps1
```

### 17.2 Power Off

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop_forward_testing_stack.ps1
```

Stop MT5 too:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop_forward_testing_stack.ps1 -StopMt5
```

### 17.3 Readiness

```powershell
python scripts\check_forward_test_readiness.py --env-file .env.n8n.local --check-supabase
```

### 17.4 MT5 Preflight

```powershell
python scripts\validate_mt5_demo_profile.py --env-file .env.n8n.local --symbols "SOL/USDT"
```

### 17.5 Poll Telegram Once

```powershell
python scripts\run_trade_oracle_daemon.py --poll-once
```

### 17.6 Run One Supervised Cycle

```powershell
python scripts\run_trade_oracle_daemon.py --once
```

### 17.7 Resolve Stale Review

```powershell
python scripts\resolve_pending_review.py --env-file .env.n8n.local --thread-id <thread_id> --backend both
```

### 17.8 Bootstrap Supabase Schema

```powershell
python scripts\bootstrap_supabase_schema.py --env-file .env.n8n.local
```

### 17.9 Migrate SQLite Runtime State To Supabase

```powershell
python scripts\migrate_sqlite_state_to_supabase.py --env-file .env.n8n.local
```

## 18. Environment Variables

Critical runtime values:

- `TRADE_ORACLE_EXECUTION_BACKEND`
- `TRADE_ORACLE_AUDIT_BACKEND`
- `TRADE_ORACLE_BENCHMARK_BACKEND`
- `TRADE_ORACLE_RUNTIME_STATE_BACKEND`
- `TRADE_ORACLE_TELEGRAM_BOT_TOKEN`
- `TRADE_ORACLE_TELEGRAM_CHAT_ID`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_DB_URL`
- `MT5_LOGIN`
- `MT5_PASSWORD`
- `MT5_SERVER`
- `MT5_TERMINAL_PATH`
- `MT5_SYMBOL_MAP`
- `TRADE_ORACLE_DAEMON_CYCLE_INTERVAL_SECONDS`
- `TRADE_ORACLE_DAEMON_TELEGRAM_POLL_TIMEOUT_SECONDS`
- `TRADE_ORACLE_DAEMON_IDLE_SLEEP_SECONDS`
- `TRADE_ORACLE_DAEMON_SEND_CYCLE_SUMMARY`

Secret rule:

- never print secret values in reports
- never commit `.env.n8n.local`
- rotate exposed tokens/passwords when needed

## 19. n8n Role

n8n is fallback/reference only.

It should not be used for the main forward-test path unless:

- the daemon path fails
- a regression comparison is needed
- a legacy workflow contract must be validated

Why n8n was demoted:

- webhook tunnels are fragile for one-laptop deployment
- Telegram long polling is simpler and more reliable
- one Python runtime reduces orchestration split-brain

## 20. Security And Safety Notes

- Use demo until operational reliability is proven.
- Use human approvals during forward testing.
- Keep trade size small.
- Treat MT5 terminal settings as part of production state.
- Keep Supabase service keys private.
- Keep Telegram bot token private.
- Rotate any credential that has been pasted into a chat or log.
- Do not run auto-approval for real supervised forward testing.

Official risk references:

- CFTC customer advisory on virtual currency trading risk: https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/understand_risks_of_virtual_currency.html
- CFTC pump-and-dump advisory: https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/beware_virtual_currency_pump_dump.html
- SEC/CFTC alert on fraudulent digital asset trading websites: https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/watch_out_for_digital_fraud.html

## 21. Recommended Next AI Prompt

```text
We are continuing TRADE_ORACLE from the daemon-first forward-testing bring-up.

First read:
1. AI_CONTEXT_HANDOFF.md
2. documents/development/trade_oracle_system_handbook.md
3. documents/development/trade_oracle_final_pipeline_readiness_report.md
4. README.md

Current truth:
- one Python daemon is the main runtime path
- Telegram uses long polling, not webhooks
- Supabase is the active unified data center
- SQLite fallback stays until parity is proven
- n8n is fallback/reference only
- MT5 demo execution has been broker-accepted
- VS Code has a one-click forward-testing power-on task
- the stack has started successfully with a healthy watchdog heartbeat
- one open `TON/USDT` pending review may be waiting for human action

Your task:
1. Reconfirm readiness without printing secrets.
2. Inspect current pending review state.
3. Help operate the supervised demo forward-test window.
4. Do not perform a repo-wide refactor until the reliability window produces evidence.
5. Pull daily forward-test evidence from Supabase, benchmark events, daemon logs, Telegram behavior, and MT5 state.
```

## 22. Final Judgment

TRADE_ORACLE is ready to begin supervised demo forward testing for operational reliability.

Do not confuse that with a profitability verdict. The system now deserves to be tested seriously, but the market still gets a vote. The next two weeks should be calm, measured, and evidence-driven.

My recommendation is to continue forward testing as-is, avoid a repo-wide refactor for now, and use the reliability data to choose the first serious cleanup pass.
