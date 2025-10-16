"""Compatibility re-export of agent specification models."""

from mcp import types as _types

AgentSpecEnvelope = _types.AgentSpecEnvelope
AgentSpecListResponse = _types.AgentSpecListResponse
AgentSpecPatch = _types.AgentSpecPatch
AgentSpecPayload = _types.AgentSpecPayload

__all__ = [
    "AgentSpecEnvelope",
    "AgentSpecListResponse",
    "AgentSpecPatch",
    "AgentSpecPayload",
]
