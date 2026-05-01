# Comprehensive Benchmarking And Infrastructure Framework For Autonomous Multi-Agent Trading Systems

## Purpose

This document turns the benchmarking research into a practical TRADE_ORACLE execution plan.

It has two jobs:

1. define the phased benchmark framework for the Super Brain
2. define the phased n8n incorporation and hosting plan

The goal is not abstract completeness.
The goal is to give TRADE_ORACLE the smallest serious framework that can:

- measure whether the Super Brain adds value
- measure whether the live operating loop is reliable
- preserve operator visibility during forward testing
- host n8n in a cheap, durable, always-on environment
- move from one-off demo success into controlled, measurable forward testing

## Current Starting Point

TRADE_ORACLE is already past the architecture-only stage.

What is already true:

- the LangGraph Super Brain exists
- the MCP, ops, brain, super-brain, and platform services exist
- pending review and review resume work
- audit persistence exists
- FTMO MT5 authentication works
- broker symbol mapping works
- the execution bridge has already placed broker-accepted demo pending orders
- the full `scanner -> superbrain -> review -> risk -> transmit` path has already been demonstrated

So the core question has changed.

The core question is no longer:

- can the architecture work at all?

The core question is now:

- can we prove that it is better than a simpler baseline and reliable enough to trust?

That is what this framework is for.

## Infrastructure Decision

### Decision

Use **Google Compute Engine**, not Cloud Run, as the first real n8n hosting target.

### Why This Is The Right Choice

n8n in TRADE_ORACLE is intended to be:

- always on
- listening for webhooks
- running scheduled workflows
- persisting operator context such as `run_id` and `thread_id`
- coordinating human review and resume flows
- acting as the outer scheduler and notifier

That is a much cleaner fit for a small always-on VM than for a request-driven container platform.

### Official Hosting Facts

As of **April 25, 2026**, Google Cloud’s official free-tier documentation says Compute Engine free usage includes:

- `1` non-preemptible `e2-micro` VM per month
- only in:
  - `us-west1`
  - `us-central1`
  - `us-east1`
- `30 GB-months` of standard persistent disk
- `1 GB` of outbound data transfer from North America per month

Cloud Run also has a free tier, but its default model is still request-based and scale-oriented rather than server-oriented. Google’s own documentation also notes that if you keep minimum instances warm, those idle instances incur billing costs. That is not fatal, but it makes Cloud Run a worse first home for an always-on orchestration tool like n8n.

n8n’s own docs recommend Docker for most self-hosting needs and provide a Docker Compose path specifically for running n8n on a Linux server.

### Practical Conclusion

For TRADE_ORACLE:

- **n8n first target:** Google Compute Engine `e2-micro`
- **OS:** Ubuntu LTS
- **runtime:** Docker Engine + Docker Compose
- **storage:** persistent disk mounted to the n8n data volume
- **network model:** one always-on public endpoint with HTTPS

Cloud Run is still useful later for stateless services if we want it.
It is just not the right first target for n8n.

### Reference Sources

- Google Cloud Free Tier:
  - `https://docs.cloud.google.com/free/docs/free-cloud-features`
- Cloud Run:
  - `https://cloud.google.com/run`
  - `https://cloud.google.com/run/docs/configuring/min-instances`
- n8n Docker:
  - `https://docs.n8n.io/hosting/installation/docker/`
- n8n Docker Compose:
  - `https://docs.n8n.io/hosting/installation/server-setups/docker-compose/`

## Role Separation

Before defining phases, the system roles must stay clear.

### What The Platform Owns

The TRADE_ORACLE platform should remain the primary intelligent boundary.

It owns:

- scanning
- LangGraph decisioning
- pending review generation
- review resume
- risk checks
- execution transmission
- benchmark event capture inside the trading runtime

### What n8n Owns

n8n should be the outer orchestration layer.

It owns:

- schedules
- health checks
- notifications
- human-review alert delivery
- storage of `run_id`, `thread_id`, and review metadata
- benchmark facts that exist outside the platform
- operational glue between people and services

### What n8n Should Not Become

n8n should not become:

- the decision engine
- the place where trade logic is duplicated
- the place where scanner rules are reimplemented
- the source of truth for trading outcomes

That split keeps the architecture clean and benchmarkable.

## Benchmarking Philosophy

The benchmark system must answer four separate questions.

### Reliability

Does the pipeline operate consistently without breaking?

### Decision Quality

Does the Super Brain improve the trade set relative to a simpler baseline?

### Trading Performance

Do approved and transmitted trades produce acceptable forward results?

