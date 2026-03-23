"""
Auth routes for Story Forge API
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
import auth as auth_module

router = APIRouter()


@router.get("/login")
def login():
    """Redirect to Google OAuth login."""
    login_url = auth_module.auth.get_login_url()
    return RedirectResponse(url=login_url)


@router.get("/callback")
def callback(code: str = None, state: str = None, error: str = None):
    """Handle OAuth callback from Google."""
    if error:
        return RedirectResponse(url="/login?error=" + error)

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    try:
        user = auth_module.auth.process_callback(code, state)
        if user:
            return RedirectResponse(url="/", status_code=302)
    except Exception as e:
        print(f"Auth callback error: {e}")

    return RedirectResponse(url="/login?error=auth_failed")


@router.post("/logout")
def logout(request: Request):
    """Logout and clear session."""
    auth_module.auth.clear_session(request)
    return {"status": "ok"}


@router.get("/me")
def get_current_user(request: Request):
    """Get current authenticated user."""
    user_id = auth_module.auth.get_session("user_id", request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_email = auth_module.auth.get_session("user_email", request) or ""
    user_name = auth_module.auth.get_session("user_name", request) or user_email.split("@")[0]
    user_avatar = auth_module.auth.get_session("user_avatar", request) or ""

    return {
        "id": user_id,
        "email": user_email,
        "name": user_name,
        "avatar": user_avatar if user_avatar else None
    }


@router.get("/status")
def auth_status(request: Request):
    """Check if user is authenticated."""
    user_id = auth_module.auth.get_session("user_id", request)
    return {"authenticated": bool(user_id)}


@router.get("/theme")
def get_theme():
    """Get current theme preference."""
    theme = auth_module.auth.get_session("theme", "light")
    return {"theme": theme}


@router.post("/theme")
def set_theme(body: dict):
    """Set theme preference (light or dark)."""
    theme = body.get("theme", "light")
    if theme not in ("light", "dark"):
        theme = "light"
    auth_module.auth.set_session("theme", theme)
    return {"theme": theme}
