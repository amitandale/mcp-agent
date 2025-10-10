"""Test helpers shared across the entire suite."""

from __future__ import annotations

import asyncio
import inspect
import importlib.util
import pathlib
import sys
from functools import lru_cache

import pytest


ROOT = pathlib.Path(__file__).resolve().parent
SRC_TESTS = ROOT.parent / "src" / "mcp_agent" / "tests"

collect_ignore_glob = ["src/mcp_agent/tests/**"]

OPTIONAL_DEPENDENCIES: dict[str, tuple[pathlib.Path, ...]] = {
    "temporalio": (
        ROOT / "executor" / "temporal",
        ROOT / "human_input" / "test_elicitation_handler.py",
    ),
    "jwt": (ROOT / "public_api" / "test_api.py",),
    "pytest_asyncio": (
        ROOT / "sentinel" / "test_authorize_matrix.py",
        ROOT / "sentinel" / "test_deny_integration.py",
    ),
    "crewai": (ROOT / "tools" / "test_crewai_tool.py",),
    "langchain_core": (ROOT / "tools" / "test_langchain_tool.py",),
    "azure.ai.inference": (
        ROOT / "utils" / "test_multipart_converter_azure.py",
        ROOT / "workflows" / "llm" / "test_augmented_llm_azure.py",
    ),
    "google.genai": (
        ROOT / "utils" / "test_multipart_converter_google.py",
        ROOT / "workflows" / "llm" / "test_augmented_llm_google.py",
    ),
    "cohere": (
        ROOT / "workflows" / "intent_classifier" / "test_intent_classifier_embedding_cohere.py",
        ROOT / "workflows" / "router" / "test_router_embedding_cohere.py",
    ),
    "boto3": (ROOT / "workflows" / "llm" / "test_augmented_llm_bedrock.py",),
    "trio": (
        ROOT / "agents" / "test_agent_tasks_concurrency.py",
        ROOT / "agents" / "test_agent_tasks_isolation.py",
        ROOT / "mcp" / "test_connection_manager_concurrency.py",
        ROOT / "mcp" / "test_connection_manager_lifecycle.py",
        ROOT / "mcp" / "test_mcp_connection_manager.py",
        ROOT / "server" / "test_app_server_memo.py",
    ),
    "instructor": (
        ROOT / "workflows" / "llm" / "test_augmented_llm_ollama.py",
    ),
}


def _purge_vendored_test_modules() -> None:
    """Remove vendored test modules imported via ``PYTHONPATH`` priming."""

    for name, module in list(sys.modules.items()):
        candidate = getattr(module, "__file__", None)
        if not candidate:
            continue
        try:
            path = pathlib.Path(candidate).resolve()
        except (FileNotFoundError, RuntimeError):
            continue
        if path.is_relative_to(SRC_TESTS):
            sys.modules.pop(name, None)


_purge_vendored_test_modules()


@lru_cache(maxsize=None)
def _dependency_missing(module: str) -> bool:
    """Return ``True`` when *module* cannot be imported."""

    try:
        return importlib.util.find_spec(module) is None
    except ModuleNotFoundError:
        return True


def _matches(candidate: pathlib.Path, target: pathlib.Path) -> bool:
    """Determine whether *candidate* resides within *target*."""

    target = target.resolve()
    if target.is_dir():
        return candidate.is_relative_to(target)
    return candidate == target


def pytest_ignore_collect(collection_path: pathlib.Path, config: pytest.Config) -> bool:
    """Skip suites that rely on optional third-party dependencies.

    The lean execution environment used for these kata exercises does not ship
    heavyweight SDKs such as Temporal, Google AI Studio, or AWS Bedrock.  When
    those libraries are unavailable we proactively skip the associated test
    modules instead of failing during collection.
    """

    candidate = pathlib.Path(str(collection_path)).resolve()

    if candidate.is_relative_to(SRC_TESTS):
        return True

    for module, paths in OPTIONAL_DEPENDENCIES.items():
        if not _dependency_missing(module):
            continue
        for target in paths:
            if _matches(candidate, target):
                return True
    return False


@pytest.hookimpl(tryfirst=True)
def pytest_pycollect_makemodule(module_path, parent):
    """Clear vendored modules before pytest imports a test module."""

    module_path = pathlib.Path(str(module_path))
    module_name = module_path.stem
    existing = sys.modules.get(module_name)
    if existing is not None:
        candidate = getattr(existing, "__file__", None)
        if candidate:
            try:
                resolved = pathlib.Path(candidate).resolve()
            except (FileNotFoundError, RuntimeError):
                resolved = None
            if resolved and resolved.is_relative_to(SRC_TESTS):
                sys.modules.pop(module_name, None)
    return None


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    """Run ``async def`` tests without requiring pytest-asyncio."""

    if "asyncio" not in pyfuncitem.keywords:
        return None

    if inspect.iscoroutinefunction(pyfuncitem.obj):
        sig = inspect.signature(pyfuncitem.obj)
        parameters = sig.parameters
        accepts_kwargs = any(
            param.kind is inspect.Parameter.VAR_KEYWORD
            for param in parameters.values()
        )

        call_kwargs = {}
        for name, param in parameters.items():
            if name in pyfuncitem.funcargs:
                call_kwargs[name] = pyfuncitem.funcargs[name]

        if accepts_kwargs:
            for name, value in pyfuncitem.funcargs.items():
                call_kwargs.setdefault(name, value)

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(pyfuncitem.obj(**call_kwargs))
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            asyncio.set_event_loop(None)
            loop.close()
        return True
    return None


def pytest_configure(config: pytest.Config) -> None:
    """Register shared markers used throughout the suite."""

    config.addinivalue_line("markers", "asyncio: mark async test functions")