### Operational Safety

Does the system stay within broker, account, and drawdown constraints while it runs?

If the benchmark layer cannot answer all four, it is incomplete.

## Benchmark Variants

At minimum, the benchmark framework must compare two variants.

### Variant A: Scanner Baseline

- Phase 2 scanner
- position sizing
- broker symbol preflight
- no Super Brain filtering

### Variant B: Super Brain Path

- Phase 2 scanner
- Super Brain
- pending review and review resume when required
- position sizing
- broker symbol preflight

The main benchmark question is:

- does Variant B improve the final transmitted trade set enough to justify its complexity?

## Benchmark Framework Phases

## Phase B0: Metric Freeze And Vocabulary Lock

### Goal

Freeze the benchmark vocabulary before implementation starts.

### Deliverables

- one canonical list of benchmark metrics
- one canonical list of event types
- one canonical definition of a cycle
- one canonical definition of benchmark variants

### Definition Of A Cycle

A **cycle** is one end-to-end opportunity flow:

- scanner run
- candidate generation
- Super Brain decision or baseline pass-through
- review decision if required
- risk result
- broker preflight
- optional transmission
- optional fill or close outcome later

### Metric Families

#### Reliability Metrics

- scanner success rate
- Super Brain run success rate
- review-resume success rate
- risk endpoint success rate
- broker preflight success rate
- transmit success rate
- broker acceptance rate
- audit completeness rate
- reconnect and restart recovery rate

#### Decision Metrics

- scanner setups per cycle
- approval rate
- pass rate
- pending-review rate
- human approval rate
- provider fallback rate
- veto reasons by category
- confidence distribution

#### Trading Metrics

- transmitted order count
- filled order count
- cancelled order count
- win rate
- loss rate
- expectancy per transmitted trade
- average `R`
- hold duration
- drawdown
- consistency score

#### Safety Metrics

- distance to trailing-failure at cycle open
- distance to trailing-failure after transmission
- active trade count
- warning-buffer trigger count
- broker-side rejection count

### Exit Criteria

- all names are frozen
- all teams and flows use the same event language
- no benchmark storage implementation begins before naming is stable

## Phase B1: Benchmark Event Model And Store

### Goal

Create a persistent benchmark event layer focused on measurement rather than trace-only logging.

### Deliverables

- benchmark event schema
- benchmark event store
- event writer hooks
- cycle ID strategy

### Minimum Event Types

- `scanner_cycle`
- `candidate_generated`
- `super_brain_run`
- `super_brain_resume`
- `risk_check`
- `symbol_preflight`
- `order_transmit_attempt`
- `order_transmit_result`
- `order_fill_update`
- `order_close_update`
- `cycle_summary`
- `incident`

### Required Event Fields

Every benchmark event should carry:

- `cycle_id`
- `run_id`
- `thread_id` where relevant
- `timestamp_utc`
- `symbol`
- `execution_backend`
- `benchmark_variant`
- `status`
- `decision`
- `request_id` if present

### Important Principle

This does **not** replace the audit store.

The audit store is for traceability.
The benchmark store is for measurement.

### Exit Criteria

- one supervised cycle produces a full benchmark trail
- benchmark events persist independently from the audit log

## Phase B2: Platform Instrumentation

### Goal

Wire benchmark events into the actual runtime boundaries that matter.

### Surfaces To Instrument First

- `/superbrain/run-once`
- `/superbrain/review-resume`
- `/services/ops/ops/risk/evaluate`
- `/services/ops/ops/account/state`
- `/services/ops/ops/execution/transmit-limit-order`

### Deliverables

- event writes from all primary decision surfaces
- transmission attempt and result capture
- broker ticket capture when accepted

### Exit Criteria

- benchmark storage is populated by real platform calls, not only synthetic tests

## Phase B3: Scoreboard And Query Surface

### Goal

Expose benchmark data in a way an operator can actually use.

### Deliverables

- summary endpoint
- recent cycles endpoint
- per-symbol view
- per-variant comparison view

### Minimum Summary Views

#### System Summary

- total cycles
- total scanner setups
- total approved candidates
- total transmitted orders
- broker acceptance rate
- provider fallback rate

#### Reliability Summary

- success and failure counts by endpoint
- incident counts by category
- recovery success rate

#### Trading Summary

- wins
- losses
- expectancy
- average `R`
- drawdown

#### Variant Summary

- scanner-only candidate set
- Super Brain filtered candidate set
- delta in approval rate
- delta in transmitted orders
- delta in forward expectancy

