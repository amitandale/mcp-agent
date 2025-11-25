"""Grok CLI adapter for mcp-agent.

This module mirrors the Grok CLI surface area, exposing every documented
command, flag, and execution mode with async-friendly helpers. The adapter
supports interactive and headless prompts, MCP server management, configurable
API keys and endpoints, and streaming output for realtime feedback.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Awaitable, Dict, Iterable, List, Optional


@dataclass
class GrokStreamEvent:
    """Represents a single streamed event from the Grok CLI."""

    kind: str
    text: str
    parsed: Any | None = None


@dataclass
class GrokCommandResult:
    """Aggregated result for a Grok CLI invocation."""

    command: List[str]
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    success: bool = False
    error: str | None = None


@dataclass
class GrokStreamingResult:
    """Handle returned when a Grok command is streamed."""

    command: List[str]
    stream: AsyncGenerator[GrokStreamEvent, None]
    completion: Awaitable[GrokCommandResult]


class GrokTool:
    """Async adapter for invoking the Grok CLI."""

    def __init__(
        self,
        *,
        binary: str = "grok",
        workspace: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        default_timeout: float | None = 300.0,
        env: Optional[Dict[str, str]] = None,
    ) -> None:
        self.binary = binary
        self.workspace = workspace
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.default_timeout = default_timeout
        self.env = env or {}

    async def run(
        self,
        *,
        prompt: str | None = None,
        directory: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        max_tool_rounds: int | None = None,
        stream: bool = False,
        prefer_short_flags: bool = False,
        extra_args: Optional[List[str]] = None,
        timeout: float | None = None,
        morph_fast_apply: bool = False,
    ) -> GrokCommandResult | GrokStreamingResult:
        """Run Grok in interactive or headless prompt mode."""

        args = self._base_args(
            directory=directory,
            api_key=api_key,
            base_url=base_url,
            model=model,
            max_tool_rounds=max_tool_rounds,
            prompt=prompt,
            prefer_short_flags=prefer_short_flags,
        )

        if extra_args:
            args.extend(extra_args)

        env_overrides: Dict[str, str] = {}
        if morph_fast_apply:
            env_overrides["MORPH_FAST_APPLY"] = "1"

        return await self._run_command(
            args,
            stream=stream,
            timeout=timeout,
            parse_json_stream=False,
            require_api_key=True,
            env_overrides=env_overrides,
        )

    async def version(self) -> GrokCommandResult:
        """Return Grok CLI version."""

        return await self._run_command(
            [self.binary, "--version"],
            stream=False,
            timeout=None,
            require_api_key=False,
        )

    async def help(self) -> GrokCommandResult:
        """Return Grok CLI help output."""

        return await self._run_command(
            [self.binary, "--help"],
            stream=False,
            timeout=None,
            require_api_key=False,
        )

    async def mcp_add(
        self,
        name: str,
        *,
        transport: str,
        command: str | None = None,
        url: str | None = None,
        args: Iterable[str] | None = None,
        directory: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        prefer_short_flags: bool = False,
        extra_args: Optional[List[str]] = None,
        timeout: float | None = None,
    ) -> GrokCommandResult:
        """Add an MCP server using ``grok mcp add``."""

        cli_args = self._base_args(
            directory=directory,
            api_key=api_key,
            base_url=base_url,
            model=model,
            prefer_short_flags=prefer_short_flags,
        )
        cli_args.extend(["mcp", "add", name])
        cli_args.extend(["--transport", transport])
        if command:
            cli_args.extend(["--command", command])
        if url:
            cli_args.extend(["--url", url])
        if args:
            for arg in args:
                cli_args.extend(["--args", arg])
        if extra_args:
            cli_args.extend(extra_args)

        return await self._run_command(
            cli_args,
            stream=False,
            timeout=timeout,
            require_api_key=True,
        )

    async def mcp_add_json(
        self,
        path: str,
        *,
        directory: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        prefer_short_flags: bool = False,
        timeout: float | None = None,
    ) -> GrokCommandResult:
        """Add MCP servers using a JSON config file via ``grok mcp add-json``."""

        cli_args = self._base_args(
            directory=directory,
            api_key=api_key,
            base_url=base_url,
            model=model,
            prefer_short_flags=prefer_short_flags,
        )
        cli_args.extend(["mcp", "add-json", path])

        return await self._run_command(
            cli_args,
            stream=False,
            timeout=timeout,
            require_api_key=True,
        )

    async def mcp_list(
        self,
        *,
        directory: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        prefer_short_flags: bool = False,
        timeout: float | None = None,
    ) -> GrokCommandResult:
        """List MCP servers using ``grok mcp list``."""

        cli_args = self._base_args(
            directory=directory,
            api_key=api_key,
            base_url=base_url,
            model=model,
            prefer_short_flags=prefer_short_flags,
        )
        cli_args.extend(["mcp", "list"])

        return await self._run_command(
            cli_args,
            stream=False,
            timeout=timeout,
            require_api_key=True,
        )

    async def mcp_test(
        self,
        name: str,
        *,
        directory: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        prefer_short_flags: bool = False,
        timeout: float | None = None,
    ) -> GrokCommandResult:
        """Test an MCP server via ``grok mcp test``."""

        cli_args = self._base_args(
            directory=directory,
            api_key=api_key,
            base_url=base_url,
            model=model,
            prefer_short_flags=prefer_short_flags,
        )
        cli_args.extend(["mcp", "test", name])

        return await self._run_command(
            cli_args,
            stream=False,
            timeout=timeout,
            require_api_key=True,
        )

    async def mcp_remove(
        self,
        name: str,
        *,
        directory: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        prefer_short_flags: bool = False,
        timeout: float | None = None,
    ) -> GrokCommandResult:
        """Remove an MCP server via ``grok mcp remove``."""

        cli_args = self._base_args(
            directory=directory,
            api_key=api_key,
            base_url=base_url,
            model=model,
            prefer_short_flags=prefer_short_flags,
        )
        cli_args.extend(["mcp", "remove", name])

        return await self._run_command(
            cli_args,
            stream=False,
            timeout=timeout,
            require_api_key=True,
        )

    async def run_raw(
        self,
        *args: str,
        stream: bool = False,
        timeout: float | None = None,
        parse_json_stream: bool = False,
        require_api_key: bool = False,
        env_overrides: Optional[Dict[str, str]] = None,
    ) -> GrokCommandResult | GrokStreamingResult:
        """Execute an arbitrary Grok CLI command."""

        full_args = [self.binary, *args]
        return await self._run_command(
            full_args,
            stream=stream,
            timeout=timeout,
            parse_json_stream=parse_json_stream,
            require_api_key=require_api_key,
            env_overrides=env_overrides or {},
        )

    def _base_args(
        self,
        *,
        directory: str | None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        max_tool_rounds: int | None = None,
        prompt: str | None = None,
        prefer_short_flags: bool = False,
    ) -> List[str]:
        args = [self.binary]
        if directory or self.workspace:
            args.extend(
                [self._flag("-d", "--directory", prefer_short_flags), directory or self.workspace]
            )
        api_key_value = api_key or self.api_key
        if api_key_value:
            args.extend([self._flag("-k", "--api-key", prefer_short_flags), api_key_value])
        base_url_value = base_url or self.base_url
        if base_url_value:
            args.extend([self._flag("-u", "--base-url", prefer_short_flags), base_url_value])
        model_value = model or self.model
        if model_value:
            args.extend([self._flag("-m", "--model", prefer_short_flags), model_value])
        if prompt:
            args.extend([self._flag("-p", "--prompt", prefer_short_flags), prompt])
        if max_tool_rounds is not None:
            args.extend(["--max-tool-rounds", str(max_tool_rounds)])
        return args

    @staticmethod
    def _flag(short: str, long: str, prefer_short: bool) -> str:
        return short if prefer_short else long

    def _resolve_api_key(self, api_key: str | None) -> str:
        resolved = (
            api_key
            or self.api_key
            or self.env.get("GROK_API_KEY")
            or os.environ.get("GROK_API_KEY")
        )
        if not resolved:
            raise ValueError(
                "Grok API key is required; supply api_key or set GROK_API_KEY."
            )
        return resolved

    async def _run_command(
        self,
        args: List[str],
        *,
        stream: bool,
        timeout: float | None,
        parse_json_stream: bool = False,
        require_api_key: bool,
        env_overrides: Optional[Dict[str, str]] = None,
    ) -> GrokCommandResult | GrokStreamingResult:
        resolved_timeout = self.default_timeout if timeout is None else timeout
        env_overrides = env_overrides or {}

        env = os.environ.copy()
        if self.env:
            env.update(self.env)
        env.update(env_overrides)

        if require_api_key:
            env["GROK_API_KEY"] = self._resolve_api_key(env.get("GROK_API_KEY"))

        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError:
            return GrokCommandResult(
                command=args,
                success=False,
                error=f"Grok CLI binary not found: {args[0]}",
                stderr="binary not found",
            )
        except Exception as exc:  # pragma: no cover - safety net
            return GrokCommandResult(
                command=args,
                success=False,
                error=f"Failed to start Grok CLI: {exc}",
            )

        if stream:
            completion_future: asyncio.Future[GrokCommandResult] = (
                asyncio.get_event_loop().create_future()
            )
            return GrokStreamingResult(
                command=args,
                stream=self._stream_process(
                    process,
                    completion_future,
                    resolved_timeout,
                    command=args,
                    parse_json_stream=parse_json_stream,
                ),
                completion=completion_future,
            )

        stdout, stderr = await self._communicate_with_timeout(process, resolved_timeout)
        exit_code = process.returncode
        success = exit_code == 0
        return GrokCommandResult(
            command=args,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            success=success,
            error=None if success else stderr or "Command failed",
        )

    async def _communicate_with_timeout(
        self, process: asyncio.subprocess.Process, timeout: float | None
    ) -> tuple[str, str]:
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return "", "Process timed out"
        return (stdout.decode().strip(), stderr.decode().strip())

    async def _stream_process(
        self,
        process: asyncio.subprocess.Process,
        completion_future: asyncio.Future[GrokCommandResult],
        timeout: float | None,
        *,
        command: List[str],
        parse_json_stream: bool,
    ) -> AsyncGenerator[GrokStreamEvent, None]:
        queue: asyncio.Queue[GrokStreamEvent | None] = asyncio.Queue()
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []

        async def pump(stream: asyncio.StreamReader | None, kind: str, collector: list[str]):
            assert stream is not None
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode(errors="replace").rstrip("\n")
                parsed: Any | None = None
                if parse_json_stream and kind == "stdout":
                    try:
                        parsed = json.loads(text)
                    except json.JSONDecodeError:
                        parsed = None
                collector.append(text)
                await queue.put(GrokStreamEvent(kind=kind, text=text, parsed=parsed))

        stdout_task = asyncio.create_task(pump(process.stdout, "stdout", stdout_chunks))
        stderr_task = asyncio.create_task(pump(process.stderr, "stderr", stderr_chunks))

        try:
            try:
                await asyncio.wait_for(process.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                await queue.put(
                    GrokStreamEvent(kind="stderr", text="Process timed out", parsed=None)
                )
            await stdout_task
            await stderr_task
        finally:
            await queue.put(None)

        result = GrokCommandResult(
            command=command,
            stdout="\n".join(stdout_chunks),
            stderr="\n".join(stderr_chunks),
            exit_code=process.returncode,
            success=process.returncode == 0,
            error=None if process.returncode == 0 else "Command failed",
        )
        if not completion_future.done():
            completion_future.set_result(result)

        while True:
            event = await queue.get()
            if event is None:
                break
            yield event
