"""Generate artifact-aware PR blueprints from an execution plan."""

from __future__ import annotations

from typing import Iterable, List

from pydantic import BaseModel, Field

from mcp_agent.agents.agent import Agent
from mcp_agent.agents.agent_spec import AgentSpec
from mcp_agent.core.context import Context
from mcp_agent.workflows.factory import create_agent

from .planning_agent import PlanTask, PlanningResult

SPEC = AgentSpec(
    name="app_pr_generation",
    instruction=(
        "Prepare detailed PR blueprints for each planned feature. Identify the exact files, "
        "directories, and code regions to modify, and describe the validations (tests, lint, "
        "typing) that must run before marking the PR ready."
    ),
    server_names=["filesystem", "code-index", "ast-grep"],
)


class PullRequestBlueprint(BaseModel):
    """Structured PR description consumed by vibe_coding."""

    identifier: str
    title: str
    branch: str
    description: str
    files: List[str] = Field(default_factory=list)
    tests: List[str] = Field(default_factory=list)
    plan_reference: PlanTask
    pr_url: str | None = None


class BlueprintResult(BaseModel):
    """List of generated PR blueprints."""

    blueprints: List[PullRequestBlueprint]


def _render_description(task: PlanTask) -> str:
    summary_lines = [task.task, "", "Changes:"]
    for artifact in task.artifacts:
        summary_lines.append(f"- Update {artifact}")
    summary_lines.append("\nTests:")
    for test in task.tests:
        summary_lines.append(f"- {test}")
    return "\n".join(summary_lines)


async def generate_blueprints(
    plan: PlanningResult,
    *,
    target_branch: str,
    context: Context | None = None,
) -> BlueprintResult:
    """Convert plan tasks to PR metadata."""

    del context
    blueprints: list[PullRequestBlueprint] = []
    for index, task in enumerate(plan.tasks, start=1):
        branch = f"{target_branch}-{index:02d}-{task.kind}"
        blueprint = PullRequestBlueprint(
            identifier=task.identifier,
            title=f"{task.kind.title()}: {task.entity}",
            branch=branch,
            description=_render_description(task),
            files=task.artifacts,
            tests=task.tests,
            plan_reference=task,
            pr_url=f"https://example.com/{branch}",
        )
        blueprints.append(blueprint)
    return BlueprintResult(blueprints=blueprints)


def build(context: Context | None = None) -> Agent:
    """Instantiate the PR generation agent."""

    return create_agent(SPEC, context=context)


__all__ = [
    "SPEC",
    "build",
    "PullRequestBlueprint",
    "BlueprintResult",
    "generate_blueprints",
]
