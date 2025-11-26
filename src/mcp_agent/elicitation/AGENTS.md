# Scope rules for `src/mcp_agent/elicitation/`

Human-in-the-loop and elicitation utilities live here.

- Reuse shared types/handlers; do not create parallel interaction protocols outside the MCP/human input abstractions.
- Keep this layer framework-agnostic so workflows and agents can consume it without extra wiring.
- Validate changes with existing examples/tests to avoid regressions in elicitation flows.
