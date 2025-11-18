"""Agent responsible for bootstrapping repositories for the App Construction workflow."""

from __future__ import annotations

from mcp_agent.agents.agent import Agent
from mcp_agent.agents.agent_spec import AgentSpec
from mcp_agent.core.context import Context
from mcp_agent.workflows.factory import create_agent

SPEC = AgentSpec(
    name="app_repo_initializer",
    instruction=(
        "You provision Git repositories for newly requested applications. "
        "Clone or copy the requested template, create the target branch, and "
        "wire Git remotes so downstream agents can push to the app-construction branch. "
        "Do not scaffold business logic; only perform bootstrap tasks that keep the repo "
        "ready for additional workflows."
    ),
    server_names=["github", "filesystem"],
)


def build(context: Context | None = None) -> Agent:
    """Instantiate the repository initializer agent."""

    return create_agent(SPEC, context=context)


__all__ = ["SPEC", "build"]
