"""Integration tests for the management API surface."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from mcp_agent.api.routes import add_public_api
from mcp_agent.api.routes import public as public_module
from mcp_agent.registry.loader import build_response
from mcp_agent.registry.models import ToolItem
from mcp_agent.registry.tool import ToolRuntimeRegistry


class _StubToolStore:
    def __init__(self, snapshot):
        self._snapshot = snapshot

    async def get_snapshot(self):
        return self._snapshot

    async def refresh(self, force: bool = False):
        return self._snapshot


def _tool(**kwargs) -> ToolItem:
    defaults = dict(
        id="alpha",
        name="Alpha",
        version="1.0.0",
        base_url="http://alpha",
        alive=True,
        latency_ms=15.2,
        capabilities=["demo"],
        tags=["internal"],
        last_checked_ts=datetime.now(timezone.utc),
        failure_reason=None,
        consecutive_failures=0,
    )
    defaults.update(kwargs)
    return ToolItem(**defaults)


@pytest.fixture
def public_api_state():
    state = public_module.PublicAPIState()
    yield state
    asyncio.run(state.cancel_all_tasks())
    state.clear()


def _app(state):
    application = Starlette()

    @application.middleware("http")
    async def inject_state(request, call_next):
        request.state.public_api_state = state
        return await call_next(request)

    add_public_api(application)
    return application


def _auth_headers():
    return {"X-API-Key": "test-key"}


def test_agent_crud(monkeypatch, public_api_state):
    monkeypatch.setenv("STUDIO_API_KEYS", "test-key")
    with TestClient(_app(public_api_state)) as client:
        create_resp = client.post(
            "/v1/agents",
            headers=_auth_headers(),
            json={
                "id": "demo-agent",
                "spec": {
                    "name": "demo",
                    "instruction": "hello",
                    "server_names": ["files"],
                },
            },
        )
        assert create_resp.status_code == 201
        record = create_resp.json()
        assert record["id"] == "demo-agent"
        list_resp = client.get("/v1/agents", headers=_auth_headers())
        assert list_resp.status_code == 200
        assert any(item["id"] == "demo-agent" for item in list_resp.json()["items"])
        patch_resp = client.patch(
            "/v1/agents/demo-agent",
            headers=_auth_headers(),
            json={"instruction": "updated"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["spec"]["instruction"] == "updated"
        download = client.get("/v1/agents/download", headers=_auth_headers())
        assert download.status_code == 200
        assert "updated" in download.text
        delete_resp = client.delete("/v1/agents/demo-agent", headers=_auth_headers())
        assert delete_resp.status_code == 204


def test_tool_registry_runtime(monkeypatch, public_api_state):
    monkeypatch.setenv("STUDIO_API_KEYS", "test-key")
    snapshot = build_response([_tool(), _tool(id="beta", name="Beta")])
    public_api_state.tool_runtime = ToolRuntimeRegistry(backing_store=_StubToolStore(snapshot))
    with TestClient(_app(public_api_state)) as client:
        runtime_resp = client.get("/v1/tools/runtime", headers=_auth_headers())
        assert runtime_resp.status_code == 200
        items = runtime_resp.json()["items"]
        assert any(item["id"] == "alpha" for item in items)
        patch = client.patch(
            "/v1/tools",
            headers=_auth_headers(),
            json={"updates": [{"id": "alpha", "enabled": False}]},
        )
        assert patch.status_code == 200
        assign = client.post(
            "/v1/tools/assign/demo-agent",
            headers=_auth_headers(),
            json={"tools": ["beta"]},
        )
        assert assign.status_code == 200
        assigned = client.get(
            "/v1/tools/assign/demo-agent", headers=_auth_headers()
        )
        assert assigned.json()["tools"] == ["beta"]


def test_workflow_builder(monkeypatch, public_api_state):
    monkeypatch.setenv("STUDIO_API_KEYS", "test-key")
    with TestClient(_app(public_api_state)) as client:
        create = client.post(
            "/v1/workflows",
            headers=_auth_headers(),
            json={
                "id": "wf1",
                "name": "Workflow One",
                "description": "demo",
                "steps": [],
            },
        )
        assert create.status_code == 201
        mutate = client.post(
            "/v1/workflows/wf1",
            headers=_auth_headers(),
            json={
                "action": "add",
                "step": {"id": "s1", "type": "task", "config": {"agent": "demo"}},
            },
        )
        assert mutate.status_code == 200
        patch = client.patch(
            "/v1/workflows/wf1",
            headers=_auth_headers(),
            json={"name": "Workflow Prime"},
        )
        assert patch.json()["name"] == "Workflow Prime"
        listing = client.get("/v1/workflows", headers=_auth_headers())
        assert listing.status_code == 200
        delete = client.delete("/v1/workflows/wf1", headers=_auth_headers())
        assert delete.status_code == 204


def test_orchestrator_runtime(monkeypatch, public_api_state):
    monkeypatch.setenv("STUDIO_API_KEYS", "test-key")
    with TestClient(_app(public_api_state)) as client:
        patch = client.patch(
            "/v1/orchestrator/main/state",
            headers=_auth_headers(),
            json={
                "plan": {"steps": [{"id": "step1", "status": "ready"}], "status": "active"},
                "queue": {"items": [{"id": "step1"}]},
            },
        )
        assert patch.status_code == 200
        plan = client.get(
            "/v1/orchestrator/main/plan", headers=_auth_headers()
        )
        assert plan.json()["status"] == "active"
        client.post(
            "/v1/orchestrator/main/events",
            headers=_auth_headers(),
            json={"type": "update", "payload": {"ok": True}},
        )
        queued = public_api_state.orchestrator_runtime._streams["main"].queue
        event = queued.get_nowait()
        assert event.type == "update"


def test_human_input_runtime(monkeypatch, public_api_state):
    monkeypatch.setenv("STUDIO_API_KEYS", "test-key")
    with TestClient(_app(public_api_state)) as client:
        create = client.post(
            "/v1/human_input/requests",
            headers=_auth_headers(),
            json={"id": "req1", "prompt": "Need approval"},
        )
        assert create.status_code == 201
        pending = asyncio.run(public_api_state.human_input_runtime.export_pending())
        assert pending and pending[0].id == "req1"
        respond = client.post(
            "/v1/human_input/respond",
            headers=_auth_headers(),
            json={"id": "req1", "response": "Approved"},
        )
        assert respond.status_code == 200
