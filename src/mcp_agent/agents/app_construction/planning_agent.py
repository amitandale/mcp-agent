"""Agent that produces system-aware implementation plans."""

from __future__ import annotations

from mcp_agent.agents.agent import Agent
from mcp_agent.agents.agent_spec import AgentSpec
from mcp_agent.core.context import Context
from mcp_agent.workflows.factory import create_agent

SPEC = AgentSpec(
    name="app_execution_planner",
    instruction=(
        "Convert structured spec notes into atomic, independently testable tasks. "
        "Each task must map to concrete files, APIs, or UI components present in the template. "
        "Sequence tasks logically and highlight dependencies that future PRs must respect."
    ),
    server_names=["filesystem", "code-index", "ast-grep"],
)


def build(context: Context | None = None) -> Agent:
    """Instantiate the execution planner agent."""

    return create_agent(SPEC, context=context)


__all__ = ["SPEC", "build"]
