# TRADE_ORACLE Live Demo Phased Plan

## Objective

Get TRADE_ORACLE to a supervised live demo state as fast as possible without expanding scope.

The target is not "full autonomous production."
The target is:

- scanner working
- super-brain evaluating real setups
- human review working
- risk checks working
- execution bridge validated
- audit trail intact
- one supervised live demo flow completed

## Operating Principle

No new architecture unless it directly unblocks the live demo.

For the next stretch:

- stop feature expansion
- fix correctness issues
- align runtime environments
- validate the real operational path

## Phase 0: Scope Lock And Critical Hardening

### Goal

Remove the smallest but highest-risk correctness issues before touching the live validation loop.

### Scope

1. Write and freeze the live-demo plan
2. Fix the DeepSeek response parsing bug
3. Harden Match-Trader position counting
4. Add regression coverage for both fixes

### Deliverables

- `documents/development/live_demo_phased_plan.md`
- `ai/inference.py` fixed
- `execution/match_trader.py` hardened
- targeted regression tests added and passing

### Exit Criteria

- DeepSeek response parsing uses `choices[0].message.content`
- Match-Trader handles missing `positions`
- targeted tests pass

## Phase 1: Runtime Alignment And Scanner Activation

### Goal

Make the actual LangGraph/platform runtime capable of running the real scanner path.

### Scope

1. Refresh the LangGraph runtime from `requirements.langgraph.txt`
2. Verify scanner imports in the real runtime
3. Verify `/services/ops/ops/scanner/phase2/run`
4. Verify platform container/runtime includes scanner dependencies

### Deliverables

- refreshed runtime
- scanner import proof
- successful Phase 2 scanner endpoint response

### Exit Criteria

- `from data.scanner import MarketScanner` succeeds in the runtime used for the platform
- `/services/ops/ops/scanner/phase2/run` returns `200`

## Phase 2: Super-Brain Live Validation

### Goal

Run the actual scanner-to-super-brain path with live setup data.

### Scope

1. Call `/superbrain/run-once` using real scanner-produced setups
2. inspect evaluations, candidates, and pending-review behavior
3. validate one `/superbrain/review-resume` cycle
4. confirm audit persistence across the cycle

### Deliverables

- one successful real `/superbrain/run-once` response
- one successful `/superbrain/review-resume` response
- saved reference payloads/results

### Exit Criteria

- end-to-end evaluation works with real scanner rows
- pending review can be resumed successfully
- audit endpoints show the full thread lifecycle

## Phase 3: Live Execution Safety Layer

### Goal

Prepare the system to submit a supervised live order safely.

### Scope

1. Add `/ops/account/state`
2. validate execution-backend authentication against the actual target environment
3. validate `get_platform_details()`
4. decide the initial TP model:
   - preferred default: TP1-only for the first live phase unless partial-close support is proven quickly
5. verify risk-check and execution payload alignment
6. begin the MT5 execution pivot without breaking the existing HTTP contract
7. validate broker symbol availability and live tick health before any transmit attempt

### Deliverables

- account oversight endpoint
- documented execution-backend auth behavior
- confirmed execution payload format
- chosen TP policy for live demo
  - current code default: `tp1_only`
- MT5 backend scaffold added behind the shared execution surface
- MT5 symbol-status endpoint and symbol-map workflow

### Exit Criteria

- operator can see distance to trailing DD limit
- broker auth/platform-details succeed
- broker symbol availability is confirmed for the intended demo asset
- execution payload is validated end to end

## Phase 4: Supervised Live Demo

### Goal

Run one small supervised live order through the full chain.

### Scope

1. scanner
2. super-brain
3. human approval
4. risk recheck
5. order transmission
6. post-trade audit inspection

### Deliverables

- one supervised live order attempt
- audit record for the full chain
- post-demo findings log

### Exit Criteria

- order is transmitted correctly
- account/platform state updates coherently
- audit trail is complete
- MT5 execution sizing is translated safely from strategy units into broker volume where needed

## Phase 5: Demo Stabilization

### Goal

