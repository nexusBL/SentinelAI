# MCP Servers

This package holds the Phase 6 MCP-style tool layer used by SentinelAI.

Current servers:

- browser server: `capture_initial_state`, `run_test_case`, `open_url`, `click`, `type`, `wait`, `extract_dom`, `screenshot`
- memory server: `retrieve_similar`, `store_execution`, `memory_stats`
- validation server: `validate_assertions`, `summarize_validation`, `extract_failure_reason`

The orchestration layer talks to these servers through `MCPToolRegistry`, which keeps tool lookups and execution loosely coupled from the LangGraph nodes.
