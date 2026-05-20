# SentinelAI Demo Guide

This guide is designed for interviews, portfolio walkthroughs, GitHub demos, and recruiter screens.

## Demo Goal

Show that SentinelAI can:

- generate a plan from natural language
- execute the plan through a reusable workflow
- persist memory and tool traces
- expose the result through both CLI and dashboard views

## Quick Demo Script

### 1. Start Ollama

```bash
ollama serve
```

### 2. Pull the default model

```bash
ollama pull llama3
```

### 3. Run the strongest CLI flow

```bash
python main.py phase6 --url https://example.com --instruction "Open the homepage, confirm the title, and validate the main heading."
```

What to point out:

- the system used the LangGraph workflow
- MCP tool routing was enabled
- artifacts were written automatically
- the run produced reports, traces, and metrics

### 4. Launch the dashboard

```bash
uvicorn dashboard.app:app --reload
```

Open:

```text
http://127.0.0.1:8000/
```

### 5. Walk through the UI

Suggested order:

1. Overview page
2. New Run page
3. Runs page
4. Run Detail page
5. Reports page
6. Memory page
7. Tools page
8. Metrics page
9. Settings page

### 6. Trigger a run from the UI

Use:

- URL: `https://example.com`
- Mode: `phase6`
- Instruction: `Test the homepage and validate the title`
- Model: `llama3`

### 7. Open the run detail page

Highlight:

- status badges
- screenshots
- graph trace
- planner trace
- tool trace
- execution metrics
- report links

### 8. Show persistent memory

Run a second similar Phase 5 or Phase 6 request and point out:

- memory retrieval count
- retrieval context on the run detail page
- memory hits in metrics

## Optional Deterministic Demo

If you want a no-LLM backup demo:

```bash
python main.py phase2 --test testcases/sample_test.json
```

This is useful when:

- Ollama is not available
- you want to show the deterministic engine first
- you want to compare structured testcases with AI planning

## Expected Outputs

After a successful Phase 6 run you should have:

- `artifacts/runs/<run_id>/reports/report.json`
- `artifacts/runs/<run_id>/reports/report.html`
- `artifacts/runs/<run_id>/graph/graph_trace.json`
- `artifacts/runs/<run_id>/graph/tool_trace.json`
- `artifacts/runs/<run_id>/planner/planner_trace.json`
- `artifacts/runs/<run_id>/metrics/execution_metrics.json`

## Suggested Demo Recording Flow

If you want to record a short walkthrough for GitHub, LinkedIn, or an interview:

1. Open the dashboard overview page and show recent run metrics.
2. Navigate to the New Run page and highlight the Phase 6 execution form.
3. Submit a safe `example.com` run.
4. Open the Runs page and show the new entry in history.
5. Open the Run Detail page and point out screenshots, report links, and status cards.
6. Expand the graph trace and MCP tool trace sections.
7. Open the Reports page to show HTML and JSON outputs.
8. Finish on the Metrics or Memory page to show that SentinelAI is more than a simple browser script.

## Talking Points For Interviews

- SentinelAI separates planning, execution, validation, reporting, memory, and tooling into replaceable layers.
- It uses local LLMs through Ollama instead of relying on hosted APIs.
- It combines deterministic validation with AI-assisted planning.
- It includes CI, tests, smoke checks, and a local product-style dashboard.
- It is structured as an extensible system, not a one-off prototype.
