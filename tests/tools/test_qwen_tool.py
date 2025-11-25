import sys

import pytest

from mcp_agent.tools.qwen_tool import (
    QwenCommandResult,
    QwenStreamEvent,
    QwenStreamingResult,
    QwenTool,
)


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_prompt_builds_full_command(monkeypatch):
    tool = QwenTool(
        workspace="/repo",
        api_key="token",
        checkpointing=True,
        include_directories=["src"],
        model="qwen2",
        base_url="https://api",
        mcp_config_file="/cfg.json",
    )

    captured: dict[str, object] = {}

    async def fake_run_command(args, *, stream, timeout, parse_json_stream=False):
        captured["args"] = args
        captured["stream"] = stream
        captured["timeout"] = timeout
        return QwenCommandResult(command=args, success=True)

    monkeypatch.setattr(tool, "_run_command", fake_run_command)

    await tool.prompt(
        "Hello",
        include_directories=["extras"],
        checkpointing=False,
        mcp_config_file="/other.json",
        model="override",
        base_url="https://alt",
        workspace="/tmp",
        timeout=12,
    )

    assert captured["args"] == [
        "qwen",
        "--workspace",
        "/tmp",
        "--model",
        "qwen2",
        "--base-url",
        "https://api",
        "--mcp-config-file",
        "/cfg.json",
        "--checkpointing",
        "--include-directories",
        "src",
        "--include-directories",
        "extras",
        "--mcp-config-file",
        "/other.json",
        "--model",
        "override",
        "--base-url",
        "https://alt",
        "--prompt",
        "Hello",
    ]
    assert captured["stream"] is False
    assert captured["timeout"] == 12


@pytest.mark.anyio
async def test_custom_command_loads_from_workspace(monkeypatch, tmp_path):
    commands_dir = tmp_path / ".qwen" / "commands"
    commands_dir.mkdir(parents=True)
    command_file = commands_dir / "refactor.toml"
    command_file.write_text("prompt = \"Refactor {{args}}\"\n")

    tool = QwenTool(workspace=str(tmp_path), api_key="token")

    captured: dict[str, object] = {}

    async def fake_prompt(prompt: str, **kwargs):
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return QwenCommandResult(command=["qwen"], success=True)

    monkeypatch.setattr(tool, "prompt", fake_prompt)

    await tool.run_custom("/refactor", args="file.py")

    assert captured["prompt"] == "Refactor file.py"
    assert captured["kwargs"] == {"workspace": None, "stream": False, "timeout": None}


@pytest.mark.anyio
async def test_resolve_api_key_from_env_file(monkeypatch, tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("QWEN_API_KEY=from-dotenv\n")

    monkeypatch.delenv("QWEN_API_KEY", raising=False)

    tool = QwenTool(workspace=str(tmp_path))

    assert tool._resolve_api_key() == "from-dotenv"


@pytest.mark.anyio
async def test_streaming_events(monkeypatch):
    tool = QwenTool(binary=sys.executable, api_key="token")

    script = "import time\nprint('first')\ntime.sleep(0.01)\nprint('second')"
    streamed = await tool.run_raw(
        "-u",
        "-c",
        script,
        stream=True,
    )

    assert isinstance(streamed, QwenStreamingResult)

    seen: list[str] = []
    async for event in streamed.stream:
        assert isinstance(event, QwenStreamEvent)
        seen.append(event.text)

    result = await streamed.completion
    assert result.success
    assert seen == ["first", "second"]
