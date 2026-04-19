# SentinelAI

SentinelAI is a production-oriented foundation for an autonomous AI web testing platform. This repository starts with **Phase 1**: open a URL with Playwright, capture baseline artifacts, and persist a report in a structure that can later host LangGraph agents, memory, MCP servers, and AI-driven validation.

## Current Phase

Phase 1 is implemented with:

- Playwright browser automation
- before/after screenshots
- DOM snapshot capture
- JSON + HTML run reports
- Docker-ready project layout

## Planned Architecture

Target workflow for later phases:

`START -> Planner -> Memory Read -> Executor -> Screenshot -> Validator -> Memory Write -> Reporter -> END`

Planned components:

- `agents/`: LangGraph planner, executor, validator, reporter
- `browser/`: Playwright browser control and resilient action execution
- `memory/`: episodic and semantic memory backed by a vector store
- `mcp_servers/`: browser, screenshot, and memory tool servers
- `validation/`: DOM, visual, and AI-assisted validation
- `reporting/`: structured logs and user-facing reports
- `config/`: runtime settings

## Repository Layout

```text
SentinelAI/
├── agents/
├── browser/
├── config/
├── docker/
├── mcp_servers/
├── memory/
├── reporting/
├── sentinelai/
├── validation/
└── main.py
```

## Local Setup

1. Create a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
python -m playwright install chromium
```

3. Run Phase 1:

```powershell
python main.py phase1 --url https://example.com --instruction "Open the landing page and capture a baseline."
```

Artifacts are written under `artifacts/runs/<run_id>/`.

## Docker

Phase 1 includes an app container scaffold:

```powershell
docker compose -f docker/docker-compose.yml up --build
```

## What Comes Next

- Phase 2: basic assertions and validation results
- Phase 3: Ollama planning prompts
- Phase 4: LangGraph agent workflow
- Phase 5: vector memory
- Phase 6: MCP tool layer
- Phase 7: expanded multi-container runtime

