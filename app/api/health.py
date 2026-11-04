"""Health and operational diagnostic endpoints."""

import os
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Response, status

from app.core.config import settings
from app.schemas.voice_schemas import (
    DiagnosticsResponse,
    LiveStatusResponse,
    ModelStatusResponse,
    ReadyStatusResponse,
)
from app.services.catalogue import get_catalogue_provider
from app.services.voice.speech_recognition import model_manager

router = APIRouter(prefix="/health", tags=["Health"])

START_TIME = time.time()
REQUEST_COUNTER = 0


def increment_request_counter():
    global REQUEST_COUNTER
    REQUEST_COUNTER += 1


@router.get("/live", response_model=LiveStatusResponse, status_code=status.HTTP_200_OK)
async def health_live():
    """Confirm the application process is running."""
    return LiveStatusResponse(
        status="alive",
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@router.get("/ready", response_model=ReadyStatusResponse)
async def health_ready(response: Response):
    """Confirm required components are initialized and ready.

    Returns 503 during cold-start if speech model or catalogue is not ready.
    """
    catalogue_ok = await get_catalogue_provider().check_health()
    model_status = model_manager.get_provider().get_status()
    model_ok = model_status.is_ready

    all_ready = catalogue_ok and model_ok
    if not all_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        status_text = "service_unavailable_cold_start"
    else:
        status_text = "ready"

    return ReadyStatusResponse(
        status=status_text,
        model_ready=model_ok,
        catalogue_provider_ready=catalogue_ok,
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@router.get("/model", response_model=ModelStatusResponse)
async def health_model():
    """Return speech recognition model lifecycle status without exposing secrets or paths."""
    return model_manager.get_provider().get_status()


@router.get("/diagnostics", response_model=DiagnosticsResponse)
async def health_diagnostics():
    """Return safe operational diagnostics."""
    uptime = round(time.time() - START_TIME, 2)
    model_status = model_manager.get_provider().get_status()

    # Calculate safe memory usage without external heavy psutil
    memory_mb = None
    try:
        import resource
        memory_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2)
    except Exception:
        # Windows fallback
        memory_mb = None

    return DiagnosticsResponse(
        status="healthy",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        model_state=model_status.state,
        uptime_seconds=uptime,
        total_requests_processed=REQUEST_COUNTER,
        memory_usage_mb=memory_mb
    )

