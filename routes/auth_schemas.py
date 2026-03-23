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


class ThemeResponse(BaseModel):
    theme: str
