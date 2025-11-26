# Scope rules for `src/mcp_agent/executor/`

These are the workflow runtime primitives. Keep changes minimal and consistent with the existing architecture:

- Extend existing primitives (`Workflow`, `WorkflowResult`, task/signal registries) instead of adding parallel runtimes.
- Do not introduce new execution backends or Temporal wrappers without aligning with the current abstractions.
- Preserve type safety and backwards compatibility for workflow authors; breaking changes require broad justification and test coverage.
- Any new helper should remain generic and reusable by workflows/agents, not domain-specific.
