# CRYPTO_SWING_TRADING

Repository for the crypto swing trading system.

AI/session handoff entrypoint:
- [AI_CONTEXT_HANDOFF.md](/c:/Users/G_R_E/Documents/REPOSITORIES/TRADE_ORACLE/TRADE_ORACLE/AI_CONTEXT_HANDOFF.md)

Contents:
- project code and modules

## Environment Split

The repository now has two explicit Python dependency tracks:

- `requirements.txt` / `requirements.trading.txt`
  Use this for the legacy scanner + risk + execution + Supabase trading pipeline.
- `requirements.langgraph.txt`
  Use this for the LangGraph + FastAPI MCP architecture.

The split is intentional. The LangGraph stack requires newer `httpx` and
`websockets` versions than the existing Supabase runtime tolerates, so both
systems should not share the same Python environment.

## LangGraph Bootstrap

Create the dedicated orchestration environment with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_langgraph_env.ps1
```

Run the MCP service:

```powershell
.venv-langgraph\Scripts\python.exe -m uvicorn api.trade_oracle_mcp_service:app --host 127.0.0.1 --port 8000
```

Run the n8n-facing LangGraph brain service:

```powershell
.venv-langgraph\Scripts\python.exe -m uvicorn api.trade_oracle_brain_service:app --host 127.0.0.1 --port 8010
```

Run the operational scanner/risk/execution service:

```powershell
.venv-langgraph\Scripts\python.exe -m uvicorn api.trade_oracle_ops_service:app --host 127.0.0.1 --port 8020
```

Run the unified LangGraph Super Brain service:

```powershell
.venv-langgraph\Scripts\python.exe -m uvicorn api.trade_oracle_super_brain_service:app --host 127.0.0.1 --port 8030
```

Run the single-container platform service that packages Super Brain + Ops + MCP:

```powershell
.venv-langgraph\Scripts\python.exe -m uvicorn api.trade_oracle_platform_service:app --host 127.0.0.1 --port 8000
```

Optional MCP auth for production-like local runs:

```powershell
$env:TRADE_ORACLE_MCP_API_KEY = "replace-me"
$env:TRADE_ORACLE_MCP_REQUIRE_AUTH = "1"
```

Run the Phase 1 graph demo against the MCP service:

```powershell
.venv-langgraph\Scripts\python.exe scripts\run_trade_oracle_phase1_demo.py --mcp-service-url http://127.0.0.1:8000
```

Trigger the LangGraph brain over HTTP the way n8n will:

```powershell
curl -X POST http://127.0.0.1:8010/brain/evaluate-setup `
  -H "Content-Type: application/json" `
  -d "{\"scanner_setup\":{\"symbol\":\"SOL/USDT\",\"regime\":\"BULLISH\",\"current_price\":145.0,\"atr\":9.25},\"account_state\":{\"current_balance\":5200.0,\"highest_equity\":5300.0,\"active_trades_count\":1}}"
```

If the graph returns `pending_review`, n8n can pause for OpenClaw approval and then resume the same thread:

```powershell
curl -X POST http://127.0.0.1:8010/brain/resume-review `
  -H "Content-Type: application/json" `
  -d "{\"thread_id\":\"<thread-id>\",\"human_decision\":{\"action\":\"APPROVE\",\"reviewer\":\"openclaw\",\"notes\":\"Approved from n8n.\"}}"
```

Phase 2 scanner over HTTP:

```powershell
curl -X POST http://127.0.0.1:8020/ops/scanner/phase2/run `
  -H "Content-Type: application/json" `
  -d "{\"watchlist\":[\"BTC/USDT\",\"ETH/USDT\",\"SOL/USDT\"]}"
```

RiskManager over HTTP:

```powershell
curl -X POST http://127.0.0.1:8020/ops/risk/evaluate `
  -H "Content-Type: application/json" `
  -d "{\"current_balance\":5100.0,\"highest_equity\":5150.0,\"active_trades_count\":1,\"entry_price\":41.25,\"atr\":1.35,\"direction\":\"BUY\"}"
```

Match-Trader execution bridge over HTTP:

