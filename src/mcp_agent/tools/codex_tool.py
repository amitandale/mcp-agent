"""Codex CLI adapter for mcp-agent.

This module mirrors the patterns used by the other tool adapters in this
package while adding rich, async-friendly wrappers around the Codex CLI. The
adapter exposes a high-level ``CodexTool`` class with helper methods for every
Codex entrypoint (``exec``, ``resume``, ``apply``, ``cloud`` subcommands, and
``mcp-server``). Each method builds the correct command invocation, applies
common defaults (model, provider, working directory), and returns structured
results that surface stdout, stderr, exit status, and streaming updates when
requested.
"""

from __future__ import annotations

import asyncio
import json
import shlex
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Awaitable, Dict, Iterable, List, Optional


@dataclass
class CodexStreamEvent:
    """Represents a single streamed event from the Codex CLI.

    Attributes:
        kind: Origin of the event (``"stdout"`` or ``"stderr"``).
        text: Raw text emitted by the process (line-stripped).
        parsed: Optional parsed JSON object when ``--json`` output is detected.
    """

    kind: str
    text: str
    parsed: Any | None = None


@dataclass
class CodexCommandResult:
    """Aggregated result for a Codex CLI invocation."""

    command: List[str]
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    success: bool = False
    error: str | None = None
    session_id: str | None = None


@dataclass
class CodexStreamingResult:
    """Handle returned when a Codex command is streamed.

    Attributes:
        command: Full command that was executed.
        stream: Async iterator yielding :class:`CodexStreamEvent` items.
        completion: Awaitable that resolves to :class:`CodexCommandResult` once
            the process finishes. This allows consumers to both stream updates
            and wait for the final aggregated output.
    """

    command: List[str]
    stream: AsyncGenerator[CodexStreamEvent, None]
    completion: Awaitable[CodexCommandResult]


