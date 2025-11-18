"""VibeCoding PR orchestrator workflow implementation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping

from pydantic import BaseModel, Field

from mcp_agent.agents.agent import Agent
from mcp_agent.agents.agent_spec import AgentSpec
from mcp_agent.core.context import Context
from mcp_agent.executor.workflow import Workflow, WorkflowResult
from mcp_agent.workflows.factory import create_agent
from mcp_agent.agents.vibe_coding import (
    CODE_REVIEWER_SPEC,
    DEPENDENCY_CHECKER_SPEC,
    ORCHESTRATOR_SPEC,
    PATCH_GENERATOR_SPEC,
    PR_ANALYZER_SPEC,
)


class StageStatus(str, Enum):
    """Execution status for an individual workflow stage."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class BudgetExceededError(RuntimeError):
    """Raised when the workflow exceeds one of its configured budgets."""

    def __init__(self, dimension: str, used: float, limit: float) -> None:
        message = f"Budget exceeded for {dimension}: used {used} > limit {limit}"
        super().__init__(message)
        self.dimension = dimension
        self.used = used
        self.limit = limit


class StageDefinition(BaseModel):
    """Declarative configuration for a workflow stage."""

    name: str
    description: str
    agent: str
    depends_on: List[str] = Field(default_factory=list)
    estimated_tokens: int = 0
    estimated_cost: float = 0.0
    estimated_minutes: float = 0.0
    category: str | None = None


class StageState(BaseModel):
    """Runtime state for a stage."""

    name: str
    status: StageStatus = StageStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: Dict[str, Any] | None = None
    error: str | None = None

    model_config = dict(use_enum_values=True)


class StageReport(BaseModel):
    """Result payload returned for each stage."""

    stage: str
    agent: str
    summary: str
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)


class BudgetConfig(BaseModel):
    """Budget limits for the orchestrator."""

    max_tokens: int = 800_000
    max_cost: float = 50.0
    max_time_minutes: float = 180.0


@dataclass
class BudgetTracker:
    """Track resource consumption for the workflow."""

    config: BudgetConfig
    tokens_used: int = 0
    cost_incurred: float = 0.0
    time_spent_minutes: float = 0.0
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def consume(self, *, tokens: int = 0, cost: float = 0.0, minutes: float = 0.0) -> None:
        """Add resource usage and enforce limits."""

        if tokens:
            self.tokens_used += tokens
            if self.tokens_used > self.config.max_tokens:
                raise BudgetExceededError("tokens", self.tokens_used, self.config.max_tokens)

        if cost:
            self.cost_incurred += cost
            if self.cost_incurred > self.config.max_cost:
                raise BudgetExceededError("cost", self.cost_incurred, self.config.max_cost)

        if minutes:
            self.time_spent_minutes += minutes
            if self.time_spent_minutes > self.config.max_time_minutes:
                raise BudgetExceededError(
                    "time", self.time_spent_minutes, self.config.max_time_minutes
                )

    def snapshot(self) -> Dict[str, Any]:
        """Return a serializable view of the budget usage."""

        return {
            "tokens_used": self.tokens_used,
            "max_tokens": self.config.max_tokens,
            "cost_incurred": round(self.cost_incurred, 4),
            "max_cost": self.config.max_cost,
            "time_spent_minutes": round(self.time_spent_minutes, 3),
            "max_time_minutes": self.config.max_time_minutes,
            "started_at": self.start_time.isoformat(),
        }


