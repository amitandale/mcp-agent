from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import List

from mcp_agent.agents.agent_spec import AgentSpec
from mcp_agent.core.context import Context
from mcp_agent.executor.workflow import Workflow, WorkflowResult
from mcp_agent.logging.event_progress import ProgressAction
from mcp_agent.workflows.factory import create_agent
from mcp_agent.workflows.implementation_workflow.app import app
from mcp_agent.workflows.implementation_workflow.models import (
    BranchCommitResult,
    CIStatus,
    CLIExecutionResult,
    DiffSummary,
    PRImplementationOutput,
    PRImplementationRequest,
    PullRequestResult,
    RepositoryCheckoutResult,
    Vendor,
)
from mcp_agent.workflows.implementation_workflow.vendor import VendorCLIRunner


GIT_AGENT_SPEC = AgentSpec(
    name="github_mcp_tool",
    instruction=(
        "Use the github-mcp-tool to manage repository checkout, branching, committing, and PR creation."
    ),
    server_names=["github-mcp-tool"],
)


def _emit_progress(context: Context, action: ProgressAction, message: str) -> None:
    try:
        context.logger.info(
            message,
            data={"progress_action": action, "target": "implementation_workflow"},
        )
    except Exception:
        pass


@app.workflow_task()
async def checkout_repository(payload: PRImplementationRequest) -> RepositoryCheckoutResult:
    context = app.context
    workspace = tempfile.mkdtemp(prefix="implementation-workflow-")
    git_agent = create_agent(spec=GIT_AGENT_SPEC, context=context)

    checkout_log: List[str] = []
    async with git_agent:
        _emit_progress(context, ProgressAction.STARTING, "Cloning repository via github-mcp-tool")
        clone = await git_agent.call_tool(
            "clone_repository",
            {
                "repo_url": payload.repo_url,
                "branch": payload.working_branch,
                "workspace": workspace,
            },
            server_name="github-mcp-tool",
        )
        for item in clone.content:
            text = getattr(item, "text", None) or getattr(getattr(item, "data", None), "get", lambda *_: None)("text")
            if text:
                checkout_log.append(text)
                _emit_progress(context, ProgressAction.RUNNING, text)

        await git_agent.call_tool(
            "checkout_branch",
            {"branch": payload.working_branch, "workspace": workspace},
            server_name="github-mcp-tool",
        )

    _emit_progress(context, ProgressAction.FINISHED, f"Repository ready in {workspace}")
    return RepositoryCheckoutResult(
        workspace_path=workspace,
        branch=payload.working_branch,
        checkout_log=checkout_log,
    )


@app.workflow_task()
async def execute_vendor_cli(
    *, payload: PRImplementationRequest, workspace_path: str
) -> CLIExecutionResult:
    context = app.context
    runner = VendorCLIRunner(payload.vendor, workspace=workspace_path)
    return await runner.run(instruction=payload.pr_text, context=context)


@app.workflow_task()
async def create_commit(
    *, payload: PRImplementationRequest, workspace_path: str
) -> BranchCommitResult:
    context = app.context
    git_agent = create_agent(spec=GIT_AGENT_SPEC, context=context)
    async with git_agent:
        commit_message = f"{payload.pr_title}"
        _emit_progress(context, ProgressAction.RUNNING, "Staging modified files")
        await git_agent.call_tool(
            "stage_all",
            {"workspace": workspace_path},
            server_name="github-mcp-tool",
        )
        _emit_progress(context, ProgressAction.RUNNING, "Creating commit")
        commit_result = await git_agent.call_tool(
            "commit_changes",
            {"workspace": workspace_path, "message": commit_message},
            server_name="github-mcp-tool",
        )
        commit_sha = None
        for item in commit_result.content:
            text = getattr(item, "text", None)
            if text and "sha" in text.lower():
                commit_sha = text.split()[-1]
        _emit_progress(context, ProgressAction.RUNNING, "Pushing branch")
        await git_agent.call_tool(
            "push_branch",
            {
                "workspace": workspace_path,
                "branch": payload.working_branch,
            },
            server_name="github-mcp-tool",
        )

    return BranchCommitResult(
        branch_name=payload.working_branch,
        commit_message=commit_message,
        commit_sha=commit_sha,
        pushed=True,
    )


@app.workflow_task()
async def create_pull_request(
    *, payload: PRImplementationRequest, commit: BranchCommitResult
) -> PullRequestResult:
    context = app.context
    git_agent = create_agent(spec=GIT_AGENT_SPEC, context=context)
    async with git_agent:
        pr_result = await git_agent.call_tool(
            "create_pull_request",
            {
                "title": payload.pr_title,
                "body": payload.pr_text,
                "branch": commit.branch_name,
                "draft": True,
            },
            server_name="github-mcp-tool",
        )

    pr_number = None
    pr_url = None
    for item in pr_result.content:
        text = getattr(item, "text", None)
        if text and text.startswith("http"):
            pr_url = text
        if text and text.lower().startswith("pr"):
            fragments = text.split()
            if len(fragments) > 1 and fragments[1].isdigit():
                pr_number = int(fragments[1])

    _emit_progress(context, ProgressAction.FINISHED, "Draft pull request created")
    return PullRequestResult(pr_number=pr_number, pr_url=pr_url, draft=True)


