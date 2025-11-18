"""Agent that converts plans into artifact-aware PR blueprints."""

from __future__ import annotations

from mcp_agent.agents.agent import Agent
from mcp_agent.agents.agent_spec import AgentSpec
from mcp_agent.core.context import Context
from mcp_agent.workflows.factory import create_agent

SPEC = AgentSpec(
    name="app_pr_generation",
    instruction=(
        "Prepare detailed PR blueprints for each planned feature. Identify the exact files, "
        "directories, and code regions to modify, and describe the validations (tests, lint, "
        "typing) that must run before marking the PR ready."
    ),
    server_names=["filesystem", "code-index", "ast-grep"],
)


def build(context: Context | None = None) -> Agent:
    """Instantiate the PR generation agent."""

    return create_agent(SPEC, context=context)


__all__ = ["SPEC", "build"]
