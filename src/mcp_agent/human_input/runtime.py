"""Runtime tracking for human input requests and responses."""

from __future__ import annotations

import asyncio
import queue
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator, Dict

from mcp_agent.models.human_input import (
    HumanInputRequestModel,
    HumanInputResponseModel,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class _PendingRequest:
    request: HumanInputRequestModel
    queue: queue.Queue[HumanInputRequestModel]


class HumanInputRuntime:
    """Tracks pending human input prompts and delivers them to listeners."""

    def __init__(self) -> None:
        self._pending: Dict[str, _PendingRequest] = {}
        self._lock = asyncio.Lock()

    async def add_request(
        self, *, request_id: str, prompt: str, metadata: dict[str, str] | None = None
    ) -> HumanInputRequestModel:
        request = HumanInputRequestModel(
            id=request_id,
            created_at=_utc_now(),
            prompt=prompt,
            metadata=metadata or {},
        )
        async with self._lock:
            if request_id in self._pending:
                raise ValueError("request already exists")
            req_queue: queue.Queue[HumanInputRequestModel] = queue.Queue()
            req_queue.put(request)
            self._pending[request_id] = _PendingRequest(request=request, queue=req_queue)
        return request

    async def subscribe(self) -> AsyncIterator[HumanInputRequestModel]:
        req_queue: queue.Queue[HumanInputRequestModel] = queue.Queue()
        async with self._lock:
            for pending in self._pending.values():
                req_queue.put(pending.request)
        while True:
            request = await asyncio.to_thread(req_queue.get)
            yield request

    async def respond(self, payload: HumanInputResponseModel) -> bool:
        async with self._lock:
            pending = self._pending.pop(payload.id, None)
        return pending is not None

    async def export_pending(self) -> list[HumanInputRequestModel]:
        async with self._lock:
            return [pending.request for pending in self._pending.values()]
