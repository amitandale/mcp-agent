"""Agent management HTTP endpoints."""

from __future__ import annotations

import json
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route, Router

from mcp_agent.agents.agent_spec import AgentSpec

from mcp_agent.models.agent import AgentRecordModel, AgentSpecCreate, AgentSpecPatch
from mcp_agent.registry.agent import AgentNotFoundError, AgentRegistryError

from .state import authenticate_request, get_public_state


def _record_to_payload(record) -> dict[str, Any]:
    model = AgentRecordModel.from_runtime(
        agent_id=record.id,
        spec=record.spec,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
    return model.model_dump(mode="json")


async def list_agents(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    state = get_public_state(request)
    records = await state.agent_registry.list_agents()
    payload = [_record_to_payload(record) for record in records]
    return JSONResponse({"items": payload})


async def create_agent(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    try:
        payload = AgentSpecCreate.model_validate(data)
    except Exception as exc:
        return JSONResponse({"error": "invalid_payload", "detail": str(exc)}, status_code=400)
    spec = payload.spec.to_spec()
    state = get_public_state(request)
    try:
        record = await state.agent_registry.create_agent(agent_id=payload.id, spec=spec)
    except AgentRegistryError as exc:
        return JSONResponse({"error": "conflict", "detail": str(exc)}, status_code=409)
    return JSONResponse(_record_to_payload(record), status_code=201)


async def get_agent(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    agent_id = request.path_params["agent_id"]
    state = get_public_state(request)
    try:
        record = await state.agent_registry.get_agent(agent_id)
    except AgentNotFoundError:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse(_record_to_payload(record))


async def patch_agent(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    agent_id = request.path_params["agent_id"]
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    try:
        patch = AgentSpecPatch.model_validate(data)
    except Exception as exc:
        return JSONResponse({"error": "invalid_payload", "detail": str(exc)}, status_code=400)
    state = get_public_state(request)
    try:
        record = await state.agent_registry.patch_agent(
            agent_id,
            name=patch.name,
            instruction=patch.instruction,
            server_names=patch.server_names,
            connection_persistence=patch.connection_persistence,
            extra=dict(patch.extra or {}),
        )
    except AgentNotFoundError:
        return JSONResponse({"error": "not_found"}, status_code=404)
    except AgentRegistryError as exc:
        return JSONResponse({"error": "conflict", "detail": str(exc)}, status_code=409)
    return JSONResponse(_record_to_payload(record))


async def delete_agent(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    agent_id = request.path_params["agent_id"]
    state = get_public_state(request)
    try:
        await state.agent_registry.delete_agent(agent_id)
    except AgentNotFoundError:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse({}, status_code=204)


async def upload_agents(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    text = body.get("text") if isinstance(body, dict) else None
    if not isinstance(text, str):
        return JSONResponse({"error": "invalid_payload"}, status_code=400)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        import yaml

        parsed = yaml.safe_load(text)
    if not isinstance(parsed, (list, dict)):
        return JSONResponse({"error": "invalid_format"}, status_code=400)
    specs: dict[str, AgentSpec] = {}
    if isinstance(parsed, list):
        for entry in parsed:
            if isinstance(entry, dict):
                spec = AgentSpec.model_validate(entry)
                specs[spec.name] = spec
    else:
        items = parsed.get("agents") if isinstance(parsed.get("agents"), list) else []
        for entry in items:
            if isinstance(entry, dict):
                spec = AgentSpec.model_validate(entry)
                specs[spec.name] = spec
    state = get_public_state(request)
    await state.agent_registry.replace_all(specs)
    return JSONResponse({"count": len(specs)})


async def download_agents(request: Request) -> PlainTextResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return PlainTextResponse("unauthorized", status_code=401)
    state = get_public_state(request)
    payload = await state.agent_registry.export_yaml()
    response = PlainTextResponse(payload)
    response.headers["Content-Disposition"] = "attachment; filename=agents.yaml"
    return response


routes = [
    Route("/agents", list_agents, methods=["GET"]),
    Route("/agents", create_agent, methods=["POST"]),
    Route("/agents/upload", upload_agents, methods=["POST"]),
    Route("/agents/download", download_agents, methods=["GET"]),
    Route("/agents/{agent_id}", get_agent, methods=["GET"]),
    Route("/agents/{agent_id}", patch_agent, methods=["PATCH"]),
    Route("/agents/{agent_id}", delete_agent, methods=["DELETE"]),
]

router = Router(routes=routes)
