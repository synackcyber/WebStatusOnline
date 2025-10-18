"""
Authentication middleware for FastAPI.

Protects routes by validating session tokens from cookies.
"""
import logging
from fastapi import Request, Response
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable

logger = logging.getLogger(__name__)

# Global auth manager reference (set by main.py during startup)
_auth_manager = None


def set_auth_manager(manager):
    """Set the global auth manager instance."""
    global _auth_manager
    _auth_manager = manager


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to protect routes with authentication."""

    # Routes that don't require authentication
    PUBLIC_PATHS = [
        "/auth/",
        "/public/",
        "/api/v1/public/",
        "/static/",
        "/sounds/",
        "/docs",
        "/openapi.json",
        "/redoc"
    ]

    # Routes that should redirect to login page (HTML pages)
    HTML_PATHS = [
        "/",
        "/ui-demo"
    ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request through authentication middleware.

        Args:
            request: FastAPI request
            call_next: Next middleware/route handler

        Returns:
            Response
        """
        # If auth manager not initialized yet, pass through
        if _auth_manager is None:
            return await call_next(request)

        path = request.url.path

        # Allow public paths
        if self._is_public_path(path):
            return await call_next(request)

        # Check if setup is required (no users exist)
        setup_required = await _auth_manager.setup_required()

        # If setup required, only allow access to setup page
        if setup_required:
            if path == "/auth/setup":
                return await call_next(request)
            else:
                # Redirect to setup for HTML pages, return 401 for API
                if self._is_html_path(path):
                    return RedirectResponse(url="/auth/setup", status_code=303)
                else:
                    return JSONResponse(
                        status_code=401,
                        content={"success": False, "message": "Setup required", "setup_required": True}
                    )

        # Get session token from cookie
        session_token = request.cookies.get("session_token")

        # Validate session
        user = await _auth_manager.validate_session(session_token) if session_token else None

        if user:
            # User is authenticated - attach user to request state
            request.state.user = user
            return await call_next(request)
        else:
            # Not authenticated
            # Allow access to login page
            if path == "/auth/login":
                return await call_next(request)

            # Redirect to login for HTML pages, return 401 for API
            if self._is_html_path(path) or path.startswith("/api/v1/"):
                if path.startswith("/api/v1/"):
                    return JSONResponse(
                        status_code=401,
                        content={"success": False, "message": "Authentication required"}
                    )
                else:
                    return RedirectResponse(url="/auth/login", status_code=303)
            else:
                return await call_next(request)

    def _is_public_path(self, path: str) -> bool:
        """Check if path is public (doesn't require auth)."""
        return any(path.startswith(public_path) for public_path in self.PUBLIC_PATHS)

    def _is_html_path(self, path: str) -> bool:
        """Check if path serves HTML (should redirect to login)."""
        return any(path == html_path for html_path in self.HTML_PATHS)
