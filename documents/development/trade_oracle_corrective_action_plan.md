# TRADE_ORACLE Corrective Action Plan

## Purpose

This document turns the valid parts of the recent external review into a concrete action plan.

The guiding principle is:

- stop broad feature expansion
- close the remaining correctness gaps
- refresh the runtime environments
- validate the live operational path end to end

## Current Ground Truth

The project is not in a design crisis. It is in an integration-and-validation phase.

The most important current facts are:

- the backtesting/re-optimization work produced a confirmed realistic 3-pair survivor
- the LangGraph architecture is built and operational
- the MCP/provider layer now supports real live CoinGecko and Binance public data
- live provider smoke tests have already succeeded through the mounted platform service
- the biggest remaining issues are:
  - a few concrete code bugs
  - runtime environment synchronization
  - end-to-end live execution validation
  - the TP1/TP2 live execution gap

## Priority Order

1. Fix correctness bugs that can break live execution.
2. Align the LangGraph runtime environment with the current repository state.
3. Validate the scanner -> super-brain -> review -> risk -> execution path in supervised mode.
4. Close the split-take-profit execution gap.
5. Incrementally enable real LLM reasoning and broader live specialist coverage.

## Workstream 1: Immediate Code Fixes

### 1. Fix the DeepSeek response parsing bug

File:

- `ai/inference.py`

Current issue:

```python
raw_content = response.choices.message.content
```

Required fix:

```python
raw_content = response.choices[0].message.content
```

Why this matters:

- this is a real defect in the legacy inference path
- it will break DeepSeek output handling on live use

Acceptance criteria:

- file updated
- add a small unit test or stubbed response test for DeepSeek response parsing
- import and invocation path confirmed

### 2. Harden Match-Trader open position counting

File:

- `execution/match_trader.py`

Current issue:

```python
open_positions = len(data.get("positions",))
```

Required fix:

```python
open_positions = len(data.get("positions", []))
```

Why this matters:

- not a syntax error
- still unsafe if `positions` is absent or `None`
- this can break live platform state reads

Acceptance criteria:

- code updated
- add test for missing `positions`
- run:

```powershell
python -c "from execution.match_trader import MatchTraderAPI; print('OK')"
```

### 3. Revalidate Match-Trader authentication behavior

File:

- `execution/match_trader.py`

Current concern:

- the code uses:

```python
self.headers["Cookie"] = f"co-auth={self.token}"
```

Required action:

- test against the actual Maven simulated account
- verify whether cookie auth alone works
- if required, add alternate header handling behind a safe toggle

Acceptance criteria:

- successful auth against the target environment
- successful `get_platform_details()`
- exact required auth header/cookie behavior documented

## Workstream 2: Runtime Environment Alignment

### 4. Refresh the LangGraph runtime environment

Files:

- `requirements.langgraph.txt`
- `data/scanner.py`

Current situation:

- scanner dependencies were added to `requirements.langgraph.txt`
- `data/scanner.py` no longer depends on `pandas_ta`
- the local `.venv-langgraph` still needs to be refreshed so `/superbrain/run-once` can use the real scanner path

Required action:

- rebuild or refresh the LangGraph environment
- confirm the following imports in the LangGraph runtime:
  - `ccxt`
  - `pandas`
  - `aiohttp`
  - `data.scanner`

Acceptance criteria:

- `python -c "from data.scanner import MarketScanner; print('OK')"` passes in the LangGraph runtime
- `POST /services/ops/ops/scanner/phase2/run` returns `200`
- `POST /superbrain/run-once` can use the built-in Phase 2 scanner

### 5. Rebuild the platform container after dependency refresh

Files:

- `Dockerfile.langgraph`
- `requirements.langgraph.txt`

Required action:

- rebuild the LangGraph/platform image after the runtime requirements are aligned
- verify that the container includes the scanner path, not just the graph/MCP layer

Acceptance criteria:

- container boots successfully
- mounted ops scanner endpoint works inside the container
- mounted MCP live-provider endpoints still work

## Workstream 3: End-to-End Operational Validation

### 6. Validate the Phase 2 scanner endpoint directly

Endpoint:

- `/services/ops/ops/scanner/phase2/run`

Required action:

- run against the live watchlist
- inspect returned setup rows
- verify:
  - `symbol`
  - `regime`
  - `current_price`
  - `atr`
  - structural metadata

Acceptance criteria:

- valid response body
- reasonable setup payloads
- no runtime dependency errors

### 7. Validate `/superbrain/run-once` with real scanner-produced data

Endpoint:

- `/superbrain/run-once`

Required action:

