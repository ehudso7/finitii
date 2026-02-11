"""In-memory rate limiting middleware for beta deployment.

Limits:
  /auth/*          → 10 requests/minute per IP
  /user/export     → 3 requests/day per user
  /user/delete     → 1 request/day per user

No Redis required — suitable for single-instance beta.
"""

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# (max_requests, window_seconds)
_IP_RULES: list[tuple[str, int, int]] = [
    ("/auth/", 10, 60),
]

_USER_RULES: list[tuple[str, int, int]] = [
    ("/user/export", 3, 86400),
    ("/user/delete", 1, 86400),
]


class _TokenBucket:
    """Simple sliding-window counter store."""

    def __init__(self) -> None:
        # key -> list of timestamps
        self._hits: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str, max_requests: int, window: int) -> bool:
        now = time.monotonic()
        cutoff = now - window
        hits = self._hits[key]
        # Prune old entries
        self._hits[key] = hits = [t for t in hits if t > cutoff]
        if len(hits) >= max_requests:
            return False
        hits.append(now)
        return True


_ip_bucket = _TokenBucket()
_user_bucket = _TokenBucket()


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        from app.config import settings
        if not settings.is_production:
            return await call_next(request)

        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"

        # IP-based rules (auth endpoints)
        for prefix, max_req, window in _IP_RULES:
            if path.startswith(prefix):
                key = f"ip:{client_ip}:{prefix}"
                if not _ip_bucket.is_allowed(key, max_req, window):
                    return _rate_limit_response(request)

        # User-based rules (export/delete) — checked after auth resolves
        # We check by session token since user_id isn't available pre-auth
        token = request.headers.get("X-Session-Token")
        if token:
            for prefix, max_req, window in _USER_RULES:
                if path.startswith(prefix):
                    key = f"user:{token}:{prefix}"
                    if not _user_bucket.is_allowed(key, max_req, window):
                        return _rate_limit_response(request)

        return await call_next(request)


def _rate_limit_response(request: Request) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=429,
        content={
            "error": True,
            "status_code": 429,
            "detail": "Rate limit exceeded. Please try again later.",
            "request_id": request_id,
        },
        headers={"Retry-After": "60"},
    )
