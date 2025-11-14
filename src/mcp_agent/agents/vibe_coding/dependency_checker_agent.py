"""Agent specification responsible for dependency impact analysis."""

from __future__ import annotations

from mcp_agent.agents.agent import Agent
from mcp_agent.agents.agent_spec import AgentSpec
from mcp_agent.core.context import Context
from mcp_agent.workflows.factory import create_agent

SPEC = AgentSpec(
    name="vibe_dependency_checker",
    instruction=(
        """Evaluate dependency file changes, verify compatibility, and detect "
        "potential breaking upgrades. Cross-reference lockfiles, manifests, "
        "and known vulnerability databases to flag high-risk updates."""
    ),
    server_names=["dependency-management", "github", "filesystem"],
)


def build(context: Context | None = None) -> Agent:
    """Instantiate the dependency checker agent bound to the context."""

    return create_agent(SPEC, context=context)


__all__ = ["SPEC", "build"]
