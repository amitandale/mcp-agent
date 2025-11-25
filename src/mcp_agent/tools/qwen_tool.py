"""Qwen Code CLI adapter for mcp-agent.

This module mirrors the Qwen Code CLI surface area so agents can drive every
first-party command (prompts, slash commands, custom TOML commands, MCP
integration, checkpoints, approval modes, and shell passthrough) without
relying on an interactive terminal. Each helper builds the appropriate
``qwen`` invocation, wires API key resolution, and optionally streams
stdout/stderr so workflows can surface incremental progress.
"""
from __future__ import annotations

import asyncio
import json
import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncGenerator, Awaitable, Dict, Iterable, List, Optional, Sequence

from dotenv import load_dotenv

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for older runtimes
    import tomli as tomllib


@dataclass
class QwenStreamEvent:
    """Represents a single streamed event from the Qwen CLI."""

    kind: str
    text: str
    parsed: Any | None = None


@dataclass
class QwenCommandResult:
    """Aggregated result for a Qwen CLI invocation."""

    command: List[str]
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    success: bool = False
    error: str | None = None


@dataclass
class QwenStreamingResult:
    """Handle returned when a Qwen command is streamed."""

    command: List[str]
    stream: AsyncGenerator[QwenStreamEvent, None]
    completion: Awaitable[QwenCommandResult]


