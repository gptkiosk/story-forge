"""
Theme-aware UI components for Story Forge.
Provides helper functions for consistent dark/light mode styling.
"""

import preferences


# =============================================================================
# Theme-Aware CSS Classes
# =============================================================================

def get_theme_classes(theme: str) -> dict:
    """Get all theme CSS classes as a dictionary."""
    return preferences.get_theme_css_classes(theme)


def theme_classes(theme: str, element: str) -> str:
    """Get CSS class string for a theme element.

    Args:
        theme: "light" or "dark"
        element: Element name (bg_primary, text_primary, etc.)

    Returns:
        CSS class string (e.g., "bg-white")
    """
    classes = get_theme_classes(theme)
    return classes.get(element, "")


# =============================================================================
# Theme-Aware Component Factory
# =============================================================================

class ThemedCard:
    """A themed card container."""

    def __init__(self, theme: str, classes: str = ""):
        self.theme = theme
        self.classes = classes

    def __enter__(self):
        bg = theme_classes(self.theme, "bg_card")
        border = theme_classes(self.theme, "border")
        combined = f"{bg} {border} {' '.join(self.classes.split())}".strip()
        return combined

    def __exit__(self, *args):
        pass


class ThemedText:
    """A themed text element."""

    @staticmethod
    def primary(theme: str, text: str, extra_classes: str = "") -> str:
        """Get primary text classes."""
        base = theme_classes(theme, "text_primary")
        return f"{base} {extra_classes}".strip()

    @staticmethod
    def secondary(theme: str, text: str, extra_classes: str = "") -> str:
        """Get secondary text classes."""
        base = theme_classes(theme, "text_secondary")
        return f"{base} {extra_classes}".strip()

    @staticmethod
    def muted(theme: str, text: str, extra_classes: str = "") -> str:
        """Get muted text classes."""
        base = theme_classes(theme, "text_muted")
        return f"{base} {extra_classes}".strip()


# =============================================================================
# Header Theme Classes
# =============================================================================

def header_classes(theme: str) -> str:
    """Get header background class."""
    return theme_classes(theme, "header_bg")


def header_text_class(theme: str) -> str:
    """Get header text class."""
    base = theme_classes(theme, "text_primary")
    return f"{base} font-bold".strip()


# =============================================================================
# Card Theme Classes
# =============================================================================

def card_classes(theme: str, extra: str = "") -> str:
    """Get card container classes."""
    bg = theme_classes(theme, "bg_card")
    border = theme_classes(theme, "border")
    return f"{bg} {border} {extra}".strip()


def card_text_classes(theme: str) -> str:
    """Get card text classes."""
    return theme_classes(theme, "text_primary")


# =============================================================================
# Button Theme Classes
# =============================================================================

def button_text_classes(theme: str) -> str:
    """Get button text classes."""
    return theme_classes(theme, "text_secondary")


# =============================================================================
# Input Theme Classes
# =============================================================================

def input_classes(theme: str) -> str:
    """Get input field classes based on theme."""
    if theme == preferences.Theme.DARK:
        return "bg-gray-800 text-white border-gray-600"
    return "bg-white text-gray-800 border-gray-300"


# =============================================================================
# Badge/Status Theme Classes
# =============================================================================

def status_badge_class(status: str, theme: str) -> str:
    """Get status badge class based on status and theme."""
    status_colors = {
        "draft": "gray",
        "in_progress": "blue",
        "completed": "green",
        "archived": "orange",
        "pending": "yellow",
        "processing": "blue",
        "failed": "red",
    }
    color = status_colors.get(status.lower(), "gray")

    if theme == preferences.Theme.DARK:
        return f"bg-{color}-900 text-{color}-300"

    return f"bg-{color}-100 text-{color}-800"


# =============================================================================
# Page Background
# =============================================================================

def page_classes(theme: str) -> str:
    """Get page container classes."""
    bg = theme_classes(theme, "bg_primary")
    return f"{bg} min-h-screen".strip()


def section_classes(theme: str) -> str:
    """Get section/container classes."""
    bg = theme_classes(theme, "bg_secondary")
    return f"{bg} rounded-lg p-6".strip()


# =============================================================================
# Divider/Separator
# =============================================================================

def divider_classes(theme: str) -> str:
    """Get divider/separator classes."""
    return theme_classes(theme, "border")
