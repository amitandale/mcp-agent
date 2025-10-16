"""Facade re-exporting administrative models without eager imports."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import TYPE_CHECKING

__all__ = [
    "AgentSpecEnvelope",
    "AgentSpecListResponse",
    "AgentSpecPatch",
    "AgentSpecPayload",
    "OrchestratorEvent",
    "OrchestratorPlan",
    "OrchestratorPlanNode",
    "OrchestratorQueueItem",
    "OrchestratorSnapshot",
    "OrchestratorState",
    "OrchestratorStatePatch",
    "WorkflowDefinition",
    "WorkflowPatch",
    "WorkflowStep",
    "WorkflowStepPatch",
    "WorkflowSummary",
]

if TYPE_CHECKING:  # pragma: no cover - only for static analysis
    from mcp.types import (  # noqa: F401 - provided lazily via __getattr__
        AgentSpecEnvelope as AgentSpecEnvelope,
        AgentSpecListResponse as AgentSpecListResponse,
        AgentSpecPatch as AgentSpecPatch,
        AgentSpecPayload as AgentSpecPayload,
        OrchestratorEvent as OrchestratorEvent,
        OrchestratorPlan as OrchestratorPlan,
        OrchestratorPlanNode as OrchestratorPlanNode,
        OrchestratorQueueItem as OrchestratorQueueItem,
        OrchestratorSnapshot as OrchestratorSnapshot,
        OrchestratorState as OrchestratorState,
        OrchestratorStatePatch as OrchestratorStatePatch,
        WorkflowDefinition as WorkflowDefinition,
        WorkflowPatch as WorkflowPatch,
        WorkflowStep as WorkflowStep,
        WorkflowStepPatch as WorkflowStepPatch,
        WorkflowSummary as WorkflowSummary,
    )


_types_module: ModuleType | None = None


def _load_types() -> ModuleType:
    global _types_module
    if _types_module is None:
        _types_module = import_module("mcp.types")
    return _types_module


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(name)
    return getattr(_load_types(), name)


def __dir__() -> list[str]:
    return sorted(__all__)