class QwenTool:
    """Async adapter for invoking the Qwen Code CLI.

    The adapter exposes helpers for:
    - One-shot prompts (`--prompt`) with optional @file injection.
    - Slash commands (`/bug`, `/summary`, `/chat`, `/directory`, `/agents`,
      `/memory`, `/mcp`, `/restore`, `/approval-mode`, etc.).
    - Shell passthrough with ``!<command>`` and directory-aware execution.
    - Custom TOML commands discovered in ``~/.qwen/commands`` and
      ``<workspace>/.qwen/commands`` with ``{{args}}`` substitution.
    - MCP configuration forwarding via ``--mcp-config-file`` and `/mcp`.

    Authentication is resolved from the provided ``api_key`` argument,
    ``QWEN_API_KEY`` environment variable, or a local ``.env`` file. Missing
    keys raise a descriptive error so callers can decide whether to prompt the
    user in a higher layer.
    """

    def __init__(
        self,
        *,
        binary: str = "qwen",
        workspace: str | None = None,
        api_key: str | None = None,
        include_directories: Optional[Iterable[str]] = None,
        checkpointing: bool = False,
        model: str | None = None,
        base_url: str | None = None,
        mcp_config_file: str | None = None,
        default_timeout: float | None = 300.0,
        env: Optional[Dict[str, str]] = None,
    ) -> None:
        load_dotenv()
        self.binary = binary
        self.workspace = workspace
        self.api_key = api_key
        self.include_directories = list(include_directories or [])
        self.checkpointing = checkpointing
        self.model = model
        self.base_url = base_url
        self.mcp_config_file = mcp_config_file
        self.default_timeout = default_timeout
        self.env = env or {}

    # --- Core prompt helpers -------------------------------------------------
    async def prompt(
        self,
        prompt: str,
        *,
        include_directories: Optional[Iterable[str]] = None,
        checkpointing: bool | None = None,
        mcp_config_file: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        workspace: str | None = None,
        stream: bool = False,
        timeout: float | None = None,
    ) -> QwenCommandResult | QwenStreamingResult:
        """Run ``qwen --prompt"` for headless automation."""

        args = self._base_args(workspace=workspace)
        args.extend(self._runtime_flags(
            include_directories=include_directories,
            checkpointing=checkpointing,
            mcp_config_file=mcp_config_file,
            model=model,
            base_url=base_url,
        ))
        args.extend(["--prompt", prompt])
        return await self._run_command(args, stream=stream, timeout=timeout)

    async def prompt_with_files(
        self,
        prompt: str,
        paths: Sequence[str],
        **kwargs: Any,
    ) -> QwenCommandResult | QwenStreamingResult:
        """Convenience for prompts that inject file/directory contents via @ syntax."""

        injected = self._inject_paths(prompt, paths)
        return await self.prompt(injected, **kwargs)

    # --- Slash commands ------------------------------------------------------
    async def slash(self, command: Sequence[str], *, workspace: str | None = None, stream: bool = False, timeout: float | None = None) -> QwenCommandResult | QwenStreamingResult:
        """Execute a raw slash command (e.g., ``/summary``)."""

        args = self._base_args(workspace=workspace)
        args.extend(self._runtime_flags())
        args.extend([f"/{command[0]}", *command[1:]])
        return await self._run_command(args, stream=stream, timeout=timeout)

    async def bug(self, title: str, **kwargs: Any) -> QwenCommandResult | QwenStreamingResult:
        return await self.slash(["bug", title], **kwargs)

    async def summary(self, **kwargs: Any) -> QwenCommandResult | QwenStreamingResult:
        return await self.slash(["summary"], **kwargs)

    async def compress_history(self, **kwargs: Any) -> QwenCommandResult | QwenStreamingResult:
        return await self.slash(["compress"], **kwargs)

    async def copy_output(self, **kwargs: Any) -> QwenCommandResult | QwenStreamingResult:
        return await self.slash(["copy"], **kwargs)

    async def directory_add(self, path: str, **kwargs: Any) -> QwenCommandResult | QwenStreamingResult:
        return await self.slash(["directory", "add", path], **kwargs)

    async def directory_show(self, **kwargs: Any) -> QwenCommandResult | QwenStreamingResult:
        return await self.slash(["directory", "show"], **kwargs)

    async def chat(self, action: str, name: str | None = None, *, share_as: str | None = None, **kwargs: Any) -> QwenCommandResult | QwenStreamingResult:
        parts = ["chat", action]
        if name:
            parts.append(name)
        if share_as:
            parts.extend(["--format", share_as])
        return await self.slash(parts, **kwargs)

    async def mcp(self, subcommand: str | None = None, **kwargs: Any) -> QwenCommandResult | QwenStreamingResult:
        parts = ["mcp"]
        if subcommand:
            parts.append(subcommand)
        return await self.slash(parts, **kwargs)

    async def memory(self, action: str, content: str | None = None, **kwargs: Any) -> QwenCommandResult | QwenStreamingResult:
        parts = ["memory", action]
        if content:
            parts.append(content)
        return await self.slash(parts, **kwargs)

    async def restore(self, tool_call_id: str | None = None, **kwargs: Any) -> QwenCommandResult | QwenStreamingResult:
        parts = ["restore"]
        if tool_call_id:
            parts.append(tool_call_id)
        return await self.slash(parts, **kwargs)

    async def stats(self, **kwargs: Any) -> QwenCommandResult | QwenStreamingResult:
        return await self.slash(["stats"], **kwargs)

    async def approval_mode(self, mode: str, scope: str | None = None, **kwargs: Any) -> QwenCommandResult | QwenStreamingResult:
        parts = ["approval-mode", mode]
        if scope:
            parts.append(f"--{scope}")
        return await self.slash(parts, **kwargs)

    async def agents(self, action: str, name: str | None = None, *, scope: str | None = None, **kwargs: Any) -> QwenCommandResult | QwenStreamingResult:
        parts = ["agents", action]
        if name:
            parts.append(name)
        if scope:
            parts.extend(["--scope", scope])
        return await self.slash(parts, **kwargs)

    async def help(self, **kwargs: Any) -> QwenCommandResult | QwenStreamingResult:
        return await self.slash(["?"], **kwargs)

    # --- Shell passthrough ---------------------------------------------------
    async def run_shell(
        self, command: str, *, workspace: str | None = None, stream: bool = False, timeout: float | None = None
    ) -> QwenCommandResult | QwenStreamingResult:
        """Execute a shell command through Qwen's ``!`` passthrough."""

        args = self._base_args(workspace=workspace)
        args.extend(self._runtime_flags())
        args.append(f"!{command}")
        return await self._run_command(args, stream=stream, timeout=timeout)

    # --- Custom commands -----------------------------------------------------
    async def run_custom(
        self,
        command_name: str,
        *,
        args: str | None = None,
        workspace: str | None = None,
        stream: bool = False,
        timeout: float | None = None,
    ) -> QwenCommandResult | QwenStreamingResult:
        """Run a custom TOML command from ~/.qwen/commands or <workspace>/.qwen/commands."""

        prompt_template = self._load_custom_command(command_name, workspace or self.workspace)
        prompt_text = prompt_template.replace("{{args}}", args or "")
        return await self.prompt(prompt_text, workspace=workspace, stream=stream, timeout=timeout)

    # --- MCP helpers ---------------------------------------------------------
    async def mcp_list(self, **kwargs: Any) -> QwenCommandResult | QwenStreamingResult:
        return await self.mcp("list", **kwargs)

    async def mcp_schema(self, **kwargs: Any) -> QwenCommandResult | QwenStreamingResult:
        return await self.mcp("schema", **kwargs)

    async def mcp_descriptions(self, **kwargs: Any) -> QwenCommandResult | QwenStreamingResult:
        return await self.mcp("descriptions", **kwargs)

    async def mcp_nodescriptions(self, **kwargs: Any) -> QwenCommandResult | QwenStreamingResult:
        return await self.mcp("nodescriptions", **kwargs)

    # --- Utility internals ---------------------------------------------------
    def _base_args(self, *, workspace: str | None) -> List[str]:
        args = [self.binary]
        if workspace or self.workspace:
            args.extend(["--workspace", workspace or self.workspace])
        if self.model:
            args.extend(["--model", self.model])
        if self.base_url:
            args.extend(["--base-url", self.base_url])
        if self.mcp_config_file:
            args.extend(["--mcp-config-file", self.mcp_config_file])
        if self.checkpointing:
            args.append("--checkpointing")
        if self.include_directories:
            for directory in self.include_directories:
                args.extend(["--include-directories", directory])
        return args

    def _runtime_flags(
        self,
        *,
        include_directories: Optional[Iterable[str]] = None,
        checkpointing: bool | None = None,
        mcp_config_file: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> List[str]:
        args: List[str] = []
        dirs = include_directories or []
        for directory in dirs:
            args.extend(["--include-directories", directory])
        if checkpointing is True or (checkpointing is None and self.checkpointing):
            args.append("--checkpointing")
        if mcp_config_file or self.mcp_config_file:
            args.extend(["--mcp-config-file", mcp_config_file or self.mcp_config_file])
        if model or self.model:
            args.extend(["--model", model or self.model])
        if base_url or self.base_url:
            args.extend(["--base-url", base_url or self.base_url])
        return args

    def _inject_paths(self, prompt: str, paths: Sequence[str]) -> str:
        blocks: List[str] = [prompt]
        for path_str in paths:
            path = Path(path_str)
            if not path.exists():
                blocks.append(f"@{path_str} (missing)")
                continue
            if path.is_dir():
                blocks.append(f"@{path_str} (directory)")
                continue
            content = self._read_text_file(path)
            blocks.append(f"@{path_str}\n{content}")
        return "\n\n".join(blocks)

    def _read_text_file(self, path: Path) -> str:
        try:
            data = path.read_bytes()
        except Exception as exc:  # pragma: no cover - filesystem errors
            return f"<error reading {path}: {exc}>"
        if b"\0" in data:
            return "<binary file skipped>"
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode(errors="replace")

    def _load_custom_command(self, command_name: str, workspace: str | None) -> str:
        sanitized = command_name.lstrip("/").replace("/", "_")
        filename = f"{sanitized}.toml"
        search_paths: List[Path] = []
        if workspace:
            search_paths.append(Path(workspace) / ".qwen" / "commands" / filename)
        search_paths.append(Path.home() / ".qwen" / "commands" / filename)

        for path in search_paths:
            if path.exists():
                with path.open("rb") as fh:
                    data = tomllib.load(fh)
                prompt = data.get("prompt")
                if not prompt:
                    raise ValueError(f"Custom command missing 'prompt': {path}")
                return str(prompt)
        raise FileNotFoundError(
            f"Custom command '{command_name}' not found in ~/.qwen/commands or workspace .qwen/commands"
        )

    def _resolve_api_key(self) -> str:
        key = self.api_key or os.getenv("QWEN_API_KEY")
        if key:
            return key
        env_path = Path(self.workspace or ".") / ".env"
        if env_path.exists():
            with env_path.open() as fh:
                for line in fh:
                    if line.startswith("QWEN_API_KEY="):
                        return line.split("=", 1)[1].strip()
        raise RuntimeError("QWEN_API_KEY is required. Set env, .env, or pass api_key.")

    async def _run_command(
        self,
        args: List[str],
        *,
        stream: bool,
        timeout: float | None,
        parse_json_stream: bool = False,
    ) -> QwenCommandResult | QwenStreamingResult:
        resolved_timeout = self.default_timeout if timeout is None else timeout
        # Inherit the current environment so system binaries (including Python
        # itself when used as a stand-in for the Qwen CLI during tests) can
        # locate their shared libraries. Only overlay custom values and the
        # required API key.
        env = {**os.environ, **self.env, "QWEN_API_KEY": self._resolve_api_key()}

        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError:
            return QwenCommandResult(
                command=args,
                success=False,
                error=f"Qwen CLI binary not found: {args[0]}",
                stderr="binary not found",
            )
        except Exception as exc:  # pragma: no cover - safety net
            return QwenCommandResult(
                command=args,
                success=False,
                error=f"Failed to start Qwen CLI: {exc}",
            )

        if stream:
            completion_future: asyncio.Future[QwenCommandResult] = (
                asyncio.get_event_loop().create_future()
            )
            return QwenStreamingResult(
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
            error_message = f"Qwen CLI exited with code {exit_code}"

        return QwenCommandResult(
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
        completion_future: asyncio.Future[QwenCommandResult],
        timeout: float | None,
        *,
        command: List[str],
        parse_json_stream: bool,
    ) -> AsyncGenerator[QwenStreamEvent, None]:
        queue: asyncio.Queue[QwenStreamEvent | None] = asyncio.Queue()
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
                await queue.put(QwenStreamEvent(kind=kind, text=text, parsed=parsed))

        stdout_task = asyncio.create_task(pump(process.stdout, "stdout", stdout_chunks))
        stderr_task = asyncio.create_task(pump(process.stderr, "stderr", stderr_chunks))

        try:
            try:
                await asyncio.wait_for(process.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                await queue.put(
                    QwenStreamEvent(
                        kind="stderr",
                        text="Qwen CLI timed out",
                        parsed=None,
                    )
                )
            await stdout_task
            await stderr_task
        finally:
            await queue.put(None)

        result = QwenCommandResult(
            command=command,
            stdout="\n".join(stdout_chunks),
            stderr="\n".join(stderr_chunks),
            exit_code=process.returncode,
            success=process.returncode == 0,
            error=None if process.returncode == 0 else f"Qwen CLI exited with code {process.returncode}",
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
            stderr = (stderr or b"") + b"\nQwen CLI timed out"
        stdout_text = stdout.decode(errors="replace") if stdout is not None else ""
        stderr_text = stderr.decode(errors="replace") if stderr is not None else ""
        return stdout_text, stderr_text

    # --- Raw invocation ------------------------------------------------------
    async def run_raw(
        self,
        *args: str,
        stream: bool = False,
        timeout: float | None = None,
        parse_json_stream: bool = False,
    ) -> QwenCommandResult | QwenStreamingResult:
        """Execute an arbitrary Qwen CLI command."""

        full_args = [self.binary, *args]
        return await self._run_command(
            full_args, stream=stream, timeout=timeout, parse_json_stream=parse_json_stream
        )

    def format_shell_command(self, command: Sequence[str]) -> str:
        """Helper to build a shell-safe ``!`` payload."""

        return "!" + " ".join(shlex.quote(part) for part in command)
