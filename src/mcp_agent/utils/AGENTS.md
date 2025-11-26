# Scope rules for `src/mcp_agent/utils/`

Shared utilities live here; keep them small and generic.

- Avoid domain-specific helpers—utilities should support multiple modules (content/mime/pydantic/tool filtering, etc.).
- Do not duplicate functionality already provided elsewhere in the runtime.
- Maintain backward compatibility; prefer additive helpers with tests.
