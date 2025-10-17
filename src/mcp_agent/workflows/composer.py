"""In-memory workflow composition runtime used by management APIs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from mcp_agent.models.workflow import WorkflowDefinitionModel, WorkflowStepModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class WorkflowRecord:
    id: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    steps: list[WorkflowStepModel]

    def as_model(self) -> WorkflowDefinitionModel:
        return WorkflowDefinitionModel(
            id=self.id,
            name=self.name,
            description=self.description,
            created_at=self.created_at,
            updated_at=self.updated_at,
            steps=list(self.steps),
        )


class WorkflowNotFoundError(RuntimeError):
    pass


class WorkflowComposer:
    """Stores and mutates workflow definitions in-memory."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._workflows: dict[str, WorkflowRecord] = {}

    async def list(self) -> list[WorkflowDefinitionModel]:
        async with self._lock:
            return [record.as_model() for record in self._workflows.values()]

    async def create(
        self,
        *,
        workflow_id: str | None,
        name: str,
        description: str | None,
        steps: Iterable[WorkflowStepModel],
    ) -> WorkflowDefinitionModel:
        async with self._lock:
            identifier = (workflow_id or name).strip()
            if not identifier:
                raise ValueError("Workflow id or name must be provided")
            if identifier in self._workflows:
                raise ValueError(f"Workflow '{identifier}' already exists")
            now = _utc_now()
            record = WorkflowRecord(
                id=identifier,
                name=name,
                description=description,
                created_at=now,
                updated_at=now,
                steps=list(steps),
            )
            self._workflows[identifier] = record
            return record.as_model()

    async def get(self, workflow_id: str) -> WorkflowDefinitionModel:
        async with self._lock:
            record = self._workflows.get(workflow_id)
            if record is None:
                raise WorkflowNotFoundError(workflow_id)
            return record.as_model()

    async def patch(
        self,
        workflow_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> WorkflowDefinitionModel:
        async with self._lock:
            record = self._workflows.get(workflow_id)
            if record is None:
                raise WorkflowNotFoundError(workflow_id)
            if name is not None:
                record.name = name
            if description is not None:
                record.description = description
            record.updated_at = _utc_now()
            return record.as_model()

    async def delete(self, workflow_id: str) -> None:
        async with self._lock:
            if workflow_id not in self._workflows:
                raise WorkflowNotFoundError(workflow_id)
            self._workflows.pop(workflow_id)

    async def apply_step_operation(
        self,
        workflow_id: str,
        *,
        action: str,
        step: WorkflowStepModel | None,
        target_step_id: str | None,
    ) -> WorkflowDefinitionModel:
        async with self._lock:
            record = self._workflows.get(workflow_id)
            if record is None:
                raise WorkflowNotFoundError(workflow_id)
            if action == "add":
                record.steps.append(step)  # type: ignore[arg-type]
            elif action == "remove":
                record.steps = [s for s in record.steps if s.id != target_step_id]
            elif action == "replace":
                new_steps: list[WorkflowStepModel] = []
                replaced = False
                for s in record.steps:
                    if s.id == target_step_id:
                        if step is None:
                            continue
                        new_steps.append(step)
                        replaced = True
                    else:
                        new_steps.append(s)
                if not replaced:
                    raise WorkflowNotFoundError(target_step_id or "")
                record.steps = new_steps
            else:  # pragma: no cover - guarded by validation
                raise ValueError(f"Unsupported action '{action}'")
            record.updated_at = _utc_now()
            return record.as_model()
