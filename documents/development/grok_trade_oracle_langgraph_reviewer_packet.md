# Grok Reviewer Packet: TRADE_ORACLE LangGraph Super Brain

## What This Packet Is For

This is the short-form architecture and progress handoff for Grok 4.2 acting as architect, architecture consultant, and progress reviewer.

It is meant to answer three questions quickly:

1. What exactly exists now?
2. What architectural choices were made?
3. What still remains before the Super Brain is fully production-complete?

## Current State in One Paragraph

TRADE_ORACLE now has a working LangGraph-centered decision layer with typed state, specialist nodes, human-in-the-loop interruption and resume, persistent SQLite checkpointing, a FastAPI MCP specialist tool layer, an ops service for scanner/risk/execution, a unified Super Brain service for n8n, and a single-container platform service that packages all of those surfaces together for remote deployment. The graph compiles and runs, tests are passing, and the deployment boundary is now cleanly aligned to n8n and Docker. The largest remaining gap is not orchestration anymore; it is external data depth for some specialist adapters.

## Architectural Decisions Already Implemented

### 1. LangGraph is the reasoning core

- The graph is built in `ai/trade_oracle_langgraph_phase1.py`.
- It follows the Supervisor-Led Specialist Subgraph pattern.
- The Intent Router is the central supervisor.

### 2. Human review is native, not bolted on

- The gatekeeper uses LangGraph `interrupt()`.
- n8n/OpenClaw is expected to persist `thread_id` and resume later.
- Resume is exposed through HTTP.

### 3. Tool boundaries are HTTP-first

- The graph does not call legacy scripts via subprocess.
- Specialist tools are exposed through FastAPI/MCP-style HTTP endpoints.
- Ops actions are exposed through FastAPI execution/risk/scanner endpoints.

### 4. The deployment boundary is now unified

- The platform service is the preferred n8n entrypoint.
- It exposes:
  - `/superbrain/run-once`
  - `/superbrain/review-resume`
  - `/system/health`
  - `/system/capabilities`
  - `/system/audit/recent`
  - `/system/audit/thread/{thread_id}`
- It mounts the auxiliary services under:
  - `/services/brain`
  - `/services/ops`
  - `/services/mcp`

### 5. Auditability is now persistent

- LangGraph evaluations and review resumes are persisted into a SQLite audit/event store.
- The platform exposes recent-event and per-thread event lookup endpoints.
- Review payloads now include an audit snapshot so human review can see more context.

### 6. The MCP layer now supports provider routing

- The specialist MCP service now has a provider registry with per-domain modes:
  - `internal`
  - `hybrid`
  - `external`
- A provider-status endpoint exposes current provider posture.
- The default free live-provider posture is now:
  - CoinGecko for macro, fundamentals, and tokenomics
  - Binance public spot market data for technicals
- This keeps the graph topology unchanged while moving the specialist layer closer to live data.

### 7. The LangGraph environment is intentionally isolated

- A separate LangGraph dependency track was created.
- This was necessary because the LangGraph/FastAPI stack pulled newer `httpx` and `websockets` versions than the older Supabase runtime tolerated.

## Major Files to Review

### Core graph

- `ai/trade_oracle_langgraph_phase1.py`
- `ai/langgraph_orchestrator.py`

### HTTP surfaces

- `api/trade_oracle_mcp_service.py`
- `api/trade_oracle_ops_service.py`
- `api/trade_oracle_brain_service.py`
- `api/trade_oracle_super_brain_service.py`
- `api/trade_oracle_platform_service.py`

### Packaging and contracts

- `contracts/trade_oracle_n8n_workflow_contract.json`
- `contracts/n8n_4h_master_orchestrator_platform.workflow.json`
- `documents/development/n8n_4h_master_orchestrator_blueprint.md`
- `Dockerfile.langgraph`
- `requirements.langgraph.txt`

## What Has Been Verified

- The graph compiles and runs in the LangGraph environment.
- Interrupt and resume work.
- The supervisor/orchestrator path works for single and batch evaluation.
- The MCP service works locally and over HTTP.
- The ops service works for scanner/risk/execution wrappers.
- The unified Super Brain service works.
- The final platform service mounts the major surfaces and exposes capabilities/health.
- Focused tests are green.

Latest reported focused suite:

- `41 passed`

## What Is Strong About the Current System

### The topology is now clean

- The graph topology is no longer the bottleneck.
- n8n has a single HTTP-first boundary.
- The codebase has clearer separation between:
  - reasoning
  - tools
  - ops
  - deployment surface

### The HITL model is correct

- Human review is a first-class execution state.
- Review is not treated as a hacky boolean.
- This is a major architectural win.

### The deployment story is now believable

- The platform service plus Docker file makes remote deployment realistic.
- The capabilities endpoint gives n8n and operators a discovery surface.

## What Is Still Not Fully Complete

### 1. Some specialist adapters are still deterministic

- Macro, fundamental, tokenomics, and technical tools are now richer than stubs.
- But not all of them are backed by live external providers yet.

### 2. Live hosted validation is still pending

- The code is ready for remote deployment.
- Full hosted end-to-end validation on Railway/Render with n8n and OpenClaw still needs to happen.

### 3. Human review workflow import is still a skeleton

- The main orchestration skeleton exists.
- A fully polished pair of import-ready n8n production workflows can still be expanded further.

### 4. Account-state sourcing still needs final production authority

- Hydration hooks and fail-safe fallbacks exist.
- Final authoritative sourcing of `current_balance`, `highest_equity`, and `active_trades_count` still needs operational standardization.

## Current Reviewer Focus Areas for Grok

If Grok 4.2 is reviewing the architecture, these are the highest-signal questions:

1. Is the current split between platform, super-brain, ops, and MCP the cleanest long-term deployment boundary?
2. Should the human review resume path remain a separate n8n workflow instead of a branch in the scheduled workflow?
3. Which specialist should be wired to live external providers first:
   - macro
   - fundamentals
   - tokenomics
   - technical enrichment
4. Should execution remain an optional post-LangGraph recheck path or be moved to a stricter broker-confirmed execution subgraph later?

## Recommended Next Actions

1. Expand the n8n import pack into:
   - main scheduled workflow
   - human review resume workflow
   - incident/error workflow
2. Wire live external data providers into the MCP layer without changing graph topology.
3. Add hosted deployment configuration for Railway/Render.
4. Add stronger audit persistence for run-level and review-level events.

## Companion Document

For the full chronological implementation history, read:

- `documents/development/trade_oracle_langgraph_full_build_report.md`
