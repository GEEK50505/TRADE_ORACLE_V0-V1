# TRADE_ORACLE Super Brain Pivot To Forward Testing Start

## Purpose Of This Document

This document is a full-context handoff for NotebookLM or any external AI reviewer.
It explains, in chronological order, what was built from the moment TRADE_ORACLE
pivoted from a strong research/backtesting repository into a LangGraph-centered
"Super Brain" platform, all the way to the point where supervised forward testing
became the next responsible step.

This is not meant to be a short summary.
It is meant to capture the actual engineering sequence, the reasoning behind each
step, the critical issues discovered, the fixes that were applied, the milestones
that were proven in reality, and the exact state of the project at the threshold
of forward testing.

The intended audience is an AI system that does not have access to the original
chat history and therefore needs a faithful reconstruction of the build arc.

## High-Level Thesis

TRADE_ORACLE did not jump directly from backtests to live trading.
The repository went through a deliberate architectural pivot:

1. The strategy research and realistic backtesting track matured first.
2. The LangGraph "Super Brain" architecture was then built on top of that
   research as the decision engine.
3. The graph was wrapped in HTTP services so that n8n and external operators
   could use it safely.
4. Auditability, provider routing, and a platform service were added so the
   system became deployable rather than merely runnable.
5. Execution infrastructure was upgraded from Match-Trader assumptions toward
   a safer MetaTrader 5 path.
6. Real FTMO demo validation proved the chain end to end.
7. Only after a real broker-accepted demo order was placed did the project
   reach the point where forward testing and operational reliability became
   the correct next step.

The important point is that this progression was not cosmetic.
Each phase converted TRADE_ORACLE from a set of strong components into a more
coherent operating system.

## The Starting Point Before The Super Brain Pivot

Before the Super Brain build began, the repository already had substantial value.
The project was not starting from scratch.

The repository already contained:

- serious backtesting and optimization work
- a refined market scanner
- risk management logic designed around strict prop-firm-style drawdown rules
- a growing understanding of where earlier strategy assumptions had been too optimistic

The major strategic backdrop was that the user had already gone through the
painful but correct process of invalidating weaker portfolio conclusions and
rebuilding toward a more realistic deployment profile.
That mattered because the Super Brain was not being attached to fantasy alpha.
It was being attached to a strategy stack that had already survived a significant
reality check.

## Why The Pivot Happened

The pivot happened because the repository needed to grow from:

- research scripts
- a scanner
- backtest outputs
- semi-manual orchestration

into something that could actually operate as a system.

The desired end state was:

- a LangGraph-driven reasoning core
- typed state flowing through specialist nodes
- deterministic or live tool access through an MCP boundary
- HTTP services that n8n could call cleanly
- human review interrupts with durable resume
- a platform service that exposed one coherent deployment surface
- eventual supervised execution through a real broker path

This was not just a UX improvement.
It was an architectural transition from "components that can be run" to
"a platform that can be operated."

## Phase 1: Core LangGraph Scaffold

The first major step in the pivot was the creation of the LangGraph stateful
reasoning scaffold.

The core design decisions were:

- use a structured `TradeState`
- model specialist execution as graph nodes
- preserve a gatekeeper at the end that compresses the graph outputs into a
  deterministic, typed final decision
- model human review with LangGraph `interrupt()`

This was a strong foundational choice because it kept the reasoning layer
separate from the execution layer.
The graph was not allowed to become a broker script.
It remained a decision engine with explicit pause points and typed outputs.

The graph shape centered around:

- an intent-routing stage
- multiple specialist nodes
- a devil's-advocate stage
- a final Pydantic gatekeeper

Even at this early phase, the build direction was clear:
TRADE_ORACLE was not being redesigned as a simple single-prompt wrapper.
It was being shaped as a multi-stage reasoning flow with explicit control points.

## Phase 2: TradeState And Reducer Discipline

The next key step was getting the graph state model right.

That meant:

- defining explicit typed payload structures
- separating raw scanner setup data from downstream specialist outputs
- giving the graph channels the right reducer behavior

