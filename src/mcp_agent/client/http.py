"""Shared async HTTP client with retries, circuit breaker, and telemetry."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Mapping, Optional

import httpx
from opentelemetry import metrics, trace
from opentelemetry.metrics import CallbackOptions, Observation
from opentelemetry.trace import SpanKind, Status, StatusCode

from ..errors.canonical import (
    CanonicalError,
    map_breaker_open,
    map_http_exception,
    map_http_response,
    map_json_decode_error,
    map_payload_too_large,
)


LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Environment configuration


def _env_ms(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:  # pragma: no cover - defensive against invalid env
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:  # pragma: no cover
        return default


HTTP_TIMEOUT_MS = _env_ms("HTTP_TIMEOUT_MS", 1500)
HTTP_CONNECT_TIMEOUT_MS = _env_ms("HTTP_CONNECT_TIMEOUT_MS", 500)
HTTP_WRITE_TIMEOUT_MS = _env_ms("HTTP_WRITE_TIMEOUT_MS", 1500)
HTTP_POOL_TIMEOUT_MS = _env_ms("HTTP_POOL_TIMEOUT_MS", 500)
RETRY_MAX = max(0, _env_ms("RETRY_MAX", 3))
RETRY_BASE_MS = max(1, _env_ms("RETRY_BASE_MS", 100))
RETRY_JITTER = max(0.0, _env_float("RETRY_JITTER", 0.2))
BREAKER_ENABLED = os.getenv("BREAKER_ENABLED", "false").lower() in {"1", "true", "yes"}
BREAKER_THRESH = float(os.getenv("BREAKER_THRESH", "0.5"))
BREAKER_WINDOW = max(1, _env_ms("BREAKER_WINDOW", 20))
BREAKER_COOLDOWN_MS = max(0, _env_ms("BREAKER_COOLDOWN_MS", 5000))
HALF_OPEN_MAX = max(1, _env_ms("HALF_OPEN_MAX", 3))
MAX_REDIRECTS = 3
ALLOWED_HOSTS = {host.strip() for host in os.getenv("ALLOWED_HOSTS", "").split(",") if host.strip()}
VALIDATION_LIMIT_BYTES = max(1, _env_ms("HTTP_VALIDATION_LIMIT_BYTES", 1_048_576))


TimeoutConfig = httpx.Timeout(
    connect=HTTP_CONNECT_TIMEOUT_MS / 1000,
    read=HTTP_TIMEOUT_MS / 1000,
    write=HTTP_WRITE_TIMEOUT_MS / 1000,
    pool=HTTP_POOL_TIMEOUT_MS / 1000,
)


# ---------------------------------------------------------------------------
# Telemetry primitives


METER = metrics.get_meter("mcp_agent.client.http")
TRACER = trace.get_tracer("mcp_agent.client.http")

LATENCY_HISTOGRAM = METER.create_histogram(
    "http_client_latency_ms",
    description="Latency of HTTP requests from tool adapters",
    unit="ms",
)
RETRY_COUNTER = METER.create_counter(
    "http_client_retries_total",
    description="Number of HTTP retries executed",
)
ERROR_COUNTER = METER.create_counter(
    "tool_client_errors_total",
    description="Canonical tool errors emitted by adapters",
)

_breaker_states: Dict[str, int] = {}


def _breaker_callback(_: CallbackOptions):
    observations = []
    for tool, state in list(_breaker_states.items()):
        observations.append(Observation(state, {"tool": tool}))
    return observations


METER.create_observable_gauge(
    "http_client_circuit_open",
    callbacks=[_breaker_callback],
    description="State of the HTTP circuit breaker (1=open)",
)


# ---------------------------------------------------------------------------
# Helpers


async def _async_sleep(seconds: float) -> None:
    await asyncio.sleep(max(0.0, seconds))


def _now_ms() -> float:
    return time.monotonic() * 1000


def _trace_id() -> int:
    span = trace.get_current_span()
    return span.get_span_context().trace_id if span else 0


def _sanitize_headers(headers: Mapping[str, str]) -> Dict[str, str]:
    redacted = {}
    for key, value in headers.items():
        if key.lower() in {"authorization", "x-signature"} or key.lower().endswith("_key"):
            redacted[key] = "***"
        else:
            redacted[key] = value
    return redacted


def _status_class(status: int) -> str:
    if status <= 0:
        return "unknown"
    return f"{int(status/100)}xx"


def _parse_retry_after(header_value: Optional[str]) -> Optional[float]:
    if not header_value:
        return None
    header_value = header_value.strip()
    try:
        seconds = float(header_value)
        if seconds >= 0:
            return seconds
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(header_value)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        delta = (when - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, delta)
    except Exception:  # pragma: no cover - fallback for invalid header
        return None


def _absolute_url(base: httpx.URL, path: str) -> httpx.URL:
    url = httpx.URL(path)
    if not url.scheme:
        url = base.join(path)
    if url.scheme not in {"http", "https"}:
        raise ValueError("Only http and https schemes are permitted")
    if ALLOWED_HOSTS and url.host not in ALLOWED_HOSTS:
        raise ValueError(f"Host {url.host!r} not in allow-list")
    return url


# ---------------------------------------------------------------------------
# Circuit breaker implementation


@dataclass
class _BreakerState:
    tool: str
    window: deque[bool]
    cooldown_expires_ms: float = 0.0
    state: str = "closed"  # closed | open | half_open
    half_open_remaining: int = 0

    def _set_state(self, state: str) -> None:
        self.state = state
        _breaker_states[self.tool] = 1 if state == "open" else 0

    def allow(self) -> str:
        now = _now_ms()
        if self.state == "open":
            if now >= self.cooldown_expires_ms:
                self._set_state("half_open")
                self.half_open_remaining = HALF_OPEN_MAX
            else:
                return "open"
        if self.state == "half_open":
            if self.half_open_remaining <= 0:
                return "open"
            self.half_open_remaining -= 1
            return "half_open"
        return "closed"

    def record(self, success: bool) -> None:
        if not BREAKER_ENABLED:
            return
        self.window.appendleft(not success)
        if success:
            if self.state in {"half_open", "open"}:
                self._set_state("closed")
                self.window.clear()
            return

        if self.state == "half_open":
            self.trip()
            return

        failures = sum(self.window)
        total = len(self.window)
        if total >= BREAKER_WINDOW and total > 0:
            rate = failures / total
            if rate >= BREAKER_THRESH:
                self.trip()

    def trip(self) -> None:
        self.cooldown_expires_ms = _now_ms() + BREAKER_COOLDOWN_MS
        self._set_state("open")


class CircuitBreakerRegistry:
    def __init__(self) -> None:
        self._states: Dict[str, _BreakerState] = {}

    def state_for(self, tool: str) -> _BreakerState:
        if tool not in self._states:
            self._states[tool] = _BreakerState(tool=tool, window=deque(maxlen=BREAKER_WINDOW))
            _breaker_states.setdefault(tool, 0)
        return self._states[tool]


_BREAKER_REGISTRY = CircuitBreakerRegistry()


# ---------------------------------------------------------------------------
# Shared async client


_CLIENT_LOCK = asyncio.Lock()
_SHARED_CLIENT: Optional[httpx.AsyncClient] = None


async def _shared_async_client() -> httpx.AsyncClient:
    global _SHARED_CLIENT
    if _SHARED_CLIENT is None:
        async with _CLIENT_LOCK:
            if _SHARED_CLIENT is None:
                _SHARED_CLIENT = httpx.AsyncClient(timeout=TimeoutConfig)
    return _SHARED_CLIENT


# ---------------------------------------------------------------------------
# HTTP client with retries and telemetry


class HTTPClient:
    IDEMPOTENT_METHODS = {"GET", "HEAD", "OPTIONS"}

    def __init__(
        self,
        tool: str,
        base_url: str,
        *,
        default_headers: Optional[Mapping[str, str]] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        random_source: Optional[random.Random] = None,
    ) -> None:
        self.tool = tool
        self.base_url = httpx.URL(base_url.rstrip("/"))
        if self.base_url.scheme not in {"http", "https"}:
            raise ValueError("base_url must use http or https")
        if ALLOWED_HOSTS and self.base_url.host not in ALLOWED_HOSTS:
            raise ValueError(f"Host {self.base_url.host!r} not in allow-list")
        self._default_headers = dict(default_headers or {})
        self._random = random_source or random.Random()
        self._transport = transport
        self._client: Optional[httpx.AsyncClient] = None
        self._breaker = _BREAKER_REGISTRY.state_for(tool)

    async def _client_instance(self) -> httpx.AsyncClient:
        if self._transport is not None:
            if self._client is None:
                self._client = httpx.AsyncClient(timeout=TimeoutConfig, transport=self._transport)
            return self._client
        return await _shared_async_client()

    def _is_idempotent(self, method: str, headers: Mapping[str, str], idempotent: Optional[bool]) -> bool:
        if idempotent is not None:
            return idempotent
        if method.upper() in self.IDEMPOTENT_METHODS:
            return True
        for key in headers:
            if key.lower() in {"idempotency-key", "x-idempotency-key"}:
                return True
        return False

    async def request(
        self,
        method: str,
        path: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        params: Optional[Mapping[str, Any]] = None,
        json_body: Any = None,
        data: Any = None,
        timeout: Optional[float] = None,
        idempotent: Optional[bool] = None,
    ) -> httpx.Response:
        method = method.upper()
        headers = {**self._default_headers, **(headers or {})}
        sanitized_headers = _sanitize_headers(headers)
        client = await self._client_instance()
        url = _absolute_url(self.base_url, path)
        request_timeout = TimeoutConfig if timeout is None else timeout

        idempotent_call = self._is_idempotent(method, headers, idempotent)

        attempt = 0
        span_name = f"HTTP {method}"
        with TRACER.start_as_current_span(span_name, kind=SpanKind.CLIENT) as span:
            span.set_attribute("tool", self.tool)
            span.set_attribute("http.method", method)
            span.set_attribute("http.url", str(url))
            while True:
                attempt += 1
                breaker_state = self._breaker.allow()
                if breaker_state == "open":
                    error = map_breaker_open(self.tool, _trace_id())
                    ERROR_COUNTER.add(1, {"tool": self.tool, "code": error.code})
                    self._log("breaker", url, method, sanitized_headers, code=error.code)
                    span.record_exception(error)
                    span.set_status(Status(StatusCode.ERROR, description=error.detail))
                    raise error
                span.set_attribute("breaker_state", breaker_state)
                retry_reason: Optional[str] = None
                start_ms = _now_ms()
                self._log("send", url, method, sanitized_headers, attempt=attempt)
                try:
                    response = await self._send(
                        client,
                        method,
                        url,
                        headers=headers,
                        params=params,
                        json=json_body,
                        data=data,
                        timeout=request_timeout,
                    )
                    elapsed_ms = _now_ms() - start_ms
                    LATENCY_HISTOGRAM.record(elapsed_ms, {
                        "tool": self.tool,
                        "method": method,
                        "status_class": _status_class(response.status_code),
                    })
                    self._log(
                        "recv",
                        url,
                        method,
                        sanitized_headers,
                        attempt=attempt,
                        status=response.status_code,
                        latency_ms=elapsed_ms,
                    )
                    span.set_attribute("http.status_code", response.status_code)
                    span.set_attribute("retry_count", attempt - 1)
                    if response.is_success:
                        self._breaker.record(True)
                        return response

                    retry_reason = self._should_retry_response(response)
                    self._breaker.record(False)
                    if retry_reason and attempt <= RETRY_MAX and idempotent_call:
                        await self._sleep_with_backoff(attempt, retry_reason, response)
                        continue

                    error = map_http_response(self.tool, response, _trace_id())
                    ERROR_COUNTER.add(1, {"tool": self.tool, "code": error.code})
                    span.record_exception(error)
                    span.set_status(Status(StatusCode.ERROR, description=error.detail))
                    raise error
                except CanonicalError:
                    raise
                except Exception as exc:
                    retry_reason = self._retry_reason_for_exception(exc)
                    self._breaker.record(False)
                    if retry_reason and attempt <= RETRY_MAX and (idempotent_call or isinstance(exc, httpx.TimeoutException)):
                        await self._sleep_with_backoff(attempt, retry_reason)
                        continue
                    error = map_http_exception(self.tool, exc, _trace_id())
                    ERROR_COUNTER.add(1, {"tool": self.tool, "code": error.code})
                    span.record_exception(error)
                    span.set_status(Status(StatusCode.ERROR, description=error.detail))
                    raise error

    async def request_json(
        self,
        method: str,
        path: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        params: Optional[Mapping[str, Any]] = None,
        json_body: Any = None,
        data: Any = None,
        timeout: Optional[float] = None,
        idempotent: Optional[bool] = None,
    ) -> Any:
        response = await self.request(
            method,
            path,
            headers=headers,
            params=params,
            json_body=json_body,
            data=data,
            timeout=timeout,
            idempotent=idempotent,
        )
        content = await response.aread()
        if len(content) > VALIDATION_LIMIT_BYTES:
            raise map_payload_too_large(self.tool, _trace_id())
        if not content:
            return None
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise map_json_decode_error(self.tool, _trace_id()) from exc

    async def _send(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: httpx.URL,
        *,
        headers: Mapping[str, str],
        params: Optional[Mapping[str, Any]],
        json: Any,
        data: Any,
        timeout: Any,
    ) -> httpx.Response:
        request = client.build_request(
            method,
            url,
            headers=headers,
            params=params,
            json=json,
            data=data,
            timeout=timeout,
        )
        redirects = 0
        while True:
            response = await client.send(request, follow_redirects=False)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if location and redirects < MAX_REDIRECTS:
                    redirects += 1
                    new_url = _absolute_url(url, location)
                    request = request.copy()
                    request.url = new_url
                    if response.status_code == 303:
                        request.method = "GET"
                        request.content = None
                    continue
            return response

    def _retry_reason_for_exception(self, exc: Exception) -> Optional[str]:
        if isinstance(exc, httpx.TimeoutException):
            return "timeout"
        if isinstance(exc, httpx.TransportError):
            return "transport"
        return None

    def _should_retry_response(self, response: httpx.Response) -> Optional[str]:
        status = response.status_code
        if status == 429:
            return "rate_limited"
        if status == 503:
            return "unavailable"
        if status == 500 or (500 < status < 600 and status != 501):
            return "server_error"
        return None

    async def _sleep_with_backoff(
        self,
        attempt: int,
        reason: str,
        response: Optional[httpx.Response] = None,
    ) -> None:
        delay = RETRY_BASE_MS * (2 ** max(0, attempt - 1)) / 1000.0
        jitter = self._random.uniform(1 - RETRY_JITTER, 1 + RETRY_JITTER)
        delay *= jitter
        retry_after = _parse_retry_after(response.headers.get("retry-after")) if response else None
        if retry_after is not None:
            delay = max(delay, retry_after)
        headers = (
            _sanitize_headers(dict(response.request.headers))
            if response and response.request is not None
            else {}
        )
        RETRY_COUNTER.add(1, {"tool": self.tool, "reason": reason})
        self._log(
            "retry",
            response.request.url if response and response.request is not None else None,
            response.request.method if response and response.request is not None else "",
            headers,
            reason=reason,
            delay_s=delay,
        )
        span = trace.get_current_span()
        if span:
            span.add_event("retry", {"reason": reason, "delay_ms": int(delay * 1000), "attempt": attempt})
        await _async_sleep(delay)

    def _log(
        self,
        phase: str,
        url: Optional[httpx.URL],
        method: str,
        headers: Mapping[str, str],
        **extra: Any,
    ) -> None:
        span = trace.get_current_span()
        trace_id = span.get_span_context().trace_id if span else 0
        payload = {
            "trace_id": f"{trace_id:032x}" if trace_id else "0" * 32,
            "tool": self.tool,
            "phase": phase,
            "method": method,
            "url": str(url) if url else None,
            "headers": dict(headers),
        }
        payload.update(extra)
        LOGGER.info(json.dumps(payload, sort_keys=True))


async def aclose() -> None:
    """Close the shared AsyncClient (for tests)."""

    global _SHARED_CLIENT
    if _SHARED_CLIENT is not None:
        await _SHARED_CLIENT.aclose()
        _SHARED_CLIENT = None

