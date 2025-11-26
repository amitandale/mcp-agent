# Implementation Workflow V1

This workflow exposes the PR Implementation Workflow V1 through the MCP entry point so UI clients can drive the end-to-end PR automation pipeline over Server-Sent Events.

## Overview
- **Entry point:** `implementation_workflow_v1` registered on the package `app`.
- **Input:** structured payload with `pr_title`, `pr_text`, `repo_url`, `working_branch`, and `vendor` (codex/claude/grok/antigravity/kimi/qwen).
- **Steps:** repository checkout, vendor CLI execution, branch + commit, draft PR creation, CI monitoring, optional deep-orchestrator fix loop, diff summary, final payload assembly.
- **Streaming:** every task emits progress logs annotated with `progress_action` for SSE consumers, and vendor CLI output is streamed line-by-line when the underlying adapter supports streaming.

## Usage

```python
from mcp_agent.workflows.implementation_workflow.workflow import register_workflow, ImplementationWorkflow
from mcp_agent.workflows.implementation_workflow.models import PRImplementationRequest, Vendor
from mcp_agent.workflows.implementation_workflow.app import app

request = PRImplementationRequest(
    pr_title="Add SSE-enabled PR workflow",
    pr_text="Implementation instructions here",
    repo_url="https://github.com/example/repo",
    working_branch="main",
    vendor=Vendor.CLAUDE,
)

async with app.run():
    workflow: ImplementationWorkflow = register_workflow()  # type: ignore[assignment]
    result = await workflow.run(request)
    print(result.output.model_dump())
```

The workflow expects the `github-mcp-tool` MCP server to provide repo/branch/commit/PR/CI tooling, and the selected vendor CLI binaries to be available on `PATH`. The deep orchestrator fix loop requires LLM credentials configured in `mcp_agent.secrets.yaml`.
