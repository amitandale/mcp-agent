"""Config-driven workflow that orchestrates application construction."""

from __future__ import annotations

import importlib
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Mapping, MutableMapping

from pydantic import BaseModel, Field, PrivateAttr

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.config import AppConstructionWorkflowSettings, Settings
from mcp_agent.core.context import Context
from mcp_agent.executor.workflow import Workflow, WorkflowResult
from mcp_agent.workflows.vibe_coding.vibe_coding_orchestrator import (
    VibeCodingOrchestrator,
    VibeCodingWorkflowConfig,
    VibeCodingOrchestratorMonitor,
)


class StageStatus(str, Enum):
    """Enum describing stage execution state."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StageState(BaseModel):
    """Holds runtime state for an individual stage."""

    name: str
    status: StageStatus = StageStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: Dict[str, Any] | None = None
    error: str | None = None


class AppConstructionAgentConfig(BaseModel):
    """Runtime-ready agent definition with a resolvable builder."""

    name: str
    builder_path: str
    server_names: List[str] = Field(default_factory=list)
    description: str | None = None

    _builder: Callable[..., Agent] | None = PrivateAttr(default=None)

    def build(self, context: Context | None) -> Agent:
        builder = self._get_builder()
        try:
            agent = builder(context=context)
        except TypeError:
            agent = builder()
        self._validate_servers(agent)
        return agent

    def _get_builder(self) -> Callable[..., Agent]:
        if self._builder is None:
            module_path, attr = self.builder_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            builder = getattr(module, attr)
            if not callable(builder):  # pragma: no cover - defensive
                raise TypeError(f"Builder at {self.builder_path} is not callable")
            self._builder = builder
        return self._builder

    def _validate_servers(self, agent: Agent) -> None:
        expected = set(self.server_names)
        actual = set(agent.server_names or [])
        if expected and actual and expected != actual:
            missing = expected - actual
            extras = actual - expected
            details = []
            if missing:
                details.append(f"missing {sorted(missing)}")
            if extras:
                details.append(f"unexpected {sorted(extras)}")
            raise ValueError(
                f"Agent '{self.name}' server mismatch: {'; '.join(details)}"
            )


class AppConstructionStageDefinition(BaseModel):
    """Resolved stage configuration."""

    name: str
    description: str
    agent: str
    kind: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class AppConstructionWorkflowConfig(BaseModel):
    """Concrete configuration used by the orchestrator."""

    repo_template: str | None = None
    system_spec_path: str
    target_branch: str
    stages: List[AppConstructionStageDefinition]
    agents: Dict[str, AppConstructionAgentConfig]
    vibe_coding_workflow: str
    vibe_coding_monitor: str

    _vibe_workflow_class: type[VibeCodingOrchestrator] | None = PrivateAttr(default=None)
    _vibe_monitor_class: type[VibeCodingOrchestratorMonitor] | None = PrivateAttr(
        default=None
    )

    @classmethod
    def from_settings(cls, settings: Settings | None) -> "AppConstructionWorkflowConfig":
        source = (
            settings.app_construction
            if settings and settings.app_construction
            else AppConstructionWorkflowSettings.default()
        )
        return cls.from_settings_model(source)

    @classmethod
    def from_settings_model(
        cls, settings: AppConstructionWorkflowSettings
    ) -> "AppConstructionWorkflowConfig":
        stages = [
            AppConstructionStageDefinition(
                name=stage.name,
                description=stage.description,
                agent=stage.agent,
                kind=stage.kind,
                parameters=stage.parameters or {},
            )
            for stage in settings.stages
        ]
        agents_source = settings.agents or {}
        agents = {
            name: AppConstructionAgentConfig(
                name=name,
                builder_path=agent.builder,
                server_names=list(agent.server_names or []),
                description=agent.description,
            )
            for name, agent in agents_source.items()
        }
        return cls(
            repo_template=settings.repo_template,
            system_spec_path=settings.system_spec_path,
            target_branch=settings.target_branch,
            stages=stages,
            agents=agents,
            vibe_coding_workflow=settings.vibe_coding_workflow,
            vibe_coding_monitor=settings.vibe_coding_monitor,
        )

    def get_agent(self, name: str) -> AppConstructionAgentConfig:
        try:
            return self.agents[name]
        except KeyError as exc:  # pragma: no cover - validated via config
            raise KeyError(f"Unknown agent '{name}'") from exc

    @property
    def vibe_workflow_class(self) -> type[VibeCodingOrchestrator]:
        if self._vibe_workflow_class is None:
            module_path, attr = self.vibe_coding_workflow.rsplit(".", 1)
            module = importlib.import_module(module_path)
            workflow_cls = getattr(module, attr)
            self._vibe_workflow_class = workflow_cls
        return self._vibe_workflow_class

    @property
    def vibe_monitor_class(self) -> type[VibeCodingOrchestratorMonitor]:
        if self._vibe_monitor_class is None:
            module_path, attr = self.vibe_coding_monitor.rsplit(".", 1)
            module = importlib.import_module(module_path)
            monitor_cls = getattr(module, attr)
            self._vibe_monitor_class = monitor_cls
        return self._vibe_monitor_class


class StageResult(BaseModel):
    """Serializable stage result payload."""

    stage: str
    agent: str
    summary: str
    outputs: Dict[str, Any] = Field(default_factory=dict)


class AppConstructionOrchestrator(Workflow[Dict[str, Any]]):
    """Multi-agent workflow that builds a repo from a canonical spec."""

    def __init__(
        self,
        *,
        config: AppConstructionWorkflowConfig | None = None,
        agent_overrides: Dict[str, AppConstructionAgentConfig] | None = None,
        vibe_workflow_builder: Callable[
            [Context | None, Mapping[str, Any]], Awaitable[Any]
        ]
        | None = None,
        context: Context | None = None,
        **kwargs: Any,
    ) -> None:
        resolved_config = config or AppConstructionWorkflowConfig.from_settings(
            context.config if context else None
        )
        if agent_overrides:
            resolved_config.agents.update(agent_overrides)

        super().__init__(name="app_construction_orchestrator", context=context, **kwargs)
        self.config = resolved_config
        self._agent_cache: Dict[str, Agent] = {}
        self._stage_states: Dict[str, StageState] = {
            stage.name: StageState(name=stage.name)
            for stage in self.config.stages
        }
        self._handlers: Dict[
            str,
            Callable[
                [AppConstructionStageDefinition, MutableMapping[str, Any]],
                Awaitable[StageResult],
            ],
        ] = {
            "bootstrap": self._handle_bootstrap,
            "spec_analysis": self._handle_spec_analysis,
            "planning": self._handle_planning,
            "pr_blueprinting": self._handle_pr_blueprinting,
            "implementation": self._handle_implementation,
            "validation": self._handle_validation,
            "commit": self._handle_commit,
        }
        self._vibe_workflow_builder = (
            vibe_workflow_builder or self._default_vibe_workflow_builder
        )
        self.state.metadata.setdefault(
            "stages", {name: state.model_dump() for name, state in self._stage_states.items()}
        )

    async def _get_agent(self, name: str) -> Agent:
        if name in self._agent_cache:
            return self._agent_cache[name]
        agent_cfg = self.config.get_agent(name)
        agent = agent_cfg.build(self.context)
        self._agent_cache[name] = agent
        return agent

    def _record_state(self, stage_name: str, update: StageState) -> None:
        self._stage_states[stage_name] = update
        self.state.metadata["stages"][stage_name] = update.model_dump()

    async def run(
        self,
        *,
        system_description_path: str | None = None,
        repo_template: str | None = None,
    ) -> WorkflowResult[Dict[str, Any]]:
        """Execute the config-defined pipeline."""

        self.update_status("running")
        shared_state: MutableMapping[str, Any] = {
            "system_spec_path": system_description_path or self.config.system_spec_path,
            "repo_template": repo_template or self.config.repo_template,
            "target_branch": self.config.target_branch,
        }
        stage_payloads: Dict[str, StageResult] = {}
        start = datetime.now(timezone.utc).timestamp()

        for stage in self.config.stages:
            state = self._stage_states[stage.name]
            state.status = StageStatus.RUNNING
            state.started_at = datetime.now(timezone.utc)
            self._record_state(stage.name, state)

            try:
                result = await self._execute_stage(stage, shared_state)
            except Exception as exc:  # pragma: no cover - propagation path
                state.status = StageStatus.FAILED
                state.error = str(exc)
                state.completed_at = datetime.now(timezone.utc)
                self._record_state(stage.name, state)
                self.update_status("failed")
                raise

            state.status = StageStatus.COMPLETED
            state.completed_at = datetime.now(timezone.utc)
            state.result = result.model_dump()
            self._record_state(stage.name, state)
            stage_payloads[stage.name] = result

        result = WorkflowResult[Dict[str, Any]](
            value={
                "stages": {name: payload.model_dump() for name, payload in stage_payloads.items()},
                "summary": self._summarize(stage_payloads),
                "shared_state": dict(shared_state),
            },
            metadata={"stages": self.state.metadata["stages"]},
            start_time=start,
            end_time=datetime.now(timezone.utc).timestamp(),
        )
        self.update_status("completed")
        return result

    async def _execute_stage(
        self,
        stage: AppConstructionStageDefinition,
        shared_state: MutableMapping[str, Any],
    ) -> StageResult:
        handler = self._handlers.get(stage.kind)
        if handler is None:
            raise KeyError(f"No handler registered for stage kind '{stage.kind}'")
        await self._get_agent(stage.agent)  # ensures validation/initialization
        return await handler(stage, shared_state)

    async def _handle_bootstrap(
        self,
        stage: AppConstructionStageDefinition,
        shared_state: MutableMapping[str, Any],
    ) -> StageResult:
        repo_name = stage.parameters.get("repo_name", "app-construction")
        repo_template = stage.parameters.get("repo_template") or shared_state.get(
            "repo_template"
        )
        target_branch = stage.parameters.get("target_branch", self.config.target_branch)
        workspace = {
            "repo_name": repo_name,
            "template": repo_template,
            "branch": target_branch,
            "status": "initialized",
        }
        shared_state["workspace"] = workspace
        return StageResult(
            stage=stage.name,
            agent=stage.agent,
            summary=f"Repository {repo_name} prepared on branch {target_branch}.",
            outputs={"workspace": workspace},
        )

    async def _handle_spec_analysis(
        self,
        stage: AppConstructionStageDefinition,
        shared_state: MutableMapping[str, Any],
    ) -> StageResult:
        path = Path(
            stage.parameters.get("system_spec_path")
            or shared_state.get("system_spec_path")
            or self.config.system_spec_path
        )
        if not path.is_absolute():
            path = Path.cwd() / path
        text = path.read_text(encoding="utf-8")
        sections = self._parse_sections(text)
        payload = {"path": str(path), "sections": sections, "raw": text}
        shared_state["spec_analysis"] = payload
        return StageResult(
            stage=stage.name,
            agent=stage.agent,
            summary=f"Parsed {len(sections)} sections from system description.",
            outputs=payload,
        )

    async def _handle_planning(
        self,
        stage: AppConstructionStageDefinition,
        shared_state: MutableMapping[str, Any],
    ) -> StageResult:
        analysis = shared_state.get("spec_analysis", {})
        sections = analysis.get("sections", [])
        plan: List[Dict[str, Any]] = []
        for section in sections:
            for item in section.get("items", []):
                artifacts = ["api"]
                if "UI" in section["title"].upper() or "DASHBOARD" in section["title"].upper():
                    artifacts.append("ui")
                plan.append(
                    {
                        "section": section["title"],
                        "task": item,
                        "artifacts": artifacts,
                    }
                )
        shared_state["plan"] = plan
        return StageResult(
            stage=stage.name,
            agent=stage.agent,
            summary=f"Created {len(plan)} execution tasks.",
            outputs={"plan": plan},
        )

    async def _handle_pr_blueprinting(
        self,
        stage: AppConstructionStageDefinition,
        shared_state: MutableMapping[str, Any],
    ) -> StageResult:
        plan: List[Dict[str, Any]] = shared_state.get("plan", [])
        limit = stage.parameters.get("max_pull_requests")
        slice_plan = plan[:limit] if limit else plan
        blueprints: List[Dict[str, Any]] = []
        for idx, task in enumerate(slice_plan, start=1):
            branch = f"{self.config.target_branch}-{idx:02d}"
            pr_url = f"https://example.com/{branch}"
            blueprint = {
                "id": idx,
                "title": f"Implement {task['task']}",
                "branch": branch,
                "files": task.get("artifacts", []),
                "plan_reference": task,
                "pr_url": pr_url,
            }
            blueprints.append(blueprint)
        shared_state["pull_requests"] = blueprints
        return StageResult(
            stage=stage.name,
            agent=stage.agent,
            summary=f"Prepared {len(blueprints)} PR blueprints.",
            outputs={"pull_requests": blueprints},
        )

    async def _handle_implementation(
        self,
        stage: AppConstructionStageDefinition,
        shared_state: MutableMapping[str, Any],
    ) -> StageResult:
        blueprints = shared_state.get("pull_requests", [])
        implementations: List[Dict[str, Any]] = []
        for blueprint in blueprints:
            vibe_result = await self._invoke_vibe_coding(blueprint)
            implementations.append(vibe_result)
        shared_state["implementations"] = implementations
        return StageResult(
            stage=stage.name,
            agent=stage.agent,
            summary=f"Executed VibeCoding for {len(implementations)} blueprints.",
            outputs={"implementations": implementations},
        )

    async def _handle_validation(
        self,
        stage: AppConstructionStageDefinition,
        shared_state: MutableMapping[str, Any],
    ) -> StageResult:
        implementations: List[Dict[str, Any]] = shared_state.get("implementations", [])
        failures = [
            impl
            for impl in implementations
            if not impl.get("result", {}).get("summary")
        ]
        status = "passed" if not failures else "needs_revision"
        validation = {
            "status": status,
            "checked": len(implementations),
            "failures": failures,
        }
        shared_state["validation"] = validation
        return StageResult(
            stage=stage.name,
            agent=stage.agent,
            summary=f"Validation {status} with {len(failures)} failures.",
            outputs=validation,
        )

    async def _handle_commit(
        self,
        stage: AppConstructionStageDefinition,
        shared_state: MutableMapping[str, Any],
    ) -> StageResult:
        workspace = shared_state.get("workspace", {})
        validation = shared_state.get("validation", {})
        commit = {
            "branch": workspace.get("branch", self.config.target_branch),
            "ready_for_ci": validation.get("status") == "passed",
            "pr_count": len(shared_state.get("pull_requests", [])),
        }
        shared_state["commit"] = commit
        return StageResult(
            stage=stage.name,
            agent=stage.agent,
            summary=(
                "Staged commits for branch "
                f"{commit['branch']} (ready_for_ci={commit['ready_for_ci']})."
            ),
            outputs=commit,
        )

    def _parse_sections(self, text: str) -> List[Dict[str, Any]]:
        sections: List[Dict[str, Any]] = []
        current: Dict[str, Any] | None = None
        for line in text.splitlines():
            if line.startswith("## "):
                if current:
                    sections.append(current)
                current = {"title": line[3:].strip(), "items": []}
            elif line.startswith("- ") and current is not None:
                current["items"].append(line[2:].strip())
        if current:
            sections.append(current)
        return sections

    async def _invoke_vibe_coding(
        self, blueprint: Mapping[str, Any]
    ) -> Dict[str, Any]:
        workflow_obj = await self._vibe_workflow_builder(self.context, blueprint)
        monitor = None
        if isinstance(workflow_obj, Workflow):
            await workflow_obj.initialize()
            workflow_result = await workflow_obj.run(pr_url=blueprint.get("pr_url"))
            monitor = self.config.vibe_monitor_class(workflow_obj)
        elif hasattr(workflow_obj, "run"):
            workflow_result = await workflow_obj.run(pr_url=blueprint.get("pr_url"))
        else:
            workflow_result = workflow_obj

        if isinstance(workflow_result, WorkflowResult):
            summary = workflow_result.value or {}
        elif isinstance(workflow_result, dict):
            summary = workflow_result
        else:
            summary = {"result": str(workflow_result)}

        progress = monitor.progress() if monitor else {}
        return {
            "blueprint": blueprint,
            "result": summary,
            "monitor": progress,
        }

    async def _default_vibe_workflow_builder(
        self, context: Context | None, blueprint: Mapping[str, Any]
    ) -> VibeCodingOrchestrator:
        del blueprint  # currently unused but kept for future filtering
        vibe_config = VibeCodingWorkflowConfig.default()
        vibe_config.monitor_refresh_interval = 0
        return await self.config.vibe_workflow_class.create(
            context=context, config=vibe_config
        )

    def _summarize(self, stages: Mapping[str, StageResult]) -> str:
        summaries = [result.summary for result in stages.values()]
        return ", ".join(summaries)


app = MCPApp(name="app_construction_orchestrator")


@app.workflow
class Workflow(AppConstructionOrchestrator):
    """Expose the orchestrator through the MCP app."""

    pass
