"""Legacy shims for agent administration models.

The authoritative definitions live in :mod:`mcp.types`.  This module re-exports
the public classes so existing imports continue to work without duplication.
"""

from mcp.types import (
    AgentSpecEnvelope,
    AgentSpecListResponse,
    AgentSpecPatch,
    AgentSpecPayload,
)

__all__ = [
    "AgentSpecEnvelope",
    "AgentSpecListResponse",
    "AgentSpecPatch",
    "AgentSpecPayload",
]
