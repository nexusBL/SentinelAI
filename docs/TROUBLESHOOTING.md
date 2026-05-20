# SentinelAI Troubleshooting

## Ollama Is Not Running

Symptoms:

- planner requests fail
- Phase 3 through Phase 6 runs return connection or timeout errors

Fix:

```bash
ollama serve
ollama pull llama3
```

Then verify the endpoint:

```text
http://localhost:11434/api/generate
```

## Playwright Browser Is Missing

Symptoms:

- browser launch fails
- Playwright reports Chromium is not installed

Fix:

```bash
python -m playwright install chromium
```

## FAISS Install Issues

Symptoms:

- memory module import fails
- CI or local setup errors mention `faiss`

Fix:

- reinstall dependencies with `pip install -r requirements.txt`
- use the hashing embedding provider first to avoid heavier model setup
- if needed, temporarily disable memory with `SENTINELAI_MEMORY_ENABLED=false`

## Dashboard Is Not Loading

Symptoms:

- `uvicorn dashboard.app:app --reload` fails
- pages return template or import errors

Fix:

```bash
pip install -r requirements.txt
python -m pytest
python scripts/smoke_test.py
```

Also confirm FastAPI dependencies such as `jinja2` and `python-multipart` are installed.

## CI Failure

Start with the local parity check:

```bash
python scripts/dev_check.py
```

Then drill down into:

```bash
python -m compileall .
python -m pytest
python scripts/smoke_test.py
```

## Memory Store Is Empty

This is normal until at least one memory-enabled Phase 5 or Phase 6 run completes.

Check:

- `SENTINELAI_MEMORY_ENABLED=true`
- `memory_store/` exists
- the run completed the memory store step

## Port Already In Use

If FastAPI cannot bind to the default port:

```bash
uvicorn dashboard.app:app --reload --port 8010
```

## Report or Artifact Files Missing

Some artifacts are phase-dependent.

Examples:

- Phase 2 has no AI planning trace
- Phase 3 has planner logs but no MCP tool trace
- Phase 6 has tool traces only if MCP is enabled

Use the dashboard empty states or inspect `artifacts/runs/<run_id>/` directly.
