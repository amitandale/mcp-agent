# Scope rules for `src/mcp_agent/logging/`

Structured logging utilities live here.

- Reuse existing transports/formatters; avoid ad-hoc print/debug logging elsewhere in the codebase.
- Keep APIs consistent so CLI/server/workflow layers can configure logging uniformly.
- Coordinate changes with telemetry/tracing to maintain coherent observability signals.