This was important because LangGraph is easy to misuse if multiple nodes update
shared state without clear merge rules.
So the build used explicit reducer semantics for:

- accumulating audit trail lines
- merging specialist outputs
- tracking completed agents

That choice prevented the graph from becoming nondeterministic or silently corrupting
its own state under parallel specialist execution.
This was one of the early signs that the build was being treated as production
architecture rather than a novelty experiment.

## Phase 3: LangGraph Runtime Packaging Split

As soon as the graph architecture became real, a dependency problem surfaced.

The repository already had an older trading/runtime dependency stack, while the
new LangGraph + FastAPI architecture wanted newer versions of packages like:

- `httpx`
- `websockets`

These requirements were not guaranteed to coexist safely with the older trading
side of the repo.

So the project introduced an explicit environment split:

- `requirements.txt` / `requirements.trading.txt`
- `requirements.langgraph.txt`

This was a critical hygiene step.
Without it, the repo risked devolving into an environment-conflict trap where
the LangGraph side and the old trading side constantly broke each other.

From that point on, the LangGraph stack had its own runtime identity.
That decision later paid off when more service-layer and provider-layer work
was added without contaminating the older environment assumptions.

## Phase 4: MCP Service And Specialist Tool Boundary

Once the core graph existed, it needed a real tool interface.

This led to the creation of the MCP service layer.

The MCP service introduced HTTP-backed specialist tools for:

- macro snapshot
- fundamental snapshot
- tokenomics snapshot
- technical snapshot
- risk guardrails

At first these were heavily deterministic or internal-context-backed.
That was still valuable because it created a stable tool boundary without
requiring live external providers on day one.

This was an architectural milestone because it meant:

- LangGraph could call tools through a clean boundary
- the tool layer could evolve independently
- external providers could later be added without changing graph topology

That separation turned out to be one of the strongest decisions in the whole build.

## Phase 5: Specialist Logic Became Structured Instead Of Decorative

An important intermediate step was strengthening the specialist outputs so they
were not just theatrical wrappers around scanner data.

The internal adapters began consuming and reflecting fields like:

- setup quality
- EMA cluster distance
- narrative tags
- portfolio context
- account state
- ATR and fib proximity

This meant the deterministic specialists started behaving like real rule-based
analytical layers instead of dummy placeholders.

At this stage the project still did not fully prove that the specialists created
independent alpha.
But it did prove that the graph was carrying structured reasoning, not merely
echoing the raw scanner payload back unchanged.

## Phase 6: Scanner Payload Adaptation Into The Graph

The Phase 2 scanner already existed, but its output shape was not yet the same
shape the graph wanted.

So the build introduced adapter logic that:

- converted scanner rows into LangGraph-ready raw setup payloads
- inferred or normalized required fields
- attached account state context to each setup

This was the bridge between the older quantitative pipeline and the new
LangGraph supervisor.

It mattered because the graph could now operate on real scanner-produced setups
rather than fixed demo payloads.
That was a major move from architecture toward actual runtime utility.

## Phase 7: LangGraph Orchestrator Layer

The graph itself was not enough.
It needed a stable orchestration wrapper that the rest of the platform could use.

That led to the creation of the LangGraph orchestrator layer, centered around:

- `LangGraphExecutionCandidate`
- `LangGraphEvaluationResult`
- `LangGraphSupervisorOrchestrator`

This layer did several important things:

- normalized outputs into service-friendly shapes
- preserved thread IDs
- supported pending-review state
- handled review resume
- converted LangGraph results into execution-ready candidate objects

This was the point where the graph stopped being "just a graph file" and started
becoming a usable subsystem in a broader platform.

## Phase 8: Brain Service

Once the orchestrator existed, the next logical step was making it callable.

This produced `api/trade_oracle_brain_service.py`.

The brain service exposed:

- one-setup evaluation
- batch evaluation
- review resume

This created the first true HTTP boundary for the LangGraph reasoning layer.
It also made the system n8n-friendly.

