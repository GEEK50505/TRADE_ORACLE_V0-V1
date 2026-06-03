# Prompt: Full TRADE_ORACLE System Check

You are entering the TRADE_ORACLE repository with no prior project context.

Your job is to perform a real full-system check of the repo and live runtime, not just a code review.

Start by reading these files in order:

1. `AI_CONTEXT_HANDOFF.md`
2. `README.md`
3. `documents/development/trade_oracle_full_system_check_guide.md`
4. `ai/trade_oracle_daemon.py`
5. `ai/langgraph_orchestrator.py`
6. `ai/trade_oracle_runtime_state.py`
7. `ai/trade_oracle_supabase.py`
8. `ai/trade_oracle_supabase_storage.py`
9. `execution/mt5_bridge.py`
10. `config/settings.py`
11. `scripts/start_forward_testing_stack.ps1`
12. `scripts/run_local_server_watchdog.ps1`
13. `scripts/check_forward_test_readiness.py`

Then do an actual end-to-end system check.

Requirements:

- do not assume any repo history
- do not ask the user to repeat project context unless absolutely necessary
- do not print secrets from `.env.n8n.local`
- use the project Python environment when needed:
  - `.\.venv-langgraph\Scripts\python.exe`
- distinguish between stale artifact files and live runtime truth
- verify both code health and operator/runtime health

Your system check must cover:

1. repo/test health
2. daemon runtime health
3. watchdog health
4. Telegram long-polling health
5. Supabase health
6. MT5 health
7. trading-journey state from benchmark, forward-journal, and broker exposure
8. restart/logon recovery behavior
9. wake/sleep recovery behavior
10. startup idempotency
11. current forward-testing readiness

Run the commands from the guide and adapt only if the environment requires it.

You must also generate the current trading-health artifacts:

- `results/trade_oracle_trading_health_report.json`
- `documents/development/trade_oracle_trading_health_report.md`

When you assess the trading journey, distinguish clearly between:

- operational reliability
- execution-path proof
- realized strategy-performance proof

Do not pretend those are the same thing.

At the end, give the result in this structure:

1. **Findings**
2. **Evidence**
3. **Trading Journey**
4. **Current Verdict**
5. **Open Risks**
6. **Recommended Next Actions**

If you find any issue during the check:

- identify whether it is:
  - a code bug
  - an environment issue
  - a stale artifact issue
  - an operational caveat
- fix it if it is safe and clearly within scope
- rerun the relevant validation after fixing it

If the system is healthy, say so clearly.

If the system is not healthy, say exactly why and whether it is:

- `GO for supervised forward testing`
- `GO with caveats`
- `NO-GO`

Do not stop at general impressions. Use real commands, real files, real logs, and real pass/fail results.
