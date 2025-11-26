# Scope rules for `src/mcp_agent/server/`

Server glue lives here. Apply root rules and:

- Use existing adapters to expose tools via MCP; do not build one-off HTTP/WS servers outside the shared abstractions.
- Respect auth/token verification helpers already provided; avoid custom security flows without review.
- Keep implementations generic so agents/workflows can mount tools consistently; domain-specific servers belong in examples only.
