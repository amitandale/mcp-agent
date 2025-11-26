# Scope rules for `src/mcp_agent/tracing/`

Tracing utilities live here.

- Use existing OTEL/token counting utilities; avoid bespoke tracing stacks.
- Keep instrumentation opt-in and consistent with telemetry/logging; no hardcoded exporters.
- Ensure new tracing hooks do not bypass request context or leak PII.
