"""HTTP route registration for the versioned Podobank API."""

from podobank.routes.events import router as events_router
from podobank.routes.sandbox import router as sandbox_router

__all__ = ["events_router", "sandbox_router"]
