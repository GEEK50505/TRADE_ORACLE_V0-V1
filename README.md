# CRYPTO_SWING_TRADING

Repository for the crypto swing trading system.

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
$env:TRADE_ORACLE_AUDIT_DB_PATH = "results/trade_oracle_audit.sqlite"
```

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
