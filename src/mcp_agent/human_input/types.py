"""Compatibility re-export of human-input integration models."""

from mcp import types as _types

HUMAN_INPUT_SIGNAL_NAME = _types.HUMAN_INPUT_SIGNAL_NAME
HumanInputCallback = _types.HumanInputCallback
HumanInputRequest = _types.HumanInputRequest
HumanInputResponse = _types.HumanInputResponse

__all__ = [
    "HUMAN_INPUT_SIGNAL_NAME",
    "HumanInputCallback",
    "HumanInputRequest",
    "HumanInputResponse",
]
