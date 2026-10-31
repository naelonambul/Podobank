"""HTTP route registration for the versioned Podobank API."""

from podobank.routes.accounts import router as accounts_router
from podobank.routes.catalog import router as catalog_router
from podobank.routes.events import router as events_router
from podobank.routes.sandbox import router as sandbox_router
from podobank.routes.transfers import router as transfers_router

__all__ = [
    "accounts_router",
    "catalog_router",
    "events_router",
    "sandbox_router",
    "transfers_router",
]
