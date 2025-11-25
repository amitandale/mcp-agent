"""Google Antigravity CLI adapter for mcp-agent.

This module exposes an async-friendly wrapper around the Google Antigravity
CLI, covering every officially documented subcommand while mirroring the
patterns used by the other adapters inside ``src/mcp_agent/tools``. The
adapter centralizes workspace/project handling, optional streaming, JSON
parsing, MCP integration commands, and structured error reporting so workflows
can orchestrate Antigravity without shelling out manually.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Awaitable, Dict, List, Optional


@dataclass
class AntigravityStreamEvent:
    """A single streamed Antigravity CLI event."""

    kind: str
    text: str
    parsed: Any | None = None


@dataclass
class AntigravityCommandResult:
    """Aggregated result for a completed Antigravity CLI invocation."""

    command: List[str]
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    success: bool = False
    error: str | None = None


@dataclass
class AntigravityStreamingResult:
    """Handle returned when a command is streamed."""

    command: List[str]
    stream: AsyncGenerator[AntigravityStreamEvent, None]
    completion: Awaitable[AntigravityCommandResult]


class AntigravityTool:
    """Async adapter for invoking the Google Antigravity CLI.

    The public methods map one-to-one with the CLI surface area, including
    ``command``, ``plan``, ``review``, ``refactor``, ``test``, ``doc``,
    ``agent``, and ``mcp`` operations. All flags documented by the CLI are
    expressed as keyword arguments, and every method supports optional
    streaming and JSON parsing where applicable.
    """

    def __init__(
        self,
        *,
        binary: str = "antigravity",
        workspace: str | None = None,
        project: str | None = None,
        default_timeout: float | None = 300.0,
        env: Optional[Dict[str, str]] = None,
        config_path: str | None = None,
    ) -> None:
        self.binary = binary
        self.workspace = workspace
        self.project = project
        self.default_timeout = default_timeout
        self.env = env or {}
        self.config_path = config_path or (
            os.path.join(workspace, ".antigravity.json") if workspace else None
        )
        self.config = self._load_manifest(self.config_path)

    async def command(
        self,
        prompt: str,
        *,
        agent: str | None = None,
        workspace: str | None = None,
        project: str | None = None,
        stream: bool = False,
        json_output: bool = False,
        params_file: str | None = None,
        timeout: float | None = None,
        extra_args: Optional[List[str]] = None,
    ) -> AntigravityCommandResult | AntigravityStreamingResult:
        """Run ``antigravity command`` with the given natural language prompt."""

        args = self._base_args(workspace=workspace, project=project)
        args.append("command")
        if agent:
            args.extend(["--agent", agent])
        if params_file:
            args.extend(["--params", params_file])
        if json_output:
            args.append("--json")
        if stream:
            args.append("--stream")
        args.append(prompt)
        if extra_args:
            args.extend(extra_args)
        return await self._run_command(
            args, stream=stream, timeout=timeout, parse_json_stream=json_output
        )

    async def plan(
        self,
        description: str,
        *,
        workspace: str | None = None,
        out: str | None = None,
        stream: bool = False,
        timeout: float | None = None,
    ) -> AntigravityCommandResult | AntigravityStreamingResult:
        """Generate a plan via ``antigravity plan``."""

        args = self._base_args(workspace=workspace)
        args.append("plan")
        if stream:
            args.append("--stream")
        if out:
            args.extend(["--out", out])
        args.append(description)
        return await self._run_command(args, stream=stream, timeout=timeout)

    async def review(
        self,
        *,
        file: str | None = None,
        workspace: str | None = None,
        stream: bool = False,
        timeout: float | None = None,
    ) -> AntigravityCommandResult | AntigravityStreamingResult:
        """Run ``antigravity review`` with optional streaming."""

        args = self._base_args(workspace=workspace)
        args.append("review")
        if file:
            args.extend(["--file", file])
        if stream:
            args.append("--stream")
        return await self._run_command(args, stream=stream, timeout=timeout)

    async def refactor(
        self,
        *,
        scope: str | None = None,
        workspace: str | None = None,
        stream: bool = False,
        timeout: float | None = None,
    ) -> AntigravityCommandResult | AntigravityStreamingResult:
        """Execute ``antigravity refactor`` with an optional scope."""

        args = self._base_args(workspace=workspace)
        args.append("refactor")
        if scope:
            args.extend(["--scope", scope])
        if stream:
            args.append("--stream")
        return await self._run_command(args, stream=stream, timeout=timeout)

    async def test(
        self,
        *,
        target: str | None = None,
        workspace: str | None = None,
        stream: bool = False,
        timeout: float | None = None,
    ) -> AntigravityCommandResult | AntigravityStreamingResult:
        """Run ``antigravity test``."""

        args = self._base_args(workspace=workspace)
        args.append("test")
        if target:
            args.extend(["--target", target])
        if stream:
            args.append("--stream")
        return await self._run_command(args, stream=stream, timeout=timeout)

    async def doc(
        self,
        *,
        file: str | None = None,
        format: str | None = None,
        workspace: str | None = None,
        stream: bool = False,
        timeout: float | None = None,
    ) -> AntigravityCommandResult | AntigravityStreamingResult:
        """Run ``antigravity doc`` to generate documentation."""

        args = self._base_args(workspace=workspace)
        args.append("doc")
        if file:
            args.extend(["--file", file])
        if format:
            args.extend(["--format", format])
        if stream:
            args.append("--stream")
        return await self._run_command(args, stream=stream, timeout=timeout)

    async def agent(
        self,
        *,
        list_agents: bool = False,
        call: str | None = None,
        args_json: Dict[str, Any] | None = None,
        stream: bool = False,
        workspace: str | None = None,
        timeout: float | None = None,
    ) -> AntigravityCommandResult | AntigravityStreamingResult:
        """Interact with Antigravity agent registry."""

        args = self._base_args(workspace=workspace)
        args.append("agent")
        if list_agents:
            args.append("--list")
        if call:
            args.extend(["--call", call])
        if args_json is not None:
            args.extend(["--args", json.dumps(args_json)])
        if stream:
            args.append("--stream")
        return await self._run_command(
            args, stream=stream, timeout=timeout, parse_json_stream=stream
        )

    async def mcp_register(
        self,
        name: str,
        *,
        config: str | None = None,
        stream: bool = False,
        workspace: str | None = None,
        timeout: float | None = None,
    ) -> AntigravityCommandResult | AntigravityStreamingResult:
        """Register an MCP server using ``antigravity mcp``."""

        args = self._mcp_base(workspace)
        args.extend(["--register", name])
        if config:
            args.extend(["--config", config])
        if stream:
            args.append("--stream")
        return await self._run_command(args, stream=stream, timeout=timeout)

    async def mcp_unregister(
        self,
        name: str,
        *,
        workspace: str | None = None,
        stream: bool = False,
        timeout: float | None = None,
    ) -> AntigravityCommandResult | AntigravityStreamingResult:
        """Unregister an MCP server."""

        args = self._mcp_base(workspace)
        args.extend(["--unregister", name])
        if stream:
            args.append("--stream")
        return await self._run_command(args, stream=stream, timeout=timeout)

    async def mcp_list(
        self,
        *,
        workspace: str | None = None,
        stream: bool = False,
        timeout: float | None = None,
    ) -> AntigravityCommandResult | AntigravityStreamingResult:
        """List configured MCP servers."""

        args = self._mcp_base(workspace)
        args.append("--list")
        if stream:
            args.append("--stream")
        return await self._run_command(
            args, stream=stream, timeout=timeout, parse_json_stream=stream
        )

    async def mcp_invoke(
        self,
        tool: str,
        *,
        params: Dict[str, Any] | None = None,
        config: str | None = None,
        workspace: str | None = None,
        stream: bool = False,
        timeout: float | None = None,
    ) -> AntigravityCommandResult | AntigravityStreamingResult:
        """Invoke an MCP tool via ``antigravity mcp --invoke``."""

        args = self._mcp_base(workspace)
        args.extend(["--invoke", tool])
        if params is not None:
            args.extend(["--args", json.dumps(params)])
        if config:
            args.extend(["--config", config])
        if stream:
            args.append("--stream")
        return await self._run_command(
            args, stream=stream, timeout=timeout, parse_json_stream=stream
        )

    async def run_raw(
        self,
        *args: str,
        stream: bool = False,
        timeout: float | None = None,
        parse_json_stream: bool = False,
    ) -> AntigravityCommandResult | AntigravityStreamingResult:
        """Execute an arbitrary Antigravity CLI command."""

        full_args = [self.binary, *args]
        return await self._run_command(
            full_args, stream=stream, timeout=timeout, parse_json_stream=parse_json_stream
        )

    def _base_args(
        self, *, workspace: str | None = None, project: str | None = None
    ) -> List[str]:
        args = [self.binary]
        effective_workspace = workspace or self.workspace
        if effective_workspace:
            args.extend(["--workspace", effective_workspace])
        effective_project = project or self.project
        if effective_project:
            args.extend(["--project", effective_project])
        if self.config_path and os.path.exists(self.config_path):
            args.extend(["--config", self.config_path])
        return args

    def _mcp_base(self, workspace: str | None) -> List[str]:
        args = self._base_args(workspace=workspace)
        args.append("mcp")
        return args

    def _load_manifest(self, path: str | None) -> Dict[str, Any]:
        if not path or not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, OSError):  # pragma: no cover - defensive
            return {}

    async def _run_command(
        self,
        args: List[str],
        *,
        stream: bool,
        timeout: float | None,
        parse_json_stream: bool = False,
    ) -> AntigravityCommandResult | AntigravityStreamingResult:
        resolved_timeout = self.default_timeout if timeout is None else timeout

        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
                env=self.env or None,
            )
        except FileNotFoundError:
            return AntigravityCommandResult(
                command=args,
                success=False,
                error=f"Antigravity CLI binary not found: {args[0]}",
                stderr="binary not found",
            )
        except Exception as exc:  # pragma: no cover - safety net
            return AntigravityCommandResult(
                command=args,
                success=False,
                error=f"Failed to start Antigravity CLI: {exc}",
            )

        if stream:
            completion_future: asyncio.Future[AntigravityCommandResult] = (
                asyncio.get_event_loop().create_future()
            )
            return AntigravityStreamingResult(
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
        error_message = None
        if exit_code is None:
            error_message = "Process did not exit cleanly"
        elif exit_code != 0:
            error_message = f"Antigravity CLI exited with code {exit_code}"

        return AntigravityCommandResult(
            command=args,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            success=success,
            error=error_message,
        )

    async def _stream_process(
        self,
        process: asyncio.subprocess.Process,
        completion_future: asyncio.Future[AntigravityCommandResult],
        timeout: float | None,
        *,
        command: List[str],
        parse_json_stream: bool,
    ) -> AsyncGenerator[AntigravityStreamEvent, None]:
        queue: asyncio.Queue[AntigravityStreamEvent | None] = asyncio.Queue()
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []

        async def pump(stream: asyncio.StreamReader, kind: str, collector: list[str]):
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode(errors="replace").rstrip("\n")
                parsed = None
                if parse_json_stream and kind == "stdout":
                    try:
                        parsed = json.loads(text)
                    except json.JSONDecodeError:
                        parsed = None
                collector.append(text)
                await queue.put(AntigravityStreamEvent(kind=kind, text=text, parsed=parsed))

        stdout_task = asyncio.create_task(pump(process.stdout, "stdout", stdout_chunks))
        stderr_task = asyncio.create_task(pump(process.stderr, "stderr", stderr_chunks))

        try:
            try:
                await asyncio.wait_for(process.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                await queue.put(
                    AntigravityStreamEvent(
                        kind="stderr",
                        text="Antigravity CLI timed out",
                        parsed=None,
                    )
                )
            await stdout_task
            await stderr_task
        finally:
            await queue.put(None)

        result = AntigravityCommandResult(
            command=command,
            stdout="\n".join(stdout_chunks),
            stderr="\n".join(stderr_chunks),
            exit_code=process.returncode,
            success=process.returncode == 0,
            error=None if process.returncode == 0 else f"Antigravity CLI exited with code {process.returncode}",
        )
        if not completion_future.done():
            completion_future.set_result(result)

        while True:
            event = await queue.get()
            if event is None:
                break
            yield event

    async def _communicate_with_timeout(
        self, process: asyncio.subprocess.Process, timeout: float | None
    ) -> tuple[str, str]:
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            stdout, stderr = await process.communicate()
            stderr += b"\nAntigravity CLI timed out"
        stdout_text = stdout.decode(errors="replace") if stdout is not None else ""
        stderr_text = stderr.decode(errors="replace") if stderr is not None else ""
        return stdout_text, stderr_text

