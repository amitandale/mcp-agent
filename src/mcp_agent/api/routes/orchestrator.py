"""HTTP routes exposing orchestrator runtime state and events."""

from __future__ import annotations

import json

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route, Router

from mcp_agent.models.orchestrator import (
    OrchestratorBudgetModel,
    OrchestratorMemoryModel,
    OrchestratorPlanModel,
    OrchestratorPolicyModel,
    OrchestratorQueueModel,
)

from .state import authenticate_request, get_public_state


async def _require_state(request: Request):
    state = get_public_state(request)
    orchestrator_id = request.path_params["orchestrator_id"]
    return orchestrator_id, state.orchestrator_runtime


async def get_state(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    orchestrator_id, runtime = await _require_state(request)
    model = await runtime.get_state(orchestrator_id)
    return JSONResponse(model.model_dump(mode="json"))


async def patch_state(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    orchestrator_id, runtime = await _require_state(request)
    plan = (
        OrchestratorPlanModel.model_validate(body["plan"])
        if "plan" in body
        else None
    )
    queue = (
        OrchestratorQueueModel.model_validate(body["queue"])
        if "queue" in body
        else None
    )
    budget = (
        OrchestratorBudgetModel.model_validate(body["budget"])
        if "budget" in body
        else None
    )
    memory = (
        OrchestratorMemoryModel.model_validate(body["memory"])
        if "memory" in body
        else None
    )
    policy = (
        OrchestratorPolicyModel.model_validate(body["policy"])
        if "policy" in body
        else None
    )
    model = await runtime.update_state(
        orchestrator_id,
        plan=plan,
        queue=queue,
        budget=budget,
        memory=memory,
        policy=policy,
    )
    return JSONResponse(model.model_dump(mode="json"))


async def get_plan(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    orchestrator_id, runtime = await _require_state(request)
    state = await runtime.get_state(orchestrator_id)
    return JSONResponse(state.plan.model_dump(mode="json"))


async def get_queue(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    orchestrator_id, runtime = await _require_state(request)
    state = await runtime.get_state(orchestrator_id)
    return JSONResponse(state.queue.model_dump(mode="json"))


async def get_budget(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    orchestrator_id, runtime = await _require_state(request)
    state = await runtime.get_state(orchestrator_id)
    return JSONResponse(state.budget.model_dump(mode="json"))


async def get_memory(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    orchestrator_id, runtime = await _require_state(request)
    state = await runtime.get_state(orchestrator_id)
    return JSONResponse(state.memory.model_dump(mode="json"))


async def get_policy(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    orchestrator_id, runtime = await _require_state(request)
    state = await runtime.get_state(orchestrator_id)
    return JSONResponse(state.policy.model_dump(mode="json"))


async def stream_events(request: Request) -> StreamingResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return StreamingResponse(iter(()), status_code=401)
    orchestrator_id, runtime = await _require_state(request)
    last_id_header = request.headers.get("last-event-id") or request.headers.get(
        "Last-Event-ID"
    )
    try:
        last_id = int(last_id_header) if last_id_header else None
    except ValueError:
        last_id = None

    async def event_source():
        async for event in runtime.subscribe_events(orchestrator_id, last_event_id=last_id):
            payload = event.model_dump(mode="json")
            data = json.dumps(payload)
            yield f"id: {event.id}\ndata: {data}\n\n"

    headers = {"Cache-Control": "no-cache", "Content-Type": "text/event-stream"}
    return StreamingResponse(event_source(), headers=headers)


async def post_event(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    event_type = body.get("type")
    payload = body.get("payload") or {}
    if not isinstance(event_type, str) or not isinstance(payload, dict):
        return JSONResponse({"error": "invalid_payload"}, status_code=400)
    orchestrator_id, runtime = await _require_state(request)
    event = await runtime.append_event(orchestrator_id, event_type=event_type, payload=payload)
    return JSONResponse(event.model_dump(mode="json"), status_code=202)


routes = [
    Route("/orchestrator/{orchestrator_id}/state", get_state, methods=["GET"]),
    Route("/orchestrator/{orchestrator_id}/state", patch_state, methods=["PATCH"]),
    Route("/orchestrator/{orchestrator_id}/plan", get_plan, methods=["GET"]),
    Route("/orchestrator/{orchestrator_id}/queue", get_queue, methods=["GET"]),
    Route("/orchestrator/{orchestrator_id}/budget", get_budget, methods=["GET"]),
    Route("/orchestrator/{orchestrator_id}/memory", get_memory, methods=["GET"]),
    Route("/orchestrator/{orchestrator_id}/policy", get_policy, methods=["GET"]),
    Route("/orchestrator/{orchestrator_id}/events", stream_events, methods=["GET"]),
    Route("/orchestrator/{orchestrator_id}/events", post_event, methods=["POST"]),
]

router = Router(routes=routes)
