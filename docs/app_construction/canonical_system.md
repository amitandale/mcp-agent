# Canonical Application Specification

This document describes the target experience that the App Construction Orchestrator implements. It intentionally focuses on functionality that can be achieved with a core API layer and a lightweight UI prototype.

## Entities
- **Workspace**: contains shared metadata about the generated project (name, template, and branch configuration).
- **Module**: represents a functional grouping such as "Auth", "Projects", or "Dashboard".
- **FeatureTask**: an atomic unit of work that results in a PR (e.g., add CRUD routes for modules or render a dashboard panel).

## Platform Requirements
- Use the selected template as the starting point (defaults to a Next.js UI with a FastAPI backend scaffold).
- Keep code ready for CI without handling deployment or release automation.
- Record every generated file or major edit in the validation summary so reviewers know what changed.

## Functional Requirements
1. Provide CRUD APIs for core modules using the backend scaffold.
2. Surface a dashboard UI page that lists the modules and exposes at least one interactive control per module.
3. Include a deterministic plan of PRs so that downstream workflows can reproduce the construction process.
4. Run lint/tests locally after each PR implementation and block merges if checks fail.

## Constraints
- Do not interact with production services or provision cloud infrastructure.
- Keep access tokens and secrets external to the repository.
- Favor standard folder naming from the template so that iterated PRs remain consistent.
