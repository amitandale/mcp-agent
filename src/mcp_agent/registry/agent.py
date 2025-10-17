"""Runtime agent registry supporting CRUD operations for specs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import yaml

from mcp_agent.agents.agent_spec import AgentSpec


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class AgentRecord:
    """Internal representation for stored agent specifications."""

    id: str
    spec: AgentSpec
    created_at: datetime
    updated_at: datetime

    def copy(self) -> "AgentRecord":
        return AgentRecord(
            id=self.id,
            spec=AgentSpec.model_validate(self.spec.model_dump(mode="python")),
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class AgentRegistryError(RuntimeError):
    """Base error class for the agent registry."""


class AgentNotFoundError(AgentRegistryError):
    """Raised when an agent id is missing."""


class AgentRegistry:
    """Thread-safe registry managing agent specifications."""

    def __init__(self, *, storage_path: Path | None = None):
        self._storage_path = storage_path
        self._agents: dict[str, AgentRecord] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _normalise_id(agent_id: str) -> str:
        normalised = agent_id.strip()
        if not normalised:
            raise ValueError("Agent identifier cannot be empty")
        return normalised

    async def list_agents(self) -> list[AgentRecord]:
        async with self._lock:
            return [record.copy() for record in self._agents.values()]

    async def get_agent(self, agent_id: str) -> AgentRecord:
        async with self._lock:
            key = self._normalise_id(agent_id)
            record = self._agents.get(key)
            if record is None:
                raise AgentNotFoundError(agent_id)
            return record.copy()

    async def create_agent(self, *, agent_id: str | None, spec: AgentSpec) -> AgentRecord:
        async with self._lock:
            key = self._normalise_id(agent_id or spec.name)
            if key in self._agents:
                raise AgentRegistryError(f"Agent '{key}' already exists")
            now = _utc_now()
            record = AgentRecord(id=key, spec=spec, created_at=now, updated_at=now)
            self._agents[key] = record
            await self._persist_locked()
            return record.copy()

    async def update_agent(self, agent_id: str, spec: AgentSpec) -> AgentRecord:
        async with self._lock:
            key = self._normalise_id(agent_id)
            record = self._agents.get(key)
            if record is None:
                raise AgentNotFoundError(agent_id)
            updated = AgentRecord(
                id=record.id,
                spec=spec,
                created_at=record.created_at,
                updated_at=_utc_now(),
            )
            self._agents[key] = updated
            await self._persist_locked()
            return updated.copy()

    async def patch_agent(
        self,
        agent_id: str,
        *,
        name: str | None = None,
        instruction: str | None = None,
        server_names: Iterable[str] | None = None,
        connection_persistence: bool | None = None,
        extra: dict[str, object] | None = None,
    ) -> AgentRecord:
        async with self._lock:
            key = self._normalise_id(agent_id)
            record = self._agents.get(key)
            if record is None:
                raise AgentNotFoundError(agent_id)
            payload = record.spec.model_dump(mode="python")
            if name is not None:
                payload["name"] = name
            if instruction is not None:
                payload["instruction"] = instruction
            if server_names is not None:
                payload["server_names"] = list(server_names)
            if connection_persistence is not None:
                payload["connection_persistence"] = connection_persistence
            if extra:
                payload.update(extra)
            spec = AgentSpec.model_validate(payload)
            updated = AgentRecord(
                id=record.id,
                spec=spec,
                created_at=record.created_at,
                updated_at=_utc_now(),
            )
            self._agents[key] = updated
            await self._persist_locked()
            return updated.copy()

    async def delete_agent(self, agent_id: str) -> None:
        async with self._lock:
            key = self._normalise_id(agent_id)
            if key not in self._agents:
                raise AgentNotFoundError(agent_id)
            self._agents.pop(key)
            await self._persist_locked()

    async def replace_all(self, specs: dict[str, AgentSpec]) -> None:
        async with self._lock:
            now = _utc_now()
            self._agents = {
                self._normalise_id(key): AgentRecord(
                    id=self._normalise_id(key),
                    spec=value,
                    created_at=now,
                    updated_at=now,
                )
                for key, value in specs.items()
            }
            await self._persist_locked()

    async def load_from_disk(self) -> None:
        if self._storage_path is None:
            return
        path = self._storage_path
        if not path.exists():
            return
        async with self._lock:
            with path.open("r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
            specs_data = data.get("agents") if isinstance(data, dict) else data
            specs: dict[str, AgentSpec] = {}
            if isinstance(specs_data, list):
                for obj in specs_data:
                    if isinstance(obj, dict):
                        spec = AgentSpec.model_validate(obj)
                        specs[spec.name] = spec
            elif isinstance(specs_data, dict):
                for key, value in specs_data.items():
                    if isinstance(value, dict):
                        specs[str(key)] = AgentSpec.model_validate(value)
            now = _utc_now()
            self._agents = {
                self._normalise_id(key): AgentRecord(
                    id=self._normalise_id(key),
                    spec=spec,
                    created_at=now,
                    updated_at=now,
                )
                for key, spec in specs.items()
            }

    async def export_yaml(self) -> str:
        async with self._lock:
            agents = [record.spec.model_dump(mode="python") for record in self._agents.values()]
        payload = {"agents": agents}
        return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)

    async def _persist_locked(self) -> None:
        if self._storage_path is None:
            return
        tmp_path = self._storage_path.with_suffix(".tmp")
        agents = [record.spec.model_dump(mode="python") for record in self._agents.values()]
        payload = {"agents": agents}
        text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
        with tmp_path.open("w", encoding="utf-8") as handle:
            handle.write(text)
        tmp_path.replace(self._storage_path)