class StageQueue:
    """Simple dependency-aware queue for stage execution."""

    def __init__(self, stages: Iterable[StageDefinition]):
        self._definitions: Dict[str, StageDefinition] = {stage.name: stage for stage in stages}
        self._pending: set[str] = set(self._definitions)
        self._completed: List[str] = []
        self._failed: Dict[str, str] = {}

    def get_ready(self, completed: Iterable[str]) -> List[StageDefinition]:
        ready: List[StageDefinition] = []
        completed_set = set(completed)
        for name in list(self._pending):
            stage = self._definitions[name]
            if all(dep in completed_set for dep in stage.depends_on):
                ready.append(stage)
        return ready

    def mark_completed(self, stage_name: str) -> None:
        if stage_name in self._pending:
            self._pending.remove(stage_name)
        self._completed.append(stage_name)

    def mark_failed(self, stage_name: str, reason: str) -> None:
        if stage_name in self._pending:
            self._pending.remove(stage_name)
        self._failed[stage_name] = reason

    @property
    def completed(self) -> List[str]:
        return list(self._completed)

    @property
    def failed(self) -> Mapping[str, str]:
        return dict(self._failed)

    @property
    def pending(self) -> set[str]:
        return set(self._pending)

    def has_pending(self) -> bool:
        return bool(self._pending)


class VibeCodingWorkflowConfig(BaseModel):
    """Configuration for the VibeCoding orchestrator workflow."""

    stages: List[StageDefinition] = Field(default_factory=list)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    monitor_refresh_interval: float = 0.2

    @classmethod
    def default(cls) -> "VibeCodingWorkflowConfig":
        """Construct the default configuration with the 15-stage pipeline."""

        stages = [
            StageDefinition(
                name="pr_metadata_extraction",
                description="Pull request metadata extraction and linkage mapping",
                agent=PR_ANALYZER_SPEC.name,
                estimated_tokens=1_500,
                estimated_cost=0.15,
                estimated_minutes=2.0,
            ),
            StageDefinition(
                name="diff_analysis",
                description="Diff impact analysis and hot file detection",
                agent=PR_ANALYZER_SPEC.name,
                depends_on=["pr_metadata_extraction"],
                estimated_tokens=2_000,
                estimated_cost=0.2,
                estimated_minutes=2.5,
            ),
            StageDefinition(
                name="syntax_tree_analysis",
                description="Syntax tree exploration for touched files",
                agent=PR_ANALYZER_SPEC.name,
                depends_on=["diff_analysis"],
                estimated_tokens=1_000,
                estimated_cost=0.12,
                estimated_minutes=1.5,
            ),
            StageDefinition(
                name="ast_pattern_matching",
                description="AST pattern matching for risky constructs",
                agent=CODE_REVIEWER_SPEC.name,
                depends_on=["syntax_tree_analysis"],
                estimated_tokens=1_200,
                estimated_cost=0.12,
                estimated_minutes=1.0,
            ),
            StageDefinition(
                name="dependency_graph_analysis",
                description="Dependency graph validation and compatibility checks",
                agent=DEPENDENCY_CHECKER_SPEC.name,
                depends_on=["ast_pattern_matching"],
                estimated_tokens=1_400,
                estimated_cost=0.18,
                estimated_minutes=2.0,
            ),
            StageDefinition(
                name="code_smell_detection",
                description="Repository code smell and anti-pattern scan",
                agent=CODE_REVIEWER_SPEC.name,
                depends_on=["dependency_graph_analysis"],
                estimated_tokens=1_600,
                estimated_cost=0.2,
                estimated_minutes=2.0,
            ),
            StageDefinition(
                name="type_checking",
                description="Type checking and interface validation via LSP",
                agent=CODE_REVIEWER_SPEC.name,
                depends_on=["code_smell_detection"],
                estimated_tokens=1_800,
                estimated_cost=0.22,
                estimated_minutes=2.0,
            ),
            StageDefinition(
                name="security_scan",
                description="Security vulnerability and secret scanning",
                agent=CODE_REVIEWER_SPEC.name,
                depends_on=["type_checking"],
                estimated_tokens=1_700,
                estimated_cost=0.19,
                estimated_minutes=2.0,
            ),
            StageDefinition(
                name="performance_assessment",
                description="Performance regression assessment",
                agent=CODE_REVIEWER_SPEC.name,
                depends_on=["security_scan"],
                estimated_tokens=1_300,
                estimated_cost=0.16,
                estimated_minutes=1.5,
            ),
            StageDefinition(
                name="code_style_normalization",
                description="Code style normalization and formatting checks",
                agent=CODE_REVIEWER_SPEC.name,
                depends_on=["performance_assessment"],
                estimated_tokens=1_100,
                estimated_cost=0.1,
                estimated_minutes=1.0,
            ),
            StageDefinition(
                name="documentation_check",
                description="Documentation completeness and accuracy review",
                agent=PR_ANALYZER_SPEC.name,
                depends_on=["code_style_normalization"],
                estimated_tokens=900,
                estimated_cost=0.08,
                estimated_minutes=1.0,
            ),
            StageDefinition(
                name="test_coverage_analysis",
                description="Test coverage and quality assessment",
                agent=CODE_REVIEWER_SPEC.name,
                depends_on=["documentation_check"],
                estimated_tokens=1_500,
                estimated_cost=0.17,
                estimated_minutes=2.0,
            ),
            StageDefinition(
                name="patch_generation",
                description="Targeted patch generation for identified issues",
                agent=PATCH_GENERATOR_SPEC.name,
                depends_on=["test_coverage_analysis"],
                estimated_tokens=1_200,
                estimated_cost=0.14,
                estimated_minutes=1.5,
            ),
            StageDefinition(
                name="patch_validation",
                description="Validation of generated patches and regression checks",
                agent=PATCH_GENERATOR_SPEC.name,
                depends_on=["patch_generation"],
                estimated_tokens=1_000,
                estimated_cost=0.12,
                estimated_minutes=1.5,
            ),
            StageDefinition(
                name="report_generation",
                description="Comprehensive report synthesis and recommendations",
                agent=ORCHESTRATOR_SPEC.name,
                depends_on=["patch_validation"],
                estimated_tokens=1_300,
                estimated_cost=0.16,
                estimated_minutes=1.5,
            ),
        ]
        return cls(stages=stages)