```powershell
curl -X POST http://127.0.0.1:8020/ops/execution/transmit-limit-order `
  -H "Content-Type: application/json" `
  -d "{\"broker_id\":\"<broker>\",\"email\":\"<user>\",\"password\":\"<pass>\",\"base_url\":\"https://mtr-api.match-trader.com\",\"system_uuid\":\"<system>\",\"symbol\":\"AVAX/USDT\",\"direction\":\"BUY\",\"size\":4.93827,\"limit_price\":41.25,\"stop_loss\":39.225,\"take_profit\":43.95}"
```

MetaTrader 5 execution bridge over HTTP:

```powershell
curl -X POST http://127.0.0.1:8020/ops/execution/transmit-limit-order `
  -H "Content-Type: application/json" `
  -d "{\"execution_backend\":\"mt5\",\"mt5_login\":\"<login>\",\"mt5_password\":\"<password>\",\"mt5_server\":\"<server>\",\"mt5_terminal_path\":\"C:\\\\Program Files\\\\MetaTrader 5\\\\terminal64.exe\",\"symbol\":\"AVAX/USDT\",\"direction\":\"BUY\",\"size\":4.93827,\"size_mode\":\"units\",\"limit_price\":41.25,\"stop_loss\":39.225,\"take_profit\":43.95}"
```

For MT5, `size_mode` supports:

- `units`
  The default. Treat `size` as strategy asset units/tokens and convert to broker volume using the MT5 symbol contract size.
- `broker_volume`
  Use `size` as a raw MT5 lot/volume value. This is intended for deliberate mechanics-only tests.

The thin n8n webhook contract lives in [contracts/trade_oracle_n8n_workflow_contract.json](contracts/trade_oracle_n8n_workflow_contract.json).

The platform service exposes deployment-aware discovery endpoints:

```powershell
curl http://127.0.0.1:8000/system/health
curl http://127.0.0.1:8000/system/capabilities
curl http://127.0.0.1:8000/system/audit/recent
curl http://127.0.0.1:8000/system/benchmark/summary
curl http://127.0.0.1:8000/system/benchmark/cycles/recent
curl http://127.0.0.1:8000/services/mcp/mcp/providers/status
```

The single-service LangGraph-first deployment endpoint is:

```powershell
curl -X POST http://127.0.0.1:8000/superbrain/run-once `
  -H "Content-Type: application/json" `
  -d "{\"account_state\":{\"current_balance\":5200.0,\"highest_equity\":5300.0,\"active_trades_count\":1},\"auto_approve\":false}"
```

Optional auxiliary service calls through the same platform container:

```powershell
curl -X POST http://127.0.0.1:8000/services/ops/ops/account/state `
  -H "Content-Type: application/json" `
  -d "{\"broker_id\":\"<broker>\",\"email\":\"<user>\",\"password\":\"<pass>\",\"base_url\":\"https://mtr-api.match-trader.com\",\"system_uuid\":\"<system>\"}"
```

```powershell
curl -X POST http://127.0.0.1:8000/services/ops/ops/risk/evaluate `
  -H "Content-Type: application/json" `
  -d "{\"current_balance\":5100.0,\"highest_equity\":5150.0,\"active_trades_count\":1,\"entry_price\":41.25,\"atr\":1.35,\"direction\":\"BUY\"}"
```

```powershell
curl -X POST http://127.0.0.1:8000/services/ops/ops/execution/symbol-status `
  -H "Content-Type: application/json" `
  -d "{\"execution_backend\":\"mt5\",\"mt5_login\":\"<login>\",\"mt5_password\":\"<password>\",\"mt5_server\":\"<server>\",\"mt5_terminal_path\":\"C:\\\\Program Files\\\\MetaTrader 5\\\\terminal64.exe\",\"mt5_symbol_map\":{\"BTC/USDT\":\"BTC\",\"ETH/USDT\":\"ETH\",\"SOL/USDT\":\"SOL\",\"XRP/USDT\":\"XXRP\"},\"symbol\":\"XRP/USDT\"}"
```

```powershell
curl -X POST http://127.0.0.1:8000/services/mcp/mcp/technical-snapshot `
  -H "Content-Type: application/json" `
  -d "{\"asset_ticker\":\"SOL/USDT\",\"timeframe\":\"4h\",\"benchmark_regime_status\":\"RISK_ON\",\"localized_atr\":9.25,\"fibonacci_convergence_proximity\":0.011,\"current_price\":145.0,\"setup_direction\":\"BUY\",\"extra_context\":{\"setup_quality\":0.88,\"ema_cluster_distance\":0.007}}"
```

