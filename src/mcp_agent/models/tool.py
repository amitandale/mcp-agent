"""Pydantic models for tool runtime management endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from pydantic import BaseModel, Field, field_validator

from mcp_agent.registry.models import ToolItem


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class ToolRuntimeItem(BaseModel):
    """Snapshot of a tool along with runtime enablement metadata."""

    id: str
    name: str
    version: str
    base_url: str
    alive: bool
    latency_ms: float
    capabilities: list[str]
    tags: list[str]
    last_checked_ts: datetime
    enabled: bool = Field(default=True)

    @field_validator("last_checked_ts", mode="before")
    @classmethod
    def _ensure_datetime(cls, value: datetime | str) -> datetime:
        if isinstance(value, datetime):
            return _ensure_utc(value)
        if isinstance(value, str):
            return _ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        raise TypeError("Invalid datetime payload")

    @classmethod
    def from_tool_item(cls, item: ToolItem, *, enabled: bool) -> "ToolRuntimeItem":
        payload = item.model_dump(mode="python")
        payload["enabled"] = enabled
        return cls.model_validate(payload)


class ToolRuntimeResponse(BaseModel):
    """Response envelope for runtime tool registry queries."""

    registry_hash: str
    generated_at: datetime
    items: list[ToolRuntimeItem]

    @field_validator("generated_at", mode="before")
    @classmethod
    def _ensure_datetime(cls, value: datetime | str) -> datetime:
        if isinstance(value, datetime):
            return _ensure_utc(value)
        if isinstance(value, str):
            return _ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        raise TypeError("Invalid datetime payload")

    @classmethod
    def from_snapshot(
        cls,
        *,
        registry_hash: str,
        generated_at: datetime,
        items: Iterable[ToolRuntimeItem],
    ) -> "ToolRuntimeResponse":
        return cls(
            registry_hash=registry_hash,
            generated_at=_ensure_utc(generated_at),
            items=list(items),
        )


class ToolPatchRequest(BaseModel):
    """Patch payload for toggling tool availability."""

    updates: list[tuple[str, bool]] | list[dict[str, object]]

    @field_validator("updates")
    @classmethod
    def _normalise_updates(
        cls, value: list[tuple[str, bool]] | list[dict[str, object]]
    ) -> list[tuple[str, bool]]:
        normalised: list[tuple[str, bool]] = []
        for entry in value:
            if isinstance(entry, tuple) and len(entry) == 2:
                tool_id, enabled = entry
            elif isinstance(entry, dict):
                tool_id = entry.get("id")
                enabled = entry.get("enabled")
            else:
                raise ValueError("Invalid tool patch entry")
            if not isinstance(tool_id, str) or not tool_id.strip():
                raise ValueError("Tool id must be a non-empty string")
            if not isinstance(enabled, bool):
                raise ValueError("Enabled flag must be boolean")
            normalised.append((tool_id.strip(), enabled))
        if not normalised:
            raise ValueError("At least one update must be provided")
        return normalised


class ToolAssignmentRequest(BaseModel):
    """Request payload for assigning tools to an agent."""

    tools: list[str] = Field(default_factory=list)

    @field_validator("tools")
    @classmethod
    def _validate_tools(cls, value: list[str]) -> list[str]:
        normalised = [tool.strip() for tool in value if tool and tool.strip()]
        if not normalised:
            raise ValueError("At least one tool id must be provided")
        return sorted(set(normalised))
