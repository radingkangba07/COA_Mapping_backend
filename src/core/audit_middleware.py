import time
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response

from src.core.security import InvalidTokenError, decode_token

EXCLUDED_PATHS: frozenset[str] = frozenset(
    {
        "/health",
        "/api/v1/health",
        "/api/docs",
        "/api/redoc",
        "/api/openapi.json",
    }
)

_audit_logger = structlog.get_logger("audit")


def _extract_user_id(request: Request) -> str | None:
    """Best-effort JWT sub extraction from Authorization header. No DB call."""
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        payload = decode_token(token)
    except InvalidTokenError:
        return None
    sub = payload.get("sub")
    return str(sub) if sub else None


def _extract_client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else None


async def audit_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Emit one structured `http_request` event per non-excluded request."""
    if request.method == "OPTIONS" or request.url.path in EXCLUDED_PATHS:
        return await call_next(request)

    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = int((time.perf_counter() - start) * 1000)

    _audit_logger.info(
        "http_request",
        user_id=_extract_user_id(request),
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration_ms,
        ip=_extract_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return response