### Exit Criteria

- an operator can answer “how is the system doing?” without reading raw logs

## Phase B4: Baseline And Ablation Harness

### Goal

Prove whether the Super Brain adds value, and identify which parts help or hurt.

### Deliverables

- scanner-only baseline mode
- Super Brain benchmark mode
- optional ablation modes such as:
  - internal-only specialist mode
  - hybrid provider mode
  - no macro veto mode
  - no tokenomics veto mode

### What Must Stay Constant

Do not change:

- broker
- account rules
- symbol universe
- risk policy
- transmission mechanics

Only change the decision layer being benchmarked.

### Comparison Set

- candidate count
- approval count
- transmitted order count
- fill count
- expectancy
- maximum adverse excursion
- maximum favorable excursion

### Exit Criteria

- we can show whether the Super Brain improves the final trade set
- we can identify if a specific specialist layer is helping, neutral, or hurting

## Phase B5: Forward-Testing Journal

### Goal

Create a human-readable log of every supervised cycle.

### Deliverables

- cycle journal table or file
- per-cycle narrative summary
- operator notes field

### Required Journal Fields

- date and time
- benchmark variant
- watchlist
- scanner setups found
- approved candidates
- rejected candidates
- rejection reasons
- whether review was required
- whether review approved
- whether risk approved
- whether broker accepted
- ticket ID if transmitted
- fill and close outcome later
- operator comments

### Exit Criteria

- every supervised cycle can be reviewed without reconstructing it from raw logs

## Phase B6: Statistical Layer

### Goal

Move from operational counts to actual performance inference once enough forward data exists.

### Do Not Start Until

- supervised forward cycles are no longer tiny in number
- enough transmitted trades exist to justify analysis

### Deliverables

- rolling expectancy
- rolling win rate
- rolling `R` distribution
- drawdown distribution
- bootstrap equity cone analysis
- simple ruin estimate

### Important Constraint

Do not pretend significance exists before enough trades exist.

The first job is not to draw fancy charts.
The first job is to collect enough clean data.

### Exit Criteria

- the system can produce a real forward-testing performance memo

## Phase B7: Reliability Burn-In

### Goal

Stress the operating system, not just the trade logic.

### Required Tests

- MT5 terminal restart during supervised operation
- platform service restart
- n8n restart
- provider failure
- stale thread resume
- duplicate transmit protection
- symbol mapping drift detection
- webhook replay protection

### Deliverables

- incident catalog
- recovery procedures
- MT5 operator playbook
- n8n operator playbook

### Exit Criteria

- no critical failure mode remains unknown

## n8n Incorporation Phases

## Phase N0: Topology Freeze

### Goal

Freeze the correct role of n8n before deployment starts.

### Deliverables

- one written statement of system ownership boundaries
- one approved topology diagram

### Exit Criteria

- the platform service remains the primary intelligent boundary
- n8n is accepted as the outer orchestration layer

## Phase N1: Local n8n Validation

### Goal

Prove that the existing n8n contract files work against the local platform.

### Deliverables

- import:
  - `contracts/n8n_4h_master_orchestrator_platform.workflow.json`
- validate local calls to:
  - `/system/health`
  - `/system/capabilities`
  - `/superbrain/run-once`
  - `/superbrain/review-resume`
  - `/services/ops/ops/account/state`
  - `/services/ops/ops/risk/evaluate`
  - `/services/ops/ops/execution/transmit-limit-order`

### Exit Criteria

- local n8n can call the live local platform successfully

## Phase N2: Review-Resume Workflow Separation

### Goal

Handle pending-review threads correctly and durably.

### Deliverables

- scheduled workflow
- separate review webhook workflow
- persistence for:
  - `run_id`
  - `thread_id`
  - `review_context`
  - candidate summary
  - operator response

### Exit Criteria

- n8n can store a pending-review thread and resume it later without manual reconstruction

## Phase N3: Benchmark Sink Integration

### Goal

Make n8n contribute to the benchmark framework rather than just call the platform.

### Why This Matters

Some benchmark facts live outside the platform:

- alert delivery success
- operator approval latency
- operator notes
- messaging failures
- webhook resume metadata

### Deliverables

- n8n per-cycle benchmark summary emission
- operator-approval metadata capture
- alert result logging

### Exit Criteria

- n8n-side events and platform-side events can be joined into one cycle record

## Phase N4: Google Compute Engine Bootstrap

### Goal

Provision the always-on host correctly before we deploy n8n.

### Target Shape

