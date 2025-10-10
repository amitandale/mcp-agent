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
async def test_validation_errors_raise_canonical(http_module):
    http, _, _ = http_module
    await http.aclose()
    http = importlib.reload(http)

    import mcp_agent.adapters.base as base

    base = importlib.reload(base)

    class ExampleResponse(base.StrictModel):
        id: int

    class ExampleAdapter(base.BaseAdapter):
        def __init__(self, client):
            super().__init__("validator", "https://example.com", client=client)

        async def fetch(self):
            return await self._request_json("GET", "/resource", response_model=ExampleResponse)

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "oops"})

    adapter = ExampleAdapter(http.HTTPClient("validator", "https://example.com", transport=httpx.MockTransport(handler)))

    with pytest.raises(CanonicalError) as excinfo:
        await adapter.fetch()
    assert excinfo.value.code == "schema_validation_error"
    assert "id" in (excinfo.value.detail or "")


@pytest.mark.anyio
async def test_extra_fields_forbidden(http_module):
    http, _, _ = http_module
    await http.aclose()
    http = importlib.reload(http)

    import mcp_agent.adapters.base as base

    base = importlib.reload(base)

    class ExampleResponse(base.StrictModel):
        name: str

    class ExampleAdapter(base.BaseAdapter):
        def __init__(self, client):
            super().__init__("validator", "https://example.com", client=client)

        async def fetch(self):
            return await self._request_json("GET", "/resource", response_model=ExampleResponse)

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"name": "ok", "extra": "nope"})

    adapter = ExampleAdapter(http.HTTPClient("validator", "https://example.com", transport=httpx.MockTransport(handler)))

    with pytest.raises(CanonicalError) as excinfo:
        await adapter.fetch()
    assert excinfo.value.code == "schema_validation_error"
    assert "extra" in (excinfo.value.detail or "")
