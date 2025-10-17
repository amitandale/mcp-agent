"""HTTP routes for managing human input requests at runtime."""

from __future__ import annotations

import json

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route, Router

from mcp_agent.models.human_input import (
    HumanInputRequestCreate,
    HumanInputResponseModel,
)

from .state import authenticate_request, get_public_state


async def create_request(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    try:
        payload = HumanInputRequestCreate.model_validate(body)
    except Exception as exc:
        return JSONResponse({"error": "invalid_payload", "detail": str(exc)}, status_code=400)
    runtime = get_public_state(request).human_input_runtime
    try:
        created = await runtime.add_request(
            request_id=payload.id,
            prompt=payload.prompt,
            metadata=payload.metadata,
        )
    except ValueError:
        return JSONResponse({"error": "conflict"}, status_code=409)
    return JSONResponse(created.model_dump(mode="json"), status_code=201)


async def stream_requests(request: Request) -> StreamingResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return StreamingResponse(iter(()), status_code=401)
    runtime = get_public_state(request).human_input_runtime

    async def event_source():
        async for item in runtime.subscribe():
            data = json.dumps(item.model_dump(mode="json"))
            yield f"id: {item.id}\ndata: {data}\n\n"

    headers = {"Cache-Control": "no-cache", "Content-Type": "text/event-stream"}
    return StreamingResponse(event_source(), headers=headers)


async def respond(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    try:
        payload = HumanInputResponseModel.model_validate(body)
    except Exception as exc:
        return JSONResponse({"error": "invalid_payload", "detail": str(exc)}, status_code=400)
    runtime = get_public_state(request).human_input_runtime
    acknowledged = await runtime.respond(payload)
    if not acknowledged:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse({"status": "ok"})


routes = [
    Route("/human_input/requests", create_request, methods=["POST"]),
    Route("/human_input/requests", stream_requests, methods=["GET"]),
    Route("/human_input/respond", respond, methods=["POST"]),
]

router = Router(routes=routes)
