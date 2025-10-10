from __future__ import annotations

import importlib
import pathlib
import sys

import httpx
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.mark.anyio
async def test_metrics_and_traces_emitted(http_module, monkeypatch):
    http, metric_reader, span_exporter = http_module
    monkeypatch.setenv("RETRY_MAX", "1")
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
            return httpx.Response(500, request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    client = http.HTTPClient("telemetry-tool", "https://example.com", transport=httpx.MockTransport(handler))
    result = await client.request_json("GET", "/telemetry")
    assert result == {"ok": True}
    assert sleep_calls  # retry occurred

    metrics_data = metric_reader.get_metrics_data()
    histogram_points = [
        point
        for resource in metrics_data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
        if metric.name == "http_client_latency_ms"
        for point in metric.data.data_points
    ]
    status_classes = {point.attributes["status_class"] for point in histogram_points}
    assert "5xx" in status_classes and "2xx" in status_classes

    retry_points = [
        point
        for resource in metrics_data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
        if metric.name == "http_client_retries_total"
        for point in metric.data.data_points
    ]
    assert retry_points and retry_points[0].value == 1

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.attributes["tool"] == "telemetry-tool"
    assert span.attributes["retry_count"] == 1
    assert any(event.name == "retry" for event in span.events)