At this point, TRADE_ORACLE was no longer relying on direct Python-only access
to the graph for all control flows.
The graph was becoming a service.

## Phase 9: Super Brain Service

The next pivot was from a generic brain wrapper to a true "Super Brain" boundary.

The Super Brain service was designed to be the single intelligent entrypoint that
could:

1. run the scanner if needed
2. evaluate the resulting setups
3. return pending-review or final decisions
4. preserve thread IDs
5. resume review later

This service introduced the top-level routes:

- `/superbrain/run-once`
- `/superbrain/review-resume`

This was a huge alignment step with the eventual orchestration model.
Instead of n8n needing to know about internal graph details, it could talk to
one intelligent boundary.

That boundary became the center of the project’s platform-first philosophy.

## Phase 10: Platform Service

After the Super Brain existed, the system still needed one deployable surface.

That led to `api/trade_oracle_platform_service.py`.

The platform service packaged:

- the Super Brain
- the auxiliary brain routes
- the ops service
- the MCP service

under one top-level application.

It exposed:

- `/system/health`
- `/system/capabilities`
- `/superbrain/run-once`
- `/superbrain/review-resume`
- mounted `/services/ops`
- mounted `/services/mcp`
- mounted `/services/brain`

This was the moment where the architecture stopped looking like multiple local
development services and started looking like a single deployable product.

That mattered deeply for:

- n8n integration
- Railway/Render-style deployment
- operational introspection
- reducing orchestration complexity

## Phase 11: Audit Store And Durable Reviewability

The next major gap was observability.

The system could now reason and serve HTTP requests, but it needed durable traces.

So a persistent SQLite audit store was added through:

- `ai/trade_oracle_audit.py`

This enabled:

- event persistence
- thread-level trace lookup
- recent event lookup
- audit snapshots inside review payloads

The platform service then exposed:

- `/system/audit/recent`
- `/system/audit/thread/{thread_id}`

This turned human review from a fragile interrupt mechanic into something much
more operationally trustworthy.
At that point, interrupted decisions were no longer ephemeral.
They were inspectable, traceable, and queryable.

## Phase 12: Provider Routing And MCP Maturation

After auditability, the next architectural gap was live provider depth.

The deterministic internal adapters were useful, but the MCP layer needed a more
real provider abstraction.

This led to:

- a provider registry
- per-domain provider modes
- support for `internal`, `hybrid`, and `external`

The MCP service became capable of:

- using internal deterministic context
- attempting a live provider call
- falling back safely if the provider failed

This was important because it meant the graph could gain live external context
without being rewritten.

## Phase 13: Real Free Providers Selected And Wired

Once provider routing existed, the next question was which live providers to use.

The build chose:

- CoinGecko for macro, fundamentals, and tokenomics
- Binance public market data for technicals

Why these mattered:

- they were free
- they were public
- they aligned with the crypto domain of the strategy
- they could be integrated without introducing immediate paid infrastructure

The provider layer was then wired so that these providers worked through the MCP
service without requiring custom external URLs.

That meant the system could switch from internal placeholder context toward live
external market context while still preserving safe fallback behavior.

## Phase 14: Dead Proxy Discovery And `trust_env=False`

When the first live provider smoke tests were attempted, the macro and technical
routes appeared to succeed at the HTTP level but silently fell back to internal
adapters.

The real cause turned out to be environment contamination:

- `HTTP_PROXY`
- `HTTPS_PROXY`
- `ALL_PROXY`

were pointing to a dead local proxy.

This was a subtle but important failure mode.
The provider routing was correct, but outbound HTTP was being hijacked before it
reached CoinGecko or Binance.

The fix was to set `trust_env=False` in the relevant `httpx` clients.

That changed the provider layer from "architecturally wired but not truly live"
into "actually able to reach external providers."

This was one of the more mature infrastructure-debugging moments in the project.

## Phase 15: Live Provider Smoke Tests Succeeded

After the proxy fix, the platform successfully reached the live provider endpoints.

This proved:

