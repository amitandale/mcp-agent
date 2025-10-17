"""HTTP routes for interacting with the runtime tool registry."""

from __future__ import annotations

import json

from datetime import datetime, timezone

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Router

from mcp_agent.models.tool import (
    ToolAssignmentRequest,
    ToolPatchRequest,
    ToolRuntimeItem,
    ToolRuntimeResponse,
)
from mcp_agent.registry.tool import ToolNotFoundError

from .state import authenticate_request, get_public_state


async def get_runtime_tools(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    state = get_public_state(request)
    registry_hash, items = await state.tool_runtime.snapshot()
    runtime_items = [
        ToolRuntimeItem.from_tool_item(item, enabled=enabled) for item, enabled in items
    ]
    response = ToolRuntimeResponse.from_snapshot(
        registry_hash=registry_hash,
        generated_at=runtime_items[0].last_checked_ts
        if runtime_items
        else datetime.now(timezone.utc),
        items=runtime_items,
    )
    return JSONResponse(response.model_dump(mode="json"))


async def patch_tools(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    try:
        payload = ToolPatchRequest.model_validate(body)
    except Exception as exc:
        return JSONResponse({"error": "invalid_payload", "detail": str(exc)}, status_code=400)
    state = get_public_state(request)
    try:
        await state.tool_runtime.apply_updates(payload.updates)
    except ToolNotFoundError as exc:
        return JSONResponse({"error": "not_found", "detail": str(exc)}, status_code=404)
    return JSONResponse({"status": "ok"})


async def reload_tools(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    state = get_public_state(request)
    await state.tool_runtime.reload()
    return JSONResponse({"status": "reloaded"})


async def assign_tools(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    agent_id = request.path_params["agent_id"]
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    try:
        payload = ToolAssignmentRequest.model_validate(body)
    except Exception as exc:
        return JSONResponse({"error": "invalid_payload", "detail": str(exc)}, status_code=400)
    state = get_public_state(request)
    try:
        await state.tool_runtime.assign_tools(agent_id, payload.tools)
    except ToolNotFoundError as exc:
        return JSONResponse({"error": "not_found", "detail": str(exc)}, status_code=404)
    assigned = await state.tool_runtime.get_assignments(agent_id)
    return JSONResponse({"agent_id": agent_id, "tools": sorted(assigned)})


async def get_assignments(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    state = get_public_state(request)
    agent_id = request.path_params["agent_id"]
    assigned = await state.tool_runtime.get_assignments(agent_id)
    return JSONResponse({"agent_id": agent_id, "tools": sorted(assigned)})


routes = [
    Route("/tools/runtime", get_runtime_tools, methods=["GET"]),
    Route("/tools", patch_tools, methods=["PATCH"]),
    Route("/tools/reload", reload_tools, methods=["POST"]),
    Route("/tools/assign/{agent_id}", assign_tools, methods=["POST"]),
    Route("/tools/assign/{agent_id}", get_assignments, methods=["GET"]),
]

router = Router(routes=routes)
