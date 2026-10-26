"""FastAPI application entrypoint for Urja Meter Ops REST API Wrapper."""

from contextlib import asynccontextmanager
import logging
import uuid
from typing import AsyncGenerator
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.dependencies import close_portal_client, get_portal_client, init_portal_client
from app.exceptions import PortalError
from app.models import HealthResponse
from app.routes.auth import router as auth_router
from app.routes.hierarchy import router as hierarchy_router
from app.routes.meters import router as meters_router

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("urja_ops_api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle: start and close outbound HTTP clients safely."""
    logger.info("Starting Urja Meter Ops API wrapper (%s)...", settings.app_env)
    await init_portal_client(settings)
    yield
    logger.info("Shutting down Urja Meter Ops API wrapper, closing HTTP pool...")
    await close_portal_client()


app = FastAPI(
    title="Flock Energy — Urja Meter Ops API",
    description=(
        "Production-quality REST API wrapper providing programmatic, normalized "
        "access to smart meter operations, interval consumption telemetry, and "
        "grid distribution topology from the legacy Urja Meter Ops portal."
    ),
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {"name": "Health", "description": "Service health and upstream availability checks"},
        {"name": "Authentication", "description": "Upstream portal session authentication"},
        {"name": "Meters", "description": "Smart meter collection, nameplate details, and interval consumption"},
        {"name": "Hierarchy", "description": "Electrical grid distribution topology (Feeders & Transformers)"},
    ]
)

# Enable permissive CORS for integration environments
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(PortalError)
async def portal_error_handler(request: Request, exc: PortalError) -> JSONResponse:
    """Format domain-specific portal adapter exceptions into consistent error response."""
    request_id = str(uuid.uuid4())[:8]
    logger.error("[%s] Portal error occurred (%s): %s", request_id, exc.code, exc.message)
    headers = {}
    if hasattr(exc, "retry_after") and exc.retry_after is not None:
        headers["Retry-After"] = str(exc.retry_after)

    return JSONResponse(
        status_code=exc.status_code,
        headers=headers,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": request_id,
            }
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Normalize FastAPI HTTP exceptions into consistent error envelope."""
    request_id = str(uuid.uuid4())[:8]
    code = "HTTP_ERROR"
    if exc.status_code == 400:
        code = "BAD_REQUEST"
    elif exc.status_code == 404:
        code = "NOT_FOUND"
    elif exc.status_code == 422:
        code = "VALIDATION_ERROR"

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message": str(exc.detail),
                "request_id": request_id,
            }
        }
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all error handler preventing internal stack traces or secrets from leaking."""
    request_id = str(uuid.uuid4())[:8]
    logger.exception("[%s] Unhandled server error: %s", request_id, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected internal server error occurred.",
                "request_id": request_id,
            }
        }
    )


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Service Health Check",
    description="Returns service runtime health, application version, and upstream portal availability."
)
async def health() -> HealthResponse:
    """Lightweight health check distinguishing API status from upstream portal availability."""
    client = get_portal_client(settings)
    upstream_health = await client.check_health()

    return HealthResponse(
        status="healthy",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        upstream=upstream_health,
    )


# Register modular routers under configured API prefix
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(meters_router, prefix=settings.api_prefix)
app.include_router(hierarchy_router, prefix=settings.api_prefix)
