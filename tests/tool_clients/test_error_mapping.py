from __future__ import annotations

import pathlib
import sys

import httpx

ROOT = pathlib.Path(__file__).resolve().parents[2] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp_agent.errors.canonical import (
    map_breaker_open,
    map_http_exception,
    map_http_response,
    map_json_decode_error,
    map_payload_too_large,
)


def _response(status: int, *, json_body=None, headers=None) -> httpx.Response:
    request = httpx.Request("GET", "https://example.com")
    return httpx.Response(status, json=json_body, headers=headers, request=request)


def test_http_status_mappings():
    err = map_http_response("tool", _response(429, headers={"Retry-After": "1"}), 0x1)
    assert err.code == "rate_limited"
    assert err.http == 429

    err = map_http_response("tool", _response(401), 0x2)
    assert err.code == "unauthorized"

    err = map_http_response("tool", _response(503), 0x3)
    assert err.code == "upstream_error"

    err = map_http_response("tool", _response(404), 0x4)
    assert err.code == "not_found"

    err = map_http_response("tool", _response(418), 0x5)
    assert err.code == "unexpected_status"


def test_exception_mapping():
    exc = httpx.TimeoutException("timed out")
    err = map_http_exception("tool", exc, 0x6)
    assert err.code == "network_timeout"


def test_breaker_mapping():
    err = map_breaker_open("tool", 0x7)
    assert err.code == "circuit_open"


def test_payload_helpers():
    err = map_payload_too_large("tool", 0x8)
    assert "exceeds" in (err.detail or "")

    err = map_json_decode_error("tool", 0x9)
    assert "valid JSON" in (err.detail or "")
