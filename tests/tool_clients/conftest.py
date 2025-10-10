from __future__ import annotations

import importlib
import pathlib
import sys

import pytest
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


ROOT = pathlib.Path(__file__).resolve().parents[2] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

METRIC_READER = InMemoryMetricReader()
METER_PROVIDER = MeterProvider(resource=Resource.create({"service.name": "test"}), metric_readers=[METRIC_READER])
metrics.set_meter_provider(METER_PROVIDER)

SPAN_EXPORTER = InMemorySpanExporter()
TRACER_PROVIDER = TracerProvider(resource=Resource.create({"service.name": "test"}))
TRACER_PROVIDER.add_span_processor(SimpleSpanProcessor(SPAN_EXPORTER))
trace.set_tracer_provider(TRACER_PROVIDER)


@pytest.fixture
async def http_module(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RETRY_JITTER", "0")
    import mcp_agent.client.http as http
    import mcp_agent.errors.canonical as canonical

    await http.aclose()
    http = importlib.reload(http)

    assert "site-packages" not in (http.__file__ or ""), http.__file__
    assert "site-packages" not in (canonical.__file__ or ""), canonical.__file__

    METRIC_READER.get_metrics_data()

    yield http, METRIC_READER, SPAN_EXPORTER

    await http.aclose()
    METRIC_READER.get_metrics_data()
    SPAN_EXPORTER.clear()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