Build the remote-deployment image:

```powershell
docker build -f Dockerfile.langgraph -t trade-oracle-langgraph .
```

Run the container locally:

```powershell
docker run --rm -p 8000:8000 --env TRADE_ORACLE_PLATFORM_REQUIRE_AUTH=0 trade-oracle-langgraph
```

Optional platform audit persistence path:

```powershell
$env:TRADE_ORACLE_AUDIT_BACKEND = "sqlite"
$env:TRADE_ORACLE_AUDIT_DB_PATH = "results/trade_oracle_audit.sqlite"
```

Optional platform benchmark persistence path:

```powershell
$env:TRADE_ORACLE_BENCHMARK_BACKEND = "sqlite"
$env:TRADE_ORACLE_BENCHMARK_DB_PATH = "results/trade_oracle_benchmark.sqlite"
$env:TRADE_ORACLE_BENCHMARK_VARIANT = "super_brain"
```

Current storage recommendation:

- keep `TRADE_ORACLE_AUDIT_BACKEND=sqlite`
- keep `TRADE_ORACLE_BENCHMARK_BACKEND=sqlite`
- treat SQLite as the primary operational store for audit and benchmark events during local validation and supervised forward-testing

The platform now resolves audit and benchmark storage through backend-selectable factories, so a future Supabase backend can be added without changing the HTTP routes or n8n contracts. At the moment, the Supabase benchmark/audit backend is intentionally not implemented yet; selecting `supabase` will raise a clear error instead of failing silently.

Local n8n validation on Windows via Docker:

1. Copy `.env.n8n.local.example` to `.env.n8n.local` and fill in the MT5 values you actually use.
2. Start the platform service on the Windows host:

```powershell
.venv-langgraph\Scripts\python.exe -m uvicorn api.trade_oracle_platform_service:app --host 0.0.0.0 --port 8000
```

3. Start n8n:

```powershell
docker compose -f docker-compose.n8n.local.yml up -d
```

4. Open `http://localhost:5678`, import:
   - `contracts/n8n_4h_master_orchestrator_platform.workflow.json`
   - for first-click local validation, prefer `contracts/n8n_4h_master_orchestrator_platform.manual_validation.workflow.json`
   - for manual human-approval resume validation, also import `contracts/n8n_openclaw_review_resume.manual_validation.workflow.json`
   - for the real Telegram-supervised operator flow, import:
     - `contracts/n8n_4h_master_orchestrator_platform.telegram.workflow.json`
     - `contracts/n8n_telegram_review_webhook.workflow.json`

5. Run one local cycle and capture the emitted `cycle_id`.

6. Validate that the benchmark trail exists:

```powershell
curl http://127.0.0.1:8000/system/benchmark/summary
curl http://127.0.0.1:8000/system/benchmark/cycles/recent
curl http://127.0.0.1:8000/system/benchmark/cycle/<cycle-id>
```

7. If the cycle ends in `pending_review`, fetch the thread information from the audit log, set:

```powershell
$env:TRADE_ORACLE_REVIEW_THREAD_ID = "<thread-id>"
$env:TRADE_ORACLE_REVIEW_RUN_ID = "<run-id>"
$env:TRADE_ORACLE_REVIEW_CYCLE_ID = "<cycle-id>"
```

Then run the imported `contracts/n8n_openclaw_review_resume.manual_validation.workflow.json` workflow to validate:

- `/superbrain/review-resume`
- optional risk recheck
- transmit path after approval

Example thread ids from one validated local pending-review batch:

- `AVAX/USDT`: `trade-oracle-phase4-0790436ae7bd4f6093f7151d344b1022`
- `XRP/USDT`: `trade-oracle-phase4-2d1f1a812ac046678f7cf3a70c35dca8`
- `SOL/USDT`: `trade-oracle-phase4-789e7c1054744611a817db2ca01e259d`

Important local note:

- because n8n runs inside Docker on Windows, the correct local platform URL inside the container is `http://host.docker.internal:8000`, not `http://127.0.0.1:8000`
- if a Code node fails with `access to env vars denied`, recreate local n8n with `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`; the provided `docker-compose.n8n.local.yml` now sets this explicitly for local validation

## Telegram Operator Flow

The Telegram-only supervised forward-testing path is now split into two workflows:

