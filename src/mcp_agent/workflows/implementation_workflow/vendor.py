from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Iterable, List, Protocol, Sequence

from mcp_agent.core.context import Context
from mcp_agent.logging.event_progress import ProgressAction
from mcp_agent.tools.antigravity_tool import AntigravityTool
from mcp_agent.tools.claude_tool import ClaudeTool
from mcp_agent.tools.codex_tool import CodexTool
from mcp_agent.tools.grok_tool import GrokTool
from mcp_agent.tools.kimi_tool import KimiTool
from mcp_agent.tools.qwen_tool import QwenTool
from mcp_agent.workflows.implementation_workflow.models import CLIExecutionResult, Vendor


class StreamingHandle(Protocol):
    stream: Iterable[Any]
    completion: asyncio.Future


def _log_progress(context: Context, message: str, *, action: ProgressAction) -> None:
    try:
        context.logger.info(
            message,
            data={"progress_action": action, "target": "implementation_workflow"},
        )
    except Exception:
        pass


class VendorCLIRunner:
    def __init__(self, vendor: Vendor, *, workspace: str | None = None):
        self.vendor = vendor
        self.workspace = workspace

    def _build_adapter(self):
        if self.vendor is Vendor.CODEX:
            return CodexTool(workspace=self.workspace)
        if self.vendor is Vendor.CLAUDE:
            return ClaudeTool(workspace=self.workspace)
        if self.vendor is Vendor.GROK:
            return GrokTool(workspace=self.workspace)
        if self.vendor is Vendor.ANTIGRAVITY:
            return AntigravityTool(workspace=self.workspace)
        if self.vendor is Vendor.KIMI:
            return KimiTool(workspace=self.workspace)
        if self.vendor is Vendor.QWEN:
            return QwenTool()
        raise ValueError(f"Unsupported vendor {self.vendor}")

    async def run(self, *, instruction: str, context: Context) -> CLIExecutionResult:
        adapter = self._build_adapter()
        _log_progress(context, f"Routing instructions to {self.vendor.value} CLI", action=ProgressAction.RUNNING)

        runner = self._build_invocation(adapter, instruction)
        try:
            outcome = await runner
        except FileNotFoundError as exc:  # pragma: no cover - environment dependent
            context.logger.error(
                f"CLI binary for {self.vendor.value} not found",
                data={"progress_action": ProgressAction.FATAL_ERROR, "error_message": str(exc)},
            )
            return CLIExecutionResult(vendor=self.vendor, instruction=instruction, success=False, streamed_output=[str(exc)])

        streamed_lines: List[str] = []
        exit_code: int | None = None
        success = False
        diff_preview: str | None = None

        if hasattr(outcome, "stream") and hasattr(outcome, "completion"):
            async for event in outcome.stream:
                text = getattr(event, "text", "")
                if text:
                    streamed_lines.append(text)
                    _log_progress(context, text, action=ProgressAction.RUNNING)
            final = await outcome.completion
        else:
            final = outcome

        stdout = getattr(final, "stdout", "")
        stderr = getattr(final, "stderr", "")
        exit_code = getattr(final, "exit_code", None)
        success = getattr(final, "success", False)
        session_id = getattr(final, "session_id", None)

        if stdout:
            streamed_lines.extend([line for line in stdout.splitlines() if line])
        if stderr:
            streamed_lines.extend([f"ERR: {line}" for line in stderr.splitlines() if line])

        if hasattr(final, "command"):
            _log_progress(
                context,
                f"Completed {self.vendor.value} command: {' '.join(getattr(final, 'command'))}",
                action=ProgressAction.FINISHED,
            )

        if session_id:
            _log_progress(
                context,
                f"Session {session_id} finished with status {exit_code}",
                action=ProgressAction.FINISHED,
            )

        return CLIExecutionResult(
            vendor=self.vendor,
            instruction=instruction,
            streamed_output=streamed_lines,
            exit_code=exit_code,
            success=success,
            diff_preview=diff_preview,
        )

    def _build_invocation(self, adapter: Any, instruction: str):
        workspace = self.workspace
        if self.vendor is Vendor.CODEX:
            return adapter.exec(prompt=instruction, stream=True, cd=workspace, json_output=True)
        if self.vendor is Vendor.CLAUDE:
            return adapter.command(prompt=instruction, stream=True, workspace=workspace)
        if self.vendor is Vendor.GROK:
            return adapter.run(prompt=instruction, stream=True, directory=workspace)
        if self.vendor is Vendor.ANTIGRAVITY:
            return adapter.command(prompt=instruction, stream=True, workspace=workspace)
        if self.vendor is Vendor.KIMI:
            return adapter.run(prompt=instruction, stream=True, directory=workspace)
        if self.vendor is Vendor.QWEN:
            command: Sequence[str] = ["run", instruction]
            if workspace:
                command = ["run", f"cd {Path(workspace).resolve()}", instruction]
            return adapter.slash(command=command, stream=True, workspace=workspace)
        raise ValueError(f"Unsupported vendor {self.vendor}")
