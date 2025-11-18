import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

try:
    from mcp_agent.core.context import Context
    from mcp_agent.workflows.vibe_coding.vibe_coding_orchestrator import (
        StageQueue,
        StageStatus,
        VibeCodingOrchestrator,
        VibeCodingWorkflowConfig,
    )
except ModuleNotFoundError:  # pragma: no cover - fallback for direct test execution
    SRC_ROOT = Path(__file__).resolve().parents[3] / "src"
    if str(SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(SRC_ROOT))
    from mcp_agent.core.context import Context
    from mcp_agent.workflows.vibe_coding.vibe_coding_orchestrator import (
        StageQueue,
        StageStatus,
        VibeCodingOrchestrator,
        VibeCodingWorkflowConfig,
    )


class FakeAgent:
    """Lightweight stand-in for real agents during tests."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.shutdown_calls = 0

    async def shutdown(self) -> None:
        self.shutdown_calls += 1


@pytest.fixture()
def mock_context() -> Context:
    context = MagicMock(spec=Context)
    context.executor = MagicMock()
    context.executor.execute = AsyncMock()
    context.server_registry = MagicMock()
    context.server_registry.registry = {}
    context.token_counter = None
    context.logger = MagicMock()
    return context


@pytest.fixture()
def agent_factory():
    def factory(spec, _context):
        return FakeAgent(spec.name)

    return factory


@pytest.fixture()
def sample_blueprint() -> dict:
    return {
        "identifier": "task-01-api",
        "title": "Backend: Invoice",
        "branch": "feature/task-01-api",
        "description": "Implements backend endpoints for invoices",
        "files": ["backend/api/invoice.py", "backend/models/invoice.py"],
        "tests": ["tests/api/test_invoice.py"],
        "pr_url": "https://example.com/pr/99",
    }


def test_default_config_contains_fifteen_stages():
    config = VibeCodingWorkflowConfig.default()
    assert len(config.stages) == 15
    expected_names = {
        "pr_metadata_extraction",
        "diff_analysis",
        "syntax_tree_analysis",
        "ast_pattern_matching",
        "dependency_graph_analysis",
        "code_smell_detection",
        "type_checking",
        "security_scan",
        "performance_assessment",
        "code_style_normalization",
        "documentation_check",
        "test_coverage_analysis",
        "patch_generation",
        "patch_validation",
        "report_generation",
    }
    assert {stage.name for stage in config.stages} == expected_names


def test_stage_queue_respects_dependencies():
    config = VibeCodingWorkflowConfig.default()
    queue = StageQueue(config.stages)
    ready = queue.get_ready(completed=[])
    assert [stage.name for stage in ready] == ["pr_metadata_extraction"]
    queue.mark_completed("pr_metadata_extraction")
    ready = queue.get_ready(completed=queue.completed)
    assert ready and ready[0].name == "diff_analysis"


def test_run_executes_all_stages(mock_context, agent_factory, sample_blueprint):
    async def _execute():
        config = VibeCodingWorkflowConfig.default()
        config.monitor_refresh_interval = 0
        orchestrator = VibeCodingOrchestrator(
            context=mock_context,
            config=config,
            agent_factory=agent_factory,
        )

        result = await orchestrator.run(pr_blueprint=sample_blueprint)
        assert len(result.value["stages"]) == 15
        snapshot = orchestrator.get_state_snapshot()
        assert all(
            state["status"] == StageStatus.COMPLETED.value
            for state in snapshot["stages"].values()
        )
        assert "summary" in result.value
        assert result.value["blueprint"]["identifier"] == sample_blueprint["identifier"]

    asyncio.run(_execute())


def test_run_requires_blueprint(mock_context, agent_factory):
    async def _execute():
        config = VibeCodingWorkflowConfig.default()
        orchestrator = VibeCodingOrchestrator(
            context=mock_context,
            config=config,
            agent_factory=agent_factory,
        )

        await orchestrator.run()

    with pytest.raises(ValueError):
        asyncio.run(_execute())
