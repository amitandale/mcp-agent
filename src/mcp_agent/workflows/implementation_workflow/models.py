from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl


class Vendor(str, Enum):
    CODEX = "codex"
    CLAUDE = "claude"
    GROK = "grok"
    ANTIGRAVITY = "antigravity"
    KIMI = "kimi"
    QWEN = "qwen"


class PRImplementationRequest(BaseModel):
    pr_title: str = Field(..., description="Pull request title")
    pr_text: str = Field(..., description="Detailed implementation instructions for the vendor CLI")
    repo_url: HttpUrl = Field(..., description="Target GitHub repository URL")
    working_branch: str = Field(..., description="Base branch to target for the PR")
    vendor: Vendor = Field(..., description="CLI vendor to route the implementation to")


class RepositoryCheckoutResult(BaseModel):
    workspace_path: str
    branch: str
    checkout_log: List[str] = Field(default_factory=list)


class CLIExecutionResult(BaseModel):
    vendor: Vendor
    instruction: str
    streamed_output: List[str] = Field(default_factory=list)
    exit_code: Optional[int] = None
    success: bool = False
    files_changed: List[str] = Field(default_factory=list)
    created: List[str] = Field(default_factory=list)
    deleted: List[str] = Field(default_factory=list)
    diff_preview: Optional[str] = None


class BranchCommitResult(BaseModel):
    branch_name: str
    commit_message: str
    commit_sha: Optional[str] = None
    pushed: bool = False


class PullRequestResult(BaseModel):
    pr_number: Optional[int] = None
    pr_url: Optional[str] = None
    draft: bool = True


class CIStatus(BaseModel):
    status: str
    logs: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class DiffSummary(BaseModel):
    files: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    full_diff: Optional[str] = None


class PRImplementationOutput(BaseModel):
    checkout: RepositoryCheckoutResult
    implementation: CLIExecutionResult
    commit: BranchCommitResult
    pull_request: PullRequestResult
    ci_status: CIStatus
    diff: DiffSummary
    fix_attempts: List[str] = Field(default_factory=list)
    success: bool = False
