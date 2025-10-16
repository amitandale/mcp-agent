"""Compatibility shim exposing :class:`~mcp.types.AgentSpec` without eager imports."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import TYPE_CHECKING

__all__ = ["AgentSpec"]

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from mcp.types import AgentSpec as AgentSpec


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
