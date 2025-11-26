# Contribution guardrails for mcp-agent

These instructions apply to the entire repository. They codify the core mcp-agent architecture so new code reuses existing primitives instead of reimplementing or bypassing them. Keep the longer reference in `agents.md` handy for deep examples and placement rules.

## Source-of-truth architecture
- Production code lives under `src/mcp_agent/**`; `examples/**` are reference-only and must not contain production logic.
- Reuse the runtime primitives that already exist: `Agent`/`AgentSpec`, workflows built on `executor.workflow.Workflow`, MCP client/server adapters, `MCPApp`, and the typed config loader. Do **not** ship bespoke CLIs, ad-hoc transports, or custom agent runtimes.
- Access external tools through **MCP servers declared in config** and attached to agents via `server_names=[...]`. Do **not** replace server access with local function tools when a server exists.
- When adding function-tools, prefer registering plain functions on `AgentSpec` and keep them minimal; domain logic belongs with the agents that need it, not in shared infra.
- Follow the directory-level `AGENTS.md` files for scoped rules before touching code in that folder.

## Workflow and agent registration
- Workflows must subclass `mcp_agent.executor.workflow.Workflow` (or the provided helpers) and be registered via `MCPApp`/`@app.workflow` entrypoints instead of standalone scripts.
- Agents should be constructed with shared factory helpers (`create_agent`, config-driven `SPEC`) and explicitly declare their MCP servers with `server_names`. No bespoke agent wiring.

## Config, secrets, and servers
- Declare MCP servers in `mcp_agent.config.yaml` using the shared schema; never hardcode commands, tokens, or URLs in code.
- Secrets stay out of version control—use the gitignored secrets file referenced by the schema.
- Give each agent only the minimal server set it needs; avoid "god" agents wired to every server.

## Testing and examples
- Mirror tests under `tests/` for any new production module.
- Use `examples/**` only as learning references; port patterns into `src/mcp_agent/**` with the existing APIs rather than copying code verbatim.

## Vibe coding system baseline
We are using this repository as the **core** for a Vibe Coding system with full CI/CD. The system must let users run vibecoding sessions against state-of-the-art code CLIs (Codex, Claude, Antigravity, Grok, Kimi, Qwen). Assume every PR is in service of this system: keep changes aligned with the mcp-agent architecture above, expose capabilities through the existing MCP surfaces, and avoid side-channel runtimes or bespoke wiring.

## 1) Project structure (what lives where)
For each folder under `src/mcp_agent/`, keep production code aligned with its purpose and primary entrypoints:
- `agents/` — Domain-specific agents (and specs) that declare `server_names`. Export `SPEC` and `build(...)` helpers. See `agents/__init__.py` for the base `Agent` and `AgentSpec` types.
- `app.py` — `MCPApp` container plus the `@app.workflow` decorator; the canonical runtime entrypoint for hosting workflows and exposing them over MCP.
- `cli/` — CLI surfaces for running agents/workflows; reuse existing commands instead of new CLIs. `__main__.py` / `main.py` wire into `MCPApp`.
- `config.py` — Typed loader for `mcp_agent.config.yaml` (servers, providers, workflows, agents). Import instead of custom config parsing.
- `console.py` — Developer REPL and interactive console helper wired to the shared runtime.
- `core/` — Request context primitives (`Context`, `ContextDependent`), shared exceptions, and base protocols used throughout the stack.
- `data/` — Check-in example assets, scaffolds, and reference configs/scripts that illustrate the architecture; never a place for production logic.
- `elicitation/` — Human-in-the-loop elicitation handlers and types. Use when workflows/agents need structured questions to users.
- `eval/` — Evaluation helpers and quality scoring utilities for workflows/agents. Prefer these over bespoke evaluators.
- `executor/` — Workflow runtime primitives (`Workflow`, `WorkflowResult`, tasks, signals, Temporal adapters). All workflows should subclass the types here.
- `human_input/` — Human input channel abstractions and helpers (prompting, confirmation, responses) used by agents/workflows.
- `logging/` — Structured logging and progress reporting; reuse transports/formatters defined here.
- `mcp/` — MCP protocol plumbing (client proxy, server registry, stdio transport, connection manager). Do not fork transports; configure here.
- `oauth/` — OAuth flows, token stores, and HTTP helpers for auth-enabled MCP servers.
- `server/` — Glue that mounts tools as MCP endpoints and hosts the runtime; reuse adapters instead of rolling new servers.
- `telemetry/` — Usage tracking hooks and metrics emitters.
- `tools/` — Framework adapters (e.g., CrewAI, LangChain). Keep domain-specific logic out; attach only lightweight wrappers registered on agents.
- `tracing/` — Tracing utilities, token counters, and OTEL helpers.
- `utils/` — Shared utilities (content/mime helpers, pydantic filters, tool filtering) reused across modules.
- `workflows/` — Production workflows organized by domain. Each should subclass `executor.workflow.Workflow` and be registered via `MCPApp`.
- Root `py.typed` — Type-checker marker; keep typings accurate.

## 2) Adding workflows (reuse patterns from examples)
Before writing a new workflow, study the relevant patterns in `src/mcp_agent/data/examples/workflows/` and port (not rewrite) the shape that fits the PR:
- **Router/Intent flows** — For routing requests to specialized agents, review `workflow_router/main.py` and `workflow_intent_classifier/main.py`.
- **Parallel/Swarm** — For concurrent tool/agent calls, see `workflow_parallel/main.py` and `workflow_swarm/main.py`.
- **Orchestrator/Worker** — For coordinator-driven execution with sub-agents, examine `workflow_orchestrator_worker/main.py` and `workflow_deep_orchestrator/main.py`.
- **Evaluator/Optimizer loops** — For evaluation-driven refinement, use `workflow_evaluator_optimizer/main.py` as the template.