- provider routing worked
- fallback logic worked
- the mounted MCP service behaved correctly
- the free live data integration was real

At this point, the Super Brain stack had:

- a graph
- a tool layer
- a platform
- auditability
- live provider plumbing

The remaining work was shifting from architecture toward operational validation.

## Phase 16: n8n Blueprint And Workflow Surface

Because n8n was intended to be the outer orchestrator, documentation and contract
work became important.

This led to:

- `documents/development/n8n_4h_master_orchestrator_blueprint.md`
- `contracts/n8n_4h_master_orchestrator_platform.workflow.json`

These artifacts defined:

- scheduler shape
- human review path
- risk recheck flow
- execution flow
- audit expectations
- state persistence requirements

This was not just documentation polish.
It was the first full operational description of how the platform should be used
in practice.

## Phase 17: Corrective Planning After External Review

At a later stage, a detailed corrective action planning cycle was done to
separate:

- what was already architecturally solid
- what was merely runtime drift
- what still needed proof

The corrective action work clarified that the main remaining gaps were not
fundamental design flaws.
They were mostly:

- environment alignment
- scanner runtime validation
- end-to-end operational proof
- execution validation

This was strategically important because it shifted the project mindset away from
"keep redesigning" and toward "finish validating."

## Phase 18: Live Demo Phased Plan

Once it was clear the build had moved into validation territory, the work was
reorganized as a phased live-demo plan.

This plan defined:

- Phase 0: scope lock and critical hardening
- Phase 1: runtime alignment and scanner activation
- Phase 2: Super Brain live validation
- Phase 3: execution safety layer
- Phase 4: supervised live demo
- Phase 5: demo stabilization
- Phase 6: forward testing and reliability burn-in

This mattered because it stopped the project from expanding sideways.
The mission became: prove the actual operational path.

## Phase 19: Phase 0 Hardening

The first live-demo phase focused on small but real correctness issues.

Two specific bugs were fixed:

1. DeepSeek response parsing:
   - the code incorrectly used `response.choices.message.content`
   - it was corrected to `response.choices[0].message.content`

2. Match-Trader position handling:
   - position counting was hardened so missing `positions` would not break the path

Regression tests were added for both.

This was not glamorous work, but it created a cleaner base before touching the
live runtime path.

## Phase 20: Runtime Alignment And Scanner Activation

The next major task was to make sure the actual LangGraph runtime could run the
real scanner path.

This involved:

- refreshing the dedicated LangGraph environment
- verifying scanner imports in that runtime
- getting the scanner endpoint to return `200`

This phase mattered because the Super Brain was only truly useful if it could
operate on real scanner-produced setups in the same runtime that the platform used.

Once this worked, the project passed the first major runtime alignment gate.

## Phase 21: Real Scanner To Super Brain Validation

After the runtime was aligned, the actual scanner-to-Super-Brain path was tested.

This proved that:

- `/superbrain/run-once` could use real scanner-produced rows
- real pending-review states were emitted
- `/superbrain/review-resume` completed successfully
- the audit trail preserved the lifecycle

This was one of the first times the architecture and the real runtime met cleanly.

That was a major milestone because the decision engine was no longer being validated
only through static tests or fake rows.
It was working on actual scanner output.

## Phase 22: `/ops/account/state` And The Execution Safety Layer

Before broker transmission could be treated seriously, the project needed a
better live account oversight boundary.

That led to the `/ops/account/state` endpoint.

Its purpose was to expose:

- current equity
- open trades
- high watermark
- drawdown distance
- warning-buffer state
- whether a new trade could be opened safely

This was operationally important because the project was designed around strict
prop-firm-style drawdown survival.
An execution path without live state oversight would have been reckless.

## Phase 23: Explicit Live TP Policy

Another important safety decision was making the live take-profit model explicit.

The code added:

- a configurable live TP mode
- an initial default of `tp1_only`

This was a practical choice.
The backtests modeled two-stage exits, but the first live supervised phase needed
the simplest reliable behavior possible.