- `contracts/n8n_4h_master_orchestrator_platform.telegram.workflow.json`
  The scheduled 4H outer orchestrator. It:
  - runs `/superbrain/run-once`
  - persists pending-review state into an n8n Data Table
  - sends Telegram inline approval buttons
  - writes a forward-test journal row after each terminal cycle outcome
- `contracts/n8n_telegram_review_webhook.workflow.json`
  The Telegram callback workflow. It:
  - receives `approve:<thread-id>` or `reject:<thread-id>`
  - reloads `thread_id`, `run_id`, `cycle_id`, and account context from the n8n review queue table
  - falls back to `/system/audit/thread/{thread_id}` if needed
  - calls `/superbrain/review-resume`
  - performs optional risk recheck and transmit
  - edits the original Telegram review message with the final outcome
  - updates the forward-test journal table

Required n8n env vars in `.env.n8n.local`:

```powershell
TRADE_ORACLE_TELEGRAM_CHAT_ID=<your-chat-id>
TRADE_ORACLE_N8N_REVIEW_QUEUE_TABLE=TRADE_ORACLE Pending Reviews
TRADE_ORACLE_N8N_FORWARD_JOURNAL_TABLE=TRADE_ORACLE Forward Test Journal
```

Telegram setup notes:

- create one Telegram bot with BotFather
- add the bot to the operator chat you want to use
- use the same Telegram credential on all Telegram nodes in both workflows
- keep only one active `Telegram Trigger` workflow per bot token in n8n
- the callback workflow expects inline button payloads in the format `approve:<thread-id>` or `reject:<thread-id>`
- the webhook workflow needs a public HTTPS `WEBHOOK_URL`; `localhost` and temporary test URLs are fine for local experiments but not for stable production use

What n8n persists automatically:

- `TRADE_ORACLE Pending Reviews`
  Holds `thread_id`, `run_id`, `cycle_id`, review payload JSON, and the Telegram message identifiers needed to edit the original review message.
- `TRADE_ORACLE Forward Test Journal`
  Holds one row per cycle with the cycle outcome, symbol, direction, benchmark event count, and transmit status.

Why `ALERT Send Cycle Summary?` can correctly be `false`:

- in the first Telegram workflow, `pending_review` is treated as a handoff state, not a terminal operator update
- that workflow should send the inline `Approve` / `Reject` message and then stop
- the final Telegram resolution message belongs to the second workflow after the callback resumes the thread
- so if the first workflow ends in `pending_review`, the `ALERT Send Cycle Summary?` gate should evaluate `false`

Suggested import order:

1. Import `contracts/n8n_4h_master_orchestrator_platform.telegram.workflow.json`
2. Attach your Telegram credential to the Telegram send-message node
3. Import `contracts/n8n_telegram_review_webhook.workflow.json`
4. Attach the same Telegram credential to:
   - `TRG Telegram Review Trigger`
   - `ALERT Ack Telegram Callback`
   - `ALERT Edit Telegram Review Message`
5. Start with manual runs before enabling the scheduled trigger

## Supervised Forward Testing

Use the n8n forward-journal table as the machine record and keep a short human review after each cycle.

Recommended operator loop after each cycle:

1. Check the latest n8n `TRADE_ORACLE Forward Test Journal` row
2. Inspect:
   - `curl http://127.0.0.1:8000/system/benchmark/cycles/recent`
   - `curl http://127.0.0.1:8000/system/benchmark/cycle/<cycle-id>`
3. If the cycle involved a human approval, also inspect:
   - `curl http://127.0.0.1:8000/system/audit/thread/<thread-id>`
4. Add a short manual note using `journal/trade_oracle_forward_test_review_template.md`

The goal at this phase is not to maximize activity. It is to build a disciplined record of:

- pending-review frequency
- approval vs rejection behavior
- no-trade frequency
- transmit success rate
- symbol-specific friction
- whether the Super Brain is producing cleaner candidates than the simpler baseline

## Windows 365 Plus Phone Operator Mode

If you want the Windows pieces without owning a separate always-on device, the cleanest split is:

- Windows 365 Cloud PC:
  - MT5 terminal
  - TRADE_ORACLE platform service
  - n8n
  - Cloudflare quick tunnel for Telegram callbacks
- phone:
  - Telegram review approvals
  - Windows App / Remote Desktop access back into the Cloud PC

