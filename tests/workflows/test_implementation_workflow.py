import pytest

from mcp_agent.workflows.implementation_workflow.models import (
    PRImplementationRequest,
    Vendor,
)
from mcp_agent.workflows.implementation_workflow.vendor import VendorCLIRunner
from mcp_agent.tools.antigravity_tool import AntigravityTool
from mcp_agent.tools.claude_tool import ClaudeTool
from mcp_agent.tools.codex_tool import CodexTool
from mcp_agent.tools.grok_tool import GrokTool
from mcp_agent.tools.kimi_tool import KimiTool
from mcp_agent.tools.qwen_tool import QwenTool


@pytest.mark.parametrize(
    "vendor, expected",
    [
        (Vendor.CODEX, CodexTool),
        (Vendor.CLAUDE, ClaudeTool),
        (Vendor.GROK, GrokTool),
        (Vendor.ANTIGRAVITY, AntigravityTool),
        (Vendor.KIMI, KimiTool),
        (Vendor.QWEN, QwenTool),
    ],
)
def test_vendor_adapter_selection(vendor, expected):
    runner = VendorCLIRunner(vendor, workspace="/tmp")
    assert isinstance(runner._build_adapter(), expected)


def test_request_validation_and_defaults():
    request = PRImplementationRequest(
        pr_title="Test Title",
        pr_text="Implement feature",
        repo_url="https://github.com/example/repo",
        working_branch="main",
        vendor="codex",
    )
    assert request.vendor == Vendor.CODEX
    assert request.repo_url.host == "github.com"
