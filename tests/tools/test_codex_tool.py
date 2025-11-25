import asyncio
import json
import sys

import pytest

from mcp_agent.tools.codex_tool import (
    CodexCommandResult,
    CodexStreamEvent,
    CodexStreamingResult,
    CodexTool,
)


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_exec_non_stream_success():
    tool = CodexTool(binary=sys.executable)
    result = await tool.run_raw("-c", "print('ok')")

    assert isinstance(result, CodexCommandResult)
    assert result.success
    assert "ok" in result.stdout
    assert result.exit_code == 0


@pytest.mark.anyio
async def test_streaming_yields_events_and_completion():
    tool = CodexTool(binary=sys.executable)
    statements = "import time\nprint('first')\ntime.sleep(0.01)\nprint('second')"
    streamed = await tool.run_raw("-u", "-c", statements, stream=True)

    assert isinstance(streamed, CodexStreamingResult)

    seen: list[str] = []
    async for event in streamed.stream:
        assert isinstance(event, CodexStreamEvent)
        seen.append(event.text)

    result = await streamed.completion
    assert result.success
    assert seen == ["first", "second"]


@pytest.mark.anyio
async def test_json_streaming_parses_objects():
    tool = CodexTool(binary=sys.executable)
    script = "import json\nprint(json.dumps({'step': 1}))\nprint(json.dumps({'step': 2}))"
    streamed = await tool.run_raw("-u", "-c", script, stream=True, parse_json_stream=True)

    parsed_steps = []
    async for event in streamed.stream:
        parsed_steps.append(event.parsed)

    result = await streamed.completion
    assert result.success
    assert parsed_steps == [{"step": 1}, {"step": 2}]


@pytest.mark.anyio
async def test_timeout_kills_process():
    tool = CodexTool(binary=sys.executable, default_timeout=0.01)
    result = await tool.run_raw("-c", "import time; time.sleep(1)")

    assert not result.success
    assert result.exit_code != 0
    assert "timed out" in result.stderr.lower()


@pytest.mark.anyio
async def test_missing_binary_returns_error():
    tool = CodexTool(binary="codex-cli-not-installed")
    result = await tool.run_raw("--version")

    assert not result.success
    assert result.error
    assert "not found" in result.error

