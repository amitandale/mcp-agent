from mcp_agent.context.telemetry import meter as meter

from .public import router as public_router
from .public_context_overlay import (
    add_public_api_with_context as add_public_api_with_context,
)
from .agent import router as agent_router
from .tool_registry import router as tool_router
from .orchestrator import router as orchestrator_router
from .workflow_builder import router as workflow_router
from .human_input import router as human_input_router


_routes_attached = False


def add_public_api(app):
    global _routes_attached
    if not _routes_attached:
        public_router.routes.extend(agent_router.routes)
        public_router.routes.extend(tool_router.routes)
        public_router.routes.extend(orchestrator_router.routes)
        public_router.routes.extend(workflow_router.routes)
        public_router.routes.extend(human_input_router.routes)
        _routes_attached = True
    app.router.mount("/v1", public_router)
