"""Pydantic models for agent specification management APIs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mcp_agent.agents.agent_spec import AgentSpec


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class AgentSpecEnvelope(BaseModel):
    """Wrapper that ensures payloads can be converted into :class:`AgentSpec`."""

    model_config = ConfigDict(extra="allow")

    name: str
    instruction: str | None = None
    server_names: list[str] = Field(default_factory=list)
    connection_persistence: bool = True

    @classmethod
    def from_spec(cls, spec: AgentSpec) -> "AgentSpecEnvelope":
        return cls(**spec.model_dump(mode="json"))

    def to_spec(self) -> AgentSpec:
        payload = self.model_dump(mode="python")
        return AgentSpec.model_validate(payload)


class AgentSpecCreate(BaseModel):
    """Creation payload for a new agent specification."""

    id: str | None = Field(default=None, description="Optional identifier override")
    spec: AgentSpecEnvelope


class AgentSpecPatch(BaseModel):
    """Partial update payload for an agent specification."""

    name: str | None = Field(default=None)
    instruction: str | None = Field(default=None)
    server_names: list[str] | None = Field(default=None)
    connection_persistence: bool | None = Field(default=None)
    extra: Mapping[str, Any] | None = Field(
        default=None,
        description="Optional arbitrary fields to merge into the AgentSpec",
    )


class AgentRecordModel(BaseModel):
    """Serialised representation of a stored agent specification."""

    id: str
    created_at: datetime
    updated_at: datetime
    spec: AgentSpecEnvelope

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _ensure_datetime(cls, value: datetime | str) -> datetime:
        if isinstance(value, str):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        elif isinstance(value, datetime):
            dt = value
        else:
            raise TypeError("Expected datetime or ISO formatted string")
        return _ensure_utc(dt)

    @classmethod
    def from_runtime(
        cls,
        *,
        agent_id: str,
        spec: AgentSpec,
        created_at: datetime,
        updated_at: datetime,
    ) -> "AgentRecordModel":
        return cls(
            id=agent_id,
            spec=AgentSpecEnvelope.from_spec(spec),
            created_at=_ensure_utc(created_at),
            updated_at=_ensure_utc(updated_at),
        )
