"""
User preferences module for Story Forge.
Provides UI styling and theme management.
"""

from typing import Optional

from db import UserPreference, get_session


# =============================================================================
# Theme Configuration
# =============================================================================

class Theme:
    """UI Theme configuration."""

    LIGHT = "light"
    DARK = "dark"

    VALID_THEMES = {LIGHT, DARK}

    # Tailwind color schemes for each theme
    SCHEMES = {
        LIGHT: {
            "bg_primary": "bg-white",
            "bg_secondary": "bg-gray-50",
            "bg_card": "bg-white",
            "text_primary": "text-gray-800",
            "text_secondary": "text-gray-600",
            "text_muted": "text-gray-500",
            "border": "border-gray-200",
            "header_bg": "bg-white",
            "accent": "blue",
        },
        DARK: {
            "bg_primary": "bg-gray-900",
            "bg_secondary": "bg-gray-800",
            "bg_card": "bg-gray-800",
            "text_primary": "text-gray-100",
            "text_secondary": "text-gray-300",
            "text_muted": "text-gray-400",
            "border": "border-gray-700",
            "header_bg": "bg-gray-900",
            "accent": "blue",
        },
    }


# =============================================================================
# Preference Management
# =============================================================================


def get_user_preferences(user_id: int) -> UserPreference:
    """
    Get or create user preferences.

    Args:
        user_id: The user's ID

    Returns:
        UserPreference instance
    """
    db = get_session()
    try:
        prefs = db.query(UserPreference).filter(
            UserPreference.user_id == user_id
        ).first()

        if not prefs:
            prefs = UserPreference(
                user_id=user_id,
                theme=Theme.LIGHT,
            )
            db.add(prefs)
            db.commit()
            db.refresh(prefs)

        return prefs
    finally:
        db.close()


def get_theme_for_user(user_id: int) -> str:
    """
    Get the theme preference for a user.

    Args:
        user_id: The user's ID

    Returns:
        Theme string ("light" or "dark")
    """
    prefs = get_user_preferences(user_id)
    return prefs.theme if prefs.theme in Theme.VALID_THEMES else Theme.LIGHT


def set_theme_for_user(user_id: int, theme: str) -> UserPreference:
    """
    Set the theme preference for a user.

    Args:
        user_id: The user's ID
        theme: Theme string ("light" or "dark")

    Returns:
        Updated UserPreference instance
    """
    if theme not in Theme.VALID_THEMES:
        raise ValueError(f"Invalid theme: {theme}")

    db = get_session()
    try:
        prefs = db.query(UserPreference).filter(
            UserPreference.user_id == user_id
        ).first()

        if not prefs:
            prefs = UserPreference(user_id=user_id)
            db.add(prefs)

        prefs.theme = theme
        db.commit()
        db.refresh(prefs)

        return prefs
    finally:
        db.close()


def get_theme_css_classes(theme: str) -> dict:
    """
    Get CSS class mappings for a theme.

    Args:
        theme: Theme string

    Returns:
        Dictionary of CSS class mappings
    """
    return Theme.SCHEMES.get(theme, Theme.SCHEMES[Theme.LIGHT])


def update_user_preference(
    user_id: int,
    *,
    theme: Optional[str] = None,
    dashboard_layout: Optional[str] = None,
    editor_font_size: Optional[int] = None,
    editor_line_height: Optional[float] = None,
    default_tts_provider: Optional[str] = None,
) -> UserPreference:
    """
    Update multiple user preferences at once.

    Args:
        user_id: The user's ID
        theme: New theme (optional)
        dashboard_layout: New dashboard layout (optional)
        editor_font_size: New editor font size (optional)
        editor_line_height: New editor line height (optional)
        default_tts_provider: New default TTS provider (optional)

    Returns:
        Updated UserPreference instance
    """
    if theme is not None and theme not in Theme.VALID_THEMES:
        raise ValueError(f"Invalid theme: {theme}")

    if editor_font_size is not None:
        if not (12 <= editor_font_size <= 24):
            raise ValueError("Font size must be between 12 and 24")

    if editor_line_height is not None:
        if not (1.2 <= editor_line_height <= 2.0):
            raise ValueError("Line height must be between 1.2 and 2.0")

    db = get_session()
    try:
        prefs = db.query(UserPreference).filter(
            UserPreference.user_id == user_id
        ).first()

        if not prefs:
            prefs = UserPreference(user_id=user_id)
            db.add(prefs)

        if theme is not None:
            prefs.theme = theme
        if dashboard_layout is not None:
            prefs.dashboard_layout = dashboard_layout
        if editor_font_size is not None:
            prefs.editor_font_size = editor_font_size
        if editor_line_height is not None:
            prefs.editor_line_height = editor_line_height
        if default_tts_provider is not None:
            prefs.default_tts_provider = default_tts_provider

        db.commit()
        db.refresh(prefs)

        return prefs
    finally:
        db.close()


def toggle_theme(user_id: int) -> tuple[str, dict]:
    """
    Toggle theme for a user between light and dark.

    Args:
        user_id: The user's ID

    Returns:
        Tuple of (new_theme, css_classes)
    """
    prefs = get_user_preferences(user_id)
    new_theme = Theme.DARK if prefs.theme == Theme.LIGHT else Theme.LIGHT
    set_theme_for_user(user_id, new_theme)
    return new_theme, get_theme_css_classes(new_theme)


def delete_user_preferences(user_id: int) -> bool:
    """
    Delete user preferences (e.g., when user is deleted).

    Args:
        user_id: The user's ID

    Returns:
        True if deleted, False if not found
    """
    db = get_session()
    try:
        prefs = db.query(UserPreference).filter(
            UserPreference.user_id == user_id
        ).first()

        if prefs:
            db.delete(prefs)
            db.commit()
            return True
        return False
    finally:
        db.close()
