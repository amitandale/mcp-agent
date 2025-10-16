"""Legacy shim that lazily re-exports agent administration models.

The canonical definitions live in :mod:`mcp.types`. Importing them lazily keeps
module loading acyclic so test discovery does not deadlock when the shims are
imported at the same time as :mod:`mcp.types`.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import TYPE_CHECKING

__all__ = [
    "AgentSpecEnvelope",
    "AgentSpecListResponse",
    "AgentSpecPatch",
    "AgentSpecPayload",
]

if TYPE_CHECKING:  # pragma: no cover - used for static analysis only
    from mcp.types import (  # noqa: F401 - re-exported via __getattr__
        AgentSpecEnvelope as AgentSpecEnvelope,
        AgentSpecListResponse as AgentSpecListResponse,
        AgentSpecPatch as AgentSpecPatch,
        AgentSpecPayload as AgentSpecPayload,
    )


_types_module: ModuleType | None = None


def _load_types() -> ModuleType:
    global _types_module
    if _types_module is None:
        _types_module = import_module("mcp.types")
    return _types_module


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(name)
    return getattr(_load_types(), name)


def __dir__() -> list[str]:
    return sorted(__all__)
