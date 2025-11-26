# Scope rules for `src/mcp_agent/human_input/`

Human input handling lives here.

- Extend the shared handlers and types; do not bypass MCP/human input abstractions with ad-hoc prompts or blocking calls.
- Keep implementations pluggable so workflows can opt-in without new runtime wiring.
- Avoid embedding UI/client code; that belongs in examples or external apps.
