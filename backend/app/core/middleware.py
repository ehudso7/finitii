"""Middleware: request ID injection, structured access logging."""

import hashlib
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("finitii.access")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Inject a unique request ID into each request and response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Structured access log: request_id, user_id (hashed), endpoint, status."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        elapsed_ms = round((time.monotonic() - start) * 1000, 1)

        request_id = getattr(request.state, "request_id", "-")
        user_id_raw = getattr(request.state, "user_id", None)
        user_id = _hash_user_id(user_id_raw) if user_id_raw else "-"
        client_ip = request.client.host if request.client else "-"

        logger.info(
            "request_id=%s user=%s ip=%s method=%s path=%s status=%d elapsed_ms=%.1f",
            request_id,
            user_id,
            client_ip,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response


def _hash_user_id(uid: str) -> str:
    """Hash user ID for log privacy — first 12 chars of SHA-256."""
    return hashlib.sha256(str(uid).encode()).hexdigest()[:12]
