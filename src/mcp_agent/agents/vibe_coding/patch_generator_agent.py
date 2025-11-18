"""Agent specification that prepares targeted remediation patches."""

from __future__ import annotations

from mcp_agent.agents.agent import Agent
from mcp_agent.agents.agent_spec import AgentSpec
from mcp_agent.core.context import Context
from mcp_agent.workflows.factory import create_agent

SPEC = AgentSpec(
    name="vibe_patch_generator",
    instruction=(
        """Synthesize precise patches that address issues uncovered during the "
        "analysis stages. Operate directly on the repository tree, propose "
        "minimal diff fixes, and prepare metadata describing test impact."""
    ),
    server_names=["tree-sitter", "ast-grep", "filesystem"],
)


def build(context: Context | None = None) -> Agent:
    """Instantiate the patch generator agent bound to the provided context."""

    return create_agent(SPEC, context=context)


__all__ = ["SPEC", "build"]
