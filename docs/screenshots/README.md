# SentinelAI Screenshot Gallery

This folder contains real dashboard screenshots captured from the local FastAPI UI.

## What Each Screenshot Shows

- `dashboard-overview.png`: the landing page with system summary cards and recent runs
- `new-run-page.png`: the execution form used to start Phase 3 through Phase 6 runs from the browser
- `runs-page.png`: searchable run history with status badges and timing information
- `run-detail-page.png`: a complete run detail view with artifacts, screenshots, and trace panels
- `reports-page.png`: generated HTML and JSON report browsing
- `memory-page.png`: memory status, recent retrievals, and memory-hit summary
- `tools-page.png`: MCP tool stats and recent tool invocations
- `metrics-page.png`: aggregate workflow metrics across runs
- `settings-page.png`: read-only runtime configuration view
- `graph-tool-trace-section.png`: a focused capture of the run detail trace section for demo storytelling

## Demo Data Used

The screenshots were generated from safe local demo artifacts using:

- `python main.py phase2 --test testcases/sample_test.json`
- an existing local Phase 6 example.com artifact with graph and tool traces

No private credentials, private URLs, or sensitive data were used.

## How To Regenerate

1. Start the dashboard:

```bash
uvicorn dashboard.app:app --reload
```

2. Ensure you have safe local artifacts available, for example:

```bash
python main.py phase2 --test testcases/sample_test.json
```

3. Capture updated screenshots from:

- `/`
- `/new-run`
- `/runs`
- `/runs/<run_id>`
- `/reports`
- `/memory`
- `/tools`
- `/metrics`
- `/settings`

4. Replace the PNG files in this folder with the refreshed captures.

Keep screenshots lightweight, avoid private data, and do not commit raw artifact folders or browser cache.
