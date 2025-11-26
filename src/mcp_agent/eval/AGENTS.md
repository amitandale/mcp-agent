# Scope rules for `src/mcp_agent/eval/`

Evaluation helpers belong here and should stay reusable.

- Build evaluators on existing workflow/agent outputs; do not introduce custom execution paths.
- Keep dependencies light and avoid hardcoded model/provider logic—use adapters from workflows or agents instead.
- Ensure tests cover any new metrics or scoring utilities.
