# Scope rules for `src/mcp_agent/workflows/`

Use this directory for production workflows only. Apply the root guidance and:

- Subclass `mcp_agent.executor.workflow.Workflow` (or provided helpers) for every workflow; avoid bespoke orchestration layers or standalone CLIs.
- Register workflows through `MCPApp`/`@app.workflow` so they participate in the shared runtime, logging, and context management.
- Compose agents, LLM adapters, and MCP servers via existing factories; do not rewire transports or config parsing here.
- Keep workflow logic thin: orchestration, routing, and evaluation are fine; heavy domain logic belongs inside agents.
- Multi-step workflows must break each numbered step into its own `@app.workflow_task` (or helper workflow) and call those tasks from `Workflow.run` to gain retry/timeout control and SSE-friendly progress.
- New production multi-step workflows should live in their own subpackage (e.g., `src/mcp_agent/workflows/<workflow_name>/` with tasks/helpers/models) instead of a single module. Keep a README.md in the workflow folder and update it with new implementations.
- Do not ship placeholder steps when a PR requires using an existing workflow (e.g., `workflows/deep_orchestrator` for failure-analysis/fix loops); wire the real workflow/tasks.
