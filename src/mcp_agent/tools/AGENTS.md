# Scope rules for `src/mcp_agent/tools/`

This directory is only for framework/tooling adapters (e.g., CrewAI, LangChain). To stay aligned with architecture:

- Do **not** place domain-specific tools here; keep them with the consuming agents.
- Keep functions minimal and adapter-focused—no bespoke clients or server bypasses.
- Prefer pure functions that can be registered on `AgentSpec(functions=[...])`; avoid embedding config or secrets.
- If an MCP server exists for a capability, route agents to it via `server_names` instead of adding a new local tool.
