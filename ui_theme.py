"""
Theme-aware UI components for Story Forge.
Provides helper functions for consistent warm studio styling.
"""

import preferences


# =============================================================================
# Theme-Aware CSS Classes
# =============================================================================

def get_theme_classes(theme: str) -> dict:
    """Get all theme CSS classes as a dictionary."""
    return preferences.get_theme_css_classes(theme)


def theme_classes(theme: str, element: str) -> str:
    """
    Get CSS class string for a theme element.

    Args:
        theme: "light" or "dark"
        element: Element name (bg_primary, text_primary, etc.)

    Returns:
        CSS class string
    """
    classes = get_theme_classes(theme)
    return classes.get(element, "")


# =============================================================================
# Theme Inline Styles for NiceGUI Components
# =============================================================================

def get_inline_styles(theme: str) -> dict:
    """Get inline style dict for NiceGUI components."""
    return preferences.get_theme_inline_styles(theme)


def inline_style(theme: str, element: str) -> str:
    """Get inline style string for an element."""
    styles = get_inline_styles(theme)
    return styles.get(element, "")


# =============================================================================
# Background Styles
# =============================================================================

def page_bg(theme: str) -> str:
    """Get page background inline style."""
    scheme = preferences.Theme.SCHEMES.get(theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])
    return f"background-color: {scheme['bg_primary']}; min-height: 100vh;"


def header_bg(theme: str) -> str:
    """Get header background inline style."""
    scheme = preferences.Theme.SCHEMES.get(theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])
    return f"background-color: {scheme['bg_header']}; border-bottom: 1px solid {scheme['border_light']};"


def card_bg(theme: str) -> str:
    """Get card background inline style."""
    scheme = preferences.Theme.SCHEMES.get(theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])
    return f"background-color: {scheme['bg_card']}; border: 1px solid {scheme['border_light']}; border-radius: 16px;"


def card_styles(theme: str, extra: str = "") -> str:
    """Get card container styles - bordered panels."""
    scheme = preferences.Theme.SCHEMES.get(theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])
    base = f"background-color: {scheme['bg_card']}; border: 2px solid {scheme['border_medium']}; border-radius: 16px; padding: 1.5rem; transition: all 0.25s ease;"
    return f"{base} {extra}".strip()


# =============================================================================
# Text Styles
# =============================================================================

def text_primary(theme: str) -> str:
    """Get primary text color style."""
    scheme = preferences.Theme.SCHEMES.get(theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])
    return f"color: {scheme['text_primary']};"


def text_secondary(theme: str) -> str:
    """Get secondary text color style."""
    scheme = preferences.Theme.SCHEMES.get(theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])
    return f"color: {scheme['text_secondary']};"


def text_muted(theme: str) -> str:
    """Get muted text color style."""
    scheme = preferences.Theme.SCHEMES.get(theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])
    return f"color: {scheme['text_muted']};"


def text_accent(theme: str) -> str:
    """Get accent text color style."""
    scheme = preferences.Theme.SCHEMES.get(theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])
    return f"color: {scheme['accent_primary']};"


# =============================================================================
# Button Styles
# =============================================================================

def button_primary_styles() -> str:
    """Get primary button styles (warm gold)."""
    return "background-color: #C9A96E; color: white; border: none; border-radius: 9999px; padding: 0.6rem 1.25rem; font-weight: 500; cursor: pointer; transition: all 0.15s ease;"


def button_secondary_styles(theme: str) -> str:
    """Get secondary button styles."""
    scheme = preferences.Theme.SCHEMES.get(theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])
    return f"background-color: {scheme['bg_secondary']}; color: {scheme['text_primary']}; border: 1px solid {scheme['border_light']}; border-radius: 9999px; padding: 0.6rem 1.25rem; font-weight: 500; cursor: pointer; transition: all 0.15s ease;"


def button_ghost_styles(theme: str) -> str:
    """Get ghost button styles."""
    scheme = preferences.Theme.SCHEMES.get(theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])
    return f"background-color: transparent; color: {scheme['text_secondary']}; border: none; border-radius: 9999px; padding: 0.6rem 1rem; font-weight: 500; cursor: pointer; transition: all 0.15s ease;"


