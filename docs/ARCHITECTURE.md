# SentinelAI Architecture

## Overview

SentinelAI is structured as a modular AI testing platform rather than a single-script automation tool. Each subsystem has a narrow responsibility and clean interface so future features can be added without rewriting the whole stack.

Core properties:

- local-first runtime
- loosely coupled modules
- deterministic validation path
- optional AI planning and dashboard layers
- persistent memory across runs
- authenticated user isolation for dashboard resources
- artifact-first observability
- testable, CI-friendly packaging

## High-Level Flow

```mermaid
flowchart LR
    U[User Instruction] --> Entry[CLI or FastAPI Dashboard]
    Entry --> Auth[JWT Auth and User Scope]
    Auth --> Jobs[Async Job Queue]
    Jobs --> Graph[LangGraph Workflow]
    Graph --> Retrieve[Memory Retrieval]
    Retrieve --> Planner[Ollama Planner]
    Planner --> Tools[MCP Tool Registry]
    Tools --> Browser[Playwright Executor]
    Browser --> Validate[Validation Engine]
    Validate --> Artifacts[Reports and Artifacts]
    Validate --> Store[Memory Storage]
```

## Module Responsibilities

| Module | Responsibility |
|---|---|
| `main.py` | CLI entrypoint for Phases 1 through 6 |
| `config/` | Environment-driven runtime configuration |
| `browser/` | Playwright execution, screenshots, DOM capture, browser result models |
| `validation/` | Deterministic assertions and pass/fail reasoning |
| `ai/` | Ollama HTTP client |
| `auth/` | SQLite users, bcrypt password hashing, JWT cookie sessions |
| `agents/planner_agent.py` | Natural-language to structured test-plan conversion |
| `agents/graph_workflow.py` | LangGraph orchestration, retries, observability, memory integration |
| `memory/` | Embeddings, FAISS vector storage, retrieval, and memory persistence |
| `mcp_servers/` | MCP-style tool servers and registry abstraction |
| `reporting/` | JSON/HTML report generation and artifact management |
| `dashboard/` | Optional FastAPI UI for runs, reports, traces, memory, tools, and metrics |
| `tests/` | Offline-friendly quality and regression protection |

## Data Flow

1. A user triggers SentinelAI from the CLI or dashboard.
2. Dashboard requests are authenticated with a JWT cookie and scoped to the current user.
3. Dashboard runs are submitted as background jobs.
4. The LangGraph workflow initializes run context and artifacts.
5. If memory is enabled, similar prior runs are retrieved from FAISS.
6. The planner calls Ollama and produces a strict JSON test plan.
7. The executor runs the plan through Playwright, either directly or via MCP.
8. The validation layer checks assertions and extracts failure reasons.
9. Retry and replan logic may loop through the planner again.
10. Reports, traces, screenshots, and metrics are written to artifacts.
11. If enabled, summarized run data is stored back into persistent memory.

## Artifact Flow

Per-run output goes under:

```text
artifacts/runs/<run_id>/
```

Key folders:

- `reports/`: `report.json`, `report.html`
- `graph/`: `graph_trace.json`, `tool_trace.json`
- `planner/`: planner attempts, normalized plan, retrieval artifacts
- `metrics/`: `execution_metrics.json`
- `screenshots/`: before/after and per-step screenshots
- `logs/`: DOM snapshots and memory store artifacts
- `metadata/`: owner metadata for authenticated dashboard-created runs

Persistent cross-run memory is stored separately under:

```text
memory_store/
```

Local dashboard users are stored in:

```text
auth_store/
```

## Extension Points

SentinelAI is intentionally designed for future extension:

- swap the embedding provider without changing planner or executor code
- replace FAISS with ChromaDB or a managed vector store behind the memory interface
- add new MCP servers for filesystem, API, or cloud capabilities
- extend LangGraph nodes without rewriting existing execution logic
- replace the dashboard with a hosted frontend later while keeping backend APIs intact
- migrate auth from local SQLite to PostgreSQL or an external identity layer
- add integration-test tiers or deployment workflows without disturbing unit-test safety

## Why The Architecture Matters

This project is not just a web automation demo. It demonstrates:

- AI orchestration with deterministic guardrails
- memory-augmented planning
- modular tool abstraction
- traceable artifact pipelines
- product-grade developer experience
- CI-backed reliability for a multi-layer AI system