- Google Compute Engine
- `e2-micro`
- Ubuntu LTS
- free-tier eligible US region
- static external IP if feasible

### Deliverables

- Google Cloud project created
- billing enabled
- VM created in a free-tier eligible region
- firewall rules defined
- SSH access working
- OS updates applied

### Exit Criteria

- the VM exists and is reachable
- the VM matches the free-tier assumptions

## Phase N5: Dockerized n8n Deployment

### Goal

Deploy n8n onto the GCE VM in the simplest durable form.

### Deployment Shape

- one `n8n` container
- persistent volume for `/home/node/.n8n`
- environment file outside the repo
- timezone configured
- task runners enabled

### Deliverables

- Docker installed
- Docker Compose installed
- `docker-compose.yml` created
- persistent data directory created
- n8n boots on the VM

### Exit Criteria

- n8n survives restart
- credentials and workflow state persist

## Phase N6: Secure Ingress And DNS

### Goal

Expose n8n safely to the outside world.

### Deliverables

- subdomain created
- DNS A record pointed at the VM
- reverse proxy configured
- HTTPS enabled
- authentication enforced
- firewall restricted to required ports only

### Exit Criteria

- webhook endpoints are reachable
- the n8n UI is not exposed insecurely

## Phase N7: Remote Platform Integration

### Goal

Point hosted n8n at the real TRADE_ORACLE platform target.

### Deliverables

- environment variables for:
  - `TRADE_ORACLE_PLATFORM_BASE_URL`
  - `TRADE_ORACLE_PLATFORM_API_KEY`
- hosted health-check workflow
- hosted `run-once` test
- hosted `review-resume` test

### Exit Criteria

- hosted n8n can orchestrate the remote platform successfully

## Phase N8: Production-Like Operator Flow

### Goal

Run the same supervised workflow from hosted n8n that we intend to use during forward testing.

### Deliverables

- schedule-based main workflow
- human-review webhook workflow
- alert integration
- benchmark sink integration
- retry and incident behavior documented

### Exit Criteria

- hosted n8n is not merely installed
- it is actively orchestrating the intended operator flow

## Combined Recommended Sequence

Do not build everything at once.

The recommended order is:

1. `B0` metric freeze and vocabulary lock
2. `B1` benchmark event model and store
3. `B2` platform instrumentation
4. `B3` scoreboard and query surface
5. `N0` topology freeze
6. `N1` local n8n validation
7. `N2` review-resume workflow separation
8. `N3` benchmark sink integration
9. `N4` Google Compute Engine bootstrap
10. `N5` Dockerized n8n deployment
11. `N6` secure ingress and DNS
12. `N7` remote platform integration
13. `B4` baseline and ablation harness
14. `B5` forward-testing journal
15. `B6` statistical layer
16. `B7` reliability burn-in
17. `N8` production-like hosted operator flow

## Immediate Recommended Next Steps

The highest-leverage next steps are:

1. implement **B0** and **B1**
2. validate the existing n8n workflow locally under **N1**
3. only after local workflow success, provision GCE under **N4**

### Why This Order Is Right

If we host n8n before benchmark capture exists, we create orchestration without measurement.

If we build statistical dashboards before event capture exists, we create analysis without data.

If we deploy hosted n8n before local workflow validation succeeds, we create infrastructure before behavior is proven.

The clean order is:

- measure first
- validate locally second
- host third

## Practical 14-Day Execution Map

### Days 1-2

- complete `B0`
- freeze metric and event vocabulary

### Days 3-4

- complete `B1`
- create the benchmark store and cycle IDs

### Days 5-6

- complete `B2`
- instrument the main platform endpoints

### Days 7-8

- complete `B3`
- expose a basic benchmark scoreboard

### Days 9-10

- complete `N1`
- validate the existing n8n contract locally

### Days 11-12

- complete `N2`
- separate schedule and review-resume workflows

### Days 13-14

- complete `N4` and `N5`
- provision the GCE VM
- deploy Dockerized n8n

This does not finish the entire framework.
It does finish the first serious measurement-and-orchestration foundation.

## Bottom Line

The correct first hosting path is:

- **Google Compute Engine `e2-micro` for n8n**

The correct benchmark path is:

- **persistent event capture before fancy analytics**

The correct orchestration path is:

- **platform remains the intelligent boundary, n8n remains the outer coordinator**

The correct execution order is:

- **benchmark foundation first**
- **local n8n validation second**
- **hosted n8n third**

That is the cleanest path from:

- one successful demo pipeline

to:

- a measured, repeatable, and operationally trustworthy trading system
