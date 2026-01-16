"""
Routers - Little Caesars Reports
Aurelia: "Todos los endpoints organizados por módulo"
"""
from .auth import router as auth_router
from .documents import router as documents_router
from .reports import router as reports_router

__all__ = [
    "auth_router",
    "documents_router",
    "reports_router",
]
