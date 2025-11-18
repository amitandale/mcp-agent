import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_agent.config import AppConstructionWorkflowSettings, Settings
from mcp_agent.core.context import Context
from mcp_agent.executor.workflow import WorkflowResult
from mcp_agent.workflows.app_construction_orchestrator import (
    AppConstructionOrchestrator,
    AppConstructionWorkflowConfig,
)


@pytest.fixture()
def workflow_config() -> AppConstructionWorkflowConfig:
    settings_model = AppConstructionWorkflowSettings.default()
    return AppConstructionWorkflowConfig.from_settings_model(settings_model)


@pytest.fixture()
def mock_context() -> Context:
    context = MagicMock(spec=Context)
    context.executor = MagicMock()
    context.executor.execute = AsyncMock()
    context.server_registry = MagicMock()
    context.token_counter = None
    context.logger = MagicMock()
    context.config = Settings()
    context.human_input_handler = None
    return context


class FakeVibeWorkflow:
    def __init__(self) -> None:
        self.blueprints: list[dict | None] = []
        self.pr_urls: list[str | None] = []

    async def run(
        self, pr_blueprint: dict | None = None, pr_url: str | None = None
    ) -> WorkflowResult[dict]:
        self.blueprints.append(pr_blueprint)
        self.pr_urls.append(pr_url)
        summary = pr_blueprint.get("identifier") if pr_blueprint else pr_url
        return WorkflowResult(value={"summary": f"handled {summary}"})


def test_orchestrator_executes_all_stages(workflow_config, mock_context):
    captured: list[FakeVibeWorkflow] = []

    async def fake_builder(_context, blueprint):
        workflow = FakeVibeWorkflow()
        captured.append(workflow)
        assert blueprint["files"], "blueprint should include target files"
        return workflow

    async def _execute():
        orchestrator = AppConstructionOrchestrator(
            context=mock_context,
            config=workflow_config,
            vibe_workflow_builder=fake_builder,
        )

        return await orchestrator.run()

    result = asyncio.run(_execute())

    assert result.value["stages"], "stages should be populated"
    assert result.value["summary"].startswith("Repository"), "summary should include bootstrap"
    impl = result.value["stages"]["feature_implementation"]["outputs"]
    assert impl["implementations"], "implementations should be recorded"
    assert captured, "vibe_coding builder should be invoked"
    assert captured[0].blueprints[0]["identifier"].startswith("task"), "blueprint id propagated"


def test_config_contains_pipeline(workflow_config):
    assert len(workflow_config.stages) >= 6
    assert "repo_initializer" in workflow_config.agents
    stage_names = [stage.name for stage in workflow_config.stages]
    assert stage_names[0] == "repository_bootstrap"
