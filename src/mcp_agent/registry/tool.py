"""Runtime registry for managing tool enablement and assignments."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Iterable

from mcp_agent.logging.logger import get_logger

from .models import ToolItem
from .store import ToolRegistryStore, store


logger = get_logger(__name__)


class ToolRuntimeRegistryError(RuntimeError):
    """Base error for runtime registry operations."""


class ToolNotFoundError(ToolRuntimeRegistryError):
    """Raised when a tool id is not present in the registry."""


class ToolRuntimeRegistry:
    """Provides runtime mutations on top of :class:`ToolRegistryStore`."""

    def __init__(self, *, backing_store: ToolRegistryStore | None = None):
        self._store = backing_store or store
        self._overrides: dict[str, bool] = {}
        self._assignments: dict[str, set[str]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def list_tools(self) -> tuple[str, list[ToolItem]]:
        snapshot = await self._store.get_snapshot()
        return snapshot.registry_hash, list(snapshot.items)

    async def snapshot(self) -> tuple[str, list[tuple[ToolItem, bool]]]:
        snapshot = await self._store.get_snapshot()
        async with self._lock:
            overrides = dict(self._overrides)
        items: list[tuple[ToolItem, bool]] = []
        for item in snapshot.items:
            enabled = overrides.get(item.id, True)
            items.append((item, enabled))
        return snapshot.registry_hash, items

    async def is_enabled(self, tool_id: str) -> bool:
        async with self._lock:
            value = self._overrides.get(tool_id)
        if value is None:
            return True
        return value

    async def apply_updates(self, updates: Iterable[tuple[str, bool]]) -> None:
        async with self._lock:
            available = {item.id for item in (await self._store.get_snapshot()).items}
            for tool_id, enabled in updates:
                if tool_id not in available:
                    raise ToolNotFoundError(tool_id)
                self._overrides[tool_id] = bool(enabled)

    async def reload(self) -> None:
        await self._store.refresh(force=True)

    async def assign_tools(self, agent_id: str, tools: Iterable[str]) -> None:
        snapshot = await self._store.get_snapshot()
        available = {item.id for item in snapshot.items}
        unknown = [tool for tool in tools if tool not in available]
        if unknown:
            raise ToolNotFoundError(unknown[0])
        async with self._lock:
            self._assignments[agent_id] = set(tools)

    async def get_assignments(self, agent_id: str) -> set[str]:
        async with self._lock:
            return set(self._assignments.get(agent_id, set()))

    async def export_assignments(self) -> dict[str, list[str]]:
        async with self._lock:
            return {key: sorted(value) for key, value in self._assignments.items()}

    async def enabled_items(self) -> list[ToolItem]:
        snapshot = await self._store.get_snapshot()
        async with self._lock:
            overrides = dict(self._overrides)
        items: list[ToolItem] = []
        for item in snapshot.items:
            enabled = overrides.get(item.id, True)
            if enabled:
                items.append(item)
        return items
