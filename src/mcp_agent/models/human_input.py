"""Pydantic schemas for human input management APIs."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class HumanInputRequestModel(BaseModel):
    """Represents a pending human input request."""

    id: str
    created_at: datetime
    prompt: str
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("created_at", mode="before")
    @classmethod
    def _ensure_datetime(cls, value: datetime | str) -> datetime:
        if isinstance(value, datetime):
            return _ensure_utc(value)
        if isinstance(value, str):
            return _ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        raise TypeError("Invalid datetime payload")


class HumanInputResponseModel(BaseModel):
    """Response payload for fulfilling a request."""

    id: str
    response: str


class HumanInputRequestCreate(BaseModel):
    """Request payload for creating a human input request."""

    id: str
    prompt: str
    metadata: dict[str, str] = Field(default_factory=dict)
