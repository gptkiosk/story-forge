"""
Auth routes for Story Forge API
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
import auth

from .auth_schemas import UserResponse, AuthStatus, ThemeResponse

import os

# Check if we're in review mode (no auth required)
REVIEW_MODE = os.environ.get("REVIEW_MODE", "true").lower() == "true"

router = APIRouter()


@router.get("/login")
def login():
    """Redirect to Google OAuth login."""
    login_url = auth.get_login_url()
    return RedirectResponse(url=login_url)


@router.get("/callback")
def callback(code: str = None, state: str = None, error: str = None):
    """Handle OAuth callback from Google."""
    if error:
        return RedirectResponse(url="/login?error=" + error)

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    try:
        user = auth.process_callback(code, state)
        if user:
            return RedirectResponse(url="/", status_code=302)
    except Exception as e:
        print(f"Auth callback error: {e}")

    return RedirectResponse(url="/login?error=auth_failed")


@router.post("/logout")
def logout(request: Request):
    """Logout and clear session."""
    auth.clear_session(request)
    return {"status": "ok"}


@router.get("/me", response_model=UserResponse)
def get_current_user(request: Request):
    """Get current authenticated user."""
    # For review mode, return demo user
    if REVIEW_MODE:
        return UserResponse(
            id="demo-user",
            email="writer@storyforge.local",
            name="Demo Writer",
            avatar=None
        )
    
    user_id = auth.get_session("user_id", request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_email = auth.get_session("user_email", request) or ""
    user_name = auth.get_session("user_name", request) or user_email.split("@")[0]
    user_avatar = auth.get_session("user_avatar", request) or ""

    return UserResponse(
        id=str(user_id),
        email=user_email,
        name=user_name,
        avatar=user_avatar if user_avatar else None
    )


@router.get("/status", response_model=AuthStatus)
def auth_status(request: Request):
    """Check if user is authenticated."""
    if REVIEW_MODE:
        return AuthStatus(authenticated=True)
    user_id = auth.get_session("user_id", request)
    return AuthStatus(authenticated=bool(user_id))


@router.get("/theme", response_model=ThemeResponse)
def get_theme(request: Request):
    """Get current theme preference."""
    if REVIEW_MODE:
        return ThemeResponse(theme="light")
    theme = auth.get_session("theme", request) or "light"
    return ThemeResponse(theme=theme)


@router.post("/theme")
def set_theme(request: Request, body: dict):
    """Set theme preference (light or dark)."""
    theme = body.get("theme", "light")
    if theme not in ("light", "dark"):
        theme = "light"
    if not REVIEW_MODE:
        auth.set_session("theme", theme, request)
    return {"theme": theme}
