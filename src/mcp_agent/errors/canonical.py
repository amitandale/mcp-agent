"""Canonical error model and mapping utilities for MCP tool clients."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError


CANONICAL_HINTS: Dict[str, str] = {
    "network_timeout": "increase HTTP_TIMEOUT_MS or fix server",
    "rate_limited": "honor Retry-After header",
    "unauthorized": "provide valid credentials",
    "forbidden": "check tool permissions",
    "not_found": "verify resource exists",
    "upstream_error": "retry later or contact tool owner",
    "circuit_open": "breaker cooling down",
    "schema_validation_error": "tool payload failed validation",
}


def _format_trace_id(trace_id: int) -> str:
    """Return a 32-character hex trace identifier."""

    if trace_id == 0:
        return "0" * 32
    return f"{trace_id:032x}"


class CanonicalErrorPayload(BaseModel):
    """Structured payload for canonical tool errors."""

    tool: str
    code: str
    http: Optional[int] = None
    detail: Optional[str] = None
    hint: Optional[str] = None
    trace_id: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class CanonicalError(Exception):
    """Exception raised for canonical tool errors."""

    def __init__(self, **fields: Any) -> None:
        payload = CanonicalErrorPayload(**fields)
        super().__init__(payload.detail or payload.code)
        self.payload = payload

    def __repr__(self) -> str:  # pragma: no cover - repr is straightforward
        return f"CanonicalError({self.payload.model_dump()!r})"

    # Convenience accessors -------------------------------------------------
    @property
    def tool(self) -> str:
        return self.payload.tool

    @property
    def code(self) -> str:
        return self.payload.code

    @property
    def http(self) -> Optional[int]:
        return self.payload.http

    @property
    def detail(self) -> Optional[str]:
        return self.payload.detail

    @property
    def hint(self) -> Optional[str]:
        return self.payload.hint

    @property
    def trace_id(self) -> str:
        return self.payload.trace_id

    def to_dict(self) -> Dict[str, Any]:
        return self.payload.model_dump()


def _clean_detail(detail: Optional[str]) -> Optional[str]:
    if detail is None:
        return None
    # Conservatively trim very long messages and scrub newline noise.
    detail = detail.replace("\n", " ").strip()
    if len(detail) > 512:
        return f"{detail[:509]}…"
    return detail


def _default_hint(code: str) -> Optional[str]:
    return CANONICAL_HINTS.get(code)


def _build_error(
    tool: str,
    code: str,
    *,
    http_status: Optional[int],
    detail: Optional[str],
    trace_id: int,
    hint: Optional[str] = None,
) -> CanonicalError:
    return CanonicalError(
        tool=tool,
        code=code,
        http=http_status,
        detail=_clean_detail(detail),
        hint=hint or _default_hint(code),
        trace_id=_format_trace_id(trace_id),
    )


def map_http_exception(tool: str, exc: Exception, trace_id: int) -> CanonicalError:
    """Map network/transport errors to canonical codes."""

    if isinstance(exc, httpx.TimeoutException):
        return _build_error(tool, "network_timeout", http_status=None, detail=str(exc), trace_id=trace_id)

    if isinstance(exc, httpx.ConnectError):
        return _build_error(tool, "network_timeout", http_status=None, detail=str(exc), trace_id=trace_id)

    if isinstance(exc, httpx.TransportError):
        return _build_error(tool, "network_timeout", http_status=None, detail=str(exc), trace_id=trace_id)

    return _build_error(tool, "unknown_error", http_status=None, detail=str(exc), trace_id=trace_id)


def map_http_response(tool: str, response: httpx.Response, trace_id: int) -> CanonicalError:
    """Map HTTP responses to canonical errors."""

    status = response.status_code
    if status == 401:
        code = "unauthorized"
    elif status == 403:
        code = "forbidden"
    elif status == 404:
        code = "not_found"
    elif status == 429:
        code = "rate_limited"
    elif 500 <= status < 600:
        code = "upstream_error"
    else:
        code = "unexpected_status"

    detail: Optional[str] = None
    try:
        if response.content:
            parsed = response.json()
            if isinstance(parsed, dict):
                detail = str(parsed.get("detail") or parsed.get("message") or response.text)
            else:
                detail = response.text
        else:
            detail = response.reason_phrase
    except Exception:  # pragma: no cover - JSON parse failure fallback
        detail = response.text or response.reason_phrase

    return _build_error(tool, code, http_status=status, detail=detail, trace_id=trace_id)


def map_breaker_open(tool: str, trace_id: int) -> CanonicalError:
    return _build_error(
        tool,
        "circuit_open",
        http_status=None,
        detail="circuit breaker open",
        trace_id=trace_id,
    )


def map_validation_error(tool: str, exc: ValidationError, trace_id: int) -> CanonicalError:
    first_error = exc.errors()[0] if exc.errors() else None
    loc = "".join([str(part) + "." for part in first_error.get("loc", [])]) if first_error else ""
    loc = loc.rstrip(".")
    msg = first_error.get("msg") if first_error else str(exc)
    detail = f"{loc}: {msg}" if loc else msg
    return _build_error(tool, "schema_validation_error", http_status=None, detail=detail, trace_id=trace_id)


def map_payload_too_large(tool: str, trace_id: int) -> CanonicalError:
    return _build_error(
        tool,
        "schema_validation_error",
        http_status=None,
        detail="response body exceeds validation limit",
        trace_id=trace_id,
    )


def map_json_decode_error(tool: str, trace_id: int) -> CanonicalError:
    return _build_error(
        tool,
        "schema_validation_error",
        http_status=None,
        detail="response payload was not valid JSON",
        trace_id=trace_id,
    )


def enrich_with_hint(error: CanonicalError, hint: Optional[str]) -> CanonicalError:
    if not hint:
        return error
    return CanonicalError(**{**error.payload.model_dump(), "hint": hint})

