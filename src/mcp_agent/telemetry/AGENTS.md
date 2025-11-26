# Scope rules for `src/mcp_agent/telemetry/`

Telemetry hooks live here.

- Hook into existing logging/tracing contexts rather than creating standalone metrics pipelines.
- Keep exports lightweight and optional so core flows work without telemetry enabled.
- Do not embed provider credentials; rely on config-driven setup.
