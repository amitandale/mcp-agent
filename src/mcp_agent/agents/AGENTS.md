# Scope rules for `src/mcp_agent/agents/`

This folder hosts production agents and agent specs. Follow the root `AGENTS.md` plus these local rules:

- Build agents with `Agent`/`AgentSpec` and the shared factory helpers (e.g., `create_agent`), not custom runtimes.
- Always declare MCP access through `server_names=[...]` that reference configured servers; do not embed ad-hoc clients or duplicate server logic.
- Register function-tools via `AgentSpec(functions=[...])` only when necessary; keep domain logic with the owning agent and avoid shared tool registries here.
- Prefer config-driven exports (`SPEC` and `build(context: Context | None) -> Agent`) so agents can be wired consistently by the app.
