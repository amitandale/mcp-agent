"""Concrete adapter for the GitHub MCP server."""

from __future__ import annotations

from typing import Any, Dict

from pydantic import Field

from .base import BaseAdapter, StrictModel


class GithubWellKnown(StrictModel):
    name: str
    version: str
    capabilities: Dict[str, Any] = Field(default_factory=dict)


class GithubMCPAdapter(BaseAdapter):
    def __init__(self, base_url: str, *, client=None) -> None:
        super().__init__("github-mcp-server", base_url, client=client)

    async def describe(self) -> GithubWellKnown:
        return await self._request_json("GET", "/.well-known/mcp", response_model=GithubWellKnown)

