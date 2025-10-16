"""Compat layer exposing MCP protocol types and client/server helpers."""

from __future__ import annotations

from importlib import import_module, metadata
from pathlib import Path
from typing import Iterable

from . import types as _types

types = _types

__all__: list[str] = ["types"]


def _export_from_types(names: Iterable[str]) -> None:
    for name in names:
        if hasattr(_types, name):
            globals()[name] = getattr(_types, name)
            __all__.append(name)


_export_from_types(
    [
        "CallToolRequest",
        "ClientCapabilities",
        "ClientNotification",
        "ClientRequest",
        "ClientResult",
        "CompleteRequest",
        "CreateMessageRequest",
        "CreateMessageResult",
        "ErrorData",
        "GetPromptRequest",
        "GetPromptResult",
        "Implementation",
        "IncludeContext",
        "InitializeRequest",
        "InitializeResult",
        "InitializedNotification",
        "JSONRPCError",
        "JSONRPCRequest",
        "JSONRPCResponse",
        "ListPromptsRequest",
        "ListPromptsResult",
        "ListResourcesRequest",
        "ListResourcesResult",
        "ListToolsResult",
        "LoggingLevel",
        "LoggingMessageNotification",
        "Notification",
        "PingRequest",
        "ProgressNotification",
        "PromptsCapability",
        "ReadResourceRequest",
        "ReadResourceResult",
        "Resource",
        "ResourceUpdatedNotification",
        "ResourcesCapability",
        "RootsCapability",
        "SamplingMessage",
        "ServerCapabilities",
        "ServerNotification",
        "ServerRequest",
        "ServerResult",
        "SetLevelRequest",
        "StopReason",
        "SubscribeRequest",
        "Tool",
        "ToolsCapability",
        "UnsubscribeRequest",
    ]
)

SamplingRole = _types.Role
__all__.append("SamplingRole")


def _append_upstream_path() -> Path | None:
    try:  # pragma: no cover - only exercised when upstream package is installed
        dist = metadata.distribution("mcp")
    except metadata.PackageNotFoundError:  # pragma: no cover - offline/CI envs
        return None

    package_dir = Path(dist.locate_file("mcp"))
    if not package_dir.is_dir():
        return None

    upstream_path = str(package_dir)
    if upstream_path not in __path__:
        __path__.append(upstream_path)
    return package_dir


_package_dir = _append_upstream_path()

if _package_dir is not None:
    _UPSTREAM_EXPORTS = {
        "ClientSession": "client.session.ClientSession",
        "ClientSessionGroup": "client.session_group.ClientSessionGroup",
        "StdioServerParameters": "client.stdio.StdioServerParameters",
        "stdio_client": "client.stdio.stdio_client",
        "ServerSession": "server.session.ServerSession",
        "stdio_server": "server.stdio.stdio_server",
        "McpError": "shared.exceptions.McpError",
    }

    for export_name, dotted_path in _UPSTREAM_EXPORTS.items():  # pragma: no cover - requires upstream
        module_name, attr_name = dotted_path.rsplit(".", 1)
        try:
            module = import_module(f".{module_name}", __name__)
        except Exception:  # pragma: no cover - best effort shim
            continue

        try:
            value = getattr(module, attr_name)
        except AttributeError:  # pragma: no cover - defensive
            continue

        globals()[export_name] = value
        __all__.append(export_name)
