"""HTTP routes for manipulating workflow definitions at runtime."""

from __future__ import annotations

import json

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Router

from mcp_agent.models.workflow import (
    WorkflowCreateRequest,
    WorkflowPatchRequest,
    WorkflowStepOperation,
)
from mcp_agent.workflows.composer import WorkflowNotFoundError

from .state import authenticate_request, get_public_state


async def list_workflows(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    composer = get_public_state(request).workflow_composer
    models = await composer.list()
    return JSONResponse({"items": [model.model_dump(mode="json") for model in models]})


async def create_workflow(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    try:
        payload = WorkflowCreateRequest.model_validate(body)
    except Exception as exc:
        return JSONResponse({"error": "invalid_payload", "detail": str(exc)}, status_code=400)
    composer = get_public_state(request).workflow_composer
    steps = [step.model_copy() for step in payload.steps]
    model = await composer.create(
        workflow_id=payload.id,
        name=payload.name,
        description=payload.description,
        steps=steps,
    )
    return JSONResponse(model.model_dump(mode="json"), status_code=201)


async def get_workflow(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    composer = get_public_state(request).workflow_composer
    workflow_id = request.path_params["workflow_id"]
    try:
        model = await composer.get(workflow_id)
    except WorkflowNotFoundError:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse(model.model_dump(mode="json"))


async def patch_workflow(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    try:
        payload = WorkflowPatchRequest.model_validate(body)
    except Exception as exc:
        return JSONResponse({"error": "invalid_payload", "detail": str(exc)}, status_code=400)
    composer = get_public_state(request).workflow_composer
    workflow_id = request.path_params["workflow_id"]
    try:
        model = await composer.patch(
            workflow_id,
            name=payload.name,
            description=payload.description,
        )
    except WorkflowNotFoundError:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse(model.model_dump(mode="json"))


async def delete_workflow(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    composer = get_public_state(request).workflow_composer
    workflow_id = request.path_params["workflow_id"]
    try:
        await composer.delete(workflow_id)
    except WorkflowNotFoundError:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse({}, status_code=204)


async def mutate_workflow(request: Request) -> JSONResponse:
    ok, _ = authenticate_request(request)
    if not ok:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    try:
        operation = WorkflowStepOperation.model_validate(body)
    except Exception as exc:
        return JSONResponse({"error": "invalid_payload", "detail": str(exc)}, status_code=400)
    composer = get_public_state(request).workflow_composer
    workflow_id = request.path_params["workflow_id"]
    step_model = operation.step.model_copy() if operation.step is not None else None
    try:
        model = await composer.apply_step_operation(
            workflow_id,
            action=operation.action,
            step=step_model,
            target_step_id=operation.target_step_id,
        )
    except WorkflowNotFoundError:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse(model.model_dump(mode="json"))


routes = [
    Route("/workflows", list_workflows, methods=["GET"]),
    Route("/workflows", create_workflow, methods=["POST"]),
    Route("/workflows/{workflow_id}", get_workflow, methods=["GET"]),
    Route("/workflows/{workflow_id}", patch_workflow, methods=["PATCH"]),
    Route("/workflows/{workflow_id}", delete_workflow, methods=["DELETE"]),
    Route("/workflows/{workflow_id}", mutate_workflow, methods=["POST"]),
]

router = Router(routes=routes)
