# VibeCoding PR Orchestrator

The VibeCoding PR Orchestrator implements a production-grade multi-agent workflow for
analyzing GitHub pull requests. The workflow coordinates five specialized agents over a
fifteen-stage pipeline to deliver actionable reviews, remediation patches, and a final
executive summary.

## Workflow Stages

| Stage | Name | Responsible Agent | Description |
| --- | --- | --- | --- |
| 1 | `pr_metadata_extraction` | `vibe_pr_analyzer` | Collect PR metadata, linked issues, and commit summaries. |
| 2 | `diff_analysis` | `vibe_pr_analyzer` | Assess diff size, risky files, and impact surface. |
| 3 | `syntax_tree_analysis` | `vibe_pr_analyzer` | Generate syntax trees for all touched files. |
| 4 | `ast_pattern_matching` | `vibe_code_reviewer` | Detect risky AST patterns and code smells. |
| 5 | `dependency_graph_analysis` | `vibe_dependency_checker` | Evaluate dependency updates and compatibility. |
| 6 | `code_smell_detection` | `vibe_code_reviewer` | Run repository-level code smell checks. |
| 7 | `type_checking` | `vibe_code_reviewer` | Perform LSP-powered type and interface validation. |
| 8 | `security_scan` | `vibe_code_reviewer` | Check for secrets and vulnerability indicators. |
| 9 | `performance_assessment` | `vibe_code_reviewer` | Flag potential performance regressions. |
| 10 | `code_style_normalization` | `vibe_code_reviewer` | Validate formatting and style consistency. |
| 11 | `documentation_check` | `vibe_pr_analyzer` | Confirm documentation updates match behavior. |
| 12 | `test_coverage_analysis` | `vibe_code_reviewer` | Estimate coverage impact and missing scenarios. |
| 13 | `patch_generation` | `vibe_patch_generator` | Produce targeted remediation patches. |
| 14 | `patch_validation` | `vibe_patch_generator` | Validate generated patches against workflow goals. |
| 15 | `report_generation` | `vibe_orchestrator` | Synthesize the complete multi-agent report. |

## Agents and MCP Servers

| Agent | Description | MCP Servers |
| --- | --- | --- |
| `vibe_pr_analyzer` | Bootstraps the workflow with PR metadata and diff context. | `github`, `code-index`, `tree-sitter`, `filesystem` |
| `vibe_code_reviewer` | Performs in-depth code review and static analysis. | `code-index`, `ast-grep`, `sourcerer`, `lsp` |
| `vibe_dependency_checker` | Audits dependency updates and risk. | `dependency-management`, `github`, `filesystem` |
| `vibe_patch_generator` | Creates and validates remediation patches. | `tree-sitter`, `ast-grep`, `filesystem` |
| `vibe_orchestrator` | Coordinates stages, maintains budgets, and produces reports. | All workflow servers |

## State Visibility and Budget Tracking

The orchestrator exposes state suitable for monitoring dashboards:

- **Stage status**: Each stage tracks pending/running/completed/failed with timestamps.
- **Budget usage**: Token, cost, and time budgets are updated after every stage.
- **Task queue**: Dependency-aware view of completed, pending, and failed stages.

The companion `VibeCodingOrchestratorMonitor` class provides simple helpers to consume
these snapshots for CLI dashboards or tests.

## Usage Example

```python
import asyncio
from mcp_agent.app import MCPApp
from mcp_agent.workflows.vibe_coding.vibe_coding_orchestrator import (
    VibeCodingOrchestrator,
)

app = MCPApp(name="vibe_coding_orchestrator")

@app.workflow
class Workflow(VibeCodingOrchestrator):
    pass


async def main() -> None:
    async with app.run() as running_app:
        workflow = await Workflow.create(context=running_app.context)
        result = await workflow.run(pr_url="https://github.com/example/repo/pull/42")
        running_app.logger.info("Summary", data=result.value["summary"])


if __name__ == "__main__":
    asyncio.run(main())
```

Ensure the `mcp_agent.config.yaml` file declares all required MCP servers before running
the workflow. Provide credentials in `mcp_agent.secrets.yaml` (see the example file at
the repository root).
