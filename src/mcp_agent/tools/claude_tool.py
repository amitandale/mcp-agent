"""Claude Code CLI adapter for mcp-agent.

This module provides an async-friendly wrapper around the Anthropic Claude
Code CLI, mirroring the ergonomics of the existing tool adapters (e.g., Codex
and Antigravity). The adapter offers helpers for the primary Claude commands,
including agent management, git flows, reviews, explanations, testing,
documentation generation, plugin orchestration, and MCP integration. Each
method constructs the appropriate command arguments, applies common defaults
(workspace, shell, debug, confirmation flags), and exposes either aggregated
results or streaming updates.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Awaitable, Dict, Iterable, List, Optional


@dataclass
class ClaudeStreamEvent:
    """Represents a single streamed event from the Claude CLI."""

    kind: str
    text: str
    parsed: Any | None = None


@dataclass
class ClaudeCommandResult:
    """Aggregated result for a Claude CLI invocation."""

    command: List[str]
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    success: bool = False
    error: str | None = None
    session_id: str | None = None


@dataclass
class ClaudeStreamingResult:
    """Handle returned when a Claude command is streamed."""

    command: List[str]
    stream: AsyncGenerator[ClaudeStreamEvent, None]
    completion: Awaitable[ClaudeCommandResult]


class ClaudeTool:
    """Async adapter for invoking the Claude Code CLI."""

    def __init__(
        self,
        *,
        binary: str = "claude",
        workspace: str | None = None,
        shell: str | None = None,
        default_timeout: float | None = 300.0,
        env: Optional[Dict[str, str]] = None,
    ) -> None:
        self.binary = binary
        self.workspace = workspace
        self.shell = shell
        self.default_timeout = default_timeout
        self.env = env or {}

    async def command(
        self,
        prompt: str,
        *,
        stream: bool = False,
        json_output: bool = False,
        debug: bool = False,
        no_confirm: bool = False,
        workspace: str | None = None,
        shell: str | None = None,
        flags: Optional[Dict[str, Any]] = None,
        extra_args: Optional[List[str]] = None,
        timeout: float | None = None,
    ) -> ClaudeCommandResult | ClaudeStreamingResult:
        """Run a free-form Claude command (``claude "<prompt>"``)."""

        args = self._base_args(workspace=workspace, shell=shell)
        args.extend(self._format_common_flags(json_output, debug, no_confirm))
        args.extend(self._format_dynamic_flags(flags))
        args.append(prompt)
        if extra_args:
            args.extend(extra_args)
        return await self._run_command(
            args,
            stream=stream,
            timeout=timeout,
            parse_json_stream=json_output,
        )

    async def agent(
        self,
        name: str,
        task: str,
        *,
        args_json: Dict[str, Any] | None = None,
        plugin: str | None = None,
        stream: bool = False,
        json_output: bool = False,
        workspace: str | None = None,
        shell: str | None = None,
        flags: Optional[Dict[str, Any]] = None,
        extra_args: Optional[List[str]] = None,
        timeout: float | None = None,
    ) -> ClaudeCommandResult | ClaudeStreamingResult:
        """Invoke ``claude agent`` with optional plugin and args."""

        args = self._base_args(workspace=workspace, shell=shell)
        args.append("agent")
        args.extend(self._format_common_flags(json_output, False, False))
        if args_json:
            args.extend(["--args", json.dumps(args_json)])
        if plugin:
            args.extend(["--plugin", plugin])
        args.extend(self._format_dynamic_flags(flags))
        args.extend([name, task])
        if extra_args:
            args.extend(extra_args)
        return await self._run_command(
            args,
            stream=stream,
            timeout=timeout,
            parse_json_stream=json_output,
        )

    async def git(
        self,
        action: str,
        *,
        branch: str | None = None,
        files: Iterable[str] | None = None,
        stream: bool = False,
        json_output: bool = False,
        workspace: str | None = None,
        shell: str | None = None,
        flags: Optional[Dict[str, Any]] = None,
        extra_args: Optional[List[str]] = None,
        timeout: float | None = None,
    ) -> ClaudeCommandResult | ClaudeStreamingResult:
        """Run ``claude git`` for git-aware flows."""

        args = self._base_args(workspace=workspace, shell=shell)
        args.extend(["git", action])
        args.extend(self._format_common_flags(json_output, False, False))
        if branch:
            args.extend(["--branch", branch])
        if files:
            for file in files:
                args.extend(["--files", str(file)])
        args.extend(self._format_dynamic_flags(flags))
        if extra_args:
            args.extend(extra_args)
        return await self._run_command(
            args,
            stream=stream,
            timeout=timeout,
            parse_json_stream=json_output,
        )

    async def review(
        self,
        *,
        file: str | None = None,
        workspace: str | None = None,
        stream: bool = False,
        json_output: bool = False,
        shell: str | None = None,
        flags: Optional[Dict[str, Any]] = None,
        extra_args: Optional[List[str]] = None,
        timeout: float | None = None,
    ) -> ClaudeCommandResult | ClaudeStreamingResult:
        """Run ``claude review`` to analyze code changes."""

        args = self._base_args(workspace=workspace, shell=shell)
        args.append("review")
        args.extend(self._format_common_flags(json_output, False, False))
        if file:
            args.extend(["--file", file])
        args.extend(self._format_dynamic_flags(flags))
        if extra_args:
            args.extend(extra_args)
        return await self._run_command(
            args,
            stream=stream,
            timeout=timeout,
            parse_json_stream=json_output,
        )

    async def explain(
        self,
        *,
        file: str | None = None,
        lines: str | None = None,
        workspace: str | None = None,
        stream: bool = False,
        json_output: bool = False,
        shell: str | None = None,
        flags: Optional[Dict[str, Any]] = None,
        extra_args: Optional[List[str]] = None,
        timeout: float | None = None,
    ) -> ClaudeCommandResult | ClaudeStreamingResult:
        """Run ``claude explain`` on a file or line range."""

        args = self._base_args(workspace=workspace, shell=shell)
        args.append("explain")
        args.extend(self._format_common_flags(json_output, False, False))
        if file:
            args.extend(["--file", file])
        if lines:
            args.extend(["--lines", lines])
        args.extend(self._format_dynamic_flags(flags))
        if extra_args:
            args.extend(extra_args)
        return await self._run_command(
            args,
            stream=stream,
            timeout=timeout,
            parse_json_stream=json_output,
        )

    async def test(
        self,
        *,
        target: str | None = None,
        args_json: Dict[str, Any] | None = None,
        workspace: str | None = None,
        stream: bool = False,
        json_output: bool = False,
        shell: str | None = None,
        flags: Optional[Dict[str, Any]] = None,
        extra_args: Optional[List[str]] = None,
        timeout: float | None = None,
    ) -> ClaudeCommandResult | ClaudeStreamingResult:
        """Execute ``claude test`` with optional args."""

        args = self._base_args(workspace=workspace, shell=shell)
        args.append("test")
        args.extend(self._format_common_flags(json_output, False, False))
        if target:
            args.extend(["--target", target])
        if args_json:
            args.extend(["--args", json.dumps(args_json)])
        args.extend(self._format_dynamic_flags(flags))
        if extra_args:
            args.extend(extra_args)
        return await self._run_command(
            args,
            stream=stream,
            timeout=timeout,
            parse_json_stream=json_output,
        )

    async def doc(
        self,
        *,
        file: str | None = None,
        out: str | None = None,
        workspace: str | None = None,
        stream: bool = False,
        json_output: bool = False,
        shell: str | None = None,
        flags: Optional[Dict[str, Any]] = None,
        extra_args: Optional[List[str]] = None,
        timeout: float | None = None,
    ) -> ClaudeCommandResult | ClaudeStreamingResult:
        """Generate documentation via ``claude doc``."""

        args = self._base_args(workspace=workspace, shell=shell)
        args.append("doc")
        args.extend(self._format_common_flags(json_output, False, False))
        if file:
            args.extend(["--file", file])
        if out:
            args.extend(["--out", out])
        args.extend(self._format_dynamic_flags(flags))
        if extra_args:
            args.extend(extra_args)
        return await self._run_command(
            args,
            stream=stream,
            timeout=timeout,
            parse_json_stream=json_output,
        )

    async def plugin(
        self,
        *,
        install: str | None = None,
        run: str | None = None,
        list_plugins: bool = False,
        args_json: Dict[str, Any] | None = None,
        stream: bool = False,
        json_output: bool = False,
        workspace: str | None = None,
        shell: str | None = None,
        flags: Optional[Dict[str, Any]] = None,
        extra_args: Optional[List[str]] = None,
        timeout: float | None = None,
    ) -> ClaudeCommandResult | ClaudeStreamingResult:
        """Manage Claude plugins via ``claude plugin``."""

        args = self._base_args(workspace=workspace, shell=shell)
        args.append("plugin")
        args.extend(self._format_common_flags(json_output, False, False))
        if install:
            args.extend(["--install", install])
        if list_plugins:
            args.append("--list")
        if run:
            args.extend(["--run", run])
        if args_json:
            args.extend(["--args", json.dumps(args_json)])
        args.extend(self._format_dynamic_flags(flags))
        if extra_args:
            args.extend(extra_args)
        return await self._run_command(
            args,
            stream=stream,
            timeout=timeout,
            parse_json_stream=json_output,
        )

    async def mcp(
        self,
        *,
        register: str | None = None,
        config: str | None = None,
        list_servers: bool = False,
        invoke: str | None = None,
        stream: bool = False,
        json_output: bool = False,
        workspace: str | None = None,
        shell: str | None = None,
        flags: Optional[Dict[str, Any]] = None,
        extra_args: Optional[List[str]] = None,
        timeout: float | None = None,
    ) -> ClaudeCommandResult | ClaudeStreamingResult:
        """Work with MCP connections via ``claude mcp``."""

        args = self._base_args(workspace=workspace, shell=shell)
        args.append("mcp")
        args.extend(self._format_common_flags(json_output, False, False))
        if register:
            args.extend(["--register", register])
        if config:
            args.extend(["--config", config])
        if list_servers:
            args.append("--list")
        if invoke:
            args.extend(["--invoke", invoke])
        args.extend(self._format_dynamic_flags(flags))
        if extra_args:
            args.extend(extra_args)
        return await self._run_command(
            args,
            stream=stream,
            timeout=timeout,
            parse_json_stream=json_output,
        )

    async def run_raw(
        self,
        *args: str,
        stream: bool = False,
        timeout: float | None = None,
        parse_json_stream: bool = False,
    ) -> ClaudeCommandResult | ClaudeStreamingResult:
        """Execute an arbitrary Claude CLI command."""

        full_args = [self.binary, *args]
        return await self._run_command(
            full_args, stream=stream, timeout=timeout, parse_json_stream=parse_json_stream
        )

    def _base_args(self, *, workspace: str | None, shell: str | None) -> List[str]:
        args = [self.binary]
        if workspace or self.workspace:
            args.extend(["--workspace", workspace or self.workspace])
        if shell or self.shell:
            args.extend(["--shell", shell or self.shell])
        return args

    def _format_common_flags(
        self, json_output: bool, debug: bool, no_confirm: bool
    ) -> List[str]:
        args: List[str] = []
        if json_output:
            args.append("--json")
        if debug:
            args.append("--debug")
        if no_confirm:
            args.append("--no-confirm")
        return args

    def _format_dynamic_flags(self, flags: Optional[Dict[str, Any]]) -> List[str]:
        if not flags:
            return []
        args: List[str] = []
        for key, value in flags.items():
            flag = f"--{key.replace('_', '-')}"
            if isinstance(value, bool):
                if value:
                    args.append(flag)
            elif isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
                for item in value:
                    args.extend([flag, str(item)])
            else:
                args.extend([flag, str(value)])
        return args

    async def _run_command(
        self,
        args: List[str],
        *,
        stream: bool,
        timeout: float | None,
        parse_json_stream: bool = False,
        session_id: str | None = None,
    ) -> ClaudeCommandResult | ClaudeStreamingResult:
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
            return ClaudeCommandResult(
                command=args,
                success=False,
                error=f"Claude CLI binary not found: {args[0]}",
                stderr="binary not found",
            )
        except Exception as exc:  # pragma: no cover - safety net
            return ClaudeCommandResult(
                command=args,
                success=False,
                error=f"Failed to start Claude CLI: {exc}",
            )

        if stream:
            completion_future: asyncio.Future[ClaudeCommandResult] = (
                asyncio.get_event_loop().create_future()
            )
            return ClaudeStreamingResult(
                command=args,
                stream=self._stream_process(
                    process,
                    completion_future,
                    resolved_timeout,
                    command=args,
                    parse_json_stream=parse_json_stream,
                    session_id=session_id,
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
            error_message = f"Claude CLI exited with code {exit_code}"

        return ClaudeCommandResult(
            command=args,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            success=success,
            error=error_message,
            session_id=session_id,
        )

    async def _stream_process(
        self,
        process: asyncio.subprocess.Process,
        completion_future: asyncio.Future[ClaudeCommandResult],
        timeout: float | None,
        *,
        command: List[str],
        parse_json_stream: bool,
        session_id: str | None,
    ) -> AsyncGenerator[ClaudeStreamEvent, None]:
        queue: asyncio.Queue[ClaudeStreamEvent | None] = asyncio.Queue()
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
                await queue.put(ClaudeStreamEvent(kind=kind, text=text, parsed=parsed))

        stdout_task = asyncio.create_task(pump(process.stdout, "stdout", stdout_chunks))
        stderr_task = asyncio.create_task(pump(process.stderr, "stderr", stderr_chunks))

        try:
            try:
                await asyncio.wait_for(process.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                await queue.put(
                    ClaudeStreamEvent(
                        kind="stderr",
                        text="Claude CLI timed out",
                        parsed=None,
                    )
                )
            await stdout_task
            await stderr_task
        finally:
            await queue.put(None)

        result = ClaudeCommandResult(
            command=command,
            stdout="\n".join(stdout_chunks),
            stderr="\n".join(stderr_chunks),
            exit_code=process.returncode,
            success=process.returncode == 0,
            error=None
            if process.returncode == 0
            else f"Claude CLI exited with code {process.returncode}",
            session_id=session_id,
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
            stderr += b"\nClaude CLI timed out"
        stdout_text = stdout.decode(errors="replace") if stdout is not None else ""
        stderr_text = stderr.decode(errors="replace") if stderr is not None else ""
        return stdout_text, stderr_text
