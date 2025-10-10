from __future__ import annotations

import importlib
import pathlib
import sys

import httpx
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp_agent.errors.canonical import CanonicalError  # noqa: E402


@pytest.mark.anyio
async def test_breaker_open_and_half_open(http_module, monkeypatch):
    http, _, _ = http_module
    monkeypatch.setenv("BREAKER_ENABLED", "true")
    monkeypatch.setenv("BREAKER_WINDOW", "4")
    monkeypatch.setenv("BREAKER_THRESH", "0.5")
    monkeypatch.setenv("BREAKER_COOLDOWN_MS", "50")
    monkeypatch.setenv("HALF_OPEN_MAX", "1")
    monkeypatch.setenv("RETRY_MAX", "0")
    await http.aclose()
    http = importlib.reload(http)

    calls = 0
    responses = iter([500, 500, 500, 500, 200])

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        status = next(responses)
        body = {"ok": status == 200}
        return httpx.Response(status, json=body, request=request)

    current_time = 0.0

    def fake_now() -> float:
        return current_time

    monkeypatch.setattr(http, "_now_ms", lambda: fake_now())

    client = http.HTTPClient("breaker-tool", "https://example.com", transport=httpx.MockTransport(handler))

    for step in range(4):
        current_time = float(step * 10)
        with pytest.raises(CanonicalError) as excinfo:
            await client.request_json("GET", "/fail")
        assert excinfo.value.code == "upstream_error"
        assert calls == step + 1

    # Breaker should open and deny further requests until cooldown expires
    current_time = 45.0
    with pytest.raises(CanonicalError) as excinfo:
        await client.request_json("GET", "/fast-fail")
    assert excinfo.value.code == "circuit_open"
    assert calls == 4

    # After cooldown the breaker allows a probe which succeeds and closes the breaker
    current_time = 120.0
    result = await client.request_json("GET", "/recover")
    assert result == {"ok": True}
    assert calls == 5