Minimal workflow skeleton (subclass + registration) to follow:
```python
from mcp_agent.app import MCPApp
from mcp_agent.executor.workflow import Workflow, WorkflowResult

app = MCPApp()

class ExampleWorkflow(Workflow[str]):
    async def run(self, context) -> WorkflowResult[str]:
        # orchestrate agents/tools here
        return WorkflowResult(output="done")

@app.workflow("example")
def register_workflow() -> Workflow[str]:
    return ExampleWorkflow()
```

## 3) Adding agents (port from examples, declare servers)
Use the agent patterns shown in `examples/usecases/**` (and the workflow examples above) as reference implementations. Always declare `server_names` and export a config-driven builder:
- **Single-purpose agents** — e.g., browser/file/finders in `mcp_browser_agent`, `mcp_basic_slack_agent`, `streamlit_mcp_basic_agent`.
- **Evaluator-backed agents** — e.g., marketing/financial/realtor agents that loop through evaluator/optimizer steps in `mcp_marketing_assistant_agent`, `mcp_financial_analyzer`, `mcp_realtor_agent`.
- **Automation/ops agents** — e.g., GitHub-to-Slack notifier, Supabase migration helper, Playwright CSV exporter in their respective folders.
- **Research/multi-tool agents** — e.g., `mcp_researcher`, `mcp_instagram_gift_advisor`, or orchestrated cohorts in `mcp_financial_analyzer`.

**Function tools (defined under `src/mcp_agent/tools`)** — Port the pattern from `examples/basic/functions/main.py`. Keep functions minimal, register them on the agent, and omit `server_names` when you only use local function tools (add MCP servers to `server_names` only when you actually consume them):
```python
from mcp_agent.agents import AgentSpec, Agent
from mcp_agent.tools.math import add_numbers, multiply_numbers
from mcp_agent.workflows.factory import create_agent

SPEC = AgentSpec(
    name="math_agent",
    instructions="Use the provided math helpers to answer",
    functions=[add_numbers, multiply_numbers],
)

def build(context=None) -> Agent:
    return create_agent(spec=SPEC, context=context)
```

**Function tools — Claude adapter example** — The CLI adapters under `src/mcp_agent/tools/` can also be attached as function tools. Instantiate the adapter and expose a thin async wrapper as the callable you register on the agent:
```python
from mcp_agent.agents import AgentSpec, Agent
from mcp_agent.tools.claude_tool import ClaudeTool
from mcp_agent.workflows.factory import create_agent

_claude = ClaudeTool()

async def run_claude(prompt: str) -> str:
    result = await _claude.command(prompt)
    return result.stdout

SPEC = AgentSpec(
    name="claude_runner",
    instructions="Use the Claude CLI to handle code tasks",
    functions=[run_claude],
)

def build(context=None) -> Agent:
    return create_agent(spec=SPEC, context=context)
```

**MCP-tools** — Prefer remote tools exposed as MCP servers declared in config. Attach them via `server_names` only:
```python
from mcp_agent.agents import AgentSpec, Agent
from mcp_agent.workflows.factory import create_agent

SPEC = AgentSpec(
    name="researcher",
    instructions="Research using search + browser",
    server_names=["search", "browser", "filesystem"],
)

def build(context=None) -> Agent:
    return create_agent(spec=SPEC, context=context)
```

## 4) Entry point and API exposure
Every workflow/agent must be hosted through a single `MCPApp` entrypoint and exposed via the existing API surfaces (MCP server adapters/CLI). Do not spin up bespoke FastAPI/Flask/etc. runtimes; instead register workflows with `@app.workflow` and let `server/` and `cli/` glue expose them over MCP, WebSocket, or the provided console.

## 5) Usecase references (analyze before implementing)
Before starting a PR, identify the closest matching use case under `examples/usecases/`, read its README, and mirror its agent/server mapping and workflow shape instead of reinventing. Reference list:
- `fastapi_websocket` — Multi-user chat via FastAPI WebSockets, each user gets an MCP agent session.
- `marimo_mcp_basic_agent` — Marimo notebook agent with fetch + filesystem servers.
- `mcp_basic_slack_agent` — Slack + filesystem agent for workspace automation.
- `mcp_browser_agent` — Console browser controller using Puppeteer MCP server.
- `mcp_financial_analyzer` — Multi-agent orchestrator for financial research/reporting.
- `mcp_github_to_slack_agent` — GitHub PR monitor that summarizes to Slack.
- `mcp_instagram_gift_advisor` — Profile analysis to propose Amazon gift links via Apify + search.
- `mcp_marketing_assistant_agent` — Brand-aware marketing content generator with evaluator loop.
- `mcp_playwright_agent` — Playwright-powered LinkedIn search + CSV export automation.
- `mcp_realtor_agent` — Research/reporting framework adaptable to domain APIs.
- `mcp_researcher` — Research assistant using search, fetch, python, filesystem.
- `mcp_supabase_migration_agent` — Automates Supabase migration type sync and PR creation.
- `reliable_conversation` — Conversation manager with quality control and persistence.
- `streamlit_mcp_basic_agent` — Streamlit UI for finder agent (fetch + filesystem).
- `streamlit_mcp_rag_agent` — Streamlit RAG agent backed by Qdrant MCP server.
