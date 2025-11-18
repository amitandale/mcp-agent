"""Repository initialization agent for the App Construction workflow.

The App Construction orchestrator interacts with purpose-built helper
functions rather than relying on free-form prompts.  This module keeps the
``Agent`` definition so the workflow can register the component with the MCP
runtime, while also exposing structured request/response models that encode
the bootstrap behaviour.

The helper performs three concrete tasks:

1. Resolve the destination workspace and copy the selected template.
2. Ensure the workspace is a Git repository on the target branch.
3. Emit a structured summary listing key metadata so downstream stages can
   use the workspace without further filesystem inspection.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, Field

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


class RepoInitializationRequest(BaseModel):
    """Input payload for ``initialize_repo``."""

    repo_name: str = Field(..., description="Name of the repository to create")
    target_branch: str = Field(..., description="Branch that downstream PRs will use")
    repo_template: str | None = Field(
        default=None, description="Optional path to a filesystem template"
    )
    destination_root: str | None = Field(
        default=None,
        description=(
            "Directory that will contain the generated repository.  Defaults to "
            "the orchestrator's working directory."
        ),
    )
    allow_existing: bool = Field(
        default=True,
        description="Whether an existing workspace can be reused if discovered.",
    )


class RepoInitializationResult(BaseModel):
    """Structured information about the bootstrapped repository."""

    workspace_path: str
    branch: str
    files_discovered: int
    template_applied: bool
    git_initialized: bool
    latest_commit: str | None = None


def _copy_template(template: Path, destination: Path) -> None:
    if not template.exists():
        destination.mkdir(parents=True, exist_ok=True)
        return
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(template, destination)


def _collect_files(directory: Path) -> Iterable[Path]:
    for item in directory.rglob("*"):
        if item.is_file():
            yield item


def _ensure_branch(directory: Path, branch: str) -> tuple[bool, str | None]:
    git_dir = directory / ".git"
    initialized = git_dir.exists()
    if not initialized:
        subprocess.run(
            ["git", "init", "-b", branch],
            cwd=str(directory),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        initialized = True
    else:
        subprocess.run(
            ["git", "checkout", branch],
            cwd=str(directory),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    commit_ref = None
    try:
        commit_ref = (
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(directory),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            .stdout.decode()
            .strip()
        )
    except subprocess.CalledProcessError:
        commit_ref = None
    return initialized, commit_ref


async def initialize_repo(
    request: RepoInitializationRequest,
    *,
    context: Context | None = None,
) -> RepoInitializationResult:
    """Materialize a repository from a template and ensure Git metadata."""

    del context  # currently unused but included for parity with other agents
    destination_root = (
        Path(request.destination_root).expanduser()
        if request.destination_root
        else Path.cwd() / "generated_apps"
    )
    destination_root.mkdir(parents=True, exist_ok=True)
    workspace = destination_root / request.repo_name

    if workspace.exists() and not request.allow_existing:
        raise FileExistsError(f"Workspace '{workspace}' already exists")

    if request.repo_template:
        template_path = Path(request.repo_template).expanduser()
        await asyncio.to_thread(_copy_template, template_path, workspace)
        template_applied = True
    else:
        workspace.mkdir(parents=True, exist_ok=True)
        template_applied = False

    git_initialized, commit_ref = await asyncio.to_thread(
        _ensure_branch, workspace, request.target_branch
    )
    file_count = sum(1 for _ in _collect_files(workspace))

    return RepoInitializationResult(
        workspace_path=str(workspace),
        branch=request.target_branch,
        files_discovered=file_count,
        template_applied=template_applied,
        git_initialized=git_initialized,
        latest_commit=commit_ref,
    )


def build(context: Context | None = None) -> Agent:
    """Instantiate the repository initializer agent."""

    return create_agent(SPEC, context=context)


__all__ = [
    "SPEC",
    "build",
    "RepoInitializationRequest",
    "RepoInitializationResult",
    "initialize_repo",
]
