"""Coordinator agent specification that supervises the VibeCoding workflow."""

from __future__ import annotations

from mcp_agent.agents.agent import Agent
from mcp_agent.agents.agent_spec import AgentSpec
from mcp_agent.core.context import Context
from mcp_agent.workflows.factory import create_agent

SPEC = AgentSpec(
    name="vibe_orchestrator",
    instruction=(
        """Oversee the multi-stage pull request workflow. Coordinate agents, "
        "manage shared context, and surface a comprehensive report that "
        "summarizes analysis findings, recommended patches, and outstanding "
        "risks."""
    ),
    server_names=[
        "github",
        "code-index",
        "tree-sitter",
        "ast-grep",
        "dependency-management",
        "sourcerer",
        "lsp",
        "filesystem",
    ],
)


def build(context: Context | None = None) -> Agent:
    """Instantiate the orchestrator agent bound to the provided context."""

    return create_agent(SPEC, context=context)


__all__ = ["SPEC", "build"]
