"""
Authentication module for Story Forge.
Provides Google OAuth 2.0 authentication using authlib.
"""

import os
import json
import keyring
from datetime import datetime, timedelta

from typing import Optional

from authlib.integrations.httpx_client import AsyncOAuth2Client
from sqlalchemy.orm import Session

# Forward declaration for type hints
User = None


def _get_user_class():
    """Get User class lazily to avoid circular imports."""
    global User
    if User is None:
        from db import User as UserClass
        return UserClass
    return User

# =============================================================================
# Configuration
# =============================================================================

# Auth toggle — set AUTH_ENABLED=1 in .env to enforce Google OAuth login
AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "").lower() in ("1", "true", "yes")

# Dev mode toggle — set DEV_MODE=1 in .env to bypass Google OAuth with a dev user
DEV_MODE = os.environ.get("DEV_MODE", "").lower() in ("1", "true", "yes")

# Dev user configuration (used when DEV_MODE=1)
DEV_USER_EMAIL = os.environ.get("DEV_USER_EMAIL", "dev@story-forge.local")
DEV_USER_NAME = os.environ.get("DEV_USER_NAME", "Dev User")
DEV_USER_ID = os.environ.get("DEV_USER_ID", "dev-user-001")

# OAuth settings
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

# Keychain service name for storing OAuth tokens
KEYCHAIN_SERVICE = "story-forge"
KEYCHAIN_TOKEN_KEY = "oauth-tokens"

# Internal user ID (single-user context)
INTERNAL_USER_ID = "story-forge-user-001"

# Session duration
SESSION_DURATION_DAYS = 30


# =============================================================================
# OAuth Client
# =============================================================================

