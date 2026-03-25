"""
Auth routes for Story Forge API
"""
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
import auth
import preferences
from db import get_session

from .auth_schemas import UserResponse, AuthStatus, ThemeResponse, UserPreferenceResponse

router = APIRouter()


@router.get("/login")
def login(request: Request, connect_drive: bool = False, return_to: str | None = Query(default=None)):
    """Redirect to Google OAuth login."""
    fallback_origin = request.headers.get('origin') or request.headers.get('referer')
    redirect_source = return_to or fallback_origin
    auth.set_post_auth_redirect(redirect_source)
    auth.set_oauth_redirect_uri(redirect_source)
    login_url = auth.get_login_url(include_drive=connect_drive, redirect_uri=auth.get_oauth_redirect_uri())
    return RedirectResponse(url=login_url)


@router.get("/callback")
def callback(code: str = None, state: str = None, error: str = None):
    """Handle OAuth callback from Google."""
    if error:
        destination = auth.get_post_auth_redirect('/') or '/'
        if destination.endswith('/'):
            destination = destination[:-1]
        return RedirectResponse(url=f"{destination}/login?error={error}")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    try:
        user = auth.process_callback(code, state)
        if user:
            return RedirectResponse(url=auth.get_post_auth_redirect("/") or "/", status_code=302)
    except Exception as e:
        print(f"Auth callback error: {e}")

    destination = auth.get_post_auth_redirect('/') or '/'
    if destination.endswith('/'):
        destination = destination[:-1]
    return RedirectResponse(url=f"{destination}/login?error=auth_failed")


@router.post("/logout")
def logout(request: Request):
    """Logout and clear session."""
    auth.logout()
    return {"status": "ok"}


@router.get("/me", response_model=UserResponse)
def get_current_user(request: Request):
    """Get current authenticated user."""
    # For review mode, return demo user
    if auth.is_review_mode():
        return UserResponse(
            id="demo-user",
            email="writer@storyforge.local",
            name="Demo Writer",
            avatar=None
        )
    
    user_id = auth.get_session("user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_email = auth.get_session("user_email", None) or ""
    user_name = auth.get_session("user_name", None) or user_email.split("@")[0]
    user_avatar = auth.get_session("user_avatar", None) or ""

    return UserResponse(
        id=str(user_id),
        email=user_email,
        name=user_name,
        avatar=user_avatar if user_avatar else None
    )


@router.get("/status", response_model=AuthStatus)
def auth_status(request: Request):
    """Check if user is authenticated."""
    if auth.is_review_mode():
        return AuthStatus(
            authenticated=True,
            auth_enabled=False,
            review_mode=True,
            google_configured=bool(auth.GOOGLE_CLIENT_ID and auth.GOOGLE_CLIENT_SECRET),
            drive_connected=False,
        )
    user_id = auth.get_session("user_id", None)
    return AuthStatus(
        authenticated=bool(user_id),
        auth_enabled=auth.AUTH_ENABLED,
        review_mode=False,
        google_configured=bool(auth.GOOGLE_CLIENT_ID and auth.GOOGLE_CLIENT_SECRET),
        drive_connected=auth.has_google_drive_access(),
    )


@router.get("/theme", response_model=ThemeResponse)
def get_theme(request: Request):
    """Get current theme preference."""
    if auth.is_review_mode():
        return ThemeResponse(theme="light")
    user_id = auth.get_session("user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return ThemeResponse(theme=preferences.get_theme_for_user(int(user_id)))


@router.post("/theme")
def set_theme(request: Request, body: dict):
    """Set theme preference (light or dark)."""
    theme = body.get("theme", "light")
    if theme not in ("light", "dark"):
        theme = "light"
    if not auth.is_review_mode():
        user_id = auth.get_session("user_id", None)
        if not user_id:
            raise HTTPException(status_code=401, detail="Not authenticated")
        preferences.set_theme_for_user(int(user_id), theme)
        auth.set_session("theme", theme, request)
    return {"theme": theme}


@router.get("/preferences", response_model=UserPreferenceResponse)
def get_preferences(request: Request):
    if auth.is_review_mode():
        return UserPreferenceResponse(
            theme="light",
            dashboard_layout="default",
            editor_font_size=16,
            editor_line_height=1.6,
            default_tts_provider="elevenlabs",
        )
    user_id = auth.get_session("user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    prefs = preferences.get_user_preferences(int(user_id))
    return UserPreferenceResponse(
        theme=prefs.theme,
        dashboard_layout=prefs.dashboard_layout,
        editor_font_size=prefs.editor_font_size,
        editor_line_height=prefs.editor_line_height,
        default_tts_provider=prefs.default_tts_provider,
    )


@router.put("/preferences", response_model=UserPreferenceResponse)
def update_preferences(request: Request, body: dict):
    if auth.is_review_mode():
        return get_preferences(request)
    user_id = auth.get_session("user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    prefs = preferences.update_user_preference(
        int(user_id),
        theme=body.get("theme"),
        dashboard_layout=body.get("dashboard_layout"),
        editor_font_size=body.get("editor_font_size"),
        editor_line_height=body.get("editor_line_height"),
        default_tts_provider=body.get("default_tts_provider"),
    )
    if body.get("theme"):
        auth.set_session("theme", prefs.theme)
    return UserPreferenceResponse(
        theme=prefs.theme,
        dashboard_layout=prefs.dashboard_layout,
        editor_font_size=prefs.editor_font_size,
        editor_line_height=prefs.editor_line_height,
        default_tts_provider=prefs.default_tts_provider,
    )
