"""Agent specification for analyzing pull request structure and metadata."""

from __future__ import annotations

from mcp_agent.agents.agent import Agent
from mcp_agent.agents.agent_spec import AgentSpec
from mcp_agent.core.context import Context
from mcp_agent.workflows.factory import create_agent

SPEC = AgentSpec(
    name="vibe_pr_analyzer",
    instruction=(
        """You are the entry-point analyst for GitHub pull requests. "
        "Review PR metadata, extract linked issues, enumerate commits, and "
        "summarize the overall scope. Identify risky files, estimate diff "
        "complexity, and prepare structured findings for downstream agents."""
    ),
    server_names=["github", "code-index", "tree-sitter", "filesystem"],
)


def build(context: Context | None = None) -> Agent:
    """Instantiate the PR analyzer agent bound to the provided context."""

    return create_agent(SPEC, context=context)


__all__ = ["SPEC", "build"]