@app.workflow_task()
async def monitor_ci(pr: PullRequestResult) -> CIStatus:
    context = app.context
    git_agent = create_agent(spec=GIT_AGENT_SPEC, context=context)
    logs: List[str] = []
    errors: List[str] = []
    status = "pending"

    async with git_agent:
        _emit_progress(context, ProgressAction.RUNNING, "Polling CI status")
        ci_result = await git_agent.call_tool(
            "watch_ci",
            {"pr_number": pr.pr_number},
            server_name="github-mcp-tool",
        )
        for item in ci_result.content:
            text = getattr(item, "text", None)
            if text:
                logs.append(text)
                _emit_progress(context, ProgressAction.RUNNING, text)
                if "error" in text.lower():
                    errors.append(text)
                if "pass" in text.lower():
                    status = "passed"
                elif "fail" in text.lower():
                    status = "failed"

    return CIStatus(status=status, logs=logs, errors=errors)


@app.workflow_task()
async def fix_with_deep_orchestrator(
    *,
    ci_status: CIStatus,
    workspace_path: str,
    payload: PRImplementationRequest,
    max_attempts: int = 3,
) -> List[str]:
    from mcp_agent.workflows.deep_orchestrator import DeepOrchestrator
    from mcp_agent.workflows.deep_orchestrator.config import DeepOrchestratorConfig

    context = app.context
    attempts: List[str] = []

    def llm_factory(agent):
        from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

        return OpenAIAugmentedLLM(agent=agent, context=context)

    orchestrator = DeepOrchestrator(
        llm_factory=llm_factory,
        config=DeepOrchestratorConfig(),
        context=context,
    )

    for attempt in range(1, max_attempts + 1):
        if ci_status.status == "passed":
            break
        prompt = (
            "Analyze the CI logs and produce targeted fixes for the failure. "
            f"Attempt {attempt}/{max_attempts}. Logs:\n" + "\n".join(ci_status.errors or ci_status.logs)
        )
        _emit_progress(context, ProgressAction.RUNNING, f"Deep orchestrator fix attempt {attempt}")
        result = await orchestrator.generate(prompt)
        attempts.append(str(result))
    return attempts


@app.workflow_task()
async def summarize_diff(workspace_path: str) -> DiffSummary:
    context = app.context
    git_agent = create_agent(spec=GIT_AGENT_SPEC, context=context)
    files: dict[str, dict[str, int]] = {}
    diff_text = None

    async with git_agent:
        stat_result = await git_agent.call_tool(
            "git_diff_stat",
            {"workspace": workspace_path},
            server_name="github-mcp-tool",
        )
        for item in stat_result.content:
            text = getattr(item, "text", None)
            if not text:
                continue
            parts = text.split()
            if len(parts) >= 3 and parts[1].isdigit() and parts[2].isdigit():
                files[parts[0]] = {"added": int(parts[1]), "deleted": int(parts[2])}
        diff_result = await git_agent.call_tool(
            "git_diff_full",
            {"workspace": workspace_path},
            server_name="github-mcp-tool",
        )
        full_lines: List[str] = []
        for item in diff_result.content:
            text = getattr(item, "text", None)
            if text:
                full_lines.append(text)
        if full_lines:
            diff_text = "\n".join(full_lines)

    return DiffSummary(files=files, full_diff=diff_text)


@app.workflow
class ImplementationWorkflow(Workflow[PRImplementationOutput]):
    @app.workflow_run
    async def run(self, payload: PRImplementationRequest) -> WorkflowResult[PRImplementationOutput]:
        context = self.context
        _emit_progress(context, ProgressAction.STARTING, "Starting Implementation Workflow V1")

        checkout = await context.executor.execute(checkout_repository, payload)
        implementation = await context.executor.execute(
            execute_vendor_cli, payload=payload, workspace_path=checkout.workspace_path
        )
        commit = await context.executor.execute(
            create_commit, payload=payload, workspace_path=checkout.workspace_path
        )
        pull_request = await context.executor.execute(
            create_pull_request, payload=payload, commit=commit
        )
        ci_status = await context.executor.execute(monitor_ci, pr=pull_request)

        fix_attempts: List[str] = []
        if ci_status.status == "failed":
            fix_attempts = await context.executor.execute(
                fix_with_deep_orchestrator,
                ci_status=ci_status,
                workspace_path=checkout.workspace_path,
                payload=payload,
            )

        diff = await context.executor.execute(summarize_diff, workspace_path=checkout.workspace_path)

        success = ci_status.status == "passed"
        _emit_progress(context, ProgressAction.FINISHED, "Implementation workflow completed")

        return WorkflowResult(
            output=PRImplementationOutput(
                checkout=checkout,
                implementation=implementation,
                commit=commit,
                pull_request=pull_request,
                ci_status=ci_status,
                diff=diff,
                fix_attempts=fix_attempts,
                success=success,
            )
        )


@app.workflow(name="implementation_workflow_v1")
def register_workflow() -> Workflow[PRImplementationOutput]:
    return ImplementationWorkflow()
