import json
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import pytest

from mcp_agent.tools.antigravity_tool import (
    AntigravityCommandResult,
    AntigravityStreamEvent,
    AntigravityStreamingResult,
    AntigravityTool,
)


pytestmark = pytest.mark.anyio


def _write_fake_cli(tmp_path: Path) -> Path:
    script = tmp_path / "antigravity.py"
    script.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import argparse
            import json
            import sys
            import time

            parser = argparse.ArgumentParser()
            parser.add_argument("--workspace")
            parser.add_argument("--project")
            parser.add_argument("--config")

            subparsers = parser.add_subparsers(dest="cmd")

            command = subparsers.add_parser("command")
            command.add_argument("prompt")
            command.add_argument("--agent")
            command.add_argument("--stream", action="store_true")
            command.add_argument("--json", dest="json_output", action="store_true")
            command.add_argument("--params")

            plan = subparsers.add_parser("plan")
            plan.add_argument("description")
            plan.add_argument("--stream", action="store_true")
            plan.add_argument("--out")

            review = subparsers.add_parser("review")
            review.add_argument("--file")
            review.add_argument("--stream", action="store_true")

            refactor = subparsers.add_parser("refactor")
            refactor.add_argument("--scope")
            refactor.add_argument("--stream", action="store_true")

            test_cmd = subparsers.add_parser("test")
            test_cmd.add_argument("--target")
            test_cmd.add_argument("--stream", action="store_true")

            doc = subparsers.add_parser("doc")
            doc.add_argument("--file")
            doc.add_argument("--format")
            doc.add_argument("--stream", action="store_true")

            agent = subparsers.add_parser("agent")
            agent.add_argument("--list", action="store_true")
            agent.add_argument("--call")
            agent.add_argument("--args")
            agent.add_argument("--stream", action="store_true")

            mcp = subparsers.add_parser("mcp")
            mcp.add_argument("--register")
            mcp.add_argument("--unregister")
            mcp.add_argument("--list", action="store_true")
            mcp.add_argument("--invoke")
            mcp.add_argument("--config")
            mcp.add_argument("--args")
            mcp.add_argument("--stream", action="store_true")

            args = parser.parse_args()

            if args.cmd == "command":
                if args.prompt == "sleep":
                    time.sleep(1.0)
                payload = {"prompt": args.prompt, "agent": args.agent, "workspace": args.workspace, "project": args.project}
                text = json.dumps(payload) if args.json_output else f"{args.prompt}:{args.agent}:{args.workspace}:{args.project}"
                if args.stream:
                    for part in ["start", text, "done"]:
                        print(part, flush=True)
                        time.sleep(0.01)
                else:
                    print(text)
            elif args.cmd == "plan":
                if args.stream:
                    print("planning", flush=True)
                    time.sleep(0.01)
                    print(f"plan:{args.description}", flush=True)
                else:
                    print(f"plan:{args.description}")
                if args.out:
                    Path(args.out).write_text(args.description)
            elif args.cmd == "review":
                print(f"review:{args.file}:{args.workspace}")
            elif args.cmd == "refactor":
                if args.scope:
                    print(f"refactor:{args.scope}")
                else:
                    print("refactor:all")
            elif args.cmd == "test":
                target = args.target or "all"
                print(f"tests:{target}")
            elif args.cmd == "doc":
                print(json.dumps({"file": args.file, "format": args.format}))
            elif args.cmd == "agent":
                if args.list:
                    agents = ["builder", "reviewer"]
                    if args.stream:
                        for agent_name in agents:
                            print(json.dumps({"name": agent_name}), flush=True)
                    else:
                        print(json.dumps(agents))
                elif args.call:
                    print(args.args or "{}")
            elif args.cmd == "mcp":
                if args.register:
                    print(f"registered:{args.register}:{args.config}")
                elif args.unregister:
                    print(f"unregistered:{args.unregister}")
                elif args.list:
                    servers = ["alpha", "beta"]
                    if args.stream:
                        for server in servers:
                            print(json.dumps({"name": server}), flush=True)
                    else:
                        print(json.dumps(servers))
                elif args.invoke:
                    params = json.loads(args.args or "{}")
                    print(json.dumps({"tool": args.invoke, "params": params, "config": args.config}))
            else:
                print("unknown")
            """
        ),
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def fake_cli(tmp_path: Path) -> Path:
    return _write_fake_cli(tmp_path)


@pytest.mark.anyio
async def test_command_one_shot(fake_cli: Path, tmp_path: Path):
    tool = AntigravityTool(binary=str(fake_cli), workspace=str(tmp_path), project="demo")
    result = await tool.command("build", agent="full", json_output=True)

    assert isinstance(result, AntigravityCommandResult)
    assert result.success
    parsed = json.loads(result.stdout)
    assert parsed["prompt"] == "build"
    assert parsed["agent"] == "full"
    assert parsed["workspace"] == str(tmp_path)
    assert parsed["project"] == "demo"


@pytest.mark.anyio
async def test_plan_streaming(fake_cli: Path):
    tool = AntigravityTool(binary=str(fake_cli))
    streamed = await tool.plan("ship", stream=True)

    assert isinstance(streamed, AntigravityStreamingResult)
    events: list[str] = []
    async for event in streamed.stream:
        assert isinstance(event, AntigravityStreamEvent)
        events.append(event.text)

    completion = await streamed.completion
    assert completion.success
    assert events == ["planning", "plan:ship"]


@pytest.mark.anyio
async def test_review_and_refactor(fake_cli: Path, tmp_path: Path):
    tool = AntigravityTool(binary=str(fake_cli), workspace=str(tmp_path))
    review_result = await tool.review(file="README.md")
    assert review_result.success
    assert "README.md" in review_result.stdout

    refactor_result = await tool.refactor(scope="src/")
    assert refactor_result.success
    assert "src/" in refactor_result.stdout


@pytest.mark.anyio
async def test_mcp_register_and_invoke(fake_cli: Path, tmp_path: Path):
    config_file = tmp_path / "config.json"
    config_file.write_text("{}")
    tool = AntigravityTool(binary=str(fake_cli), workspace=str(tmp_path))

    register = await tool.mcp_register("alpha", config=str(config_file))
    assert register.success
    assert "registered:alpha" in register.stdout

    invoke = await tool.mcp_invoke("db.schema", params={"db": "main"}, config=str(config_file))
    assert invoke.success
    payload = json.loads(invoke.stdout)
    assert payload == {"tool": "db.schema", "params": {"db": "main"}, "config": str(config_file)}


@pytest.mark.anyio
async def test_agent_listing_stream(fake_cli: Path):
    tool = AntigravityTool(binary=str(fake_cli))
    streamed = await tool.agent(list_agents=True, stream=True)

    names: list[str] = []
    async for event in streamed.stream:
        assert event.kind == "stdout"
        names.append(event.parsed["name"] if event.parsed else event.text)

    result = await streamed.completion
    assert result.success
    assert names == ["builder", "reviewer"]


@pytest.mark.anyio
async def test_timeout_and_missing_binary(tmp_path: Path):
    cli = _write_fake_cli(tmp_path)
    tool = AntigravityTool(binary=str(cli), default_timeout=0.01)
    timeout_result = await tool.command("sleep")
    assert not timeout_result.success
    assert "timed out" in timeout_result.stderr.lower()

    missing = AntigravityTool(binary="antigravity-not-installed")
    missing_result = await missing.command("noop")
    assert not missing_result.success
    assert "not found" in (missing_result.error or "")

