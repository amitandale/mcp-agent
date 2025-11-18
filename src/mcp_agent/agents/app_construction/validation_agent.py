"""Validation agent that inspects implementations and local tooling output."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field

from mcp_agent.agents.agent import Agent
from mcp_agent.agents.agent_spec import AgentSpec
from mcp_agent.core.context import Context
from mcp_agent.workflows.factory import create_agent

SPEC = AgentSpec(
    name="app_validation",
    instruction=(
        "Run the lint/test suite that each PR blueprint requires, inspect dependency updates, "
        "and verify that the workspace matches the canonical plan. Flag any gaps and request "
        "revisions before allowing commits."
    ),
    server_names=["filesystem", "code-index", "dependency-management", "lsp"],
)


class ValidationIssue(BaseModel):
    """Single validation failure."""

    scope: str
    detail: str


class ValidationResult(BaseModel):
    """Summary of validation status."""

    status: str
    checked: int
    issues: List[ValidationIssue] = Field(default_factory=list)
    logs: List[str] = Field(default_factory=list)


def _run_command(command: list[str], cwd: Path | None = None) -> str:
    process = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    return process.stdout


async def validate_workspace(
    *,
    workspace_path: str,
    implementations: list[dict],
    context: Context | None = None,
) -> ValidationResult:
    """Run lightweight checks against the workspace."""

    del context
    workspace = Path(workspace_path)
    logs: list[str] = []
    issues: list[ValidationIssue] = []

    if (workspace / "pyproject.toml").exists():
        logs.append(_run_command(["python", "-m", "compileall", "-q", "."], cwd=workspace))

    if (workspace / "package.json").exists():
        logs.append("package.json detected; npm/yarn validation deferred in sandbox")

    missing_blueprints = [
        str(index)
        for index, impl in enumerate(implementations, start=1)
        if not impl.get("blueprint")
    ]
    if missing_blueprints:
        issues.append(
            ValidationIssue(
                scope="plan",
                detail="Missing blueprint metadata for implementations "
                + ", ".join(missing_blueprints),
            )
        )

    failing = [
        impl
        for impl in implementations
        if not impl.get("result") or not impl["result"].get("summary")
    ]
    if failing:
        issues.append(
            ValidationIssue(
                scope="tests", detail=f"{len(failing)} implementations missing summaries"
            )
        )

    status = "passed" if not issues else "needs_revision"
    return ValidationResult(status=status, checked=len(implementations), issues=issues, logs=logs)


def build(context: Context | None = None) -> Agent:
    """Instantiate the validation agent."""

    return create_agent(SPEC, context=context)


__all__ = [
    "SPEC",
    "build",
    "ValidationResult",
    "ValidationIssue",
    "validate_workspace",
]
