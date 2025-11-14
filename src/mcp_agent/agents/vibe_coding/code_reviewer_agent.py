"""Agent specification for code review and quality analysis."""

from __future__ import annotations

from mcp_agent.agents.agent import Agent
from mcp_agent.agents.agent_spec import AgentSpec
from mcp_agent.core.context import Context
from mcp_agent.workflows.factory import create_agent

SPEC = AgentSpec(
    name="vibe_code_reviewer",
    instruction=(
        """Perform deep code review on the proposed changes. Identify "
        "potential regressions, code smells, anti-patterns, and style "
        "violations. Surface reasoning with explicit references to the "
        "diff and repository history."""
    ),
    server_names=["code-index", "ast-grep", "sourcerer", "lsp"],
)


def build(context: Context | None = None) -> Agent:
    """Instantiate the code reviewer agent bound to the provided context."""

    return create_agent(SPEC, context=context)


__all__ = ["SPEC", "build"]