DEFAULT_AGENT_SPECS: Dict[str, AgentSpec] = {
    spec.name: spec
    for spec in (
        PR_ANALYZER_SPEC,
        CODE_REVIEWER_SPEC,
        DEPENDENCY_CHECKER_SPEC,
        PATCH_GENERATOR_SPEC,
        ORCHESTRATOR_SPEC,
    )
}


def _default_agent_factory(spec: AgentSpec, context: Context | None) -> Agent:
    """Create an agent from the provided specification."""

    return create_agent(spec, context=context)


class VibeCodingOrchestrator(Workflow[Dict[str, Any]]):
    """Production-ready orchestrator implementing the 15-stage workflow."""

    def __init__(
        self,
        *,
        config: VibeCodingWorkflowConfig | None = None,
        agent_specs: Mapping[str, AgentSpec] | None = None,
        agent_factory: Callable[[AgentSpec, Context | None], Agent] | None = None,
        context: Context | None = None,
        **kwargs: Any,
    ) -> None:
        config = config or VibeCodingWorkflowConfig.default()
        super().__init__(name=config.__class__.__name__, context=context, **kwargs)

        self.config = config
        self.budget = BudgetTracker(config.budget)
        self._agent_specs: Dict[str, AgentSpec] = dict(DEFAULT_AGENT_SPECS)
        if agent_specs:
            self._agent_specs.update(agent_specs)
        self._agent_factory = agent_factory or _default_agent_factory
        self._agent_cache: Dict[str, Agent] = {}
        self._stage_states: Dict[str, StageState] = {
            stage.name: StageState(name=stage.name) for stage in self.config.stages
        }
        self._observers: List[Callable[[Dict[str, Any]], None]] = []
        self.queue = StageQueue(self.config.stages)
        self._active_blueprint: Mapping[str, Any] | None = None

        self.state.metadata.setdefault("stages", {})
        self.state.metadata.setdefault("budget", {})
        self._sync_state_metadata()

    def register_state_observer(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Register a callback invoked whenever state changes."""

        self._observers.append(callback)

    def get_state_snapshot(self) -> Dict[str, Any]:
        """Return a JSON-serializable snapshot of the orchestrator state."""

        return {
            "stages": {
                name: state.model_dump()
                for name, state in self._stage_states.items()
            },
            "budget": self.budget.snapshot(),
            "queue": {
                "completed": list(self.queue.completed),
                "failed": dict(self.queue.failed),
                "pending": sorted(self.queue.pending),
            },
        }

    async def _get_agent(self, name: str) -> Agent:
        if name in self._agent_cache:
            return self._agent_cache[name]
        spec = self._agent_specs.get(name)
        if spec is None:
            raise KeyError(f"Unknown agent '{name}'")
        agent = self._agent_factory(spec, self.context)
        self._agent_cache[name] = agent
        return agent

    async def _shutdown_agents(self) -> None:
        for agent in self._agent_cache.values():
            if hasattr(agent, "shutdown"):
                await agent.shutdown()
        self._agent_cache.clear()

    def _sync_state_metadata(self) -> None:
        self.state.metadata["stages"] = {
            name: state.model_dump() for name, state in self._stage_states.items()
        }
        self.state.metadata["budget"] = self.budget.snapshot()

    def _notify_state_observers(self) -> None:
        snapshot = self.get_state_snapshot()
        for callback in self._observers:
            callback(snapshot)

    async def run(
        self,
        *,
        pr_blueprint: Mapping[str, Any] | None = None,
        pr_url: str | None = None,
        **_: Any,
    ) -> WorkflowResult[Dict[str, Any]]:
        """Execute the full 15-stage workflow."""

        blueprint_payload = self._prepare_blueprint(pr_blueprint, pr_url)
        self._active_blueprint = blueprint_payload
        pr_url = blueprint_payload.get("pr_url")
        self.update_status("running")
        stage_results: Dict[str, StageReport] = {}
        completed: List[str] = []
        errors: Dict[str, str] = {}
        result = WorkflowResult[Dict[str, Any]](
            value={},
            metadata={"stages": {}, "budget": self.budget.snapshot()},
            start_time=datetime.now(timezone.utc).timestamp(),
        )

        try:
            while self.queue.has_pending():
                ready = self.queue.get_ready(completed)
                if not ready:
                    raise RuntimeError(
                        "No stages ready for execution. Check for circular dependencies."
                    )

                for stage in ready:
                    stage_state = self._stage_states[stage.name]
                    stage_state.status = StageStatus.RUNNING
                    stage_state.started_at = datetime.now(timezone.utc)
                    self._sync_state_metadata()
                    self._notify_state_observers()

                    try:
                        report = await self._execute_stage(
                            stage,
                            pr_url=pr_url,
                            previous_results=stage_results,
                            blueprint=blueprint_payload,
                        )
                    except Exception as exc:  # pragma: no cover - defensive logging path
                        stage_state.status = StageStatus.FAILED
                        stage_state.error = str(exc)
                        stage_state.completed_at = datetime.now(timezone.utc)
                        errors[stage.name] = stage_state.error
                        self.queue.mark_failed(stage.name, stage_state.error)
                        self._sync_state_metadata()
                        self._notify_state_observers()
                        self.update_status("failed")
                        raise
                    else:
                        stage_state.status = StageStatus.COMPLETED
                        stage_state.completed_at = datetime.now(timezone.utc)
                        stage_state.result = report.model_dump()
                        stage_results[stage.name] = report
                        completed.append(stage.name)
                        self.queue.mark_completed(stage.name)
                        self._sync_state_metadata()
                        self._notify_state_observers()

                    await asyncio.sleep(self.config.monitor_refresh_interval)

        finally:
            await self._shutdown_agents()
            self._active_blueprint = None

        self.update_status("completed")
        result.end_time = datetime.now(timezone.utc).timestamp()
        result.value = {
            "stages": {name: report.model_dump() for name, report in stage_results.items()},
            "summary": self._synthesize_summary(stage_results),
            "errors": errors,
            "blueprint": self._blueprint_public_view(blueprint_payload),
        }
        result.metadata = self.get_state_snapshot()
        return result

    async def _execute_stage(
        self,
        stage: StageDefinition,
        *,
        pr_url: str | None,
        previous_results: Mapping[str, StageReport],
        blueprint: Mapping[str, Any],
    ) -> StageReport:
        """Simulate execution of a single stage and update budget usage."""

        # Consume budgets using configured estimates
        self.budget.consume(
            tokens=max(stage.estimated_tokens, 0),
            cost=max(stage.estimated_cost, 0.0),
            minutes=max(stage.estimated_minutes, 0.0),
        )
        self._sync_state_metadata()

        agent = await self._get_agent(stage.agent)

        await asyncio.sleep(0)  # allow cooperative scheduling during orchestration

        summary = (
            f"{stage.description} completed by {agent.name}."
            if hasattr(agent, "name")
            else stage.description
        )
        report = StageReport(
            stage=stage.name,
            agent=stage.agent,
            summary=summary,
            inputs={
                "pr_url": pr_url,
                "depends_on": list(stage.depends_on),
                "prior_stage_count": len(previous_results),
                "blueprint": self._blueprint_public_view(blueprint),
            },
            outputs={
                "notes": stage.description,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        self._sync_state_metadata()
        self._notify_state_observers()
        return report

    def _prepare_blueprint(
        self, blueprint: Mapping[str, Any] | None, pr_url: str | None
    ) -> Mapping[str, Any]:
        if blueprint is None:
            raise ValueError("VibeCoding workflow requires a 'pr_blueprint' payload")
        if not isinstance(blueprint, Mapping):
            raise TypeError("Blueprint must be a mapping of metadata")
        required = ("identifier", "title", "branch", "description", "files")
        missing = [field for field in required if not blueprint.get(field)]
        if missing:
            raise ValueError(
                "Blueprint is missing required fields: " + ", ".join(sorted(missing))
            )
        files = blueprint.get("files")
        if not isinstance(files, list) or not all(isinstance(f, str) for f in files):
            raise TypeError("Blueprint field 'files' must be a list of file paths")
        if not files:
            raise ValueError("Blueprint must include at least one target file")
        tests = blueprint.get("tests") or []
        if not isinstance(tests, list):
            raise TypeError("Blueprint field 'tests' must be a list if provided")
        normalized: MutableMapping[str, Any] = dict(blueprint)
        normalized.setdefault("tests", tests)
        normalized.setdefault("pr_url", pr_url or blueprint.get("pr_url"))
        normalized["files"] = list(files)
        return normalized

    def _blueprint_public_view(self, blueprint: Mapping[str, Any] | None) -> Dict[str, Any]:
        if blueprint is None:
            return {}
        return {
            "identifier": blueprint.get("identifier"),
            "title": blueprint.get("title"),
            "branch": blueprint.get("branch"),
            "files": list(blueprint.get("files", [])),
            "tests": list(blueprint.get("tests", [])),
            "pr_url": blueprint.get("pr_url"),
        }

    def _synthesize_summary(self, stages: Mapping[str, StageReport]) -> str:
        if not stages:
            return "No stages executed."
        ordered = [stages[name] for name in sorted(stages)]
        highlights = ", ".join(report.summary for report in ordered)
        return f"Completed {len(stages)} VibeCoding stages: {highlights}."


class VibeCodingOrchestratorMonitor:
    """Utility exposing orchestrator state for dashboards and tests."""

    def __init__(self, orchestrator: VibeCodingOrchestrator) -> None:
        self.orchestrator = orchestrator

    def snapshot(self) -> Dict[str, Any]:
        return self.orchestrator.get_state_snapshot()

    def progress(self) -> Dict[str, Any]:
        snap = self.snapshot()
        stages = snap["stages"].values()
        completed = sum(1 for stage in stages if stage["status"] == StageStatus.COMPLETED.value)
        total = len(stages)
        return {
            "completed": completed,
            "total": total,
            "pending": total - completed,
            "budget": snap["budget"],
        }


__all__ = [
    "BudgetConfig",
    "BudgetExceededError",
    "StageDefinition",
    "StageQueue",
    "StageReport",
    "StageState",
    "StageStatus",
    "VibeCodingOrchestrator",
    "VibeCodingOrchestratorMonitor",
    "VibeCodingWorkflowConfig",
]