Turn the one-off supervised demo into a repeatable supervised operating loop.

### Scope

1. n8n orchestration cleanup
2. review thread persistence verification
3. alerting refinement
4. repeated dry/supervised cycles

### Deliverables

- stable supervisory loop
- reusable operator playbook

### Exit Criteria

- multiple consecutive supervised cycles complete cleanly

## Phase 6: Forward Testing And Reliability Burn-In

### Goal

Prove the confirmed execution pipeline behaves reliably over repeated supervised cycles before any funded live deployment.

### Scope

1. run repeated forward-test cycles on the chosen demo venue
2. compare scanner candidates versus approved / transmitted trades
3. verify order lifecycle, audit continuity, and restart recovery
4. track broker symbol drift, quote health, and session-state failures
5. measure operational reliability over multiple market sessions

### Deliverables

- forward-testing journal
- reliability incident log
- broker-specific operator runbook
- decision memo on readiness for funded live deployment

### Exit Criteria

- repeated supervised cycles complete across multiple sessions
- no unresolved order-state or audit-state gaps remain
- execution venue behavior is understood well enough to justify funded testing

## Recommended Sequence

Do not skip phases.

The order is:

1. Phase 0
2. Phase 1
3. Phase 2
4. Phase 3
5. Phase 4
6. Phase 5
7. Phase 6

## Immediate Focus

Start now with Phase 0 only.

That means:

1. fix the two known correctness issues
2. add tests
3. stop there
4. then enter Phase 1 cleanly

## Current Progress Snapshot

- Phase 0: complete
- Phase 1: complete
- Phase 2: complete
- Phase 3: complete on the FTMO MT5 demo path
- Phase 4: complete for the first supervised FTMO demo transmit

What is already proven:

- MT5 auth works against the demo account
- `/services/ops/ops/account/state` returns coherent equity and drawdown-distance values
- `/services/ops/ops/execution/symbol-status` can resolve broker-side MT5 symbols and quote health
- mapped demo symbols confirmed so far:
  - `BTC/USDT -> BTC`
  - `ETH/USDT -> ETH`
  - `SOL/USDT -> SOL`
  - `XRP/USDT -> XXRP`
- the current MetaQuotes demo server does not expose quoted `AVAX/USDT` or `DOGE/USDT`
- a full pre-transmit supervised chain now works on a mapped symbol:
  - scanner
  - super-brain
  - pending review
  - review resume
  - risk recheck
  - MT5 symbol preflight
- the active next demo target is now `FTMO MT5`, replacing the earlier Eightcap planning path
- FTMO-specific next gate:
  - authenticate with the FTMO-provided MT5 terminal
  - audit actual FTMO crypto symbols
  - remap `AVAX/USDT` and `DOGE/USDT` only after the symbol inventory is confirmed
- FTMO demo symbol inventory discovered so far:
  - `BTCUSD`
  - `ETHUSD`
  - `XRPUSD`
  - `SOLUSD`
  - `AVAUSD`
  - `DOGEUSD`
- the FTMO MT5 full chain is now proven end to end:
  - `/superbrain/run-once` returned a real `pending_review` for `AVAX/USDT`
  - `/superbrain/review-resume` completed to an approved `BUY` candidate
  - `/services/ops/ops/risk/evaluate` passed
  - `/services/ops/ops/execution/transmit-limit-order` created broker-side pending orders on `AVAUSD`
- MT5 execution sizing now distinguishes:
  - strategy `units`
  - explicit `broker_volume`
- for FTMO crypto CFDs, TRADE_ORACLE now converts strategy units into broker volume before transmit

The strongest current candidate for the supervised MT5 demo is `XRP/USDT`, because it:

- produced a real `pending_review`
- resumed to an approved candidate
- passed risk recheck
- resolves to a quoted MT5 symbol on the demo account

What comes immediately after full-pipeline confirmation:

- yes, the next step is forward testing plus operational reliability work
- not full unsupervised production yet
- the first objective after pipeline confirmation is repeated supervised demo cycles on the chosen broker profile
