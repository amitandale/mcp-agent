"""Legacy shim lazily re-exporting human-input models and constants."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import TYPE_CHECKING

__all__ = [
    "HUMAN_INPUT_SIGNAL_NAME",
    "HumanInputCallback",
    "HumanInputRequest",
    "HumanInputResponse",
]

if TYPE_CHECKING:  # pragma: no cover - static analysis only
    from mcp.types import (  # noqa: F401 - resolved lazily via __getattr__
        HUMAN_INPUT_SIGNAL_NAME as HUMAN_INPUT_SIGNAL_NAME,
        HumanInputCallback as HumanInputCallback,
        HumanInputRequest as HumanInputRequest,
        HumanInputResponse as HumanInputResponse,
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