Recommended trial shape:

1. Choose a Windows 365 Cloud PC with enough resources for nested virtualization and Docker Desktop.
   Microsoft documents virtualization-based workloads such as WSL and Hyper-V on supported Windows 365 Cloud PCs, and Docker Desktop on Windows depends on WSL2 or Hyper-V.
2. Install on the Cloud PC:
   - Git
   - Python
   - Docker Desktop
   - MetaTrader 5 / FTMO terminal
   - `cloudflared`
3. Clone this repo onto the Cloud PC and prepare `.env.n8n.local`.
4. Run the bootstrap script:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_windows365_phone_stack.ps1
```

That script will:

- start a Cloudflare quick tunnel for n8n
- write the temporary public HTTPS URL into `.env.n8n.local`
- start or reuse the platform service on port `8000`
- recreate the local n8n Docker stack on port `5678`
- print the URLs and log-file locations you need

Useful companion shutdown command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop_windows365_phone_stack.ps1
```

Operational notes:

- the quick-tunnel URL is temporary, so rerun the bootstrap script after a reboot or if Telegram callbacks stop working
- keep Telegram open on your phone for `Approve` / `Reject`
- use the Windows App / Remote Desktop client on the phone only for maintenance, not for every review event
- this is a strong trial/testing path, not a forever-production URL strategy

## Local Server Automation

If you want your PC to act like a practical local server, the repo now includes a watchdog and scheduled-task installer:

- `scripts/run_local_server_watchdog.ps1`
  - defaults to `daemon` mode and checks the Python daemon pid file
  - can still run in `n8n` fallback mode with `-RuntimeMode n8n`
  - reruns the matching bootstrap if the stack degrades
  - can send direct Telegram alerts when the stack breaks or recovers
  - writes heartbeat/state files into `results/`
- `scripts/install_local_server_automation.ps1`
  - installs a Task Scheduler job at user logon
  - if run as Administrator, also installs a startup task as `SYSTEM`

Recommended setup:

1. Put your bot token into `.env.n8n.local`:

```powershell
TRADE_ORACLE_ALERT_TELEGRAM_BOT_TOKEN=<your-bot-token>
TRADE_ORACLE_ALERT_TELEGRAM_CHAT_ID=<your-chat-id>
```

2. Install the watchdog task:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_local_server_automation.ps1
```

This installs daemon-first automation. To install the legacy n8n watchdog instead, pass:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_local_server_automation.ps1 -RuntimeMode n8n
```

3. Optionally test the watchdog one time:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_local_server_watchdog.ps1 -RunOnce
```

Useful env vars:

```powershell
TRADE_ORACLE_WATCHDOG_INTERVAL_SECONDS=60
TRADE_ORACLE_WATCHDOG_COOLDOWN_MINUTES=15
TRADE_ORACLE_HEARTBEAT_URL=
```

What the watchdog can and cannot do:

- it **can** alert you if:
  - the Python daemon stops in `daemon` mode
  - `n8n`, the platform service, or the temporary Telegram tunnel stops in `n8n` mode
- it **can** try to restart the stack automatically
- it **cannot** send an alert from the laptop after the laptop is already fully powered off

If you want an alert when the whole laptop is off, use `TRADE_ORACLE_HEARTBEAT_URL` with any external heartbeat-monitor service. The watchdog will ping that URL while healthy; if your laptop goes dark, the external service can alert your Telegram or email after missed heartbeats.

To wake the PC for the 4H cycle from sleep or hibernate, install the repeating wake task:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_4h_wake_cycle_task.ps1
```

Notes on wake behavior:

- Windows can usually wake the PC from sleep/hibernate for a scheduled task if wake timers are enabled
- Windows cannot guarantee power-on from a full shutdown; that depends on BIOS/UEFI options such as RTC alarm / Resume by Alarm / Wake by RTC
- keep the laptop on AC power for the most reliable wake behavior

## VS Code / GitHub Port Forwarding Reality Check

The Cloudflare quick-tunnel problem is only partially solved:

- for **local testing and supervised use**, the repo now auto-starts a Cloudflare quick tunnel and can auto-restart it with the watchdog
- for **true production**, quick tunnels are still a testing tool, not a durable endpoint

Why not replace it with GitHub/VS Code port forwarding:

