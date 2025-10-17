"""Runtime state manager for orchestrator inspection APIs."""

from __future__ import annotations

import asyncio
import queue as sync_queue
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator, Dict, Iterable

from mcp_agent.models.orchestrator import (
    OrchestratorBudgetModel,
    OrchestratorEvent,
    OrchestratorMemoryModel,
    OrchestratorPlanModel,
    OrchestratorPolicyModel,
    OrchestratorQueueModel,
    OrchestratorStateModel,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class _EventStream:
    queue: sync_queue.Queue[OrchestratorEvent]
    last_id: int


@dataclass
class OrchestratorState:
    id: str
    plan: OrchestratorPlanModel
    queue: OrchestratorQueueModel
    budget: OrchestratorBudgetModel
    memory: OrchestratorMemoryModel
    policy: OrchestratorPolicyModel
    updated_at: datetime
    last_event_id: int = 0

    def as_model(self) -> OrchestratorStateModel:
        return OrchestratorStateModel(
            id=self.id,
            plan=self.plan,
            queue=self.queue,
            budget=self.budget,
            memory=self.memory,
            policy=self.policy,
            updated_at=self.updated_at,
        )


class OrchestratorRuntime:
    """Tracks orchestrator state and publishes event streams."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._states: Dict[str, OrchestratorState] = {}
        self._streams: Dict[str, _EventStream] = {}

    async def ensure(self, orchestrator_id: str) -> OrchestratorState:
        async with self._lock:
            state = self._states.get(orchestrator_id)
            if state is None:
                state = OrchestratorState(
                    id=orchestrator_id,
                    plan=OrchestratorPlanModel(),
                    queue=OrchestratorQueueModel(),
                    budget=OrchestratorBudgetModel(),
                    memory=OrchestratorMemoryModel(),
                    policy=OrchestratorPolicyModel(),
                    updated_at=_utc_now(),
                )
                self._states[orchestrator_id] = state
            if orchestrator_id not in self._streams:
                self._streams[orchestrator_id] = _EventStream(
                    queue=sync_queue.Queue(),
                    last_id=0,
                )
            return state

    async def get_state(self, orchestrator_id: str) -> OrchestratorStateModel:
        state = await self.ensure(orchestrator_id)
        return state.as_model()

    async def update_state(
        self,
        orchestrator_id: str,
        *,
        plan: OrchestratorPlanModel | None = None,
        queue: OrchestratorQueueModel | None = None,
        budget: OrchestratorBudgetModel | None = None,
        memory: OrchestratorMemoryModel | None = None,
        policy: OrchestratorPolicyModel | None = None,
    ) -> OrchestratorStateModel:
        await self.ensure(orchestrator_id)
        async with self._lock:
            state = self._states[orchestrator_id]
            if plan is not None:
                state.plan = plan
            if queue is not None:
                state.queue = queue
            if budget is not None:
                state.budget = budget
            if memory is not None:
                state.memory = memory
            if policy is not None:
                state.policy = policy
            state.updated_at = _utc_now()
            return state.as_model()

    async def append_event(
        self, orchestrator_id: str, *, event_type: str, payload: dict
    ) -> OrchestratorEvent:
        stream = await self._get_stream(orchestrator_id)
        await self.ensure(orchestrator_id)
        async with self._lock:
            state = self._states[orchestrator_id]
            state.last_event_id += 1
            event_id = state.last_event_id
        event = OrchestratorEvent(
            id=event_id,
            timestamp=_utc_now(),
            type=event_type,
            payload=payload,
        )
        stream.queue.put(event)
        return event

    async def _get_stream(self, orchestrator_id: str) -> _EventStream:
        await self.ensure(orchestrator_id)
        async with self._lock:
            return self._streams[orchestrator_id]

    async def subscribe_events(
        self, orchestrator_id: str, *, last_event_id: int | None = None
    ) -> AsyncIterator[OrchestratorEvent]:
        stream = await self._get_stream(orchestrator_id)
        stream_queue = stream.queue
        if last_event_id is not None and last_event_id < stream.last_id:
            # Fast-forward by pushing sentinel events up to the requested id
            missing = stream.last_id - last_event_id
            for _ in range(missing):
                try:
                    stream_queue.get_nowait()
                except sync_queue.Empty:  # pragma: no cover - best effort
                    break
        while True:
            event = await asyncio.to_thread(stream_queue.get)
            stream.last_id = event.id
            yield event

    async def export_state(self) -> Iterable[OrchestratorStateModel]:
        async with self._lock:
            return [state.as_model() for state in self._states.values()]
