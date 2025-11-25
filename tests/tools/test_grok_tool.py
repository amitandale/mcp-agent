import sys

import pytest

from mcp_agent.tools.grok_tool import (
    GrokCommandResult,
    GrokStreamEvent,
    GrokStreamingResult,
    GrokTool,
)


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_run_builds_full_command(monkeypatch):
    tool = GrokTool()

    captured: dict[str, list[str] | dict[str, str]] = {}

    async def fake_run_command(
        args, *, stream, timeout, parse_json_stream=False, require_api_key=True, env_overrides=None
    ):
        captured["args"] = args
        captured["env"] = env_overrides or {}
        return GrokCommandResult(command=args, success=True)

    monkeypatch.setattr(tool, "_run_command", fake_run_command)

    await tool.run(
        prompt="do it",
        directory="/repo",
        api_key="token",
        base_url="https://api.grok",
        model="grok-3",
        max_tool_rounds=50,
        prefer_short_flags=True,
    )

    assert captured["args"] == [
        "grok",
        "-d",
        "/repo",
        "-k",
        "token",
        "-u",
        "https://api.grok",
        "-m",
        "grok-3",
        "-p",
        "do it",
        "--max-tool-rounds",
        "50",
    ]


@pytest.mark.anyio
async def test_missing_api_key_raises():
    tool = GrokTool()

    with pytest.raises(ValueError):
        await tool.run(prompt="hi")


@pytest.mark.anyio
async def test_streaming_events(monkeypatch):
    tool = GrokTool(binary=sys.executable, env={"GROK_API_KEY": "token"})

    statements = "import time\nprint('first')\ntime.sleep(0.01)\nprint('second')"
    streamed = await tool.run_raw(
        "-u",
        "-c",
        statements,
        stream=True,
        parse_json_stream=False,
        require_api_key=True,
    )

    assert isinstance(streamed, GrokStreamingResult)

    seen: list[str] = []
    async for event in streamed.stream:
        assert isinstance(event, GrokStreamEvent)
        seen.append(event.text)

    result = await streamed.completion
    assert result.success
    assert seen == ["first", "second"]


@pytest.mark.anyio
async def test_mcp_add_arguments(monkeypatch):
    tool = GrokTool(api_key="token")

    recorded: list[str] = []

    async def fake_run_command(
        args, *, stream, timeout, parse_json_stream=False, require_api_key=True, env_overrides=None
    ):
        recorded.extend(args)
        return GrokCommandResult(command=args, success=True)

    monkeypatch.setattr(tool, "_run_command", fake_run_command)

    await tool.mcp_add(
        "db",
        transport="http",
        command="python",
        url="http://localhost:4040",
        args=["--debug"],
        env={"API_KEY": "abc", "DEBUG": "1"},
    )

    assert recorded == [
        "grok",
        "--api-key",
        "token",
        "mcp",
        "add",
        "db",
        "--transport",
        "http",
        "--command",
        "python",
        "--url",
        "http://localhost:4040",
        "--args",
        "--debug",
        "--env",
        "API_KEY=abc",
        "--env",
        "DEBUG=1",
    ]


@pytest.mark.anyio
async def test_mcp_add_json_inline(monkeypatch):
    tool = GrokTool(api_key="token")

    captured: list[str] = []

    async def fake_run_command(
        args, *, stream, timeout, parse_json_stream=False, require_api_key=True, env_overrides=None
    ):
        captured.extend(args)
        return GrokCommandResult(command=args, success=True)

    monkeypatch.setattr(tool, "_run_command", fake_run_command)

    await tool.mcp_add_json("linear", '{"command":"bun","args":["server.js"],"env":{"API_KEY":"key"}}')

    assert captured == [
        "grok",
        "--api-key",
        "token",
        "mcp",
        "add-json",
        "linear",
        '{"command":"bun","args":["server.js"],"env":{"API_KEY":"key"}}',
    ]
