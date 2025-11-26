# Scope rules for `src/mcp_agent/core/`

Core primitives live here; changes ripple across the codebase. Follow root guidance and:

- Avoid breaking signatures for `Context`, `ContextDependent`, and shared exceptions; keep them backward compatible.
- Do not duplicate context handling or request-scoped state elsewhere—extend these primitives instead.
- Keep this layer minimal and dependency-light to avoid cyclical imports.
