"""Typed adapter base class for MCP tool clients."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Type, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError

from ..client.http import HTTPClient
from ..errors.canonical import map_validation_error


ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)


class StrictModel(BaseModel):
    """Base class enforcing strict validation for DTOs."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=False)


class BaseAdapter:
    """Base adapter providing typed helpers for tool interactions."""

    def __init__(
        self,
        tool_id: str,
        base_url: str,
        *,
        client: Optional[HTTPClient] = None,
        default_headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        self.tool_id = tool_id
        self._client = client or HTTPClient(tool_id, base_url, default_headers=default_headers)

    @property
    def client(self) -> HTTPClient:
        return self._client

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        params: Optional[Mapping[str, Any]] = None,
        json_body: Any = None,
        data: Any = None,
        response_model: Optional[Type[ResponseModelT]] = None,
        idempotent: Optional[bool] = None,
    ) -> ResponseModelT | Any:
        raw = await self.client.request_json(
            method,
            path,
            headers=headers,
            params=params,
            json_body=json_body,
            data=data,
            idempotent=idempotent if idempotent is not None else self._idempotent(method, path),
        )
        if response_model is None:
            return raw
        return self._validate(response_model, raw)

    def _idempotent(self, method: str, path: str) -> bool:
        return method.upper() in HTTPClient.IDEMPOTENT_METHODS

    def _validate(self, model: Type[ResponseModelT], data: Any) -> ResponseModelT:
        if not issubclass(model, BaseModel):  # pragma: no cover - defensive programming
            raise TypeError("response_model must be a Pydantic model class")
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            raise map_validation_error(self.tool_id, exc, self._trace_id()) from exc

    def _trace_id(self) -> int:
        from opentelemetry import trace

        span = trace.get_current_span()
        return span.get_span_context().trace_id if span else 0

