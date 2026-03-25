"""
Auth schemas for Story Forge API
"""
from pydantic import BaseModel
from typing import Optional


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    avatar: Optional[str] = None


class AuthStatus(BaseModel):
    authenticated: bool
    auth_enabled: bool = False
    review_mode: bool = False
    google_configured: bool = False
    drive_connected: bool = False


class ThemeResponse(BaseModel):
    theme: str


class UserPreferenceResponse(BaseModel):
    theme: str
    dashboard_layout: str
    editor_font_size: int
    editor_line_height: float
    default_tts_provider: str
