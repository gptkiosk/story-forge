"""
User preferences module for Story Forge.
Provides UI styling and theme management.
"""

from typing import Optional

from db import UserPreference, get_session


# =============================================================================
# Theme Configuration - Warm Studio Palette
# =============================================================================

class Theme:
    """UI Theme configuration with warm, cozy writing studio colors."""

    LIGHT = "light"
    DARK = "dark"

    VALID_THEMES = {LIGHT, DARK}

    # Warm Cream Light Mode
    LIGHT_SCHEME = {
        # Backgrounds
        "bg_primary": "#FDF8F3",
        "bg_secondary": "#F7F1EB",
        "bg_card": "#FFFFFF",
        "bg_header": "#FDF8F3",
        "bg_input": "#FFFFFF",
        "bg_hover": "#F5EFE8",
        "bg_selected": "#EDE6DD",

        # Text
        "text_primary": "#2D2A26",
        "text_secondary": "#6B6560",
        "text_muted": "#9A948D",
        "text_inverse": "#FFFFFF",

        # Accents
        "accent_primary": "#C9A96E",
        "accent_hover": "#B8955A",
        "accent_soft": "#F5EDE0",
        "accent_blue": "#6B8CAE",
        "accent_green": "#7CAE8D",
        "accent_purple": "#9B8BB4",

        # Borders
        "border_light": "#E8E0D8",
        "border_medium": "#D4CBC2",

        # Status
        "status_draft": "#9A948D",
        "status_in_progress": "#6B8CAE",
        "status_completed": "#7CAE8D",
        "status_archived": "#B8955A",
        "status_pending": "#D4B87A",
        "status_failed": "#CA8B8B",

        # Shadows
        "shadow_sm": "0 1px 2px rgba(45, 42, 38, 0.05)",
        "shadow_md": "0 4px 12px rgba(45, 42, 38, 0.08)",
        "shadow_lg": "0 8px 24px rgba(45, 42, 38, 0.12)",

        # Radii
        "radius_sm": "6px",
        "radius_md": "10px",
        "radius_lg": "16px",
        "radius_full": "9999px",
    }

    # Soft Shaded Dark Mode (warm dark brown, transitions from cream theme)
    DARK_SCHEME = {
        # Backgrounds
        "bg_primary": "#2A2723",
        "bg_secondary": "#353028",
        "bg_card": "#302B26",
        "bg_header": "#2D2924",
        "bg_input": "#3A352D",
        "bg_hover": "#403A31",
        "bg_selected": "#4A443B",

        # Text
        "text_primary": "#F5F0EB",
        "text_secondary": "#A8A099",
        "text_muted": "#7A756E",
        "text_inverse": "#FDF8F3",

        # Accents
        "accent_primary": "#D4B87A",
        "accent_hover": "#E5C98A",
        "accent_soft": "#3D3528",
        "accent_blue": "#8BA8C4",
        "accent_green": "#8BC4A8",
        "accent_purple": "#B4A8CC",

        # Borders
        "border_light": "#3D3933",
        "border_medium": "#524B43",

        # Status
        "status_draft": "#A8A099",
        "status_in_progress": "#8BA8C4",
        "status_completed": "#8BC4A8",
        "status_archived": "#D4B87A",
        "status_pending": "#E5C98A",
        "status_failed": "#CA9B9B",

        # Shadows
        "shadow_sm": "0 1px 2px rgba(0, 0, 0, 0.2)",
        "shadow_md": "0 4px 12px rgba(0, 0, 0, 0.3)",
        "shadow_lg": "0 8px 24px rgba(0, 0, 0, 0.4)",

        # Radii
        "radius_sm": "6px",
        "radius_md": "10px",
        "radius_lg": "16px",
        "radius_full": "9999px",
    }

    SCHEMES = {
        LIGHT: LIGHT_SCHEME,
        DARK: DARK_SCHEME,
    }


# =============================================================================
# Writers' Quotes
# =============================================================================

WRITERS_QUOTES = [
    "Start writing, no matter what. The water does not flow until the faucet is turned on. — Louis L'Amour",
    "There is no greater agony than bearing an untold story inside you. — Maya Angelou",
    "You can always edit a bad page. You can't edit a blank page. — Terry Pratchett",
    "The first draft is just you telling yourself the story. — Terry Pratchett",
    "Writing is easy. All you have to do is cross out the wrong words. — Mark Twain",
    "One day I will find the right words, and they will be simple. — Jack Kerouac",
    "Fill your paper with the breathings of your heart. — William Wordsworth",
    "Either write something worth reading or do something worth writing. — Benjamin Franklin",
    "A writer is someone for whom writing is more difficult than it is for other people. — Thomas Mann",
    "The scariest moment is always just before you start. — Stephen King",
    "You don't start out writing good stuff. You start out writing crap and thinking it's good stuff. — Octavia E. Butler",
    "I write to discover what I know. — Flannery O'Connor",
    "Writing is thinking on paper. — William Zinsser",
    "The art of writing is the art of discovering what you believe. — Gustave Flaubert",
    "If you want to be a writer, you must do two things: read a lot and write a lot. — Stephen King",
]


def get_random_quote() -> str:
    """Get a random writers' quote."""
    import random
    return random.choice(WRITERS_QUOTES)


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


def get_theme_inline_styles(theme: str) -> dict:
    """
    Get inline style mappings for a theme.
    Used for NiceGUI components.

    Args:
        theme: Theme string

    Returns:
        Dictionary of style mappings
    """
    scheme = Theme.SCHEMES.get(theme, Theme.SCHEMES[Theme.LIGHT])

    return {
        "bg_primary": f"background-color: {scheme['bg_primary']}",
        "bg_secondary": f"background-color: {scheme['bg_secondary']}",
        "bg_card": f"background-color: {scheme['bg_card']}",
        "text_primary": f"color: {scheme['text_primary']}",
        "text_secondary": f"color: {scheme['text_secondary']}",
        "text_muted": f"color: {scheme['text_muted']}",
        "border_light": f"border-color: {scheme['border_light']}",
        "accent_primary": f"color: {scheme['accent_primary']}",
    }


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


def get_status_color(status: str, theme: str) -> str:
    """
    Get status color for a given status and theme.

    Args:
        status: Status string (draft, in_progress, completed, etc.)
        theme: Theme string

    Returns:
        Color string
    """
    scheme = Theme.SCHEMES.get(theme, Theme.SCHEMES[Theme.LIGHT])
    key = f"status_{status.lower()}"
    return scheme.get(key, scheme["status_draft"])
