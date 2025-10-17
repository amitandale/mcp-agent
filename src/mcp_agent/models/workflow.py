"""Pydantic models for workflow composition management APIs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class WorkflowStepModel(BaseModel):
    """Single step in a workflow graph."""

    id: str
    type: Literal["task", "router", "parallel", "fan_in", "fan_out", "custom"]
    config: dict[str, Any] = Field(default_factory=dict)


class WorkflowDefinitionModel(BaseModel):
    """Definition of a workflow with metadata."""

    id: str
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime
    steps: list[WorkflowStepModel] = Field(default_factory=list)

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _ensure_datetime(cls, value: datetime | str) -> datetime:
        if isinstance(value, datetime):
            return _ensure_utc(value)
        if isinstance(value, str):
            return _ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        raise TypeError("Invalid datetime payload")


class WorkflowCreateRequest(BaseModel):
    """Creation request for a workflow definition."""

    id: str | None = None
    name: str
    description: str | None = None
    steps: list[WorkflowStepModel] = Field(default_factory=list)


class WorkflowPatchRequest(BaseModel):
    """Partial update request for workflow metadata."""

    name: str | None = None
    description: str | None = None


class WorkflowStepOperation(BaseModel):
    """Operation to mutate workflow steps."""

    action: Literal["add", "remove", "replace"]
    step: WorkflowStepModel | None = None
    target_step_id: str | None = Field(
        default=None, description="Identifier of the step to mutate"
    )

    @field_validator("step")
    @classmethod
    def _validate_step(
        cls, value: WorkflowStepModel | None, info: ValidationInfo
    ) -> WorkflowStepModel | None:
        action = (info.data or {}).get("action") if isinstance(info.data, dict) else None
        if action in {"add", "replace"} and value is None:
            raise ValueError("Step payload is required for add/replace operations")
        return value

    @field_validator("target_step_id")
    @classmethod
    def _validate_target(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        action = (info.data or {}).get("action") if isinstance(info.data, dict) else None
        if action in {"remove", "replace"} and not value:
            raise ValueError("target_step_id is required for remove/replace")
        return value
