import secrets

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import get_settings

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_HEADER = "x-csrf-token"


def set_csrf_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.csrf_cookie_name,
        token,
        httponly=False,  # must be readable by the SPA (double-submit pattern)
        secure=bool(settings.cookie_secure),
        samesite="lax",
        path="/",
    )


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit cookie CSRF protection for mutating /api requests."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = get_settings()
        cookie_token = request.cookies.get(settings.csrf_cookie_name)

        if request.method not in SAFE_METHODS and request.url.path.startswith("/api"):
            header_token = request.headers.get(CSRF_HEADER)
            if (
                not cookie_token
                or not header_token
                or not secrets.compare_digest(cookie_token, header_token)
            ):
                return JSONResponse({"detail": "csrf_failed"}, status_code=403)

        request.state.csrf_token = cookie_token or secrets.token_urlsafe(24)
        response = await call_next(request)
        if not cookie_token:
            set_csrf_cookie(response, request.state.csrf_token)
        return response
