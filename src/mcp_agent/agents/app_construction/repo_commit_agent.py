"""Agent that finalizes commits for the App Construction workflow."""

from __future__ import annotations

from mcp_agent.agents.agent import Agent
from mcp_agent.agents.agent_spec import AgentSpec
from mcp_agent.core.context import Context
from mcp_agent.workflows.factory import create_agent

SPEC = AgentSpec(
    name="app_repo_commit",
    instruction=(
        "Stage generated artifacts, craft clear commit messages, and push to the configured "
        "app-construction branch. Ensure that branch history reflects the planned PR sequence "
        "and that no deployment-specific assets are touched."
    ),
    server_names=["filesystem", "github"],
)


def build(context: Context | None = None) -> Agent:
    """Instantiate the repo commit agent."""

    return create_agent(SPEC, context=context)


__all__ = ["SPEC", "build"]
