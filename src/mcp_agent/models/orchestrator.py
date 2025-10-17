"""Pydantic models representing orchestrator runtime state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class OrchestratorBudgetModel(BaseModel):
    """Represents LLM budget or quota information."""

    spent_seconds: float = 0.0
    limit_seconds: float | None = None


class OrchestratorPolicyModel(BaseModel):
    """Policy configuration describing orchestrator behaviour."""

    allow_parallel: bool = True
    max_children: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrchestratorPlanModel(BaseModel):
    """Current plan document produced by an orchestrator."""

    steps: list[dict[str, Any]] = Field(default_factory=list)
    status: str = "pending"


class OrchestratorQueueModel(BaseModel):
    """Queue of pending tasks or steps."""

    items: list[dict[str, Any]] = Field(default_factory=list)


class OrchestratorMemoryModel(BaseModel):
    """Memory snapshot for orchestrator context."""

    documents: list[dict[str, Any]] = Field(default_factory=list)
    annotations: list[dict[str, Any]] = Field(default_factory=list)


class OrchestratorEvent(BaseModel):
    """Single event delivered over SSE."""

    id: int
    timestamp: datetime
    type: str
    payload: dict[str, Any]

    @field_validator("timestamp", mode="before")
    @classmethod
    def _ensure_datetime(cls, value: datetime | str) -> datetime:
        if isinstance(value, datetime):
            return _ensure_utc(value)
        if isinstance(value, str):
            return _ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        raise TypeError("Invalid datetime payload")


class OrchestratorStateModel(BaseModel):
    """Full orchestrator state representation."""

    id: str
    updated_at: datetime
    plan: OrchestratorPlanModel
    queue: OrchestratorQueueModel
    budget: OrchestratorBudgetModel
    memory: OrchestratorMemoryModel
    policy: OrchestratorPolicyModel

    @field_validator("updated_at", mode="before")
    @classmethod
    def _ensure_datetime(cls, value: datetime | str) -> datetime:
        if isinstance(value, datetime):
            return _ensure_utc(value)
        if isinstance(value, str):
            return _ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        raise TypeError("Invalid datetime payload")
