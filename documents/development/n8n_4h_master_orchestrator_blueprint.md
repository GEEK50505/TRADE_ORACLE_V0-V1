# 4H Master Orchestrator Blueprint

## Purpose

This blueprint refactors the current n8n "4H Master Orchestrator" into a cleaner, platform-first workflow aligned with the TRADE_ORACLE LangGraph deployment model.

The key architectural shift is:

- n8n becomes the outer scheduler, notifier, audit layer, and human-review coordinator
- the TRADE_ORACLE platform service becomes the single intelligent HTTP boundary
- LangGraph handles decision-making, interruption, and resume
- FastAPI ops endpoints handle optional external risk recheck and execution

This matches the current platform surface exposed by:

- `/superbrain/run-once`
- `/superbrain/review-resume`
- `/services/ops/ops/risk/evaluate`
- `/services/ops/ops/execution/transmit-limit-order`
- `/system/health`
- `/system/capabilities`
- `/system/benchmark/summary`
- `/system/benchmark/cycles/recent`

## Core Design Principles

1. One primary entrypoint for n8n

- Use the platform service as the main boundary.
- Avoid calling internal sub-workflows for LangGraph unless there is a strong operational reason.
- Prefer `HTTP Request` nodes over `Execute Workflow` when crossing service boundaries.

2. State-aware human review

- LangGraph is not a simple yes/no node.
- It can return:
  - `pending_review`
  - `completed`
  - `no_trade`
- n8n must persist `thread_id` and `review_context` for interrupted cases.

3. Risk is layered, not duplicated blindly

- LangGraph already performs internal risk guardrails in the gatekeeper.
- The n8n risk node should be treated as an optional defense-in-depth recheck before execution.

4. Execution must be idempotent

- Scanner, health, and analysis requests can retry.
- Order transmission must not be blindly retried without an idempotency key or downstream execution-state check.

5. Logging is first-class

- Every run should have a `run_id`.
- Every scheduled cycle should also have a `cycle_id`.
- Every benchmarked orchestration path should carry a `benchmark_variant`.
- Every external request should carry `X-Request-ID`.
- n8n should persist summary records for:
  - scanner source
  - evaluation result
  - pending review payload
  - risk recheck result
  - execution result
  - benchmark cycle outcome

## Recommended Production Workflow

### Workflow Name

`TRADE_ORACLE 4H Master Orchestrator`

### Node-by-Node Structure

#### 1. Schedule Every 4 Hours

Type:

- `Schedule Trigger`

Purpose:

- Launch the main cycle every 4 hours.

Recommendations:

- Keep UTC.
- Add overlap protection outside the workflow if possible.
- Record the schedule timestamp immediately.

Suggested name:

- `TRG Schedule Every 4 Hours`

#### 2. Resolve Runtime Context

Type:

- `Code` or `Set`

Purpose:

- Build shared runtime values once for the whole execution.

Recommended fields:

- `run_id`
- `cycle_id`
- `benchmark_variant`
- `scheduled_at_utc`
- `platform_base_url`
- `platform_api_key`
- `execution_mode`
- `auto_approve`
- `enable_live_llm`
- `watchlist`

Suggested name:

- `CTX Resolve Runtime Context`

#### 3. Platform Health Check

Type:

- `HTTP Request`

Endpoint:

- `GET /system/health`

Purpose:

- Fail fast if the platform service is unavailable.

Suggested name:

- `PRECHECK Platform Health`

#### 4. Resolve Account Context

Type:

- `Set`, `Code`, or external account sync node

Purpose:

- Provide:
  - `current_balance`
  - `highest_equity`
  - `active_trades_count`

Suggested name:

- `CTX Resolve Account State`

#### 5. Build Super Brain Request

Type:

- `Code`

Purpose:

- Construct one canonical payload for `/superbrain/run-once`.

Required benchmark-aware fields:

- `run_id`
- `cycle_id`
- `benchmark_variant`

Suggested name:

- `BRAIN Build Run Once Request`

#### 6. Call LangGraph Super Brain

Type:

- `HTTP Request`

Endpoint:

- `POST /superbrain/run-once`

Purpose:

- Let the platform run scanner + LangGraph evaluation in one step.

Important:

- pass `run_id`, `cycle_id`, and `benchmark_variant` in the request body
- also send `X-Request-ID={{run_id}}`

Suggested name:

- `BRAIN Run Super Brain`

#### 7. Normalize Super Brain Output

Type:

- `Code`

Purpose:

- Parse:
  - `result.evaluations`
  - `result.candidates`
- Extract:
  - `run_id`
  - `cycle_id`
  - `benchmark_variant`
  - top candidate
  - first pending review
  - counts
  - summary flags

Suggested name:

- `BRAIN Normalize Result`

#### 8. Pending Review?

Type:

- `IF`

Condition:

- `pending_review_count > 0`

Purpose:

- Separate interrupted LangGraph threads from completed decisions.

Suggested name:

- `BRAIN Pending Review?`

#### 9. Prepare OpenClaw Review Alert

Type:

- `Code`, `Set`, then messaging node

Purpose:

- Build the human-review message from:
  - `run_id`
  - `cycle_id`
  - `thread_id`
  - `review_context`
  - `final_decision`
  - `risk_guardrails`
  - `position_sizing`

