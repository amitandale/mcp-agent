"""Agent that summarizes git state and prepares commits."""

from __future__ import annotations

import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

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


class CommitSummary(BaseModel):
    """Structured commit metadata for downstream CI."""

    branch: str
    staged: int
    unstaged: int
    status_output: str
    ready_for_ci: bool = Field(default=False)


def _git_status(repo: Path) -> tuple[int, int, str]:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=str(repo),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    status_output = result.stdout.strip()
    staged = len([line for line in status_output.splitlines() if line.startswith(("M ", "A ", "D "))])
    unstaged = len([line for line in status_output.splitlines() if line.startswith((" M", "??", " D"))])
    return staged, unstaged, status_output


async def summarize_commits(
    *,
    workspace_path: str,
    branch: str,
    validation_passed: bool,
    context: Context | None = None,
) -> CommitSummary:
    """Summarize git state for the repo_commit stage."""

    del context
    repo = Path(workspace_path)
    staged, unstaged, status_output = _git_status(repo)
    ready = validation_passed and unstaged == 0
    return CommitSummary(
        branch=branch,
        staged=staged,
        unstaged=unstaged,
        status_output=status_output,
        ready_for_ci=ready,
    )


def build(context: Context | None = None) -> Agent:
    """Instantiate the repo commit agent."""

    return create_agent(SPEC, context=context)


__all__ = [
    "SPEC",
    "build",
    "CommitSummary",
    "summarize_commits",
]