That decision reduced complexity on the critical path while preserving a path
for future richer execution behavior.

## Phase 24: Match-Trader Versus MT5 Reality Check

At one point, the current code path and the documented architectural direction
were no longer aligned.

The historical docs increasingly favored MetaTrader 5 because:

- Match-Trader REST access had proved unreliable
- prop-firm-managed APIs were brittle
- MT5 gave a local IPC path instead of a more fragile web path

But parts of the repo still assumed Match-Trader.

That forced an important clarification:

- documented architectural intent: MT5
- actual implemented execution path at that moment: still partially Match-Trader

The project then deliberately pivoted the code toward MT5.

## Phase 25: MT5 Execution Scaffold

To support the pivot, the following execution-side work was added:

- `execution/mt5_bridge.py`
- `execution/runtime.py`
- shared execution-backend selection
- MT5 env configuration in settings
- MT5 support in the ops service
- MT5 support in the main loop

This made MT5 a first-class backend instead of a theoretical future target.

The important detail is that the default backend was not flipped recklessly.
The system was upgraded to support MT5 while preserving the existing structure
until validation proved the MT5 path.

## Phase 26: First Generic MT5 Demo Validation

The initial MT5 demo experiments were done against generic or non-final venues
like MetaQuotes demo paths.

These experiments were useful for proving:

- MT5 authentication mechanics
- symbol-status checks
- platform-details access
- account-state access

But they also revealed a critical mismatch:
generic demos did not necessarily expose the real crypto symbols the strategy wanted.

For example:

- some environments exposed ETF-like proxies instead of the actual intended crypto CFDs

This was a key learning moment:
execution plumbing alone is not enough.
The venue has to match the strategy.

## Phase 27: FTMO Demo As The Real Validation Venue

Because the long-term target was a prop-firm-like environment and the MT5 crypto
instrument set mattered, FTMO demo became the next serious validation venue.

The repo was updated so the active demo target shifted from earlier demo assumptions
to FTMO MT5.

The docs and setup instructions were updated accordingly.

This was the right move because it moved testing closer to the kind of operational
environment the project ultimately cared about.

## Phase 28: FTMO Session Instability And The Real Cause

Early FTMO MT5 authentication attempts seemed unstable.
The terminal would connect and later show invalid-account failures.

The eventual diagnosis was important:

- the automated auth attempts had used a password extracted from a screenshot
- the OCR read was wrong
- repeated login attempts with the wrong credentials could disrupt the attached session

This was not a trivial detail.
It showed that the instability was not necessarily "FTMO being broken."
It was largely caused by bad credential transcription combined with aggressive re-auth behavior.

This also led to a safer engineering decision:

- stop forcing `mt5.login()` unnecessarily
- attach to the existing authenticated terminal session if it already matches

## Phase 29: Attached-Session MT5 Safety Patch

The MT5 bridge was patched so that if the local MT5 terminal was:

- already connected
- already authenticated
- already on the correct account
- already on the correct server

then the bridge would attach to that live session instead of forcing another login.

This was a meaningful robustness improvement.

It reduced:

- accidental disconnects
- session churn
- bad-credential damage from repeated logins

This patch became part of the production-safe behavior of the MT5 bridge.

## Phase 30: FTMO Symbol Discovery

With the correct FTMO session running, the next step was to inspect the actual
crypto symbols on the broker.

The discovered symbol set included:

- `BTCUSD`
- `ETHUSD`
- `XRPUSD`
- `SOLUSD`
- `AVAUSD`
- `DOGEUSD`

This had a very important implication:

- `AVAX/USDT` mapped to `AVAUSD`
- `DOGE/USDT` mapped to `DOGEUSD`

That broker-specific symbol knowledge was essential.
Without it, the system could have passed internal validation but still failed
at the broker boundary.

## Phase 31: FTMO Preflight Validation

Once the symbol map was known, a proper FTMO MT5 preflight was run.

That validated:

- auth
- account oversight state
- drawdown distance
- symbol resolution
- live quote availability