Suggested name:

- `ALERT Prepare OpenClaw Review`

Important recommendation:

- Make human review a separate workflow or webhook-driven resume path.
- Do not try to keep one long scheduled workflow waiting indefinitely if you can avoid it.

#### 10. Resume Review Workflow

Type:

- Separate webhook-driven workflow

Purpose:

- Receive human decision from OpenClaw or Telegram action.
- Call `/superbrain/review-resume`.

Required fields to persist and resend:

- `thread_id`
- `run_id`
- `cycle_id`
- `benchmark_variant`

Suggested workflow name:

- `TRADE_ORACLE OpenClaw Review Resume`

#### 11. Executable Candidate Ready?

Type:

- `IF`

Condition:

- `top_candidate.execute_trade == true`
- `top_candidate.execution_status == "approved"`

Suggested name:

- `EXEC Candidate Approved?`

#### 12. Optional Risk Recheck

Type:

- `HTTP Request`

Endpoint:

- `POST /services/ops/ops/risk/evaluate`

Purpose:

- Defense-in-depth check before execution.

Required benchmark-aware fields:

- `symbol`
- `run_id`
- `cycle_id`
- `benchmark_variant`

Suggested name:

- `RISK Optional Recheck`

#### 13. Risk Passed?

Type:

- `IF`

Condition:

- `result.can_open_new_trade == true`
- `result.position_size exists`

Suggested name:

- `RISK Passed?`

#### 14. Build Execution Request

Type:

- `Code`

Purpose:

- Convert candidate + risk result into the exact execution payload expected by the ops service.

Required benchmark-aware fields:

- `execution_backend`
- `run_id`
- `cycle_id`
- `benchmark_variant`
- `size_mode`

Suggested name:

- `EXEC Build Order Payload`

#### 15. Call Execution API

Type:

- `HTTP Request`

Endpoint:

- `POST /services/ops/ops/execution/transmit-limit-order`

Critical note:

- Do not configure aggressive automatic retries here.
- include `X-Request-ID={{run_id}}` for traceability

Suggested name:

- `EXEC Transmit Limit Order`

#### 16. Send Alerts

Split alerts by event type:

- human review requested
- no trade
- risk rejected
- order transmitted
- execution failure

#### 17. Persist Audit Record

Type:

- database node, HTTP log sink, or storage adapter

Recommended fields:

- `run_id`
- `cycle_id`
- `benchmark_variant`
- schedule timestamp
- scanner row count
- evaluation count
- pending review count
- chosen candidate
- risk result
- execution result

Suggested name:

- `AUDIT Persist Cycle Record`

#### 18. Optional Benchmark Pullback

Type:

- `HTTP Request`

Recommended endpoints:

- `GET /system/benchmark/summary`
- `GET /system/benchmark/cycles/recent`
- `GET /system/benchmark/cycle/{cycle_id}`

Purpose:

- verify that the scheduled cycle produced a benchmark trail
- let n8n persist operator-facing cycle summaries without reading raw sqlite files

## Naming Standard

Use prefixes consistently:

- `TRG` trigger
- `CTX` context
- `PRECHECK` health/readiness
- `BRAIN` LangGraph platform calls
- `RISK` optional external risk gates
- `EXEC` execution
- `ALERT` human/operator notifications
- `AUDIT` persistence/logging

## Data Contract Mapping

Replace legacy checks like:

- `data.authorization == true`
- `data.risk_status == "APPROVED"`

With current platform fields:

- pending review:
  - `result.evaluations[*].status == "pending_review"`
- candidates:
  - `result.candidates`
- approved candidate:
  - `candidate.execute_trade == true`
  - `candidate.execution_status == "approved"`
- risk pass:
  - `result.can_open_new_trade == true`
  - `result.position_size != null`
- execution success:
  - `result.order_transmitted == true`

## Error Handling Recommendations

Safe to retry:

- `/system/health`
- `/superbrain/run-once`
- `/superbrain/review-resume`
- `/services/ops/ops/risk/evaluate`

Retry carefully or not automatically:

- `/services/ops/ops/execution/transmit-limit-order`

## Final Recommended Topology

### Main Scheduled Workflow

1. Schedule
2. Resolve runtime context
3. Health check
4. Resolve account state
5. Call Super Brain
6. Normalize output
7. Branch:
   - pending review
   - approved candidate
   - no trade
8. Optional risk recheck
9. Execution
10. Alert and audit

### Separate Review Resume Workflow

1. Receive OpenClaw approval/rejection
2. Load saved `thread_id`
3. Call `/superbrain/review-resume`
4. Optional risk recheck
5. Execution
6. Alert and audit

## Bottom Line

The cleanest production shape is:

- n8n as the outer scheduler and human-review coordinator
- the platform service as the primary TRADE_ORACLE boundary
- LangGraph as the decision engine
- ops endpoints as execution-facing utilities

For the current phase, the benchmark-aware local validation rule is:

- every n8n-scheduled cycle must emit `run_id`, `cycle_id`, and `benchmark_variant`
- those fields must be passed into `run-once`, `review-resume`, `risk`, and `transmit-limit-order`
- local validation is only complete when `/system/benchmark/cycle/{cycle_id}` shows the full trail

That is cleaner, more durable, and much closer to how the current codebase is already built.
