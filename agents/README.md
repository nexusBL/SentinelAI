# Agents

This package is reserved for the LangGraph agent system.

Planned agents:

- `planner_agent`: turns natural-language intent into test steps
- `executor_agent`: runs browser actions and tool calls
- `validator_agent`: checks DOM, screenshots, and AI reasoning
- `reporter_agent`: produces structured run summaries

Current deterministic runtime support:

- `step_executor`: executes structured Phase 2 test steps before AI planning is added
- `planner_agent`: calls Ollama and turns natural language into Phase 2-compatible plans
