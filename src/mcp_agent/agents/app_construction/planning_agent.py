"""Agent that converts parsed specs into deterministic implementation plans."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from mcp_agent.agents.agent import Agent
from mcp_agent.agents.agent_spec import AgentSpec
from mcp_agent.core.context import Context
from mcp_agent.workflows.factory import create_agent

from .spec_parser_agent import SpecParserResult

SPEC = AgentSpec(
    name="app_execution_planner",
    instruction=(
        "Convert structured spec notes into atomic, independently testable tasks. "
        "Each task must map to concrete files, APIs, or UI components present in the template. "
        "Sequence tasks logically and highlight dependencies that future PRs must respect."
    ),
    server_names=["filesystem", "code-index", "ast-grep"],
)


class PlanTask(BaseModel):
    """Atomic unit of implementation that eventually maps to a PR."""

    identifier: str
    task: str
    entity: str
    kind: str
    artifacts: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    tests: List[str] = Field(default_factory=list)


class PlanningResult(BaseModel):
    """Ordered plan with coverage metadata."""

    tasks: List[PlanTask]
    coverage: dict[str, List[str]]


def _derive_tasks(spec: SpecParserResult) -> List[PlanTask]:
    module_map = spec.module_map()
    modules = spec.module_candidates or spec.primary_entities or ["Workspace"]
    tasks: list[PlanTask] = []
    for index, module in enumerate(modules, start=1):
        module_key = module.replace(" ", "_").lower()
        backend_files = [f for f in module_map.get(module, []) if f.endswith(".py")]
        frontend_files = [
            f
            for f in module_map.get(module, [])
            if f.endswith((".tsx", ".jsx")) or "/page" in f
        ]
        api_task = PlanTask(
            identifier=f"task-{index:02d}-api",
            task=f"Implement CRUD endpoints for {module}",
            entity=module,
            kind="backend",
            artifacts=backend_files or [f"api/{module_key}.py"],
            tests=[f"tests/{module_key}/test_api.py"],
        )
        ui_task = PlanTask(
            identifier=f"task-{index:02d}-ui",
            task=f"Render {module} dashboard widgets",
            entity=module,
            kind="frontend",
            artifacts=frontend_files or [f"app/{module_key}/page.tsx"],
            dependencies=[api_task.identifier],
            tests=[f"tests/{module_key}/test_ui.py"],
        )
        tasks.extend([api_task, ui_task])
    return tasks


async def generate_plan(
    spec: SpecParserResult,
    *,
    context: Context | None = None,
) -> PlanningResult:
    """Create an ordered plan that mirrors the canonical spec."""

    del context
    tasks = _derive_tasks(spec)
    coverage: dict[str, list[str]] = {}
    for task in tasks:
        coverage.setdefault(task.entity, []).append(task.identifier)
    return PlanningResult(tasks=tasks, coverage=coverage)


def build(context: Context | None = None) -> Agent:
    """Instantiate the execution planner agent."""

    return create_agent(SPEC, context=context)


__all__ = [
    "SPEC",
    "build",
    "PlanTask",
    "PlanningResult",
    "generate_plan",
]
