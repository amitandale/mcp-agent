"""Compatibility re-export of workflow models."""

from mcp import types as _types

WorkflowDefinition = _types.WorkflowDefinition
WorkflowPatch = _types.WorkflowPatch
WorkflowStep = _types.WorkflowStep
WorkflowStepPatch = _types.WorkflowStepPatch
WorkflowSummary = _types.WorkflowSummary

__all__ = [
    "WorkflowDefinition",
    "WorkflowPatch",
    "WorkflowStep",
    "WorkflowStepPatch",
    "WorkflowSummary",
]