- GitHub Codespaces forwarded ports expose ports running **inside a codespace**, not your local Windows laptop
- VS Code Remote Tunnels are excellent for **you reaching your PC remotely**, but they are not the same as a stable public webhook endpoint for Telegram bot callbacks
- neither option helps if the laptop is fully off

So the practical answer is:

- use the current Cloudflare quick-tunnel automation on your PC now
- use the watchdog + wake task to keep it alive
- later, if you want a truly durable endpoint, move to a named Cloudflare Tunnel or a real hosted machine

## Production Cutover Checklist

Once the local Telegram loop is working end to end, the production-ready path is:

1. Replace the temporary quick tunnel with a stable public HTTPS endpoint.
   Use a named Cloudflare Tunnel or a deployed n8n domain and set `WEBHOOK_URL` to that permanent URL.
2. Run only one active copy of each Telegram workflow.
   Keep one active main orchestrator and one active Telegram trigger workflow per bot token.
3. Keep n8n and the platform service always on.
   Use Docker restart policies, a VM service manager, or your GCE deployment so the callback path is not lost after restarts.
4. Keep audit and benchmark SQLite files on persistent disk.
   The key files are `results/trade_oracle_audit.sqlite` and `results/trade_oracle_benchmark.sqlite`.
5. Keep the n8n volume persistent and backed up.
   This preserves the forward journal table, pending review queue, workflow state, and Telegram message linkage.
6. Verify broker symbol support before live-forward operation.
   Use `/services/ops/ops/execution/symbol-status` and confirm `MT5_SYMBOL_MAP` for every traded symbol.
7. Start with supervised forward-testing before any unattended operation.
   Review the journal row, benchmark cycle, and audit thread after each cycle.
8. Promote analytics later, not first.
   Keep SQLite as the primary operational store and mirror to Supabase only when you want remote dashboards and longer-term analytics.

Production scaffolding now included in the repo:

- `docker-compose.n8n.production.yml`
  Runs n8n behind a named Cloudflare Tunnel with a persistent Docker volume.
- `.env.n8n.production.example`
  Baseline production env template for the Telegram workflows.
- `scripts/setup_cloudflare_named_tunnel.ps1`
  Bootstraps a named Cloudflare Tunnel, routes a hostname, fetches the tunnel token, and writes the key values into `.env.n8n.production`.

Suggested production bring-up:

1. Copy `.env.n8n.production.example` to `.env.n8n.production`
2. Run the tunnel bootstrap:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_cloudflare_named_tunnel.ps1 `
  -TunnelName trade-oracle-n8n `
  -Hostname n8n.example.com
```

3. Start the production n8n stack:

```powershell
docker compose -f docker-compose.n8n.production.yml up -d
```

4. Keep the platform service reachable at the URL in `TRADE_ORACLE_PLATFORM_BASE_URL`
5. Open your n8n editor on the stable hostname and activate only the production copies of the Telegram workflows

Execution backend selection:

```powershell
$env:TRADE_ORACLE_EXECUTION_BACKEND = "match_trader"
```

Supported values:

- `match_trader`
- `mt5`

Optional MT5 execution env vars:

```powershell
$env:MT5_LOGIN = "<login>"
$env:MT5_PASSWORD = "<password>"
$env:MT5_SERVER = "<server>"
$env:MT5_TERMINAL_PATH = "C:\\Program Files\\MetaTrader 5\\terminal64.exe"
$env:MT5_SYMBOL_SUFFIX = ""
$env:MT5_SYMBOL_MAP = "{\"BTC/USDT\":\"BTC\",\"ETH/USDT\":\"ETH\",\"SOL/USDT\":\"SOL\",\"XRP/USDT\":\"XXRP\"}"
```

The MetaQuotes demo account validated so far supports the mapped symbols above.
It does not currently expose `AVAX/USDT` or `DOGE/USDT` as quoted MT5 symbols on
the tested server, so use `/services/ops/ops/execution/symbol-status` before any
supervised demo transmit to confirm the exact broker-side symbol and live tick.

FTMO MT5 demo prep:

```powershell
$env:TRADE_ORACLE_EXECUTION_BACKEND = "mt5"
$env:MT5_LOGIN = "<ftmo-login>"
$env:MT5_PASSWORD = "<ftmo-password>"
$env:MT5_SERVER = "FTMO-Demo"
$env:MT5_TERMINAL_PATH = "<path-to-ftmo-terminal64.exe>"
$env:MT5_SYMBOL_MAP = "{\"AVAX/USDT\":\"AVAUSD\",\"DOGE/USDT\":\"DOGEUSD\"}"
```

Use the FTMO-provided MT5 terminal, log in manually once, and confirm the
terminal is connected before running any TRADE_ORACLE checks. The exact FTMO
crypto symbol names can vary by server, so treat the map above as a starting
template and verify the real names inside MT5 `Market Watch -> Symbols`.

On the FTMO demo environment validated so far, the visible crypto CFD symbols include:

- `BTCUSD`
- `ETHUSD`
- `XRPUSD`
- `SOLUSD`
- `AVAUSD`
- `DOGEUSD`

Run the local preflight checker after setting the env vars:

```powershell
.venv-langgraph\Scripts\python.exe scripts\validate_mt5_demo_profile.py `
  --symbols "AVAX/USDT,DOGE/USDT,BTC/USDT,ETH/USDT,SOL/USDT,XRP/USDT" `
  --output results/ftmo_mt5_preflight.json