At this point the FTMO preflight confirmed that the intended symbols were not
just listed, but were actually available with live ticks.

That was a big shift from generic demo uncertainty to broker-relevant confidence.

## Phase 32: First Tiny Mechanics-Only Broker Order

Before trusting the full decision pipeline, the system intentionally placed a
small mechanics-only pending order through the MT5 execution path.

The purpose of this was not to prove the strategy.
It was to prove the broker pipe.

This order confirmed:

- the MT5 bridge could authenticate
- the order transmit route worked
- the broker accepted a real pending order
- the order appeared in the FTMO MT5 terminal

This was one of the clearest milestones in the entire project.
It showed that TRADE_ORACLE was no longer just able to "simulate" its own execution path.
It could actually place a broker-accepted order on a real demo venue.

## Phase 33: Full Pipeline Test Revealed A Real Sizing Bug

After the mechanics-only order, the next task was to test the full actual chain:

- scanner
- Super Brain
- review/resume
- risk
- execution

That full-pipeline validation exposed an important issue:

- the candidate's `size_tokens` was being passed straight into MT5 as broker `volume`

That was not safe for FTMO crypto CFDs because MT5 contract sizes vary by symbol.
Examples discovered in the broker metadata included:

- `AVAUSD` contract size `1000`
- `DOGEUSD` contract size `100000`
- other symbols each with their own volume semantics

This meant the project had successfully reached the point where a subtle but
very real broker integration bug could be discovered.
That was actually good news.
The system was being tested deeply enough to catch a true execution-risk issue
before forward testing or funded deployment.

## Phase 34: MT5 Size Conversion Fix

To fix the sizing problem, the MT5 bridge was upgraded so that it distinguished
between two concepts:

- strategy units
- broker volume

The new behavior introduced:

- `size_mode="units"` as the safe default
- `size_mode="broker_volume"` for explicit mechanics-only tests

For MT5 in `units` mode, the bridge now:

- inspects the symbol contract size
- converts strategy units into MT5 broker volume
- rounds safely against broker volume step rules
- enforces broker minimums and maximums

This was a critical correctness upgrade.
It meant the real pipeline could now transmit strategy-derived positions safely
instead of merely proving transport mechanics.

## Phase 35: Full FTMO Pipeline Passed End To End

After the size-conversion fix, the full FTMO chain was re-tested.

This was the true milestone run:

1. `/superbrain/run-once`
   - returned a real `pending_review` for `AVAX/USDT`

2. `/superbrain/review-resume`
   - completed to an approved `BUY` candidate

3. risk recheck
   - passed cleanly

4. broker symbol resolution
   - mapped `AVAX/USDT` to `AVAUSD`
   - confirmed live tick availability

5. `/services/ops/ops/execution/transmit-limit-order`
   - transmitted a real FTMO MT5 pending order

6. FTMO terminal inspection
   - confirmed the broker-side pending order existed

This meant the project had fully crossed the line from:

- architecture validated

to:

- operationally demonstrated

That was not a minor milestone.
It was the first real proof that the Super Brain plus execution stack could
complete its intended chain in a real broker environment.

## Phase 36: Documentation Was Updated To Reflect Reality

Once the FTMO full chain was proven, the docs were aligned to match the new truth.

This included:

- FTMO MT5 setup notes
- symbol maps
- execution policy notes
- the live-demo phased plan

The plan explicitly recorded that the FTMO full chain was proven end to end.

This mattered because the repository no longer had to rely on chat history
to explain where it stood.
The project state became legible from the repo itself.

## What Was Proven By The End Of This Arc

By the time the project reached the forward-testing threshold, the following had
been proven in reality:

### Research And Strategy Foundation

- the project had already matured through a realistic backtesting and optimization arc
- the LangGraph build was attached to a serious strategy context, not a toy signal source

### Super Brain Core

- the LangGraph reasoning topology exists
- state modeling is real
- specialist nodes execute
- the gatekeeper produces typed final decisions

### Human Review

- pending review works
- thread IDs persist
- review resume works
- interrupted threads are auditable

