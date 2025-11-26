# Scope rules for `src/mcp_agent/workflows/`

Use this directory for production workflows only. Apply the root guidance and:

- Subclass `mcp_agent.executor.workflow.Workflow` (or provided helpers) for every workflow; avoid bespoke orchestration layers or standalone CLIs.
- Register workflows through `MCPApp`/`@app.workflow` so they participate in the shared runtime, logging, and context management.
- Compose agents, LLM adapters, and MCP servers via existing factories; do not rewire transports or config parsing here.
- Keep workflow logic thin: orchestration, routing, and evaluation are fine; heavy domain logic belongs inside agents.
