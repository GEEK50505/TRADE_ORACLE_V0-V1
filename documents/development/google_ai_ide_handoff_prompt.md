# Google AI IDE Handoff Prompt

Paste this to the next AI agent as the opening prompt:

```text
You are taking over the TRADE_ORACLE repository mid-stream.

Project root:
- c:\Users\G_R_E\Documents\REPOSITORIES\TRADE_ORACLE\TRADE_ORACLE

Your first job is to absorb current reality before making changes.

Read these files first, in order:
1. AI_CONTEXT_HANDOFF.md
2. documents/development/trade_oracle_ai_agent_handoff_packet.md
3. documents/development/current_trade_oracle_trading_health_report.md
4. documents/development/trade_oracle_system_handbook.md
5. documents/development/trade_oracle_final_pipeline_readiness_report.md
6. README.md

Important current truths:
- TRADE_ORACLE is daemon-first now
- Telegram review flow uses long polling
- Supabase is the active data center
- SQLite remains the fallback
- MT5 demo is the execution target
- the repo is dirty, with many modified and untracked files
- do not revert unrelated work
- do not print secrets from .env.n8n.local
- do not do a broad refactor unless explicitly instructed

Important nuance:
- some docs and workflow names still say 4H
- config/settings.py currently defaults TRADE_ORACLE_DAEMON_CYCLE_INTERVAL_SECONDS to 3600
- verify runtime truth from code and env before assuming the schedule

Your initial tasks:
1. Confirm the correct repo root and inspect git status.
2. Summarize current system state from the handoff docs.
3. Reconfirm forward-test readiness without exposing secrets.
4. Inspect daemon/watchdog/lock status before starting or stopping anything.
5. Identify the smallest high-value next action for operational reliability.

Working style requirements:
- be conservative with destructive actions
- preserve existing local changes
- prefer targeted fixes and verification
- explain what you verify versus what you infer
- leave updated docs if you materially change the system state
```