### Service Surface

- the brain service works
- the Super Brain service works
- the platform service works
- the system is exposed through clear HTTP boundaries

### Tool Layer

- MCP tools exist
- provider routing exists
- live free providers were integrated
- fallback behavior works

### Observability

- audit events persist in SQLite
- recent audit lookup works
- thread audit lookup works

### Execution Infrastructure

- MT5 backend exists as a real code path
- FTMO MT5 authentication works
- broker symbol mapping works
- account oversight works
- symbol-status checks work
- pending orders can be transmitted and confirmed at the broker

### Full Operational Chain

- scanner -> Super Brain -> review -> risk -> MT5 execution was proven on FTMO demo

## What Was Not Yet Fully Proven

Even after all of the above, some things were still not fully proven.

That distinction matters because it explains why forward testing is the next
correct step rather than immediate funded live deployment.

The remaining unproven or partially proven areas include:

- long-horizon forward performance
- statistical decision-quality uplift of the Super Brain versus a simpler baseline
- repeated operational reliability across many sessions
- all restart/recovery behaviors under real incident conditions
- long-run broker behavior under repeated supervised use
- whether forward-tested execution outcomes remain aligned with backtest expectations

So the correct interpretation is:

- the system is operationally real
- the architecture is substantially built
- the broker path is proven
- the next responsibility is reliability and benchmark validation

## Why Forward Testing Is The Correct Next Step

Forward testing is the correct next step because the project has now earned it.

Before the FTMO full-chain validation, forward testing would have been premature.
Too many questions were still about architecture and plumbing.

After the FTMO full-chain validation, the nature of the remaining questions changed.

The open questions became:

- Does the system behave consistently across repeated supervised cycles?
- Does the Super Brain improve or degrade the raw scanner path over time?
- Do broker interactions remain stable across sessions?
- Are there hidden operational edge cases?
- Does the audit trail remain complete through repeated use?

Those are forward-testing questions, not build questions.

## Exact Project State At The Start Of Forward Testing

At the point this document ends, TRADE_ORACLE is in the following state:

- the Super Brain pivot is complete enough to be treated as real platform architecture
- the FTMO MT5 demo venue is validated as the current supervised test bed
- the system has already transmitted broker-accepted demo pending orders
- the execution sizing path has been corrected for MT5 contract semantics
- the platform is ready to begin supervised repeated demo cycles

The next phase is not redesign.
The next phase is:

- forward testing
- operational reliability burn-in
- benchmark collection
- supervised iteration

## The Most Important Interpretation For NotebookLM

If NotebookLM is asked to evaluate this project, the single most important
interpretation is:

TRADE_ORACLE is no longer at the "is this architecture even real?" stage.
It has crossed that line.

The relevant evaluation lens now is:

- operational maturity
- benchmark design
- forward-testing discipline
- reliability
- decision-quality measurement

That is where the project now lives.

## Suggested Questions For Further AI Analysis

If this document is loaded into NotebookLM, useful follow-up questions would be:

1. What benchmark framework should be used to compare raw scanner decisions versus Super Brain-filtered decisions during forward testing?
2. What are the highest-risk operational failure modes remaining in the FTMO MT5 demo path?
3. What metrics should be recorded on every supervised cycle to decide when the system is ready for funded live testing?
4. What is the best way to separate broker-pipe reliability from actual strategy quality during the burn-in period?
5. What evidence threshold should be required before shifting from supervised demo operation to funded live deployment?

## Bottom Line

The Super Brain pivot was not just a refactor.
It was a stepwise transformation of TRADE_ORACLE into a deployable, reviewable,
auditable, broker-connected decision system.

The build passed through these major transitions:

- graph scaffold
- service surface
- platform packaging
- auditability
- live provider integration
- runtime alignment
- live scanner validation
- MT5 execution pivot
- FTMO venue alignment
- broker-accepted pending orders
- full pipeline proof

That is the context needed to understand why the project is now at the start of
forward testing rather than still in raw architecture construction.
