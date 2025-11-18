"""Agent that parses the canonical system description and local template files."""

from __future__ import annotations

from mcp_agent.agents.agent import Agent
from mcp_agent.agents.agent_spec import AgentSpec
from mcp_agent.core.context import Context
from mcp_agent.workflows.factory import create_agent

SPEC = AgentSpec(
    name="app_spec_parser",
    instruction=(
        "Read the canonical system description, inspect the cloned template, and "
        "summarize relevant modules, components, and UI primitives. Produce structured "
        "notes that map spec requirements to existing folders so the planner can operate "
        "without assumptions."
    ),
    server_names=["filesystem", "code-index"],
)


def build(context: Context | None = None) -> Agent:
    """Instantiate the spec parser agent."""

    return create_agent(SPEC, context=context)


__all__ = ["SPEC", "build"]
