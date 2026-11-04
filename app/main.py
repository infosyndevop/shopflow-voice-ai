"""CRYVEX ShopFlow Voice AI Backend - Main Application Entrypoint."""

from contextlib import asynccontextmanager
from typing import Any, Dict
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.api.voice import router as voice_router
from app.core.config import settings
from app.core.errors import VoiceAIException
from app.core.logging import logger
from app.services.voice.speech_recognition import model_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan managing safe startup, model warmup, and shutdown."""
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION} [{settings.ENVIRONMENT}]")

    # Safe model warmup during startup (loaded once, not per-request)
    if settings.SPEECH_MODEL_WARMUP_ON_STARTUP:
        logger.info("Initializing speech recognition provider...")
        await model_manager.startup()

    yield

    logger.info("Shutting down Cryvex Voice AI Backend cleanly...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Independent multilingual Voice Intelligence microservice for Cryvex ShopFlow.",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# Register API Routers
app.include_router(health_router)
app.include_router(voice_router)


# --- Centralized Safe Error Handlers ---

@app.exception_handler(VoiceAIException)
async def handle_voice_ai_exception(request: Request, exc: VoiceAIException):
    """Handles domain-specific Voice AI exceptions with structured, safe error payloads."""
    req_id = request.headers.get("X-Request-ID", "-")
    logger.warning(
        f"VoiceAIException [{exc.error_code}]: {exc.message} (status: {exc.status_code})",
        extra={"request_id": req_id}
    )
    content: Dict[str, Any] = {
        "status": "error",
        "error_code": exc.error_code,
        "message": exc.message,
        "retryable": exc.retryable,
    }
    if exc.details:
        content["details"] = exc.details

    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    """Sanitizes Pydantic request validation errors to avoid leaking internal structures."""
    req_id = request.headers.get("X-Request-ID", "-")
    logger.warning(f"Request validation failure on {request.url.path}", extra={"request_id": req_id})
    errors = []
    for err in exc.errors():
        field_loc = " -> ".join([str(loc) for loc in err.get("loc", []) if loc != "body"])
        errors.append({
            "field": field_loc or "body",
            "message": err.get("msg", "Invalid value"),
        })

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": "error",
            "error_code": "REQUEST_VALIDATION_FAILED",
            "message": "The request body or parameters failed validation",
            "retryable": False,
            "validation_errors": errors,
        }
    )


@app.exception_handler(HTTPException)
async def handle_http_exception(request: Request, exc: HTTPException):
    """Wraps FastAPI HTTPExceptions safely."""
    req_id = request.headers.get("X-Request-ID", "-")
    logger.warning(f"HTTPException [{exc.status_code}]: {exc.detail}", extra={"request_id": req_id})
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "error_code": "HTTP_ERROR",
            "message": str(exc.detail),
            "retryable": False,
        }
    )


@app.exception_handler(Exception)
async def handle_unexpected_exception(request: Request, exc: Exception):
    """Catch-all handler ensuring internal stack traces, DB credentials, or secrets never leak."""
    req_id = request.headers.get("X-Request-ID", "-")
    logger.error(f"Unhandled internal server error: {type(exc).__name__}: {str(exc)}", extra={"request_id": req_id})
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": "error",
            "error_code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected internal server error occurred. Please retry with a valid request ID.",
            "retryable": True,
        }
    )