class GoogleOAuth:
    """Google OAuth 2.0 client using authlib."""

    def __init__(self, redirect_uri: str = "http://localhost:8080/auth/callback"):
        self.client_id = GOOGLE_CLIENT_ID
        self.client_secret = GOOGLE_CLIENT_SECRET
        self.redirect_uri = redirect_uri

        # Google OAuth endpoints
        self.authorize_url = "https://accounts.google.com/o/oauth2/v2/auth"
        self.token_url = "https://oauth2.googleapis.com/token"
        self.userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"

        # Scopes requested
        self.scope = "openid email profile"

    def get_authorization_url(self, state: str) -> str:
        """Generate the Google OAuth authorization URL."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": self.scope,
            "state": state,
            "access_type": "offline",  # Get refresh token
            "prompt": "consent",  # Force consent to get refresh token
        }
        # Build URL manually to avoid encoding issues
        param_str = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.authorize_url}?{param_str}"

    async def exchange_code_for_tokens(self, code: str) -> dict:
        """Exchange authorization code for access and refresh tokens."""
        async with AsyncOAuth2Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
        ) as client:
            # Exchange code for tokens
            token_response = await client.post(
                self.token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                },
            )
            token_response.raise_for_status()
            return token_response.json()

    async def get_user_info(self, access_token: str) -> dict:
        """Fetch user information from Google's userinfo endpoint."""
        async with AsyncOAuth2Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
        ) as client:
            response = await client.get(
                self.userinfo_url,
                token=access_token,
            )
            response.raise_for_status()
            return response.json()

    async def refresh_access_token(self, refresh_token: str) -> dict:
        """Refresh the access token using the refresh token."""
        async with AsyncOAuth2Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
        ) as client:
            response = await client.post(
                self.token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
            response.raise_for_status()
            return response.json()


# =============================================================================
# Token Storage (Keyring)
# =============================================================================

def store_tokens(tokens: dict) -> None:
    """Store OAuth tokens securely in the system keychain."""
    token_json = json.dumps(tokens)
    keyring.set_password(KEYCHAIN_SERVICE, KEYCHAIN_TOKEN_KEY, token_json)


def get_tokens() -> Optional[dict]:
    """Retrieve OAuth tokens from the keychain."""
    token_json = keyring.get_password(KEYCHAIN_SERVICE, KEYCHAIN_TOKEN_KEY)
    if token_json:
        return json.loads(token_json)
    return None


def delete_tokens() -> None:
    """Remove OAuth tokens from the keychain."""
    keyring.delete_password(KEYCHAIN_SERVICE, KEYCHAIN_TOKEN_KEY)


def is_token_expired(tokens: dict) -> bool:
    """Check if the access token is expired."""
    if not tokens or "expires_at" not in tokens:
        return True
    expires_at = datetime.fromisoformat(tokens["expires_at"])
    return datetime.now() >= expires_at - timedelta(minutes=5)  # Refresh 5 min early


# =============================================================================
# User Management
# =============================================================================

def get_or_create_user(db: Session, user_info: dict):
    """Get existing user or create new one from OAuth user info."""
    User = _get_user_class()

    provider_user_id = user_info.get("sub", "")
    email = user_info.get("email", "")
    name = user_info.get("name", "")
    avatar_url = user_info.get("picture", "")

    # Try to find existing user
    user = db.query(User).filter(
        User.provider == "google",
        User.provider_user_id == provider_user_id,
    ).first()

    if user:
        # Update user info
        user.email = email
        user.name = name
        user.avatar_url = avatar_url
        user.last_login_at = datetime.now()
    else:
        # Create new user
        user = User(
            provider="google",
            provider_user_id=provider_user_id,
            email=email,
            name=name,
            avatar_url=avatar_url,
            internal_user_id=INTERNAL_USER_ID,
        )
        db.add(user)

    db.commit()
    db.refresh(user)
    return user


def get_current_user(db: Session):
    """Get the current authenticated user (single-user context)."""
    User = _get_user_class()
    return db.query(User).filter(
        User.internal_user_id == INTERNAL_USER_ID
    ).first()


# =============================================================================
# Session Management (NiceGUI)
# =============================================================================

# In-memory session storage for NiceGUI
_session_data = {}


def set_session(key: str, value: any) -> None:
    """Set a session value."""
    _session_data[key] = value


def get_session(key: str, default: any = None) -> any:
    """Get a session value."""
    return _session_data.get(key, default)


def clear_session() -> None:
    """Clear all session data."""
    _session_data.clear()


def is_authenticated() -> bool:
    """Check if user is authenticated. Auth is bypassed when AUTH_ENABLED is not set."""
    if not AUTH_ENABLED or DEV_MODE:
        # In dev mode, check if dev user session is set
        return get_session("user_id") is not None
    return get_session("user_id") is not None


def is_dev_mode() -> bool:
    """Check if dev mode is enabled."""
    return DEV_MODE


def ensure_dev_user() -> Optional[dict]:
    """
    Ensure dev user exists in database.
    Used when DEV_MODE=1 to create a local user for testing.

    Returns:
        dict with dev user info, or None if not in dev mode
    """
    if not DEV_MODE:
        return None

    from db import get_session, User
    db = get_session()
    try:
        # Find or create dev user
        user = db.query(User).filter(User.email == DEV_USER_EMAIL).first()

        if not user:
            user = User(
                provider="dev",
                provider_user_id=DEV_USER_ID,
                email=DEV_USER_EMAIL,
                name=DEV_USER_NAME,
                internal_user_id=DEV_USER_ID,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        return {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "provider": user.provider,
        }
    finally:
        db.close()


def login_dev_user() -> bool:
    """
    Set up session for dev user.
    Call this when in dev mode to bypass OAuth.

    Returns:
        True if dev user was logged in, False otherwise
    """
    if not DEV_MODE:
        return False

    dev_user = ensure_dev_user()
    if dev_user:
        set_session("user_id", dev_user["id"])
        set_session("user_email", dev_user["email"])
        set_session("user_name", dev_user["name"])
        set_session("user_provider", dev_user["provider"])
        return True

    return False


def dev_mode_toggle(enabled: bool) -> None:
    """
    Toggle dev mode at runtime.

    Args:
        enabled: True to enable dev mode, False to disable
    """
    global DEV_MODE
    DEV_MODE = enabled
    if not enabled:
        # Clear session when disabling dev mode
        clear_session()


# =============================================================================
# Login Flow
# =============================================================================

async def handle_oauth_callback(db: Session, code: str) -> dict:
    """Handle the OAuth callback and complete authentication."""
    oauth = GoogleOAuth()
    
    # Exchange code for tokens
    tokens = await oauth.exchange_code_for_tokens(code)
    
    # Calculate expiry
    expires_in = tokens.get("expires_in", 3600)
    expires_at = datetime.now() + timedelta(seconds=expires_in)
    tokens["expires_at"] = expires_at.isoformat()
    
    # Store tokens securely
    store_tokens(tokens)
    
    # Get user info
    user_info = await oauth.get_user_info(tokens["access_token"])
    
    # Create or update user
    user = get_or_create_user(db, user_info)
    
    # Set session
    set_session("user_id", user.id)
    set_session("user_email", user.email)
    set_session("user_name", user.name)
    set_session("user_avatar", user.avatar_url)
    
    return {
        "user": user,
        "tokens": tokens,
    }


async def refresh_session_if_needed() -> bool:
    """Refresh access token if expired. Returns True if successful."""
    tokens = get_tokens()
    if not tokens or "refresh_token" not in tokens:
        return False
    
    if is_token_expired(tokens):
        oauth = GoogleOAuth()
        try:
            new_tokens = await oauth.refresh_access_token(tokens["refresh_token"])
            
            # Preserve the refresh token (it might not be in the response)
            if "refresh_token" not in new_tokens:
                new_tokens["refresh_token"] = tokens["refresh_token"]
            
            # Calculate new expiry
            expires_in = new_tokens.get("expires_in", 3600)
            expires_at = datetime.now() + timedelta(seconds=expires_in)
            new_tokens["expires_at"] = expires_at.isoformat()
            
            store_tokens(new_tokens)
            return True
        except Exception:
            # Token refresh failed
            return False
    
    return True


def logout() -> None:
    """Log out the user."""
    delete_tokens()
    clear_session()


def get_login_url() -> str:
    """Get the Google OAuth login URL."""
    import secrets
    state = secrets.token_urlsafe(32)
    set_session("oauth_state", state)
    
    oauth = GoogleOAuth()
    return oauth.get_authorization_url(state)


def validate_state(state: str) -> bool:
    """Validate the OAuth state parameter."""
    saved_state = get_session("oauth_state")
    return saved_state == state
