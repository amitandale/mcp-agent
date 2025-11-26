# Scope rules for `src/mcp_agent/oauth/`

OAuth flows and helpers reside here.

- Reuse shared HTTP helpers and token stores; avoid bespoke auth clients or inline credential handling.
- Keep flows configurable (via `mcp_agent.config.yaml`) and avoid hardcoded app IDs or secrets.
- Integrate with server/cli layers through existing adapters instead of new entrypoints.
