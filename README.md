# SentinelAI
[![CI](https://github.com/nexusBL/SentinelAI/actions/workflows/ci.yml/badge.svg)](https://github.com/nexusBL/SentinelAI/actions/workflows/ci.yml)

SentinelAI is a production-oriented foundation for an autonomous AI web testing platform. The repository currently covers **Phase 1** through **Phase 9**: browser automation, artifact capture, structured test execution, rule-based validation, Ollama-based AI planning, LangGraph-based orchestration with retries and replanning, persistent memory-backed learning, MCP-style tool orchestration, automated quality gates, GitHub Actions CI, and an optional FastAPI dashboard for local product-style visibility.

## Current Capabilities

- Playwright browser automation
- before/after screenshots
- per-step screenshots
- DOM snapshot capture
- JSON + HTML reports
- structured JSON test cases
- deterministic step execution
- rule-based assertions
- AI test planning with Ollama
- LangGraph workflow orchestration
- retry-aware replanning
- persistent FAISS-backed memory
- retrieval-augmented planning
- MCP-style tool registry and modular tool servers
- tool invocation tracing and MCP metrics
- centralized logging utilities
- GitHub Actions quality pipeline
- FastAPI multi-page dashboard with artifact browsing
- Docker-ready app scaffold

## Architecture Direction

Target workflow for later phases:

`START -> Planner -> Memory Read -> Executor -> Screenshot -> Validator -> Memory Write -> Reporter -> END`

Current implementation path:

- `ai/`: Ollama HTTP client
- `agents/`: planner and deterministic step execution
- `browser/`: Playwright browser control
- `reporting/`: artifact and report generation
- `memory/`: embeddings, vector store, and memory manager
- `mcp_servers/`: MCP-style registry and tool servers
- `dashboard/`: optional FastAPI UI, templates, static assets, and artifact viewers
- `validation/`: rule-based assertions
- `sentinelai/`: shared runtime types and test-case schema

## Repository Layout

```text
SentinelAI/
|-- ai/
|-- agents/
|-- browser/
|-- config/
|-- dashboard/
|-- docker/
|-- mcp_servers/
|-- memory/
|-- reporting/
|-- sentinelai/
|-- testcases/
|-- validation/
`-- main.py
```

## Python Setup

1. Create and activate the virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

2. Install Python dependencies inside `.venv`:

```powershell
pip install -r requirements.txt
python -m playwright install chromium
```

This installs the current Python runtime stack, including `playwright`, `requests`, `langgraph`, `faiss-cpu`, and `sentence-transformers`.

Phase 7 also adds the local developer test stack:

- `pytest`
- `pytest-asyncio`

## Ollama Setup

Ollama runs as a separate system service. It is **not** installed inside the Python virtual environment.

1. Install Ollama from:

```text
https://ollama.com
```

2. Start the Ollama service:

```bash
ollama serve
```

3. Pull the default model:

```bash
ollama pull llama3
```

Default Ollama endpoint used by SentinelAI:

```text
http://localhost:11434/api/generate
```

Optional environment variables are shown in [.env.example](/c:/Users/l670b/OneDrive/Desktop/SentinelAI/.env.example:1).

## Running SentinelAI

Phase 1 baseline navigation:

```powershell
python main.py phase1 --url https://example.com --instruction "Open the landing page and capture a baseline."
```

Phase 2 deterministic JSON testcase:

```powershell
python main.py phase2 --test testcases/sample_test.json
```

Phase 3 natural-language planning with Ollama:

```powershell
python main.py phase3 --url https://example.com --instruction "Open the homepage and verify the title contains Example Domain"
```

Phase 4 LangGraph orchestration with retries:

```powershell
python main.py phase4 --url https://example.com --instruction "Test the homepage" --max-retries 2
```

Phase 5 LangGraph orchestration with persistent memory:

```powershell
python main.py phase5 --url https://example.com --instruction "Test the homepage" --max-retries 2
```

Phase 6 LangGraph orchestration with MCP tool routing:

```powershell
python main.py phase6 --url https://example.com --instruction "Test the homepage" --max-retries 2
```

Optional model override:

```powershell
python main.py phase3 --url https://example.com --instruction "test homepage" --model mistral
```

Artifacts are written under `artifacts/runs/<run_id>/`.

Each run now pre-creates orchestration-ready subdirectories for future observability and reproducibility work:

- `graph/`
- `planner/`
- `metrics/`

Phase 4 writes:

- `graph/graph_trace.json`
- `planner/planner_trace.json`
- `metrics/execution_metrics.json`

Phase 6 additionally writes:

- `graph/tool_trace.json`

Phase 5 also persists local vector memory outside per-run artifacts. By default this lives under `memory_store/` and can be changed with `SENTINELAI_MEMORY_VECTOR_DB_PATH`.

Default memory configuration:

- memory enabled: `true`
- vector store backend: FAISS
- default embedding provider: `hashing`
- optional embedding provider: `sentence_transformers`
- default retrieval depth: `3`

Default MCP configuration:

- MCP enabled: `true`
- tool tracing enabled: `true`
- MCP timeout seconds: `90`
- enabled tools: `browser,memory,validation`

Phase 3 planner logs include:

- planner prompt
- raw LLM responses per attempt
- parsed JSON per valid parse attempt
- final normalized test plan

## Dashboard

Phase 9 adds an optional local-first dashboard built with FastAPI, Jinja2 templates, custom CSS, and vanilla JavaScript. It does not replace the CLI or backend workflows; it wraps the existing system so you can demo runs, browse artifacts, and inspect traces in a more product-like interface.

Run the dashboard locally:

```powershell
uvicorn dashboard.app:app --reload
```

Primary routes:

- `/`: overview cards, recent runs, system status
- `/new-run`: polished run form for Phase 3 through Phase 6 workflows
- `/runs`: searchable run history
- `/runs/{run_id}`: run detail, screenshots, traces, metrics, and report links
- `/reports`: generated HTML and JSON reports
- `/memory`: memory status, recent writes, and retrieval activity
- `/tools`: MCP tool summary and recent tool invocations
- `/metrics`: aggregate workflow metrics
- `/settings`: read-only runtime configuration

The dashboard is:

- optional
- local-first
- safe on missing artifacts
- separate from the planner, executor, validation, memory, MCP, and CLI layers

No Streamlit is used. The existing CLI remains fully supported.

Screenshot placeholder section:

- Add product screenshots or demo captures here for GitHub presentation once you have a preferred local run history to showcase.

## Testing And Quality Gates

Before pushing changes, run the same core checks locally that CI runs:

```powershell
python -m compileall .
python -m pytest
python scripts/smoke_test.py
python scripts/dev_check.py
```

Run the automated test suite:

```powershell
python -m pytest
```

Run the lightweight smoke test:

```powershell
python scripts/smoke_test.py
```

Run the full local developer gate before pushing:

```powershell
python scripts/dev_check.py
```

What the Phase 7 checks cover:

- `tests/test_config.py`: settings defaults and environment overrides
- `tests/test_test_case_schema.py`: testcase loading, schema validation, and serialization
- `tests/test_assertions.py`: deterministic validation behavior and failure messages
- `tests/test_planner_agent.py`: planner retries, schema rejection, metadata, and memory-context injection
- `tests/test_memory_manager.py`: FAISS persistence, retrieval, disabled mode, and empty-store safety
- `tests/test_mcp_registry.py` and `tests/test_mcp_servers.py`: MCP registry, tool interfaces, structured errors, and timeout handling
- `tests/test_graph_workflow.py`: success, retry, max-retry stop, memory ordering, and MCP-enabled or disabled graph behavior
- `tests/test_reporting.py`: report and trace artifact writing
- `tests/test_backward_compatibility.py`: phase command availability, help output, and import safety
- `tests/test_dashboard_utils.py` and `tests/test_dashboard_routes.py`: safe artifact loading, empty-state rendering, run-detail APIs, and dashboard route behavior without real Ollama or browser execution

The unit test suite is designed to run without a real Ollama service and without internet access. Planner tests use mock responses, and the smoke test only checks initialization paths.

## CI Pipeline

GitHub Actions now runs the SentinelAI quality pipeline on every push to `main` and every pull request targeting `main`.

The workflow lives in [.github/workflows/ci.yml](/c:/Users/l670b/OneDrive/Desktop/SentinelAI/.github/workflows/ci.yml:1) and currently runs:

- dependency installation from `requirements.txt`
- Python compile checks
- `python -m pytest`
- `python scripts/smoke_test.py`
- `python scripts/dev_check.py` as a parity check against the local developer gate

CI is intentionally lightweight and mock-friendly:

- it does not require a real Ollama service
- it does not download Playwright browsers by default
- it uses safe CI-friendly environment defaults
- it does not depend on local `memory_store/`, `artifacts/runs/`, or `.venv/`

If CI fails, the fastest local reproduction path is:

```powershell
python scripts/dev_check.py
```

If you need more detail, run the individual steps locally:

```powershell
python -m compileall .
python -m pytest
python scripts/smoke_test.py
```

Known warning handling:

- the project filters only the known harmless FAISS/SWIG deprecation warnings in [pytest.ini](/c:/Users/l670b/OneDrive/Desktop/SentinelAI/pytest.ini:1)
- other warnings still surface normally so the test output stays useful

## Docker

The Docker scaffold currently runs the deterministic app container workflow:

```powershell
docker compose -f docker/docker-compose.yml up --build
```

If you want to use Phase 3 from Docker later, point the container at a reachable Ollama service endpoint.

## What Comes Next

- Phase 10+: richer productization layers such as hosted UI, deployment workflows, integration tests, or comparative report tooling
