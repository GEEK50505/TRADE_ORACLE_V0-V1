# TRADE_ORACLE — Full System Check Report

Generated: 2026-05-06T09:40:10Z (UTC)

**1. Findings**
- **Repo/tests:** Passed — `97 passed, 1 xfailed, 1 warning` (run with project venv).
- **Daemon runtime:** Running; daemon logs show normal operation and repeated Telegram transient DNS/connect warnings but recovered (see logs).
- **Watchdog:** Healthy; last heartbeat `2026-05-05T21:34:27.8997948Z` — [results/local_server_watchdog_heartbeat.json](results/local_server_watchdog_heartbeat.json)
- **Telegram long-polling:** Experienced transient DNS/connect errors (`getaddrinfo failed`, `httpx.ReadError`) but the client recovered and continued polling successfully — see [results/trade_oracle_daemon.err.log](results/trade_oracle_daemon.err.log)
- **Supabase:** Reachable and used as primary storage for benchmark and runtime-state (POST/PATCH requests returned `200/201`).
- **MT5:** Authenticated and responsive; account equity `10012.17`, `active_trades=2` — [results/forward_testing_mt5_preflight.json](results/forward_testing_mt5_preflight.json)
- **Trading journey (benchmark):** 38 cycles, 152 events, 36 transmit attempts, 19 successes, broker acceptance ≈ 52.78% — [results/trade_oracle_trading_health_report.json](results/trade_oracle_trading_health_report.json)
- **Startup idempotency:** `scripts/start_forward_testing_stack.ps1` returned `FORWARD_TESTING_ALREADY_RUNNING=True` when run while stack active — [results/forward_testing_stack_status.json](results/forward_testing_stack_status.json)
- **Wake/sleep capability:** Host exposes only S0 (Network Connected Idle); S3/Hibernate unavailable — limits wake/sleep recovery testing.

**2. Evidence (select artifacts)**
- **Trading health JSON:** [results/trade_oracle_trading_health_report.json](results/trade_oracle_trading_health_report.json)
- **MT5 preflight:** [results/forward_testing_mt5_preflight.json](results/forward_testing_mt5_preflight.json)
- **Watchdog heartbeat:** [results/local_server_watchdog_heartbeat.json](results/local_server_watchdog_heartbeat.json)
- **Daemon logs (errors & info):** [results/trade_oracle_daemon.err.log](results/trade_oracle_daemon.err.log), [results/trade_oracle_daemon.log](results/trade_oracle_daemon.log)
- **Startup status:** [results/forward_testing_stack_status.json](results/forward_testing_stack_status.json)

**3. Trading Journey**
- **Operational reliability:** Runtime components (daemon, watchdog, Supabase, MT5 bridge) are online and exchanging data. Supabase requests succeed (201/200). Watchdog heartbeat present.
- **Execution-path proof:** Demo MT5 preflight shows `SOLUSD` has live ticks and account `can_open_new_trade=true`. Benchmark artifacts show transmitted attempts and recorded transmit results with acceptance rate ~52.78%.
- **Realized strategy-performance proof:** Benchmark indicates many cycles ended with `risk_rejected` decisions (13 risk rejections), limited confirmed executed resume results (1) and `transmit_successes=19`. This is evidence of strategy gating and risk checks preventing many transmits; not a proof of positive strategy performance.

**4. Current Verdict**
- **Status:** GO with caveats
- **Rationale:** System components are healthy and ready for supervised forward-testing: Supabase reachable, MT5 authenticated, watchdog and daemon running, trading-health report generated. However transient Telegram connectivity issues were observed and host sleep-state limits wake/sleep testing.

**5. Open Risks**
- **Network stability:** Repeated `getaddrinfo failed` / `httpx.ReadError` during Telegram polling — could cause missed callbacks if persistent.
- **Execution acceptance variability:** Broker acceptance rate ≈ 52.8%; confirm expected for demo account and risk filters.
- **Wake/sleep recovery:** Host doesn't support S3/hibernate — scheduled wake tasks and sleep recovery flows unverified.
- **Stale artifacts vs live truth:** Several `results/` artifacts exist; ensure validation uses live probes (we used preflight and readiness scripts).

**6. Recommended Next Actions (prioritized)**
- **(A)** Monitor and stabilize network/DNS for runtime host; consider system-level DNS caching or a more stable DNS resolver.
- **(B)** Run a safe `--poll-once` daemon check to validate Telegram callbacks flow now (command: `.\.venv-langgraph\Scripts\python.exe scripts\run_trade_oracle_daemon.py --poll-once`).
- **(C)** Verify restart/logon recovery (run startup launcher on a fresh login or simulate via `Start-Process` and confirm `trade_oracle_watchdog.pid` is written and watchdog heartbeat appears).
- **(D)** Validate wake/sleep recovery only if host power-state policy allows; otherwise mark as operational caveat.
- **(E)** Review acceptance rate with trading ops: validate expected broker behavior in demo vs live accounts.
- **(F)** Add a short-run supervised forward test (monitor positions and forward-journal) before unsupervised runs.

**Appendix — Quick commands used**
- Run tests: `.\.venv-langgraph\Scripts\python.exe -m pytest -p no:cacheprovider -q`
- Readiness check: `.\.venv-langgraph\Scripts\python.exe scripts\check_forward_test_readiness.py --env-file .env.n8n.local --check-supabase`
- MT5 preflight: `.\.venv-langgraph\Scripts\python.exe scripts\validate_mt5_demo_profile.py --env-file .env.n8n.local --symbols "SOL/USDT" --output results/forward_testing_mt5_preflight.json`
- Generate health report: `.\.venv-langgraph\Scripts\python.exe scripts\generate_trade_oracle_trading_health_report.py --env-file .env.n8n.local --json-output results/trade_oracle_trading_health_report.json --markdown-output documents/development/trade_oracle_trading_health_report.md`

---
Report generated from live checks and artifacts in `results/` on 2026-05-06.
