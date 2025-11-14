"""Entry point for running the VibeCoding PR orchestrator workflow manually."""

from __future__ import annotations

import asyncio

from mcp_agent.app import MCPApp
from mcp_agent.workflows.vibe_coding.vibe_coding_orchestrator import (
    VibeCodingOrchestrator,
    VibeCodingOrchestratorMonitor,
)

app = MCPApp(name="vibe_coding_pr_orchestrator")


@app.workflow
class Workflow(VibeCodingOrchestrator):
    """Expose the orchestrator as an MCP workflow."""

    pass


async def main() -> None:
    """Run the orchestrator end-to-end and print a concise status report."""

    async with app.run() as running_app:
        workflow = await Workflow.create(context=running_app.context)
        result = await workflow.run(pr_url="https://github.com/example/repo/pull/1")

        monitor = VibeCodingOrchestratorMonitor(workflow)
        running_app.logger.info("VibeCoding summary", data=result.value["summary"])
        running_app.logger.info("Budget", data=monitor.progress()["budget"])


if __name__ == "__main__":
    asyncio.run(main())
