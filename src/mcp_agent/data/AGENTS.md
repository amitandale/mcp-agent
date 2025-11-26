# Scope rules for `src/mcp_agent/data/`

This directory primarily contains embedded examples and reference assets.

- Keep code here read-only/reference; production logic belongs under the main `src/mcp_agent/**` modules.
- When updating examples, mirror patterns from production code instead of inventing new frameworks.
- Do not store secrets or environment-specific configs in this folder.