```

That script validates:

- MT5 auth
- live account oversight state
- exact symbol resolution
- quote / tick availability

It does not transmit any orders.

The FTMO MT5 path has now been validated end to end with:

- real FTMO auth
- live quote checks for `AVAUSD`, `DOGEUSD`, `BTCUSD`, `ETHUSD`, `SOLUSD`, `XRPUSD`
- real `/superbrain/run-once`
- real `/superbrain/review-resume`
- real risk recheck
- real broker-accepted pending orders on `AVAUSD`

Explicit live-demo execution policy:

```powershell
$env:TRADE_ORACLE_LIVE_TP_MODE = "tp1_only"
```

Supported values:

- `tp1_only`
- `tp2_full`

Optional MCP provider-layer controls for live specialist adapters:

```powershell
$env:TRADE_ORACLE_MCP_PROVIDER_MODE = "hybrid"
$env:TRADE_ORACLE_MCP_MACRO_PROVIDER = "coingecko"
$env:TRADE_ORACLE_MCP_FUNDAMENTAL_PROVIDER = "coingecko"
$env:TRADE_ORACLE_MCP_TOKENOMICS_PROVIDER = "coingecko"
$env:TRADE_ORACLE_MCP_TECHNICAL_PROVIDER = "binance_public"
$env:TRADE_ORACLE_COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
$env:TRADE_ORACLE_BINANCE_BASE_URL = "https://api.binance.com"
```

Optional explicit external-HTTP override per specialist domain:

```powershell
$env:TRADE_ORACLE_MCP_MACRO_PROVIDER_URL = "https://macro-provider.example/api/v1/snapshot"
$env:TRADE_ORACLE_MCP_FUNDAMENTAL_PROVIDER_URL = "https://fundamental-provider.example/api/v1/snapshot"
$env:TRADE_ORACLE_MCP_TOKENOMICS_PROVIDER_URL = "https://tokenomics-provider.example/api/v1/snapshot"
$env:TRADE_ORACLE_MCP_TECHNICAL_PROVIDER_URL = "https://technical-provider.example/api/v1/snapshot"
```

Hydrate the graph with live account context when Match-Trader / Supabase credentials and deps are available:

```powershell
.venv-langgraph\Scripts\python.exe scripts\run_trade_oracle_phase1_demo.py --hydrate-account-state --mcp-service-url http://127.0.0.1:8000
```

Run the graph from the existing Phase 2 MarketScanner output instead of the fixed demo payload:

```powershell
.venv-langgraph\Scripts\python.exe scripts\run_trade_oracle_phase1_demo.py --from-scanner --scanner-setup-index 0
```

Run the original inline Phase 1 graph demo:

```powershell
.venv-langgraph\Scripts\python.exe -c "from ai.trade_oracle_langgraph_phase1 import run_phase1_demo; first, final = run_phase1_demo(mcp_service_base_url='http://127.0.0.1:8000'); print('__interrupt__' in first); print(final['final_decision'])"
```

## Single Runtime Daemon

The repo now has a Python-only forward-testing daemon that can replace the n8n review loop on one PC:

- scans the watchlist
- runs the LangGraph supervisor
- persists pending reviews and forward-journal rows through the runtime-state store
- polls Telegram callback buttons without webhooks
- resumes the same thread and continues through risk + execution

Main entrypoint:

```powershell
.venv-langgraph\Scripts\python.exe scripts\run_trade_oracle_daemon.py
```

Useful modes:

```powershell
.venv-langgraph\Scripts\python.exe scripts\run_trade_oracle_daemon.py --once
.venv-langgraph\Scripts\python.exe scripts\run_trade_oracle_daemon.py --poll-once
```

Minimum env knobs for the daemon path:

- `TRADE_ORACLE_RUNTIME_STATE_BACKEND=sqlite|supabase`
- `TRADE_ORACLE_RUNTIME_STATE_DB_PATH=results/trade_oracle_runtime_state.sqlite`
- `TRADE_ORACLE_TELEGRAM_BOT_TOKEN=...`
- `TRADE_ORACLE_TELEGRAM_CHAT_ID=...`
- `TRADE_ORACLE_SUPABASE_DAEMON_CHECKPOINT_TABLE=trade_oracle_daemon_checkpoints`
- `TRADE_ORACLE_DAEMON_CYCLE_INTERVAL_SECONDS=14400`
- `TRADE_ORACLE_DAEMON_TELEGRAM_POLL_TIMEOUT_SECONDS=20`
- `TRADE_ORACLE_DAEMON_IDLE_SLEEP_SECONDS=2`
- `TRADE_ORACLE_DAEMON_SEND_CYCLE_SUMMARY=1`

Forward-test operating note:

- if unresolved pending reviews already exist, the daemon skips new cycles until they are resolved
- this is intentional so we do not silently stack unreviewed threads on one laptop
- the daemon path does not need a webhook tunnel because Telegram is polled directly

Current production boundary:

- benchmark, audit, pending-review state, and forward journal are all backend-selectable
- daemon Telegram cursor/checkpoint state is persisted through the runtime-state backend
- local-server automation now defaults to watchdog-driven daemon startup, with `-RuntimeMode n8n` kept as fallback
- that means this path is forward-test ready now, and one step away from the fully unified production loop

## Supabase Unified Data Center Migration

If we want one advanced cloud data center instead of mixed local SQLite, n8n data tables, and webhook-era handoff state, the clean production path is:

1. Move benchmark and audit events behind the backend-selectable storage layer.
   This repo now supports real `supabase` backends for those stores instead of placeholder errors.
2. Promote pending-review queue and forward journal into dedicated runtime-state storage.
   This repo now exposes one backend-selectable runtime-state store for:
   `trade_oracle_pending_reviews`, `trade_oracle_forward_journal`, `trade_oracle_daemon_checkpoints`
3. Keep SQLite as the local fail-safe during parity testing.
   Run dual-write or side-by-side verification before cutting operational reads fully to Supabase.
4. Move daemon runtime state to Supabase only after the Python-only orchestrator is stable.
   This keeps Telegram review, scheduling, and resume logic reconstructible after machine restarts.
5. Cut platform reads to Supabase once cycle summaries, audit lookups, pending-review state, and review resume all match the current SQLite trail.

Relevant runtime-state settings:

- `TRADE_ORACLE_RUNTIME_STATE_BACKEND=sqlite|supabase`
- `TRADE_ORACLE_RUNTIME_STATE_DB_PATH=results/trade_oracle_runtime_state.sqlite`
- `TRADE_ORACLE_SUPABASE_PENDING_REVIEW_TABLE=trade_oracle_pending_reviews`
- `TRADE_ORACLE_SUPABASE_FORWARD_JOURNAL_TABLE=trade_oracle_forward_journal`
- `TRADE_ORACLE_SUPABASE_DAEMON_CHECKPOINT_TABLE=trade_oracle_daemon_checkpoints`

The Supabase daemon-checkpoint table expects:
`checkpoint_key` as a unique text key, `checkpoint_value` as JSON/JSONB, and `updated_at_utc` as text or timestamp.

Recommended production gate:

- SQLite and Supabase produce matching benchmark cycle summaries for at least 20 supervised cycles.
- SQLite and Supabase produce matching pending-review rows, forward-journal rows, and daemon checkpoints for the same cycles.
- Telegram review/resume works with no n8n dependency.
- Restart recovery can reconstruct pending reviews and Telegram polling cursor state from Supabase alone.
