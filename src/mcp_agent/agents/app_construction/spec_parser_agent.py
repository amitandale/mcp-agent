"""Parse the canonical system description and map it to local template files."""

from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import BaseModel, Field

from mcp_agent.agents.agent import Agent
from mcp_agent.agents.agent_spec import AgentSpec
from mcp_agent.core.context import Context
from mcp_agent.workflows.factory import create_agent

SPEC = AgentSpec(
    name="app_spec_parser",
    instruction=(
        "Read the canonical system description, inspect the cloned template, and "
        "summarize relevant modules, components, and UI primitives. Produce structured "
        "notes that map spec requirements to existing folders so the planner can operate "
        "without assumptions."
    ),
    server_names=["filesystem", "code-index"],
)


class SpecSection(BaseModel):
    """Represents a markdown section from the canonical spec."""

    title: str
    items: List[str] = Field(default_factory=list)


class TemplateInventory(BaseModel):
    """Directory and file inventory for the cloned template."""

    root: str
    top_level: List[str]
    python_packages: List[str]
    frontend_packages: List[str]
    files: List[str]


class SpecParserResult(BaseModel):
    """Structured output consumed by the planning stage."""

    spec_path: str
    sections: List[SpecSection]
    primary_entities: List[str]
    module_candidates: List[str]
    inventory: TemplateInventory

    def module_map(self) -> dict[str, list[str]]:
        mapping: dict[str, list[str]] = {}
        for module in self.module_candidates:
            mapping[module] = [
                f
                for f in self.inventory.files
                if module.lower().replace(" ", "_") in Path(f).name.lower()
            ]
        return mapping


def _parse_markdown_sections(text: str) -> List[SpecSection]:
    sections: list[SpecSection] = []
    current: SpecSection | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections.append(current)
            current = SpecSection(title=line[3:].strip())
        elif line.startswith("- ") and current is not None:
            current.items.append(line[2:].strip())
        elif line.strip() and current is not None and not current.items:
            current.items.append(line.strip())
    if current is not None:
        sections.append(current)
    return sections


def _inventory_template(workspace: Path) -> TemplateInventory:
    files = [str(path.relative_to(workspace)) for path in workspace.rglob("*") if path.is_file()]
    top_level = sorted([p.name for p in workspace.iterdir() if p.is_dir()])
    python_packages = sorted(
        {
            str(path.relative_to(workspace.parent))
            for path in workspace.rglob("__init__.py")
        }
    )
    frontend_packages = sorted(
        {
            str(path.relative_to(workspace))
            for path in workspace.glob("**/package.json")
        }
    )
    return TemplateInventory(
        root=str(workspace),
        top_level=top_level,
        python_packages=python_packages,
        frontend_packages=frontend_packages,
        files=files,
    )


async def parse_spec(
    *,
    spec_path: str,
    workspace_path: str,
    context: Context | None = None,
) -> SpecParserResult:
    """Parse the canonical spec and workspace inventory."""

    del context
    spec_text = Path(spec_path).read_text(encoding="utf-8")
    sections = _parse_markdown_sections(spec_text)
    entities = next((s.items for s in sections if s.title.lower().startswith("entities")), [])
    modules = next(
        (s.items for s in sections if "module" in s.title.lower()),
        [item for item in entities if item.lower().startswith("module")],
    )
    inventory = _inventory_template(Path(workspace_path))

    return SpecParserResult(
        spec_path=spec_path,
        sections=sections,
        primary_entities=entities,
        module_candidates=modules or entities,
        inventory=inventory,
    )


def build(context: Context | None = None) -> Agent:
    """Instantiate the spec parser agent."""

    return create_agent(SPEC, context=context)


__all__ = [
    "SPEC",
    "build",
    "SpecParserResult",
    "SpecSection",
    "TemplateInventory",
    "parse_spec",
]