- run with:
  - live Phase 2 scanner input
  - realistic account state
  - `auto_approve=false`
- confirm the graph can:
  - scan
  - evaluate
  - produce pending review or completed decisions

Acceptance criteria:

- `scanner_source = "phase2_scanner"` when scanner input is not supplied manually
- evaluations returned
- candidate or pending-review payloads structurally valid

### 8. Validate review resume flow

Endpoint:

- `/superbrain/review-resume`

Required action:

- trigger at least one interrupted thread
- resume it with a human approval payload
- confirm the thread returns a usable execution candidate

Acceptance criteria:

- thread resume succeeds
- audit trail contains both the initial evaluation and the resume event
- returned candidate is structurally valid

### 9. Validate risk recheck in the ops layer

Endpoint:

- `/services/ops/ops/risk/evaluate`

Required action:

- pass approved candidate context into the risk service
- compare returned sizing and gating decision against the LangGraph output

Acceptance criteria:

- can_open_new_trade is coherent with account state
- position size is populated when expected
- no drift between graph assumptions and ops risk results

### 10. Validate first supervised Match-Trader transmission

Endpoint:

- `/services/ops/ops/execution/transmit-limit-order`

Required action:

- use a simulated Maven account
- place one very small supervised order
- verify it appears on the platform

Acceptance criteria:

- order transmitted successfully
- order visible in Match-Trader
- resulting platform state query is correct

## Workstream 4: TP1 / TP2 Execution Gap

### 11. Decide how live execution will honor the backtested exit model

Current issue:

- the backtests model fractional exits:
  - 50% at TP1
  - 50% at TP2
  - stop moved to breakeven after TP1
- the live execution bridge currently does not fully enforce that multi-stage exit behavior

Decision options:

- Option A:
  - implement two-leg live execution plus state tracking
- Option B:
  - intentionally simplify live trading to TP1-only
  - revalidate backtests under that simplified exit model

Recommendation:

- choose one explicitly
- do not leave the live behavior ambiguous

Acceptance criteria:

- documented live exit model
- implementation or backtest adjustment completed

## Workstream 5: AI / Specialist Maturity

### 12. Keep deterministic fallback, but begin incremental live specialist upgrades

Current reality:

- deterministic reasoning is still the default
- this is acceptable for safety and development
- the live provider layer is now working

Required action:

- keep `hybrid` mode available
- roll out real external data one specialist at a time
- do not flip everything to live LLM mode at once

Recommended order:

1. macro
2. technical
3. tokenomics
4. fundamentals
5. live LLM routing for the highest-value node only after the data path is stable

Acceptance criteria:

- each domain validated independently
- fallback path still works
- no regressions in the graph topology

## Workstream 6: Testing And Guardrails

### 13. Add regression tests for the corrected weak points

Required additions:

- `ai/inference.py` DeepSeek response indexing
- `execution/match_trader.py` missing-positions handling
- scanner import/runtime coverage in the LangGraph environment
- at least one `/superbrain/run-once` integration test using injected scanner rows

Acceptance criteria:

- tests added
- tests green

### 14. Add a simple account-state oversight endpoint

Recommended endpoint:

- `/ops/account/state`

Purpose:

- expose:
  - current equity
  - open trade count
  - distance to 3% trailing drawdown limit
  - current high-watermark

Why this matters:

- the operator needs a fast operational safety view
- this is more urgent than adding new feature branches

Acceptance criteria:

- endpoint available
- values consistent with broker state and high-watermark memory

## 30-Day Execution Plan

### Week 1

- fix `ai/inference.py`
- harden `execution/match_trader.py`
- refresh LangGraph runtime
- verify scanner endpoint works in the LangGraph platform runtime

### Week 2

- run real `/superbrain/run-once` with live scanner data
- validate pending-review and completed-decision flows
- validate `/superbrain/review-resume`

### Week 3

- validate risk recheck against approved candidates
- test Match-Trader auth and platform details on the simulated account
- transmit one supervised small order

### Week 4

- resolve TP1/TP2 live-exit decision
- either implement split-exit behavior or simplify live exits and document the deviation
- run one full supervised cycle from scan to order transmission with audit retention

## Stop-Doing List

For the next phase, avoid:

- adding new specialist roles
- adding new orchestration surfaces
- redesigning n8n again before the live path is validated
- expanding the portfolio search pipeline further before the execution loop is proven

## Success Definition

The next milestone is not “more architecture.”

The next milestone is:

- one clean live scanner run
- one clean super-brain evaluation cycle
- one clean review/resume cycle
- one clean risk check
- one clean supervised order transmission

Once that sequence works end to end, the project moves from “well-built system” to “validated operational trading platform.”
