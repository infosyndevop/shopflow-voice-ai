"""Service-to-service authentication and strict tenant security context."""

import re
import secrets
import uuid
from typing import Optional
from fastapi import Header, Request
from pydantic import BaseModel

from app.core.config import settings
from app.core.errors import AuthenticationError, TenantContextError
from app.core.logging import logger


TENANT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]+$")


class TenantSecurityContext(BaseModel):
    """Verified tenant execution context derived from authenticated headers."""
    tenant_id: str
    is_authenticated: bool
    request_id: str


def sanitize_tenant_id(raw_tenant_id: Optional[str]) -> str:
    """Validates and sanitizes tenant identifier to prevent tenant injection or directory traversal."""
    if not raw_tenant_id or not raw_tenant_id.strip():
        raise TenantContextError("Missing required tenant identification header")

    tenant_id = raw_tenant_id.strip()
    if len(tenant_id) > 64 or not TENANT_ID_PATTERN.match(tenant_id):
        raise TenantContextError("Invalid tenant identifier format")

    return tenant_id


def verify_service_credentials(
    service_key: Optional[str] = Header(None, alias="X-Service-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> bool:
    """Validates service-to-service shared secret using constant-time comparison."""
    token: Optional[str] = None

    if service_key:
        token = service_key.strip()
    elif authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()

    if not token:
        raise AuthenticationError("Service authentication credential missing")

    # Constant-time comparison to prevent timing attacks
    expected_key = settings.SERVICE_API_KEY
    if not secrets.compare_digest(token, expected_key):
        raise AuthenticationError("Invalid service authentication credential")

    return True


async def get_tenant_context(
    request: Request,
    tenant_header: Optional[str] = Header(None, alias="X-Tenant-ID"),
    service_key: Optional[str] = Header(None, alias="X-Service-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> TenantSecurityContext:
    """FastAPI dependency to extract and authenticate tenant security context.

    Ensures that every incoming request is verified with service credentials,
    and the tenant_id is properly extracted and validated.
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

    # Step 1: Verify service-to-service credentials
    verify_service_credentials(service_key=service_key, authorization=authorization)

    # Step 2: Validate tenant ID
    tenant_id = sanitize_tenant_id(tenant_header)

    return TenantSecurityContext(
        tenant_id=tenant_id,
        is_authenticated=True,
        request_id=request_id
    )
