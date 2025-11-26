# Scope rules for `src/mcp_agent/workflows/`

Use this directory for production workflows only. Apply the root guidance and:

- Subclass `mcp_agent.executor.workflow.Workflow` (or provided helpers) for every workflow; avoid bespoke orchestration layers or standalone CLIs.
- Register workflows through `MCPApp`/`@app.workflow` so they participate in the shared runtime, logging, and context management.
- Compose agents, LLM adapters, and MCP servers via existing factories; do not rewire transports or config parsing here.
- Keep workflow logic thin: orchestration, routing, and evaluation are fine; heavy domain logic belongs inside agents.

## Multi-step workflow structure
- Break numbered/major steps into dedicated `@app.workflow_task` functions (or helper workflows) and invoke them from the parent `Workflow.run` for retry/timeout control and SSE-friendly progress.
- For production workflows with multiple steps, create a subpackage under `src/mcp_agent/workflows/<workflow_name>/` (e.g., `tasks.py`, `helpers/`, `models.py`, `__init__.py`) rather than a single module file, and group any workflow-specific agents under `src/mcp_agent/agents/<agents_group_name>/`.
- Workflows must orchestrate `Agent` instances (wired to MCP servers declared in config) instead of calling tool adapters directly. Add/update agent specs/builders and tests when introducing new CLI/tool integrations.
- Register every new workflow (and related agents) in `mcp_agent.config.yaml` with required servers/providers, and ensure PR checklists confirm the config update and secrets implications.
- Do not ship placeholder steps when the PR requires using an existing workflow/orchestrator (e.g., `workflows/deep_orchestrator` for failure-analysis/fix loops); wire the real dependency.
- Each workflow folder must contain an up-to-date `README.md` describing behavior/usage; create or update it with the implementation.

## Never do
- Do not keep all workflow steps in a monolithic `run` method—taskify them so retries, timeouts, and event streaming function correctly.
- Do not bypass agents by invoking CLI/tool adapters directly from workflows; orchestrate agents that expose those tools over MCP.
- Do not leave stubbed/placeholder steps for branching/PR/CI/fix-loop handling when existing orchestrator workflows must be used—integrate them explicitly.
- Do not omit config registration or README updates when adding workflows or agents.
