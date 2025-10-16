# Pytest Hang Root Cause Analysis

## Summary
- Identified that the compatibility modules under `mcp_agent.models` still import the `mcp` package during module import time.
- The local compatibility `mcp` package at `src/mcp/__init__.py` continues to manipulate `sys.modules` to temporarily replace itself with the upstream distribution when present.
- When pytest collects modules that hit both the compatibility shims and the upstream server helpers, the re-entrant import of `mcp` while its loader is already executing can deadlock on Python's global import lock.

## Details
1. Each shim in `mcp_agent.models` immediately imports `mcp.types` via the `mcp` package:
   - `src/mcp_agent/models/__init__.py`
   - `src/mcp_agent/models/agent.py`
   - `src/mcp_agent/models/orchestrator.py`
   - `src/mcp_agent/models/workflow.py`

2. The `src/mcp/__init__.py` module still performs dynamic wiring:
   - Calls `metadata.distribution("mcp")` and, if found, appends the upstream package path to `__path__`.
   - Temporarily assigns `sys.modules['mcp']` to the upstream module object before calling `spec.loader.exec_module(upstream_mod)`.
   - Restores the original module after execution.

3. While the upstream `mcp` package executes, it imports runtime helpers like `mcp.server.fastmcp`, which in turn imports `mcp.types`. Because `sys.modules['mcp']` points to the partially initialized upstream module during this window, Python tries to re-import `mcp` while the import lock is still held, resulting in a futex wait and a frozen pytest run.

4. Removing the dynamic module replacement (or ensuring the shim modules import `mcp.types` without re-entering `mcp.__init__`) breaks the cycle and allows pytest to proceed past collection.

## Recommendation
- Eliminate the dynamic `sys.modules` replacement in `src/mcp/__init__.py` and export the local `types` definitions directly.
- Update consumers to import `mcp.types` explicitly so that the compatibility package no longer needs to load the upstream distribution during test collection.
