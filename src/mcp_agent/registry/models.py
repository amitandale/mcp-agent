"""Compatibility re-export of tool registry models."""

from mcp import types as _types

ToolItem = _types.ToolItem
ToolProbeResult = _types.ToolProbeResult
ToolSource = _types.ToolSource
ToolsResponse = _types.ToolsResponse

__all__ = ["ToolItem", "ToolProbeResult", "ToolSource", "ToolsResponse"]
