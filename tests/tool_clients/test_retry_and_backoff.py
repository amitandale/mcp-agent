from __future__ import annotations

import importlib
import pathlib
import sys

import httpx
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp_agent.errors.canonical import CanonicalError


@pytest.mark.anyio
async def test_retries_then_succeeds(http_module, monkeypatch):
    http, metric_reader, _ = http_module
    monkeypatch.setenv("RETRY_MAX", "3")
    monkeypatch.setenv("RETRY_BASE_MS", "1")
    await http.aclose()
    http = importlib.reload(http)

    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(500, request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    transport = httpx.MockTransport(handler)
    client = http.HTTPClient("retry-tool", "https://example.com", transport=transport)

    result = await client.request_json("GET", "/ping")
    assert result == {"ok": True}
    assert attempts == 2

    metrics_data = metric_reader.get_metrics_data()
    retry_metric = [
        point
        for resource in metrics_data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
        if metric.name == "http_client_retries_total"
        for point in metric.data.data_points
        if point.attributes.get("tool") == "retry-tool"
    ]
    assert retry_metric and retry_metric[0].value == 1


@pytest.mark.anyio
async def test_retry_after_respected(http_module, monkeypatch):
    http, _, _ = http_module
    monkeypatch.setenv("RETRY_MAX", "2")
    monkeypatch.setenv("RETRY_BASE_MS", "1")
    await http.aclose()
    http = importlib.reload(http)

    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(http, "_async_sleep", fake_sleep)

    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "0.05"}, request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    client = http.HTTPClient("retry-after", "https://example.com", transport=httpx.MockTransport(handler))
    result = await client.request_json("GET", "/path")
    assert result == {"ok": True}
    assert sleep_calls and sleep_calls[0] >= 0.05


@pytest.mark.anyio
async def test_connect_timeout_exhausts_retries(http_module, monkeypatch):
    http, metric_reader, _ = http_module
    monkeypatch.setenv("RETRY_MAX", "2")
    monkeypatch.setenv("RETRY_BASE_MS", "1")
    await http.aclose()
    http = importlib.reload(http)

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("boom", request=request)

    client = http.HTTPClient("retry-timeout", "https://example.com", transport=httpx.MockTransport(handler))

    with pytest.raises(CanonicalError) as excinfo:
        await client.request_json("GET", "/timeout")
    assert excinfo.value.code == "network_timeout"

    metrics_data = metric_reader.get_metrics_data()
    retry_metric = [
        point
        for resource in metrics_data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
        if metric.name == "http_client_retries_total"
        for point in metric.data.data_points
        if point.attributes.get("tool") == "retry-timeout"
    ]
    assert retry_metric and retry_metric[0].value == 2
