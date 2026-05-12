# SentinelAI

SentinelAI is a production-oriented foundation for an autonomous AI web testing platform. The repository currently covers **Phase 1**, **Phase 2**, **Phase 3**, **Phase 4**, **Phase 5**, and **Phase 6**: browser automation, artifact capture, structured test execution, rule-based validation, Ollama-based AI planning, LangGraph-based orchestration with retries and replanning, persistent memory-backed learning, and MCP-style tool orchestration.

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
- `validation/`: rule-based assertions
- `sentinelai/`: shared runtime types and test-case schema

## Repository Layout

```text
SentinelAI/
|-- ai/
|-- agents/
|-- browser/
|-- config/
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

## Docker

The Docker scaffold currently runs the deterministic app container workflow:

```powershell
docker compose -f docker/docker-compose.yml up --build
```

If you want to use Phase 3 from Docker later, point the container at a reachable Ollama service endpoint.

## What Comes Next

- Phase 7: expanded multi-container runtime