class CodexTool:
    """Async adapter for invoking the Codex CLI.

    Parameters mirror the official Codex CLI flags while following the
    conventions established by other adapters in ``src/mcp_agent/tools``.
    The adapter embraces async subprocess execution, optional streaming, JSON
    parsing, and robust error handling.
    """

    def __init__(
        self,
        *,
        binary: str = "codex",
        model: str | None = None,
        provider: str | None = None,
        workspace: str | None = None,
        default_timeout: float | None = 300.0,
        env: Optional[Dict[str, str]] = None,
    ) -> None:
        self.binary = binary
        self.model = model
        self.provider = provider
        self.workspace = workspace
        self.default_timeout = default_timeout
        self.env = env or {}

    async def exec(
        self,
        *,
        prompt: str,
        stream: bool = False,
        full_auto: bool = False,
        cd: str | None = None,
        json_output: bool = False,
        output_schema: str | None = None,
        flags: Optional[Dict[str, Any]] = None,
        extra_args: Optional[List[str]] = None,
        timeout: float | None = None,
        session_id: str | None = None,
    ) -> CodexCommandResult | CodexStreamingResult:
        """Run ``codex exec``.

        Args:
            prompt: Prompt passed to the Codex CLI.
            stream: Whether to stream stdout/stderr as they are produced.
            full_auto: Map to the ``--full-auto`` flag.
            cd: Working directory to pass via ``--cd`` (overrides default).
            json_output: Request JSON-formatted output (``--json``).
            output_schema: Optional path passed to ``--output-schema``.
            flags: Additional key/value flags appended as ``--<key> <value>``.
            extra_args: Extra CLI args appended verbatim at the end.
            timeout: Override the adapter timeout for this call.
            session_id: Optional session identifier propagated to the CLI.
        """

        args = self._base_args(cd)
        args.append("exec")
        args.extend(self._format_common_flags(full_auto, json_output, output_schema))
        args.extend(self._format_dynamic_flags(flags))
        if session_id:
            args.extend(["--session", session_id])
        args.append(prompt)
        if extra_args:
            args.extend(extra_args)
        return await self._run_command(
            args,
            stream=stream,
            timeout=timeout,
            parse_json_stream=json_output,
            session_id=session_id,
        )

    async def resume(
        self,
        *,
        session_id: str,
        prompt: str | None = None,
        stream: bool = False,
        json_output: bool = False,
        flags: Optional[Dict[str, Any]] = None,
        extra_args: Optional[List[str]] = None,
        timeout: float | None = None,
    ) -> CodexCommandResult | CodexStreamingResult:
        """Resume a Codex session via ``codex resume``."""

        args = self._base_args()
        args.extend(["resume", "--session", session_id])
        if prompt:
            args.extend(["--prompt", prompt])
        args.extend(self._format_dynamic_flags(flags))
        if json_output:
            args.append("--json")
        if extra_args:
            args.extend(extra_args)
        return await self._run_command(
            args,
            stream=stream,
            timeout=timeout,
            parse_json_stream=json_output,
            session_id=session_id,
        )

    async def apply(
        self,
        *,
        task_id: str,
        stream: bool = False,
        flags: Optional[Dict[str, Any]] = None,
        extra_args: Optional[List[str]] = None,
        timeout: float | None = None,
    ) -> CodexCommandResult | CodexStreamingResult:
        """Apply a Codex diff via ``codex apply``."""

        args = self._base_args()
        args.extend(["apply", "--task", task_id])
        args.extend(self._format_dynamic_flags(flags))
        if extra_args:
            args.extend(extra_args)
        return await self._run_command(args, stream=stream, timeout=timeout, session_id=None)

    async def cloud_exec(
        self,
        *,
        prompt: str,
        stream: bool = False,
        json_output: bool = False,
        flags: Optional[Dict[str, Any]] = None,
        extra_args: Optional[List[str]] = None,
        timeout: float | None = None,
    ) -> CodexCommandResult | CodexStreamingResult:
        """Run ``codex cloud exec`` with streaming support."""

        args = self._base_args()
        args.extend(["cloud", "exec"])
        if json_output:
            args.append("--json")
        args.extend(self._format_dynamic_flags(flags))
        args.append(prompt)
        if extra_args:
            args.extend(extra_args)
        return await self._run_command(
            args, stream=stream, timeout=timeout, parse_json_stream=json_output
        )

    async def cloud_diff(
        self,
        *,
        stream: bool = False,
        flags: Optional[Dict[str, Any]] = None,
        extra_args: Optional[List[str]] = None,
        timeout: float | None = None,
    ) -> CodexCommandResult | CodexStreamingResult:
        """Run ``codex cloud diff``."""

        args = self._base_args()
        args.extend(["cloud", "diff"])
        args.extend(self._format_dynamic_flags(flags))
        if extra_args:
            args.extend(extra_args)
        return await self._run_command(args, stream=stream, timeout=timeout)

    async def cloud_tasks(
        self,
        *,
        stream: bool = False,
        flags: Optional[Dict[str, Any]] = None,
        extra_args: Optional[List[str]] = None,
        timeout: float | None = None,
    ) -> CodexCommandResult | CodexStreamingResult:
        """List or watch tasks via ``codex cloud tasks``."""

        args = self._base_args()
        args.extend(["cloud", "tasks"])
        args.extend(self._format_dynamic_flags(flags))
        if extra_args:
            args.extend(extra_args)
        return await self._run_command(args, stream=stream, timeout=timeout)

    async def mcp_server(
        self,
        *,
        stream: bool = False,
        flags: Optional[Dict[str, Any]] = None,
        extra_args: Optional[List[str]] = None,
        timeout: float | None = None,
    ) -> CodexCommandResult | CodexStreamingResult:
        """Start the Codex MCP server via ``codex mcp-server``."""

        args = self._base_args()
        args.append("mcp-server")
        args.extend(self._format_dynamic_flags(flags))
        if extra_args:
            args.extend(extra_args)
        return await self._run_command(args, stream=stream, timeout=timeout)

    async def run_raw(
        self,
        *args: str,
        stream: bool = False,
        timeout: float | None = None,
        parse_json_stream: bool = False,
    ) -> CodexCommandResult | CodexStreamingResult:
        """Execute an arbitrary Codex CLI command.

        This method is intentionally flexible to support new or experimental CLI
        arguments without requiring an adapter code change. Arguments are passed
        verbatim to the Codex binary.
        """

        full_args = [self.binary, *args]
        return await self._run_command(
            full_args, stream=stream, timeout=timeout, parse_json_stream=parse_json_stream
        )

    def _base_args(self, cd: str | None = None) -> List[str]:
        args = [self.binary]
        if self.model:
            args.extend(["--model", self.model])
        if self.provider:
            args.extend(["--provider", self.provider])
        if cd or self.workspace:
            args.extend(["--cd", cd or self.workspace])
        return args

    def _format_common_flags(
        self, full_auto: bool, json_output: bool, output_schema: str | None
    ) -> List[str]:
        args: List[str] = []
        if full_auto:
            args.append("--full-auto")
        if json_output:
            args.append("--json")
        if output_schema:
            args.extend(["--output-schema", output_schema])
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
    ) -> CodexCommandResult | CodexStreamingResult:
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
            return CodexCommandResult(
                command=args,
                success=False,
                error=f"Codex CLI binary not found: {args[0]}",
                stderr="binary not found",
            )
        except Exception as exc:  # pragma: no cover - safety net
            return CodexCommandResult(
                command=args,
                success=False,
                error=f"Failed to start Codex CLI: {exc}",
            )

        if stream:
            completion_future: asyncio.Future[CodexCommandResult] = asyncio.get_event_loop().create_future()
            return CodexStreamingResult(
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
            error_message = f"Codex CLI exited with code {exit_code}"

        return CodexCommandResult(
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
        completion_future: asyncio.Future[CodexCommandResult],
        timeout: float | None,
        *,
        command: List[str],
        parse_json_stream: bool,
        session_id: str | None,
    ) -> AsyncGenerator[CodexStreamEvent, None]:
        queue: asyncio.Queue[CodexStreamEvent | None] = asyncio.Queue()
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
                await queue.put(CodexStreamEvent(kind=kind, text=text, parsed=parsed))

        stdout_task = asyncio.create_task(pump(process.stdout, "stdout", stdout_chunks))
        stderr_task = asyncio.create_task(pump(process.stderr, "stderr", stderr_chunks))

        try:
            try:
                await asyncio.wait_for(process.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                await queue.put(
                    CodexStreamEvent(
                        kind="stderr",
                        text="Codex CLI timed out",
                        parsed=None,
                    )
                )
            await stdout_task
            await stderr_task
        finally:
            await queue.put(None)

        result = CodexCommandResult(
            command=command,
            stdout="\n".join(stdout_chunks),
            stderr="\n".join(stderr_chunks),
            exit_code=process.returncode,
            success=process.returncode == 0,
            error=None if process.returncode == 0 else f"Codex CLI exited with code {process.returncode}",
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
            stderr += b"\nCodex CLI timed out"
        stdout_text = stdout.decode(errors="replace") if stdout is not None else ""
        stderr_text = stderr.decode(errors="replace") if stderr is not None else ""
        return stdout_text, stderr_text

