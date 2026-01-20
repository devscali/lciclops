"""
Main Application - Little Caesars Reports
Aurelia: "El punto de entrada del backend, aquí todo se conecta"
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import time

from app.config import get_settings
from app.routers import auth_router, documents_router, reports_router
from app.services import init_firebase

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

settings = get_settings()

# Crear aplicación
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
    🍕 Little Caesars Reports API

    Sistema de reportes financieros automatizados para franquicias Little Caesars.

    **Equipo de desarrollo:**
    - Livia (Coordinadora)
    - Julia (Data Scientist)
    - Elena (UI/UX Designer)
    - Aurelia (Backend Architect)
    """,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Middleware para logging de requests
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()

    response = await call_next(request)

    process_time = time.time() - start_time
    logger.info(
        f"{request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Time: {process_time:.3f}s"
    )

    return response


# Exception handler global
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Error interno del servidor",
            "message": str(exc) if settings.debug else "Contacta al administrador"
        }
    )


# Evento de startup
@app.on_event("startup")
async def startup_event():
    """
    Aurelia: "Inicializamos todo cuando arranca el servidor"
    """
    logger.info("🍕 Starting Little Caesars Reports API...")

    try:
        # Inicializar Firebase
        init_firebase()
        logger.info("✅ Firebase initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Firebase: {e}")
        # En desarrollo, continuar sin Firebase
        if not settings.debug:
            raise

    logger.info(f"✅ API ready at {settings.frontend_url}")


# Evento de shutdown
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("👋 Shutting down Little Caesars Reports API...")


# Registrar routers
app.include_router(auth_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(reports_router, prefix="/api")


# Health check
@app.get("/health")
async def health_check():
    """
    Livia: "Para saber si todo está funcionando"
    """
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version
    }


# Root endpoint
@app.get("/")
async def root():
    """
    Livia: "¡Hola! Bienvenido al API de Little Caesars Reports"
    """
    return {
        "message": "🍕 Bienvenido a Little Caesars Reports API",
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
        "team": {
            "coordinator": "Livia",
            "data_scientist": "Julia",
            "designer": "Elena",
            "architect": "Aurelia"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )
