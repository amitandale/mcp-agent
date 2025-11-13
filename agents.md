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
- `src/mcp_agent/tools/` — Plain function-tools and adapters (e.g., CrewAI/LangChain wrappers) for agent registration.
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

- Create under `src/mcp_agent/agents/<name>.py`.
- Prefer config-driven: export `SPEC: AgentSpec` and `build(context: Context | None = None) -> Agent` using `mcp_agent.workflows.factory.create_agent`.
- Optional (advanced/minimal): module-level `AGENT: Agent` for immediate, stateless agents.

### Workflows

- Subclass `mcp_agent.executor.workflow.Workflow[T]`; implement `async def run(...) -> WorkflowResult[T]`.
- Place at `src/mcp_agent/workflows/<domain>/<name>_workflow.py` (or directly under `workflows/` for general flows).

### Function-tools (local tools)

- Add plain typed functions under `src/mcp_agent/tools/<domain>.py`.
- Register on agents via `AgentSpec(functions=[...])` or `Agent(functions=[...])`.

### MCP servers (remote tools)

- Declare in `mcp_agent.config.yaml` under `mcp.servers`. Do not commit secrets. Use schema in `schema/mcp-agent.config.schema.json`.

### Configs

- Keep production config at repo root (`mcp_agent.config.yaml`); example configs in `examples/**` are reference only.
