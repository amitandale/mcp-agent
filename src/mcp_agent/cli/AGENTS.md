# Scope rules for `src/mcp_agent/cli/`

CLI commands should orchestrate existing runtime pieces, not create new ones.

- Invoke workflows/agents through the shared application/container APIs; avoid standalone runners that bypass `MCPApp`.
- Keep commands thin wrappers over config-driven behavior—no embedded secrets or environment-specific hacks.
- Prefer reusing logging/telemetry utilities from `src/mcp_agent/logging` and `src/mcp_agent/telemetry` rather than custom wiring.
