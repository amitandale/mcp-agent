"""Test helpers shared across the entire suite."""

from __future__ import annotations

import asyncio
import inspect

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    """Run ``async def`` tests without requiring pytest-asyncio.

    Several suites rely on ``@pytest.mark.asyncio`` but the optional
    ``pytest-asyncio`` dependency is not installed in the lean CI image used
    for these exercises.  The hook mirrors the behaviour of that plugin by
    detecting coroutine functions and driving them to completion with a fresh
    event loop.
    """

    if "asyncio" not in pyfuncitem.keywords:
        return None

    if inspect.iscoroutinefunction(pyfuncitem.obj):
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(pyfuncitem.obj(**pyfuncitem.funcargs))
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            asyncio.set_event_loop(None)
            loop.close()
        return True
    return None


def pytest_configure(config: pytest.Config) -> None:
    """Register shared markers used throughout the suite."""

    config.addinivalue_line("markers", "asyncio: mark async test functions")
