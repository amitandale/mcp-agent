"""Kimi CLI adapter for mcp-agent.

This module mirrors the documented Kimi (MoonshotAI) CLI surface area so agent
workflows can automate the same commands without bespoke shell scripting. The
adapter covers interactive sessions, one-shot prompts, chat, configuration,
API key discovery, model selection, MCP config forwarding, and streaming output
handling.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncGenerator, Awaitable, Dict, List, Optional


@dataclass
class KimiStreamEvent:
    """Represents a single streamed event from the Kimi CLI."""

    kind: str
    text: str
    parsed: Any | None = None


@dataclass
class KimiCommandResult:
    """Aggregated result for a Kimi CLI invocation."""

    command: List[str]
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    success: bool = False
    error: str | None = None


@dataclass
class KimiStreamingResult:
    """Handle returned when a Kimi command is streamed."""

    command: List[str]
    stream: AsyncGenerator[KimiStreamEvent, None]
    completion: Awaitable[KimiCommandResult]


class KimiTool:
    """Async adapter for invoking the Kimi CLI."""

    def __init__(
        self,
        *,
        binary: str = "kimi",
        workspace: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        default_timeout: float | None = 300.0,
        env: Optional[Dict[str, str]] = None,
        dotenv_path: str | None = None,
    ) -> None:
        self.binary = binary
        self.workspace = workspace
        self.api_key = api_key
        self.model = model
        self.default_timeout = default_timeout
        self.env = env or {}
        self.dotenv_path = dotenv_path

    async def run(
        self,
        *,
        model: str | None = None,
        mcp_config_file: str | None = None,
        stream: bool = False,
        timeout: float | None = None,
        extra_args: Optional[List[str]] = None,
    ) -> KimiCommandResult | KimiStreamingResult:
        """Launch the interactive Kimi session (``kimi``)."""

        args = self._base_args(model=model, mcp_config_file=mcp_config_file)
        if extra_args:
            args.extend(extra_args)
        return await self._run_command(
            args,
            stream=stream,
            timeout=timeout,
            require_api_key=True,
        )

    async def ask(
        self,
        question: str,
        *,
        model: str | None = None,
        mcp_config_file: str | None = None,
        stream: bool = False,
        timeout: float | None = None,
        extra_args: Optional[List[str]] = None,
    ) -> KimiCommandResult | KimiStreamingResult:
        """Run ``kimi ask`` for one-shot prompts."""

        args = self._base_args(model=model, mcp_config_file=mcp_config_file)
        args.extend(["ask", question])
        if extra_args:
            args.extend(extra_args)
        return await self._run_command(
            args,
            stream=stream,
            timeout=timeout,
            require_api_key=True,
        )

    async def chat(
        self,
        *,
        model: str | None = None,
        mcp_config_file: str | None = None,
        stream: bool = False,
        timeout: float | None = None,
        extra_args: Optional[List[str]] = None,
    ) -> KimiCommandResult | KimiStreamingResult:
        """Start an interactive chat (``kimi chat``)."""

        args = self._base_args(model=model, mcp_config_file=mcp_config_file)
        args.append("chat")
        if extra_args:
            args.extend(extra_args)
        return await self._run_command(
            args,
            stream=stream,
            timeout=timeout,
            require_api_key=True,
        )

    async def config_set_key(
        self,
        api_key: str | None = None,
        *,
        stream: bool = False,
        timeout: float | None = None,
    ) -> KimiCommandResult | KimiStreamingResult:
        """Persist an API key via ``kimi config set-key``.

        If ``api_key`` is provided, it is piped to stdin so the CLI does not
        need to prompt the user interactively. If omitted, the CLI is launched
        interactively and the user is expected to type the key.
        """

        args = [self.binary, "config", "set-key"]
        input_text = None
        if api_key:
            input_text = f"{api_key}\n"
        return await self._run_command(
            args,
            stream=stream,
            timeout=timeout,
            require_api_key=False,
            input_text=input_text,
        )

    async def config_show(
        self,
        *,
        stream: bool = False,
        timeout: float | None = None,
    ) -> KimiCommandResult | KimiStreamingResult:
        """Show current configuration via ``kimi config show``."""

        args = [self.binary, "config", "show"]
        return await self._run_command(
            args,
            stream=stream,
            timeout=timeout,
            require_api_key=False,
        )

    async def history_list(
        self,
        *,
        stream: bool = False,
        timeout: float | None = None,
    ) -> KimiCommandResult | KimiStreamingResult:
        """List previous sessions using ``kimi history list``."""

        args = [self.binary, "history", "list"]
        return await self._run_command(
            args,
            stream=stream,
            timeout=timeout,
            require_api_key=True,
        )

    async def version(self) -> KimiCommandResult:
        """Return the Kimi CLI version."""

        return await self._run_command(
            [self.binary, "--version"],
            stream=False,
            timeout=None,
            require_api_key=False,
        )

    async def run_raw(
        self,
        *args: str,
        stream: bool = False,
        timeout: float | None = None,
        parse_json_stream: bool = False,
        require_api_key: bool = True,
    ) -> KimiCommandResult | KimiStreamingResult:
        """Run an arbitrary Kimi CLI command with passthrough arguments."""

        command = [self.binary, *args]
        return await self._run_command(
            command,
            stream=stream,
            timeout=timeout,
            parse_json_stream=parse_json_stream,
            require_api_key=require_api_key,
        )

    def _base_args(
        self,
        *,
        model: str | None = None,
        mcp_config_file: str | None = None,
    ) -> List[str]:
        args = [self.binary]

        if model_value := self._resolve_model(model):
            args.extend(["--model", model_value])

        if mcp_config_file:
            validated = self._validate_mcp_config_file(mcp_config_file)
            args.extend(["--mcp-config-file", validated])

        return args

    def _resolve_model(self, model: str | None) -> str | None:
        return model or os.environ.get("MOONSHOT_MODEL") or self.model

    def _validate_mcp_config_file(self, path: str) -> str:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"MCP config file not found: {path}")
        try:
            data = json.loads(file_path.read_text())
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid MCP config JSON: {exc}") from exc
        if not isinstance(data, dict) and not isinstance(data, list):
            raise ValueError("MCP config must be a JSON object or array")
        return str(file_path)

    def _resolve_api_key(self, api_key: str | None, env: Dict[str, str]) -> str:
        resolved = (
            api_key
            or self.api_key
            or env.get("KIMI_API_KEY")
            or os.environ.get("KIMI_API_KEY")
            or self._load_project_setting("KIMI_API_KEY")
            or self._load_global_setting("KIMI_API_KEY")
            or self._load_dotenv_key()
        )
        if not resolved:
            raise ValueError(
                "No API key found in KIMI_API_KEY, configuration files, or .env. Use "
                "`kimi config set-key` to initialize credentials."
            )
        return resolved

    def _load_project_setting(self, key: str) -> str | None:
        if not self.workspace:
            return None
        project_settings = Path(self.workspace) / ".kimi" / "settings.json"
        if not project_settings.exists():
            return None
        try:
            data = json.loads(project_settings.read_text())
        except json.JSONDecodeError:
            return None
        return data.get(key)

    def _load_global_setting(self, key: str) -> str | None:
        user_settings = Path(os.path.expanduser("~/.kimi/user-settings.json"))
        if not user_settings.exists():
            return None
        try:
            data = json.loads(user_settings.read_text())
        except json.JSONDecodeError:
            return None
        return data.get(key)

    def _load_dotenv_key(self) -> str | None:
        dotenv_path = (
            Path(self.dotenv_path)
            if self.dotenv_path
            else (Path(self.workspace) / ".env" if self.workspace else None)
        )
        if not dotenv_path or not dotenv_path.exists():
            return None
        for line in dotenv_path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("KIMI_API_KEY="):
                return stripped.split("=", 1)[1].strip()
        return None

    async def _run_command(
        self,
        args: List[str],
        *,
        stream: bool,
        timeout: float | None,
        parse_json_stream: bool = False,
        require_api_key: bool,
        input_text: str | None = None,
    ) -> KimiCommandResult | KimiStreamingResult:
        resolved_timeout = self.default_timeout if timeout is None else timeout

        env = os.environ.copy()
        if self.env:
            env.update(self.env)

        if require_api_key:
            env["KIMI_API_KEY"] = self._resolve_api_key(env.get("KIMI_API_KEY"), env)

        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
                cwd=self.workspace,
                env=env,
            )
        except FileNotFoundError:
            return KimiCommandResult(
                command=args,
                success=False,
                error=f"Kimi CLI binary not found: {args[0]}",
                stderr="binary not found",
            )
        except Exception as exc:  # pragma: no cover - safety net
            return KimiCommandResult(
                command=args,
                success=False,
                error=f"Failed to start Kimi CLI: {exc}",
            )

        if stream:
            completion_future: asyncio.Future[KimiCommandResult] = (
                asyncio.get_event_loop().create_future()
            )
            return KimiStreamingResult(
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

        stdout, stderr = await self._communicate_with_timeout(
            process, resolved_timeout, input_text
        )
        exit_code = process.returncode
        success = exit_code == 0
        return KimiCommandResult(
            command=args,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            success=success,
            error=None if success else stderr or "Command failed",
        )

    async def _communicate_with_timeout(
        self,
        process: asyncio.subprocess.Process,
        timeout: float | None,
        input_text: str | None,
    ) -> tuple[str, str]:
        input_bytes = input_text.encode() if input_text is not None else None
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input_bytes), timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return "", "Process timed out"
        return (stdout.decode().strip(), stderr.decode().strip())

    async def _stream_process(
        self,
        process: asyncio.subprocess.Process,
        completion_future: asyncio.Future[KimiCommandResult],
        timeout: float | None,
        *,
        command: List[str],
        parse_json_stream: bool,
    ) -> AsyncGenerator[KimiStreamEvent, None]:
        queue: asyncio.Queue[KimiStreamEvent | None] = asyncio.Queue()
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
                await queue.put(KimiStreamEvent(kind=kind, text=text, parsed=parsed))

        stdout_task = asyncio.create_task(pump(process.stdout, "stdout", stdout_chunks))
        stderr_task = asyncio.create_task(pump(process.stderr, "stderr", stderr_chunks))

        try:
            try:
                await asyncio.wait_for(process.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                await queue.put(
                    KimiStreamEvent(kind="stderr", text="Process timed out", parsed=None)
                )
            await stdout_task
            await stderr_task
        finally:
            await queue.put(None)

        result = KimiCommandResult(
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