# =============================================================================
# Input Styles
# =============================================================================

def input_styles(theme: str) -> str:
    """Get input field styles based on theme."""
    scheme = preferences.Theme.SCHEMES.get(theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])
    return f"background-color: {scheme['bg_input']}; color: {scheme['text_primary']}; border: 1px solid {scheme['border_light']}; border-radius: 10px; padding: 0.75rem 1rem; font-size: 0.9375rem; width: 100%; transition: all 0.15s ease;"


def input_focus_styles(theme: str) -> str:
    """Get input focus styles."""
    scheme = preferences.Theme.SCHEMES.get(theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])
    return f"outline: none; border-color: {scheme['accent_primary']}; box-shadow: 0 0 0 3px {scheme['accent_soft']};"


# =============================================================================
# Badge/Spacing Styles
# =============================================================================

def badge_styles(status: str, theme: str) -> str:
    """Get status badge styles."""
    scheme = preferences.Theme.SCHEMES.get(theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])

    status_colors = {
        "draft": scheme["status_draft"],
        "in_progress": scheme["status_in_progress"],
        "completed": scheme["status_completed"],
        "archived": scheme["status_archived"],
        "pending": scheme["status_pending"],
        "failed": scheme["status_failed"],
    }
    color = status_colors.get(status.lower(), scheme["status_draft"])

    # Light mode uses soft backgrounds, dark mode uses softer versions
    if theme == preferences.Theme.LIGHT:
        return f"background-color: {color}22; color: {color}; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 500;"
    else:
        return f"background-color: {color}33; color: {color}; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 500;"


# =============================================================================
# Section Styles
# =============================================================================

def section_bg(theme: str) -> str:
    """Get section background style."""
    scheme = preferences.Theme.SCHEMES.get(theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])
    return f"background-color: {scheme['bg_secondary']}; border-radius: 16px; padding: 1.5rem;"


def divider_styles(theme: str) -> str:
    """Get divider/separator style."""
    scheme = preferences.Theme.SCHEMES.get(theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])
    return f"height: 1px; background-color: {scheme['border_light']}; margin: 1.5rem 0;"


# =============================================================================
# Login Page Styles
# =============================================================================

def login_container_styles(theme: str) -> str:
    """Get login container style."""
    scheme = preferences.Theme.SCHEMES.get(theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])
    return f"min-height: 100vh; display: flex; align-items: center; justify-content: center; background-color: {scheme['bg_primary']}; padding: 2rem;"


def login_card_styles(theme: str) -> str:
    """Get login card style."""
    scheme = preferences.Theme.SCHEMES.get(theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])
    return f"background-color: {scheme['bg_card']}; border: 1px solid {scheme['border_light']}; border-radius: 16px; padding: 3rem; width: 100%; max-width: 420px; box-shadow: {scheme['shadow_lg']}; text-align: center;"


# =============================================================================
# Typography Styles
# =============================================================================

def serif_font() -> str:
    """Get serif font family for comfortable reading."""
    return "font-family: 'Merriweather', Georgia, serif;"


def sans_font() -> str:
    """Get sans-serif font family."""
    return "font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;"


def script_font() -> str:
    """Get script font for writers' quotes."""
    return "font-family: 'Caveat', cursive;"


def heading_styles(theme: str) -> str:
    """Get heading styles."""
    scheme = preferences.Theme.SCHEMES.get(theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])
    return f"font-family: 'Merriweather', Georgia, serif; color: {scheme['text_primary']}; line-height: 1.3;"


# =============================================================================
# Responsive Helpers
# =============================================================================

def responsive_grid(columns: int = 1) -> str:
    """Get responsive grid classes."""
    if columns == 1:
        return "display: grid; gap: 1.5rem;"
    return "display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1.5rem;"


def stat_card_grid() -> str:
    """Get stats card grid layout."""
    return "display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem;"
