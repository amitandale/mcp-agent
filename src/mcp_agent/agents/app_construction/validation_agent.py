"""Agent that validates the workspace against the planned specification."""

from __future__ import annotations

from mcp_agent.agents.agent import Agent
from mcp_agent.agents.agent_spec import AgentSpec
from mcp_agent.core.context import Context
from mcp_agent.workflows.factory import create_agent

SPEC = AgentSpec(
    name="app_validation",
    instruction=(
        "Run the lint/test suite that each PR blueprint requires, inspect dependency updates, "
        "and verify that the workspace matches the canonical plan. Flag any gaps and request "
        "revisions before allowing commits."
    ),
    server_names=["filesystem", "code-index", "dependency-management", "lsp"],
)


def build(context: Context | None = None) -> Agent:
    """Instantiate the validation agent."""

    return create_agent(SPEC, context=context)


__all__ = ["SPEC", "build"]
