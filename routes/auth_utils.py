"""
Auth bypass utilities for Story Forge API
For review/development mode - allows access without OAuth
"""
import os

# Check if we're in review mode (no auth required)
_REVIEW_MODE = os.environ.get("REVIEW_MODE", "true").lower()
REVIEW_MODE = _REVIEW_MODE in ("true", "1", "yes")

# Default user ID for review mode
DEFAULT_USER_ID = "1"


def get_user_id(request) -> str:
    """Get user ID from session, or return default for review mode."""
    import auth
    
    user_id = auth.get_session("user_id", request)
    if not user_id and REVIEW_MODE:
        user_id = DEFAULT_USER_ID
    return user_id


def require_auth(request) -> str:
    """Require authentication, returning user_id or raising 401."""
    user_id = get_user_id(request)
    if not user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id
