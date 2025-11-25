import json
import sys

import pytest

from mcp_agent.tools.kimi_tool import (
    KimiCommandResult,
    KimiStreamEvent,
    KimiStreamingResult,
    KimiTool,
)


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_ask_builds_full_command(monkeypatch, tmp_path):
    mcp_path = tmp_path / "mcp.json"
    mcp_path.write_text(json.dumps({"servers": []}))

    tool = KimiTool(workspace="/repo", api_key="token", model="kimi-default")

    captured: dict[str, list[str]] = {}

    async def fake_run_command(
        args, *, stream, timeout, parse_json_stream=False, require_api_key=True, input_text=None
    ):
        captured["args"] = args
        return KimiCommandResult(command=args, success=True)

    monkeypatch.setattr(tool, "_run_command", fake_run_command)

    await tool.ask(
        "What is the status?",
        model="kimi-k2-turbo-preview",
        mcp_config_file=str(mcp_path),
    )

    assert captured["args"] == [
        "kimi",
        "--model",
        "kimi-k2-turbo-preview",
        "--mcp-config-file",
        str(mcp_path),
        "ask",
        "What is the status?",
    ]


@pytest.mark.anyio
async def test_resolves_api_key_from_project_and_global(monkeypatch, tmp_path):
    project_settings = tmp_path / ".kimi"
    project_settings.mkdir()
    (project_settings / "settings.json").write_text(json.dumps({"KIMI_API_KEY": "project-key"}))

    home = tmp_path / "home"
    home.mkdir()
    (home / ".kimi").mkdir(parents=True, exist_ok=True)
    (home / ".kimi" / "user-settings.json").write_text(
        json.dumps({"KIMI_API_KEY": "global-key"})
    )

    dotenv = tmp_path / ".env"
    dotenv.write_text("KIMI_API_KEY=dotenv-key\n")

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("KIMI_API_KEY", raising=False)

    tool = KimiTool(workspace=str(tmp_path), dotenv_path=str(dotenv))

    resolved = tool._resolve_api_key(None, {})
    assert resolved == "project-key"


@pytest.mark.anyio
async def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    tool = KimiTool()

    with pytest.raises(ValueError):
        await tool.ask("hi")


@pytest.mark.anyio
async def test_validate_mcp_config_errors(tmp_path):
    tool = KimiTool()

    with pytest.raises(FileNotFoundError):
        tool._validate_mcp_config_file(str(tmp_path / "missing.json"))

    invalid = tmp_path / "invalid.json"
    invalid.write_text("not-json")

    with pytest.raises(ValueError):
        tool._validate_mcp_config_file(str(invalid))


@pytest.mark.anyio
async def test_streaming_events(monkeypatch):
    tool = KimiTool(binary=sys.executable, env={"KIMI_API_KEY": "token"})

    script = "import time\nprint('first')\ntime.sleep(0.01)\nprint('second')"
    streamed = await tool.run_raw(
        "-u",
        "-c",
        script,
        stream=True,
        parse_json_stream=False,
        require_api_key=True,
    )

    assert isinstance(streamed, KimiStreamingResult)

    seen: list[str] = []
    async for event in streamed.stream:
        assert isinstance(event, KimiStreamEvent)
        seen.append(event.text)

    result = await streamed.completion
    assert result.success
    assert seen == ["first", "second"]
