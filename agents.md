# Agents, Workflows, and MCP Tools — How to Extend mcp-agent

This document explains exactly how to implement new functionality (workflows, agents, and MCP tools) in this repository, where to place code/config, and which files are read-only. It is based on a full pass over all examples/** and the current src/mcp_agent/** framework.

## How to use `examples/`:

The examples/ directory is strictly for learning patterns and verifying how to implement things correctly for production; do not place or maintain production code there. New features and changes must be implemented under src/mcp_agent/ in the appropriate subfolder that matches the requested functionality (e.g., workflows/ for workflows, agents/ for agent logic, mcp/ or server/ for protocol plumbing, workflows/llm/ for provider adapters). Use the examples only as reference for structure, configuration, and usage; ship production-ready code exclusively inside src/mcp_agent/**.

## Project structure:

- `src/mcp_agent/agents/` — Agent runtime and spec (`Agent`, `AgentSpec`); build config-driven agents; attach tools/LLMs at runtime.
- `src/mcp_agent/workflows/` — Production workflows and helpers (router/parallel/orchestrator/swarm, LLM adapters, evaluator/intent).
- `src/mcp_agent/executor/` — Workflow runtime primitives: `Workflow`, `WorkflowResult`, task/signal registries, Temporal integration.
- `src/mcp_agent/mcp/` — Protocol layer: MCP client proxy, connection manager, server registry, aggregator, stdio transport.
- `src/mcp_agent/server/` — App/server glue: mount tools as MCP endpoints, token verification, server adapters.
- `src/mcp_agent/core/` — Core primitives: `Context`, `ContextDependent`, request context, shared exceptions.
- `src/mcp_agent/app.py` — `MCPApp` container and `@app.workflow` decorator for workflow registration.
- `src/mcp_agent/config.py` — Typed settings loader for project config (`mcp_agent.config.yaml`).
- `src/mcp_agent/tools/` — Framework adapters ONLY (crewai_tool.py, langchain_tool.py). **CRITICAL**: Do NOT place domain-specific tools here. Domain logic belongs in `src/mcp_agent/agents/<domain>/`. Agents access MCP servers via `Agent(server_names=[...])`, not via local function-tools.

- `src/mcp_agent/telemetry/` — Usage tracking hooks.
- `src/mcp_agent/logging/` — Structured logging, progress, transports.
- `src/mcp_agent/tracing/` — Tracing, token counters, OTEL utilities.
- `src/mcp_agent/cli/` — CLI commands and cloud/deploy orchestrations.
- `src/mcp_agent/oauth/` — OAuth flows, stores, HTTP helpers.
- `src/mcp_agent/elicitation/` — Elicitation handlers/types for human-in-the-loop.
- `src/mcp_agent/human_input/` — Human input handlers and types.
- `src/mcp_agent/utils/` — Shared utilities (content/mime/pydantic/tool filtering).
- `schema/` — JSON Schemas defining public config contracts.
- `examples/` — Reference-only demos (agents, workflows, servers, transports, providers).
- `tests/` — Pytest suite mirroring `src/`.
- Root tooling: `pyproject.toml`, `Makefile`, `.pre-commit-config.yaml`, `README.md`, (add `mcp_agent.config.yaml` at repo root for production).

---

## File placement rules:

### Agents

[Permalink: Agents](https://github.com/amitandale/mcp-agent/blob/main/agents.md#agents)

- Create under `src/mcp_agent/agents/<domain>/<agent_name>_agent.py` for domain-specific agents, or `src/mcp_agent/agents/<agent_name>.py` for standalone agents.
- **ALWAYS declare MCP server access via `server_names=[]` parameter, NOT as local function-tools**. Example: `Agent(name="analyzer", server_names=["github", "code-index"], ...)`.
- Prefer config-driven: export `SPEC: AgentSpec` and `build(context: Context | None = None) -> Agent` using `mcp_agent.workflows.factory.create_agent`.
-  REFERENCE: See `src/mcp_agent/data/examples/workflows/workflow_deep_orchestrator/main.py` for multi-agent patterns with `server_names`.


### Workflows

- Subclass `mcp_agent.executor.workflow.Workflow[T]`; implement `async def run(...) -> WorkflowResult[T]`.
- Place at `src/mcp_agent/workflows/<domain>/<name>_workflow.py` (or directly under `workflows/` for general flows).

### Function-tools (local tools)

- Add plain typed functions under `src/mcp_agent/tools/<domain>.py`.
- Register on agents via `AgentSpec(functions=[...])` or `Agent(functions=[...])`.

### MCP servers (remote tools)

**Declare** in `mcp_agent.config.yaml` under `mcp.servers` with command and args (e.g., `command: "uvx", args: ["code-index-mcp"]`).
**Access via agents** using `server_names=[]` parameter: `Agent(server_names=["github", "code-index"], ...)`.
- Do NOT implement servers as local function-tools.
- Do not commit secrets; use `mcp_agent.secrets.yaml` (gitignored). Schema: `schema/mcp-agent.config.schema.json`.
- FERENCE: `src/mcp_agent/data/examples/workflows/workflow_router/main.py` shows agents accessing different server subsets.



### Configs

- Keep production config at repo root (`mcp_agent.config.yaml`); example configs in `examples/**` are reference only.
- MCP servers must be declared in config BEFORE agents can use them. Agents reference by name via `server_names=[]`.

### Agent-to-Server Mapping Patterns
**Rule: Each agent declares which MCP servers it needs via `server_names=[]`.**
- Identify what external tools/APIs the agent needs.
- Find corresponding MCP servers declared in `mcp_agent.config.yaml`.
- Pass server names to agent: `Agent(name="code_analyzer", server_names=["code-index", "tree-sitter", "ast-grep", "github"], ...)`.

**CRITICAL**: Each agent gets a SUBSET of servers appropriate for its role. Do NOT give every agent all servers.
- REFERENCE: `src/mcp_agent/data/examples/workflows/workflow_deep_orchestrator/main.py` creates FileExpert, StyleChecker, Proofreader with different `server_names` subsets.


## Examples References

### How to use examples list:

Start from the primary category that matches the PR scope:

- **Agents** → see "Basic/Hello or Use-case agents" and provider-specific under "LLM Providers."
- **Workflows** → see "Orchestration/Factory/Parallel/Router," plus "Temporal & Workers" when background workers/clients are relevant.
- **MCP Tools** → client usage and transports for interacting with servers (SSE, WebSockets, HTTP, roots, prompts/resources).
- **Local Tools & Adapters** → authoring simple Python function-tools or using CrewAI/LangChain.
- **LLM Providers** → provider basics and utilities for selection/token accounting/intent.

If your change touches servers, OAuth, tracing, human input, or app demos, jump to the dedicated categories above for patterns before implementing production code under src/mcp_agent/**. Include both top-level examples/ and embedded examples under src/mcp_agent/data/examples/ so Codex has full coverage.

### Agents

#### Basic/Hello or Use-case agents

- `examples/basic/mcp_basic_agent/main.py` — Display comprehensive token usage summary using app/agent convenience APIs.
- `examples/basic/mcp_hello_world/main.py` — Main example entrypoint
- `examples/cloud/hello_world/main.py` — import asyncio
- `examples/usecases/marimo_mcp_basic_agent/notebook.py` — # 💬 Basic agent chatbot
- `examples/usecases/mcp_basic_slack_agent/main.py` — Get the latest message from general channel and provide a summary.
- `examples/usecases/mcp_browser_agent/main.py` — Use case: mcp_browser_agent
- `examples/usecases/mcp_financial_analyzer/main.py` — Use case: mcp_financial_analyzer
- `examples/usecases/mcp_github_to_slack/main.py` — Use case: mcp_github_to_slack
- `examples/usecases/mcp_instagram_agent/main.py` — Use case: mcp_instagram_agent
- `examples/usecases/mcp_marketing_agent/main.py` — Use case: mcp_marketing_agent
- `examples/usecases/mcp_playwright_agent/main.py` — Use case: mcp_playwright_agent
- `examples/usecases/mcp_realtor_agent/main.py` — Use case: mcp_realtor_agent
- `examples/usecases/mcp_researcher/main.py` — Use case: mcp_researcher
- `examples/usecases/mcp_slack_agent/main.py` — Use case: mcp_slack_agent
- `examples/usecases/mcp_streamlit_basic_agent/main.py` — Use case: mcp_streamlit_basic_agent
- `examples/usecases/mcp_streamlit_rag_agent/agent_state.py` — Use case: mcp_streamlit_rag_agent
- `examples/usecases/mcp_streamlit_rag_agent/main.py` — Use case: mcp_streamlit_rag_agent
- `examples/basic/oauth_basic_agent/main.py` — OAuth integration demo

### Workflows

#### Orchestration/Factory/Parallel/Router

- `examples/basic/agent_factory/auto_loaded_subagents.py` — Example
- `examples/basic/agent_factory/load_and_route.py` — Example
- `examples/basic/agent_factory/main.py` — Route a prompt to the appropriate agent using an LLMRouter.
- `examples/basic/agent_factory/orchestrator_demo.py` — Orchestrator pattern demo
- `examples/basic/agent_factory/parallel_demo.py` — Parallel orchestration demo
- `examples/cloud/agent_factory/main.py` — Main example entrypoint
- `src/mcp_agent/data/examples/workflows/workflow_deep_orchestrator/main.py` — Main example entrypoint
- `src/mcp_agent/data/examples/workflows/workflow_evaluator_optimizer/main.py` — Main example entrypoint
- `src/mcp_agent/data/examples/workflows/workflow_intent_classifier/main.py` — Main example entrypoint
- `src/mcp_agent/data/examples/workflows/workflow_orchestrator_worker/main.py` — Main example entrypoint
- `src/mcp_agent/data/examples/workflows/workflow_parallel/main.py` — Main example entrypoint
- `src/mcp_agent/data/examples/workflows/workflow_router/main.py` — Main example entrypoint
- `src/mcp_agent/data/examples/workflows/workflow_swarm/main.py` — Main example entrypoint
- `examples/temporal/main.py` — Temporal workflow/client/worker example
- `examples/temporal/router.py` — Routing/selection demo
- `examples/temporal/parallel.py` — Parallel orchestration demo
- `examples/temporal/orchestrator.py` — Orchestrator pattern demo
- `examples/temporal/evaluator_optimizer.py` — Orchestrator pattern demo
- `examples/temporal/interactive.py` — Interactive CLI example
- `examples/temporal/basic.py` — Temporal workflow/client/worker example
- `examples/temporal/workflows.py` — Example
- `examples/cloud/temporal/main.py` — Temporal workflow/client/worker example
- `examples/human_input/temporal/main.py` — Temporal workflow/client/worker example
- `examples/mcp/mcp_elicitation/main.py` — Main example entrypoint
- `examples/mcp/mcp_elicitation/cloud/main.py` — Main example entrypoint
- `examples/mcp/mcp_prompts_and_resources/main.py` — Main example entrypoint
- `examples/mcp/mcp_roots/main.py` — Main example entrypoint
- `examples/mcp/mcp_sse/main.py` — Server-Sent Events transport demo
- `examples/mcp/mcp_sse_with_headers/main.py` — Server-Sent Events transport demo
- `examples/mcp/mcp_streamable_http/main.py` — Streamable HTTP transport demo
- `examples/mcp/mcp_websockets/main.py` — WebSockets transport demo
- `examples/basic/mcp_server_aggregator/main.py` — Main example entrypoint
- `examples/basic/mcp_tool_filter/main.py` — Tool selection/filtering
- `examples/basic/mcp_tool_filter/quickstart.py` — Main example entrypoint
- `examples/cloud/mcp/main.py` — Main example entrypoint
- `examples/cloud/observability/main.py` — Main example entrypoint
- `examples/usecases/reliable_conversation/main.py` — Use case: reliable_conversation
- `examples/usecases/reliable_conversation/workflows.py` — Example
- `examples/usecases/reliable_conversation/basic.py` — Temporal workflow/client/worker example

#### Temporal & Workers (Workers/Clients/Entrypoints)

- `examples/basic/agent_factory/run_worker.py` — Worker entrypoint
- `examples/cloud/agent_factory/run_worker.py` — Worker entrypoint
- `examples/cloud/temporal/temporal_worker.py` — Worker entrypoint
- `examples/human_input/temporal/client.py` — Client example
- `examples/human_input/temporal/worker.py` — Worker entrypoint
- `examples/mcp/mcp_elicitation/temporal/client.py` — Client example
- `examples/mcp/mcp_elicitation/temporal/main.py` — Temporal workflow/client/worker example
- `examples/mcp/mcp_elicitation/temporal/worker.py` — Worker entrypoint
- `examples/temporal/run_worker.py` — Worker entrypoint
- `examples/tracing/temporal/basic.py` — Temporal workflow/client/worker example
- `examples/tracing/temporal/main.py` — Main example entrypoint
- `examples/tracing/temporal/workflows.py` — Example
- `examples/tracing/temporal/run_worker.py` — Worker entrypoint

### MCP Tools

#### Client usage & transports

- `examples/basic/mcp_model_selector/main.py` — Model selection workflow
- `examples/basic/mcp_model_selector/interactive.py` — Interactive CLI example
- `examples/basic/token_counter/main.py` — Token counting utility
- `examples/basic/mcp_server_aggregator/main.py` — MCP server aggregator usage
- `examples/basic/mcp_tool_filter/main.py` — Tool selection/filtering
- `examples/basic/mcp_tool_filter/quickstart.py` — Main example entrypoint
- `examples/mcp/mcp_prompts_and_resources/main.py` — MCP prompts/resources API
- `examples/mcp/mcp_roots/main.py` — MCP roots discovery
- `examples/mcp/mcp_sse/main.py` — Server-Sent Events transport demo
- `examples/mcp/mcp_sse_with_headers/main.py` — Server-Sent Events transport demo
- `examples/mcp/mcp_streamable_http/main.py` — Streamable HTTP transport demo
- `examples/mcp/mcp_websockets/main.py` — WebSockets transport demo

### Local Tools & Adapters

#### Function tools & 3rd-party adapters

- `examples/basic/functions/main.py` — Local function-tool demo
- `examples/crewai/main.py` — CrewAI tool adapter usage
- `examples/langchain/main.py` — LangChain tool adapter usage
- `examples/multithread/main.py` — Main example entrypoint
- `examples/multithread/word_count.py` — Local function-tool demo

### LLM Providers

#### Selection/Token/Intent utilities

- `examples/basic/mcp_model_selector/main.py` — Model selection workflow
- `examples/basic/mcp_model_selector/interactive.py` — Interactive CLI example
- `examples/basic/token_counter/main.py` — Token counting utility
- `src/mcp_agent/data/examples/workflows/workflow_evaluator_optimizer/main.py` — Main example entrypoint
- `src/mcp_agent/data/examples/workflows/workflow_intent_classifier/main.py` — Main example entrypoint

#### Basic provider agent

- `examples/model_providers/mcp_basic_azure_agent/main.py` — Main example entrypoint
- `examples/model_providers/mcp_basic_bedrock_agent/main.py` — Main example entrypoint
- `examples/model_providers/mcp_basic_google_agent/main.py` — Main example entrypoint
- `examples/model_providers/mcp_basic_ollama_agent/main.py` — Main example entrypoint

### MCP Servers (server-side demos & adapters)

- `examples/mcp/mcp_elicitation/demo_server.py` — Server demo
- `examples/mcp/mcp_prompts_and_resources/demo_server.py` — Server demo
- `examples/mcp/mcp_roots/root_test_server.py` — Server demo
- `examples/mcp/mcp_sse/server.py` — Server demo
- `examples/mcp/mcp_streamable_http/stateless_server.py` — Server demo
- `examples/mcp_agent_server/asyncio/client.py` — Client example
- `examples/mcp_agent_server/asyncio/main.py` — Main example entrypoint
- `examples/mcp_agent_server/asyncio/nested_elicitation_server.py` — Server demo
- `examples/mcp_agent_server/asyncio/prompts_resources_client.py` — Client example
- `examples/mcp_agent_server/asyncio/prompts_resources_server.py` — Server demo
- `examples/mcp_agent_server/asyncio/roots_client.py` — Client example
- `examples/mcp_agent_server/asyncio/roots_server.py` — Server demo
- `examples/mcp_agent_server/asyncio/sse_telemetry_client.py` — Client example
- `examples/mcp_agent_server/asyncio/sse_telemetry_server.py` — Server demo
- `examples/mcp_agent_server/asyncio/streamable_http_client.py` — Client example
- `examples/mcp_agent_server/asyncio/streamable_http_server.py` — Server demo
- `examples/mcp_agent_server/context_isolation/server.py` — Server demo
- `examples/mcp_agent_server/context_isolation/clients.py` — Client example
- `examples/mcp_agent_server/temporal/basic_agent_server_worker.py` — Worker entrypoint
- `examples/mcp_agent_server/temporal/client.py` — Client example
- `examples/mcp_agent_server/temporal/main.py` — Main example entrypoint
- `examples/mcp_agent_server/temporal/workflows.py` — Example
- `src/mcp_agent/data/examples/mcp_agent_server/elicitation/server.py` — Server demo
- `src/mcp_agent/data/examples/mcp_agent_server/notifications/client.py` — Client example
- `src/mcp_agent/data/examples/mcp_agent_server/notifications/server.py` — Server demo
- `src/mcp_agent/data/examples/mcp_agent_server/reference/client.py` — Client example
- `src/mcp_agent/data/examples/mcp_agent_server/reference/server.py` — Server demo
- `src/mcp_agent/data/examples/mcp_agent_server/sampling/client.py` — Client example
- `src/mcp_agent/data/examples/mcp_agent_server/sampling/server.py` — Server demo

### Security & OAuth

- `examples/basic/oauth_basic_agent/main.py` — OAuth integration demo
- `examples/oauth/interactive_tool/client.py` — Client example
- `examples/oauth/interactive_tool/server.py` — Server demo
- `examples/oauth/pre_authorize/client.py` — Client example
- `examples/oauth/pre_authorize/main.py` — Main example entrypoint
- `examples/oauth/pre_authorize/worker.py` — Worker entrypoint
- `examples/oauth/protected_by_oauth/main.py` — Main example entrypoint
- `examples/oauth/protected_by_oauth/registration.py` — Server demo

### Observability & Tracing

- `examples/cloud/observability/main.py` — Main example entrypoint
- `examples/tracing/agent/main.py` — Example
- `examples/tracing/langfuse/main.py` — Observability/Tracing demo
- `examples/tracing/llm/main.py` — Observability/Tracing demo
- `examples/tracing/mcp/main.py` — Observability/Tracing demo
- `examples/tracing/mcp/server.py` — Server demo
- `examples/tracing/temporal/basic.py` — Temporal workflow/client/worker example
- `examples/tracing/temporal/main.py` — Main example entrypoint
- `examples/tracing/temporal/workflows.py` — Example
- `examples/tracing/temporal/run_worker.py` — Worker entrypoint

### Human-in-the-Loop

- `examples/human_input/temporal/client.py` — Client example
- `examples/human_input/temporal/main.py` — Temporal workflow/client/worker example
- `examples/human_input/temporal/worker.py` — Worker entrypoint
- `examples/mcp/mcp_elicitation/main.py` — Main example entrypoint
- `examples/mcp/mcp_elicitation/cloud/main.py` — Main example entrypoint
- `examples/mcp/mcp_elicitation/temporal/client.py` — Client example
- `examples/mcp/mcp_elicitation/temporal/main.py` — Temporal workflow/client/worker example
- `examples/mcp/mcp_elicitation/temporal/worker.py` — Worker entrypoint
- `examples/mcp/mcp_elicitation/demo_server.py` — Server demo

### Apps & Demos

- `examples/cloud/chatgpt_apps/basic_app/main.py` — ChatGPT App example
- `examples/cloud/chatgpt_apps/timer/main.py` — ChatGPT App example

### Use Cases (domain demos)

- `examples/usecases/fastapi_websocket/main.py` — Main example entrypoint
- `examples/usecases/fastapi_websocket/session_manager.py` — Example
- `examples/usecases/fastapi_websocket/websocket_client_async.py` — Client example
- `examples/usecases/marimo_mcp_basic_agent/notebook.py` — # 💬 Basic agent chatbot
- `examples/usecases/mcp_basic_slack_agent/main.py` — Get the latest message from general channel and provide a summary.
- `examples/usecases/mcp_browser_agent/main.py` — Use case: mcp_browser_agent
- `examples/usecases/mcp_financial_analyzer/main.py` — Use case: mcp_financial_analyzer
- `examples/usecases/mcp_github_to_slack/main.py` — Use case: mcp_github_to_slack
- `examples/usecases/mcp_instagram_agent/main.py` — Use case: mcp_instagram_agent
- `examples/usecases/mcp_marketing_agent/main.py` — Use case: mcp_marketing_agent
- `examples/usecases/mcp_playwright_agent/main.py` — Use case: mcp_playwright_agent
- `examples/usecases/mcp_realtor_agent/main.py` — Use case: mcp_realtor_agent
- `examples/usecases/mcp_researcher/main.py` — Use case: mcp_researcher
- `examples/usecases/mcp_slack_agent/main.py` — Use case: mcp_slack_agent
- `examples/usecases/mcp_streamlit_basic_agent/main.py` — Use case: mcp_streamlit_basic_agent
- `examples/usecases/mcp_streamlit_rag_agent/agent_state.py` — Use case: mcp_streamlit_rag_agent
- `examples/usecases/mcp_streamlit_rag_agent/main.py` — Use case: mcp_streamlit_rag_agent
- `examples/usecases/reliable_conversation/basic.py` — Temporal workflow/client/worker example
- `examples/usecases/reliable_conversation/main.py` — Use case: reliable_conversation
- `examples/usecases/reliable_conversation/workflows.py` — Example
- `src/mcp_agent/data/examples/usecases/mcp_financial_analyzer/main.py` — Main example entrypoint
- `src/mcp_agent/data/examples/usecases/mcp_researcher/main.py` — Main example entrypoint

### Cloud (cloud-oriented examples)

- `examples/cloud/agent_factory/main.py` — Main example entrypoint
- `examples/cloud/agent_factory/run_worker.py` — Worker entrypoint
- `examples/cloud/chatgpt_apps/basic_app/main.py` — ChatGPT App example
- `examples/cloud/chatgpt_apps/timer/main.py` — ChatGPT App example
- `examples/cloud/hello_world/main.py` — import asyncio
- `examples/cloud/mcp/main.py` — Main example entrypoint
- `examples/cloud/observability/main.py` — Main example entrypoint
- `examples/cloud/temporal/main.py` — Temporal workflow/client/worker example
- `examples/cloud/temporal/temporal_worker.py` — Worker entrypoint

### Additional "Misc/Uncategorized" (very small helper entries that didn't match above heuristics)

- `examples/tracing/agent/main.py` — Example
- `examples/temporal/workflows.py` — Example
- `examples/mcp_agent_server/temporal/workflows.py` — Example

