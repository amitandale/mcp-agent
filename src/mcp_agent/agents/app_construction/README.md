# App Construction Agents

This package defines the specialized agents used by the App Construction Orchestrator. Each agent follows the guidance in `agents.md`, exposes a focused instruction set, and limits MCP server access to the minimum subset required for its responsibilities.

| Agent | Module | Purpose | Servers |
| --- | --- | --- | --- |
| `app_repo_initializer` | `repo_initializer_agent.py` | Bootstraps repositories from the requested template, manages the initial branch, and wires Git remotes. | `github`, `filesystem` |
| `app_spec_parser` | `spec_parser_agent.py` | Reads the canonical system description and inspects the cloned template to understand existing components. | `filesystem`, `code-index` |
| `app_execution_planner` | `planning_agent.py` | Breaks the spec into atomic implementation steps that align with the template architecture. | `filesystem`, `code-index`, `ast-grep` |
| `app_pr_generation` | `pr_generation_agent.py` | Prepares artifact-aware PR plans, including file/line targets and structured descriptions. | `filesystem`, `code-index`, `ast-grep` |
| `app_validation` | `validation_agent.py` | Runs tests/lint and ensures the workspace matches the planned functionality prior to commit. | `filesystem`, `code-index`, `dependency-management`, `lsp` |
| `app_repo_commit` | `repo_commit_agent.py` | Finalizes branches, assembles commits, and pushes to the staging branch that is ready for CI. | `filesystem`, `github` |

The orchestrator loads these agents via config-driven builder strings so they can be swapped or extended without modifying workflow code.
