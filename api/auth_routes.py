"""
Authentication API routes.

Endpoints:
- POST /auth/setup - Initial user setup
- POST /auth/login - User login
- POST /auth/logout - User logout
- GET /auth/status - Check auth status
- GET /auth/setup - Serve setup page
- GET /auth/login - Serve login page
"""
import logging
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from auth.models import (
    SetupRequest,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    StatusResponse,
    ErrorResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])

# Global auth manager (set by main.py)
auth_manager = None


def set_auth_manager(manager):
    """Set the global auth manager instance."""
    global auth_manager
    auth_manager = manager


def get_client_ip(request: Request) -> str:
    """Extract client IP address from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.get("/setup", response_class=HTMLResponse)
async def get_setup_page():
    """Serve the setup wizard page."""
    try:
        with open('web/templates/setup.html', 'r') as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Setup page not found")


@router.post("/setup")
async def setup(request: Request, setup_data: SetupRequest):
    """
    Create initial user account.

    Only works if no users exist.
    """
    if not auth_manager:
        raise HTTPException(status_code=500, detail="Auth manager not initialized")

    # Check if setup already complete
    setup_required = await auth_manager.setup_required()
    if not setup_required:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Setup already completed"}
        )

    # Create user
    ip_address = get_client_ip(request)
    success, message, user_id = await auth_manager.create_user(
        setup_data.username,
        setup_data.password,
        ip_address
    )

    if not success:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": message}
        )

    # Auto-login after setup
    success, message, session_token = await auth_manager.login(
        setup_data.username,
        setup_data.password,
        ip_address,
        request.headers.get("user-agent")
    )

    if not success:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "User created but login failed"}
        )

    # Set session cookie
    response = JSONResponse(content={
        "success": True,
        "message": "Setup completed successfully"
    })

    cookie_settings = auth_manager.session_manager.get_cookie_settings(session_token)
    response.set_cookie(**cookie_settings)

    return response


@router.get("/login", response_class=HTMLResponse)
async def get_login_page():
    """Serve the login page."""
    try:
        with open('web/templates/login.html', 'r') as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Login page not found")


@router.post("/login")
async def login(request: Request, login_data: LoginRequest):
    """
    Authenticate user and create session.

    Returns session token in HTTP-only cookie.
    """
    if not auth_manager:
        raise HTTPException(status_code=500, detail="Auth manager not initialized")

    # Attempt login
    ip_address = get_client_ip(request)
    user_agent = request.headers.get("user-agent")

    success, message, session_token = await auth_manager.login(
        login_data.username,
        login_data.password,
        ip_address,
        user_agent
    )

    if not success:
        return JSONResponse(
            status_code=401,
            content={"success": False, "message": message}
        )

    # Set session cookie
    response = JSONResponse(content={
        "success": True,
        "message": "Login successful"
    })

    cookie_settings = auth_manager.session_manager.get_cookie_settings(session_token)
    response.set_cookie(**cookie_settings)

    return response


@router.post("/logout")
async def logout(request: Request):
    """
    Logout user by invalidating session.

    Clears session cookie.
    """
    if not auth_manager:
        raise HTTPException(status_code=500, detail="Auth manager not initialized")

    session_token = request.cookies.get("session_token")
    if session_token:
        ip_address = get_client_ip(request)
        await auth_manager.logout(session_token, ip_address)

    # Clear cookie
    response = JSONResponse(content={
        "success": True,
        "message": "Logged out successfully"
    })

    cookie_settings = auth_manager.session_manager.get_logout_cookie_settings()
    response.set_cookie(**cookie_settings)

    return response


@router.get("/status")
async def get_status(request: Request):
    """
    Get current authentication status.

    Returns whether user is authenticated and if setup is required.
    """
    if not auth_manager:
        raise HTTPException(status_code=500, detail="Auth manager not initialized")

    # Check if setup required
    setup_required = await auth_manager.setup_required()

    if setup_required:
        return StatusResponse(
            authenticated=False,
            setup_required=True,
            user=None
        )

    # Check if authenticated
    session_token = request.cookies.get("session_token")
    user = await auth_manager.validate_session(session_token) if session_token else None

    return StatusResponse(
        authenticated=user is not None,
        setup_required=False,
        user=user
    )
