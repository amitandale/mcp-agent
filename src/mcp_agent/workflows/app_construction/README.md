# App Construction Orchestrator

This workflow composes six specialized agents and the VibeCoding workflow into a deterministic pipeline that builds a "ready for CI" application skeleton.

Key traits:

- **Config-driven**: `mcp_agent.config.yaml` defines the participating agents, stage order, and VibeCoding integration. Nothing is hardcoded in the orchestrator so new templates or roles can be introduced by editing config only.
- **Spec-aligned**: The workflow reads `docs/app_construction/canonical_system.md` (or a supplied path) and carries structured data from parsing → planning → PR blueprinting → implementation.
- **VibeCoding integration**: Each PR blueprint is executed by the production `VibeCodingOrchestrator`, ensuring we reuse the same PR assembly process as other workflows.
- **Validation gate**: Work stops if validations fail; the orchestrator emits detailed stage metadata so downstream reviewers know what needs attention.

For usage, import `AppConstructionOrchestrator` from `src/mcp_agent/workflows/app_construction/app_construction_orchestrator.py` (or the package shortcut `mcp_agent.workflows.app_construction`) or run it through the `MCPApp` workflow registration defined in that module.
