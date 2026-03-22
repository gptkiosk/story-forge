"""
Story Forge - Self-Publishing Dashboard
Main entry point for the NiceGUI application.

A cozy, professional writing studio for self-publishers.
Warm cream palette with soft dark mode.
"""

import os
import asyncio
import sqlalchemy
from sqlalchemy.orm import joinedload
from pathlib import Path
from urllib import parse as urllib_parse
from datetime import datetime

from nicegui import ui, app
import auth
import tts
import backup
import preferences
import ui_theme
from db import (
    init_db,
    get_session,
    Book,
    Chapter,
    BookStatus,
    TTSJob,
    TTSJobStatus,
    TTSProviderType,
    CharacterVoice,
)



# Configure environment
DATA_DIR = Path("./data")
DATA_DIR.mkdir(exist_ok=True)

# Application configuration
APP_TITLE = "Story Forge"
APP_VERSION = "0.1.0"
APP_TAGLINE = "Your cozy writing studio"

# Pagination settings
ITEMS_PER_PAGE = 10

# Theme CSS path
THEME_CSS = "/static/css/theme.css"


# =============================================================================
# Database Helpers
# =============================================================================

def get_book_count() -> int:
    """Get total number of books."""
    db = get_session()
    try:
        return db.query(Book).count()
    finally:
        db.close()


def get_chapter_count() -> int:
    """Get total number of chapters across all books."""
    db = get_session()
    try:
        return db.query(Chapter).count()
    finally:
        db.close()


def get_total_word_count() -> int:
    """Get total word count across all books."""
    db = get_session()
    try:
        total = db.query(Book).with_entities(
            sqlalchemy.func.sum(Book.word_count)
        ).scalar()
        return total or 0
    finally:
        db.close()


def get_all_books(search: str = "", status_filter: str = "", page: int = 1) -> tuple[list[Book], int]:
    """Get paginated books with optional search and filter."""
    db = get_session()
    try:
        query = db.query(Book)

        if search:
            search_term = f"%{search}%"
            query = query.filter(
                (Book.title.ilike(search_term)) |
                (Book.author.ilike(search_term)) |
                (Book.description.ilike(search_term))
            )

        if status_filter:
            try:
                status = BookStatus(status_filter)
                query = query.filter(Book.status == status)
            except ValueError:
                pass

        total = query.count()
        offset = (page - 1) * ITEMS_PER_PAGE
        books = query.options(joinedload(Book.chapters)).order_by(Book.updated_at.desc()).offset(offset).limit(ITEMS_PER_PAGE).all()

        return books, total
    finally:
        db.close()


def get_book_by_id(book_id: int) -> Book | None:
    """Get a book by ID."""
    db = get_session()
    try:
        return db.query(Book).filter(Book.id == book_id).first()
    finally:
        db.close()


def create_book(title: str, description: str = "", author: str = "", status: str = "draft") -> Book:
    """Create a new book."""
    db = get_session()
    try:
        book = Book(
            title=title,
            description=description,
            author=author,
            status=BookStatus(status),
        )
        db.add(book)
        db.commit()
        db.refresh(book)
        return book
    finally:
        db.close()


def update_book(book_id: int, **kwargs) -> Book | None:
    """Update a book."""
    db = get_session()
    try:
        book = db.query(Book).filter(Book.id == book_id).first()
        if not book:
            return None

        for key, value in kwargs.items():
            if key == "status" and isinstance(value, str):
                value = BookStatus(value)
            if hasattr(book, key):
                setattr(book, key, value)

        db.commit()
        db.refresh(book)
        return book
    finally:
        db.close()


def delete_book(book_id: int) -> bool:
    """Delete a book and all its chapters."""
    db = get_session()
    try:
        book = db.query(Book).filter(Book.id == book_id).first()
        if not book:
            return False
        db.delete(book)
        db.commit()
        return True
    finally:
        db.close()


def get_chapters_for_book(book_id: int) -> list[Chapter]:
    """Get all chapters for a book."""
    db = get_session()
    try:
        return db.query(Chapter).filter(Chapter.book_id == book_id).order_by(Chapter.order).all()
    finally:
        db.close()


def get_chapter_with_tts_jobs(chapter_id: int) -> Chapter | None:
    """Get a chapter with all its TTS jobs loaded."""
    db = get_session()
    try:
        return db.query(Chapter).filter(Chapter.id == chapter_id).first()
    finally:
        db.close()


def create_chapter(book_id: int, title: str, order: int) -> Chapter:
    """Create a new chapter."""
    db = get_session()
    try:
        chapter = Chapter(
            book_id=book_id,
            title=title,
            order=order,
        )
        db.add(chapter)
        db.commit()
        db.refresh(chapter)
        return chapter
    finally:
        db.close()


def update_chapter(chapter_id: int, **kwargs) -> Chapter | None:
    """Update a chapter."""
    db = get_session()
    try:
        chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
        if not chapter:
            return None

        for key, value in kwargs.items():
            if hasattr(chapter, key):
                setattr(chapter, key, value)

        db.commit()
        db.refresh(chapter)
        return chapter
    finally:
        db.close()


def delete_chapter(chapter_id: int) -> bool:
    """Delete a chapter."""
    db = get_session()
    try:
        chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
        if not chapter:
            return False
        db.delete(chapter)
        db.commit()
        return True
    finally:
        db.close()


def recalculate_book_word_count(book_id: int) -> int:
    """Recalculate and update word count for a book."""
    db = get_session()
    try:
        book = db.query(Book).filter(Book.id == book_id).first()
        if not book:
            return 0

        total_words = sum(chapter.word_count or 0 for chapter in book.chapters)
        book.word_count = total_words
        db.commit()
        return total_words
    finally:
        db.close()


# =============================================================================
# UI Components
# =============================================================================

def render_header():
    """Render the common header with navigation - warm studio theme."""
    # Load Material Symbols Outlined font + global placeholder styling
    ui.add_head_html('''
        <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL@20..48,100..700,0..1&display=swap" rel="stylesheet">
        <style>
            html, body { overflow: hidden; height: 100vh; }
            .scrollable-pane { overflow-y: auto; height: 100%; }
            .q-page-container { overflow: hidden !important; }
            .q-field__native, .q-field__input { color: inherit !important; }
            input::placeholder { color: #9A948D; opacity: 1; }
            input::-webkit-input-placeholder { color: #9A948D; }
        </style>
    ''')

    user_email = auth.get_session("user_email", "")
    user_avatar = auth.get_session("user_avatar", "")
    user_id = auth.get_session("user_id")

    # Get current theme
    current_theme = preferences.Theme.LIGHT
    if user_id:
        current_theme = preferences.get_theme_for_user(user_id)

    theme_icon = "dark_mode" if current_theme == preferences.Theme.LIGHT else "light_mode"
    theme_label = "Dark Mode" if current_theme == preferences.Theme.LIGHT else "Light Mode"

    # Get theme styles
    scheme = preferences.Theme.SCHEMES.get(current_theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])

    # Header with warm styling
    header_style = f"background-color: {scheme['bg_header']}; border-bottom: 1px solid {scheme['border_light']}; padding: 0.75rem 1.5rem; backdrop-filter: blur(10px); position: sticky; top: 0; z-index: 100;"

    with ui.header().classes("").style(header_style):
        with ui.row().classes("w-full justify-between items-center"):
            with ui.row().classes("items-center gap-4"):
                # App title in serif font
                ui.label(APP_TITLE).style(
                    f"font-family: 'Merriweather', Georgia, serif; font-size: 1.25rem; font-weight: 700; color: {scheme['text_primary']};"
                )

                # Dev mode indicator
                if auth.is_dev_mode():
                    ui.label("DEV MODE").style(
                        f"background-color: #E67E22; color: {scheme['text_inverse']}; font-size: 0.7rem; font-weight: 600; padding: 0.2rem 0.5rem; border-radius: 6px; text-transform: uppercase; letter-spacing: 0.5px;"
                    )

            with ui.row().classes("items-center gap-1"):
                # Navigation buttons - warm ghost style
                nav_buttons = [
                    ("Dashboard", "dashboard", "/dashboard"),
                    ("Books", "library_books", "/books"),
                    ("Voice Studio", "record_voice_over", "/voice-studio"),
                    ("Backups", "backup", "/backups"),
                ]

                for label, icon, route in nav_buttons:
                    ui.button(
                        label,
                        icon=icon,
                        on_click=lambda r=route: ui.navigate.to(r)
                    ).props("flat dense").style(
                        f"background-color: transparent; color: {scheme['text_secondary']}; border: none; border-radius: 9999px; padding: 0.5rem 1rem; font-weight: 500; font-size: 0.875rem;"
                    )

                # Divider
                ui.separator().props("vertical").style(f"height: 24px; background-color: {scheme['border_light']}; margin: 0 0.5rem;")

                # Theme toggle button
                ui.button(
                    theme_label,
                    icon=theme_icon,
                    on_click=lambda: _toggle_theme()
                ).props("flat dense").style(
                    f"background-color: {scheme['bg_secondary']}; color: {scheme['text_secondary']}; border: 1px solid {scheme['border_light']}; border-radius: 9999px; padding: 0.5rem 1rem; font-weight: 500; font-size: 0.875rem;"
                )

                # User avatar
                if user_avatar:
                    ui.avatar(source=user_avatar, size="sm").style("margin-left: 0.5rem;")
                else:
                    ui.avatar(user_email[0].upper() if user_email else "?").props("size=sm").style("margin-left: 0.5rem;")


def _toggle_theme():
    """Toggle the theme and refresh the page."""
    user_id = auth.get_session("user_id")
    if user_id:
        new_theme, _ = preferences.toggle_theme(user_id)
        # Refresh to apply new theme
        ui.run_javascript("window.location.reload()")
    else:
        # For non-authenticated users, use client-side toggle via JavaScript
        ui.run_javascript("""
            document.body.classList.toggle('dark');
            const isDark = document.body.classList.contains('dark');
            localStorage.setItem('theme', isDark ? 'dark' : 'light');
        """)


# =============================================================================
# Page Routes
# =============================================================================

def create_app():
    """Create and configure the NiceGUI application."""
    # Initialize database
    init_db()

    @ui.page("/")
    def home_page():
        """Home page - redirect to login or dashboard."""
        if not auth.is_authenticated():
            ui.navigate.to("/login")
        else:
            ui.navigate.to("/dashboard")

    @ui.page("/login")
    def login_page():
        """Login page with Google OAuth - warm studio theme."""
        if auth.is_authenticated():
            ui.navigate.to("/dashboard")
            return

        # Dev mode: auto-login as dev user
        if auth.is_dev_mode():
            auth.login_dev_user()
            ui.navigate.to("/dashboard")
            return

        # Get random writers' quote
        quote = preferences.get_random_quote()

        # Login container with warm cream background
        with ui.column().style(ui_theme.login_container_styles("light")).classes("w-full"):
            # Login card - warm and inviting
            with ui.card().classes("").style(ui_theme.login_card_styles("light")):
                # App title with serif font
                ui.label(APP_TITLE).classes("text-3xl font-bold").style(
                    "font-family: 'Merriweather', Georgia, serif; color: #2D2A26; text-align: center;"
                )
                ui.label(APP_TAGLINE).classes("text-sm").style(
                    "font-family: 'Merriweather', Georgia, serif; color: #9A948D; font-style: italic; margin-bottom: 1.5rem;"
                )

                # Writers' quote at top
                ui.label(quote).classes("text-base").style(
                    "font-family: 'Caveat', cursive; color: #9A948D; font-style: italic; padding: 1rem 0; border-top: 1px solid #E8E0D8; border-bottom: 1px solid #E8E0D8; margin: 1rem 0;"
                )

                ui.label("Sign in to continue").classes("text-lg font-medium mt-4").style(
                    "color: #2D2A26;"
                )

                def go_to_google():
                    login_url = auth.get_login_url()
                    ui.navigate.to(login_url, new_tab=True)

                # Rounded modern button
                with ui.button(
                    "Sign in with Google",
                    on_click=go_to_google,
                    icon="o_login"
                ).classes("w-full mt-4").style(ui_theme.button_primary_styles()):
                    pass

                # Auth footer
                ui.label("Secure authentication powered by Google OAuth 2.0").classes("text-xs mt-6").style(
                    "color: #9A948D;"
                )

                # Dev mode hint
                if os.environ.get("DEV_MODE", "").lower() in ("1", "true", "yes"):
                    ui.label("DEV MODE: Auth bypass enabled").classes("text-xs mt-2").style(
                        "color: #E67E22; font-weight: 600;"
                    )

    @ui.page("/auth/callback")
    def auth_callback_page(code: str = None, state: str = None, error: str = None):
        """OAuth callback handler."""

        if error:
            ui.notify(f"Authentication error: {error}", type="negative")
            ui.navigate.to("/login")
            return

        if not code or not state:
            ui.notify("Missing authentication parameters", type="negative")
            ui.navigate.to("/login")
            return

        if not auth.validate_state(state):
            ui.notify("Invalid state parameter", type="negative")
            ui.navigate.to("/login")
            return

        with ui.column().classes("w-full h-screen justify-center items-center"):
            ui.spinner(size="lg")
            ui.label("Completing sign in...").classes("mt-4")

        async def process_callback():
            try:
                db = get_session()
                await auth.handle_oauth_callback(db, code)
                db.close()
                ui.notify("Successfully signed in!", type="positive")
                ui.navigate.to("/dashboard")
            except Exception as e:
                ui.notify(f"Sign in failed: {str(e)}", type="negative")
                ui.navigate.to("/login")

        asyncio.create_task(process_callback())

    @ui.page("/logout")
    def logout_page():
        """Logout handler."""
        auth.logout()
        ui.notify("You have been signed out", type="info")
        ui.navigate.to("/login")

    @ui.page("/dashboard")
    def dashboard_page():
        """Dashboard page - requires authentication."""
        if not auth.is_authenticated():
            ui.navigate.to("/login")
            return

        user_name = auth.get_session("user_name", "User")
        user_id = auth.get_session("user_id")

        # Get current theme
        current_theme = preferences.Theme.LIGHT
        if user_id:
            current_theme = preferences.get_theme_for_user(user_id)

        scheme = preferences.Theme.SCHEMES.get(current_theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])

        # Header
        render_header()

        # Get random writers' quote
        quote = preferences.get_random_quote()

        # Page background with scrollable content
        page_style = f"background-color: {scheme['bg_primary']}; height: calc(100vh - 60px); overflow-y: auto;"

        with ui.column().classes("w-full scrollable-pane").style(page_style):
            # Page content
            with ui.column().classes("w-full max-w-6xl mx-auto p-8"):
                # Welcome section
                ui.label(f"Welcome back, {user_name}!").style(
                    f"font-family: 'Merriweather', Georgia, serif; font-size: 2rem; font-weight: 700; color: {scheme['text_primary']}; margin-bottom: 0.5rem;"
                )
                ui.label("Your cozy writing studio awaits").style(
                    f"font-family: 'Merriweather', Georgia, serif; font-size: 1rem; color: {scheme['text_muted']}; margin-bottom: 2rem;"
                )

                # Writers' quote
                ui.label(quote).style(
                    f"font-family: 'Caveat', cursive; font-size: 1.25rem; color: {scheme['text_muted']}; font-style: italic; padding: 1rem 1.5rem; background-color: {scheme['bg_secondary']}; border-radius: 16px; margin-bottom: 2rem; max-width: 600px;"
                )

                # Get book count for empty state check
                book_count = get_book_count()

                # Illustrated empty state when no books
                if book_count == 0:
                    with ui.card().classes("w-full").style(ui_theme.card_styles(current_theme)):
                        ui.image("/static/svg/open-book.svg").style("width: 80px; height: 80px; margin: 0 auto 1rem; display: block;")
                        ui.label("Your story starts here").style(
                            f"font-family: 'Merriweather', Georgia, serif; font-size: 1.25rem; font-weight: 600; color: {scheme['text_primary']}; text-align: center;"
                        )
                        ui.label("Create your first book and watch your library grow.").style(
                            f"font-size: 0.875rem; color: {scheme['text_muted']}; text-align: center; margin-top: 0.5rem; margin-bottom: 1.5rem;"
                        )
                        with ui.button(
                            "Start Writing",
                            icon="o_add",
                            on_click=lambda: ui.navigate.to("/books/new")
                        ).classes("").style(ui_theme.button_primary_styles()):
                            pass

                # Stats cards - warm studio style
                book_count = get_book_count()
                chapter_count = get_chapter_count()
                total_words = get_total_word_count()

                with ui.row().classes("w-full gap-6 flex-wrap").style(ui_theme.stat_card_grid()):
                    # Books stat
                    with ui.card().classes("").style(ui_theme.card_styles(current_theme)):
                        with ui.column().classes("items-center"):
                            ui.icon("library_books", size="xl").style(f"color: {scheme['accent_primary']}; margin-bottom: 0.5rem;")
                            ui.label(str(book_count)).style(
                                f"font-family: 'Merriweather', Georgia, serif; font-size: 2.5rem; font-weight: 700; color: {scheme['accent_primary']}; line-height: 1.2;"
                            )
                            ui.label("Books").style(
                                f"font-size: 0.875rem; font-weight: 500; color: {scheme['text_secondary']};"
                            )
                            ui.label("in your library").style(
                                f"font-size: 0.75rem; color: {scheme['text_muted']};"
                            )

                    # Chapters stat
                    with ui.card().classes("").style(ui_theme.card_styles(current_theme)):
                        with ui.column().classes("items-center"):
                            ui.icon("article", size="xl").style(f"color: {scheme['accent_green']}; margin-bottom: 0.5rem;")
                            ui.label(str(chapter_count)).style(
                                f"font-family: 'Merriweather', Georgia, serif; font-size: 2.5rem; font-weight: 700; color: {scheme['accent_green']}; line-height: 1.2;"
                            )
                            ui.label("Chapters").style(
                                f"font-size: 0.875rem; font-weight: 500; color: {scheme['text_secondary']};"
                            )
                            ui.label("written").style(
                                f"font-size: 0.75rem; color: {scheme['text_muted']};"
                            )

                    # Words stat
                    with ui.card().classes("").style(ui_theme.card_styles(current_theme)):
                        with ui.column().classes("items-center"):
                            ui.icon("text_fields", size="xl").style(f"color: {scheme['accent_purple']}; margin-bottom: 0.5rem;")
                            ui.label(f"{total_words:,}").style(
                                f"font-family: 'Merriweather', Georgia, serif; font-size: 2.5rem; font-weight: 700; color: {scheme['accent_purple']}; line-height: 1.2;"
                            )
                            ui.label("Words").style(
                                f"font-size: 0.875rem; font-weight: 500; color: {scheme['text_secondary']};"
                            )
                            ui.label("total").style(
                                f"font-size: 0.75rem; color: {scheme['text_muted']};"
                            )

                # Quick actions
                with ui.card().classes("mt-8 w-full").style(ui_theme.card_styles(current_theme)):
                    ui.label("Quick Actions").style(
                        f"font-family: 'Merriweather', Georgia, serif; font-size: 1.25rem; font-weight: 600; color: {scheme['text_primary']}; margin-bottom: 1rem;"
                    )
                    with ui.row().classes("gap-4 flex-wrap"):
                        with ui.button(
                            "New Book",
                            icon="o_add",
                            on_click=lambda: ui.navigate.to("/books/new")
                        ).classes("").style(ui_theme.button_primary_styles()):
                            pass
                        with ui.button(
                            "View All Books",
                            icon="o_library_books",
                            on_click=lambda: ui.navigate.to("/books")
                        ).classes("").style(ui_theme.button_secondary_styles(current_theme)):
                            pass
                        with ui.button(
                            "Voice Studio",
                            icon="o_record_voice_over",
                            on_click=lambda: ui.navigate.to("/voice-studio")
                        ).classes("").style(ui_theme.button_secondary_styles(current_theme)):
                            pass

                # Footer with quote
                with ui.column().classes("w-full mt-12 items-center").style(f"padding: 2rem; border-top: 1px solid {scheme['border_light']};"):
                    pass

    @ui.page("/books")
    def books_page(page: int = 1, search: str = "", status: str = ""):
        """Books management page with search and pagination - warm studio theme."""
        if not auth.is_authenticated():
            ui.navigate.to("/login")
            return

        # Get query params for pagination and filtering
        page = int(page) if page else 1
        search = search or ""
        status = status or ""

        # Get current theme
        user_id = auth.get_session("user_id")
        current_theme = preferences.Theme.LIGHT
        if user_id:
            current_theme = preferences.get_theme_for_user(user_id)

        scheme = preferences.Theme.SCHEMES.get(current_theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])

        # Header
        render_header()

        # Page background with scrollable content
        page_style = f"background-color: {scheme['bg_primary']}; height: calc(100vh - 60px); overflow-y: auto;"

        with ui.column().classes("w-full scrollable-pane").style(page_style):
            # Books content
            with ui.column().classes("w-full max-w-6xl mx-auto p-8"):
                with ui.row().classes("justify-between items-center w-full mb-6"):
                    ui.label("Your Books").style(
                        f"font-family: 'Merriweather', Georgia, serif; font-size: 2rem; font-weight: 700; color: {scheme['text_primary']};"
                    )
                    with ui.button(
                        "New Book",
                        icon="o_add",
                        on_click=lambda: ui.navigate.to("/books/new")
                    ).classes("").style(ui_theme.button_primary_styles()):
                        pass

                # Search and filter bar - warm card style
                with ui.card().classes("w-full mb-6").style(f"background-color: {scheme['bg_card']}; border: 1px solid {scheme['border_light']}; border-radius: 16px; padding: 1rem;"):
                    with ui.row().classes("w-full gap-4 items-center"):
                        search_input = ui.input(
                            label="Search books...",
                            value=search or "",
                            placeholder="Type to search..."
                        ).classes("flex-1").style(
                            f"background-color: {scheme['bg_input']}; color: {scheme['text_primary']}; border: 1px solid {scheme['border_light']}; border-radius: 10px; padding: 0.75rem 1rem; text-align: center;"
                        )

                        status_options = [
                            {"label": "All Statuses", "value": None},
                            {"label": "Draft", "value": "draft"},
                            {"label": "In Progress", "value": "in_progress"},
                            {"label": "Completed", "value": "completed"},
                            {"label": "Archived", "value": "archived"},
                        ]
                        status_select = ui.select(
                            label="Status",
                            options=status_options,
                            value=status if status else None,
                        ).classes("w-48").style(
                            f"background-color: {scheme['bg_input']}; color: {scheme['text_primary']}; border: 1px solid {scheme['border_light']}; border-radius: 10px;"
                        )

                        def apply_filters():
                            params = {}
                            if search_input.value:
                                params["search"] = search_input.value
                            if status_select.value:
                                params["status"] = status_select.value
                            params["page"] = "1"
                            ui.navigate.to(f"/books?{urllib_parse.urlencode(params)}")

                        with ui.button(
                            "Search",
                            icon="o_search",
                            on_click=apply_filters
                        ).classes("").style(ui_theme.button_secondary_styles(current_theme)):
                            pass

                # Get books
                books, total = get_all_books(search=search, status_filter=status, page=page)
                total_pages = (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

                # Books grid
                if books:
                    with ui.row().classes("w-full gap-6 flex-wrap").style(
                        "display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1.5rem;"
                    ):
                        for book in books:
                            status_key = book.status.value
                            status_color_map = {
                                "draft": scheme["status_draft"],
                                "in_progress": scheme["status_in_progress"],
                                "completed": scheme["status_completed"],
                                "archived": scheme["status_archived"],
                            }
                            status_color = status_color_map.get(status_key, scheme["status_draft"])

                            # Book card - warm style
                            with ui.card().classes("cursor-pointer").style(
                                f"background-color: {scheme['bg_card']}; border: 1px solid {scheme['border_light']}; border-radius: 16px; padding: 1.25rem; transition: all 0.25s ease; cursor: pointer;"
                            ):
                                with ui.column().classes("w-full"):
                                    with ui.row().classes("w-full justify-between items-start"):
                                        ui.label(book.title).style(
                                            f"font-family: 'Merriweather', Georgia, serif; font-size: 1.1rem; font-weight: 600; color: {scheme['text_primary']}; margin-bottom: 0.25rem;"
                                        )
                                        # Status badge - warm style
                                        ui.label(book.status.value.replace("_", " ").title()).style(
                                            f"background-color: {status_color}22; color: {status_color}; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 500;"
                                        )

                                    if book.author:
                                        ui.label(f"by {book.author}").style(
                                            f"font-size: 0.875rem; color: {scheme['text_muted']}; margin-bottom: 0.75rem;"
                                        )

                                    if book.description:
                                        desc = book.description
                                        if len(desc) > 100:
                                            desc = desc[:100] + "..."
                                        ui.label(desc).style(
                                            f"font-family: 'Merriweather', Georgia, serif; font-size: 0.875rem; color: {scheme['text_secondary']}; line-height: 1.6; margin-bottom: 1rem;"
                                        )

                                    with ui.row().classes("gap-4 items-center").style("margin-bottom: 1rem;"):
                                        ui.label(f"{len(book.chapters)} chapters").style(f"font-size: 0.75rem; color: {scheme['text_muted']};")
                                        ui.label(f"{book.word_count:,} words").style(f"font-size: 0.75rem; color: {scheme['text_muted']};")

                                    with ui.row().classes("gap-2"):
                                        with ui.button(
                                            "View",
                                            icon="o_visibility",
                                            on_click=lambda b=book: ui.navigate.to(f"/book/{b.id}")
                                        ).classes("").style(ui_theme.button_ghost_styles(current_theme)):
                                            pass
                                        with ui.button(
                                            "Edit",
                                            icon="o_edit",
                                            on_click=lambda b=book: ui.navigate.to(f"/book/{b.id}/edit")
                                        ).classes("").style(ui_theme.button_ghost_styles(current_theme)):
                                            pass

                # Empty state
                else:
                    with ui.card().classes("w-full").style(f"background-color: {scheme['bg_card']}; border: 1px solid {scheme['border_light']}; border-radius: 16px; padding: 3rem; text-align: center;"):
                        ui.image("/static/svg/book-feather.svg").style("width: 100px; height: 100px; margin: 0 auto 1rem; display: block;")
                        ui.label("No books yet").style(
                            f"font-family: 'Merriweather', Georgia, serif; font-size: 1.25rem; font-weight: 600; color: {scheme['text_primary']};"
                        )
                        ui.label("Start your writing journey by creating your first book.").style(
                            f"font-size: 0.875rem; color: {scheme['text_muted']}; margin-top: 0.5rem; margin-bottom: 1.5rem;"
                        )
                        with ui.button(
                            "Create Your First Book",
                            icon="o_add",
                            on_click=lambda: ui.navigate.to("/books/new")
                        ).classes("").style(ui_theme.button_primary_styles()):
                            pass

                # Pagination
                if total_pages > 1:
                    with ui.row().classes("w-full justify-center items-center mt-8 gap-2"):
                        if page > 1:
                            prev_params = {"page": str(page - 1)}
                            if search:
                                prev_params["search"] = search
                            if status:
                                prev_params["status"] = status
                            with ui.button(
                                "Previous",
                                icon="o_chevron_left",
                                on_click=lambda: ui.navigate.to(f"/books?{urllib_parse.urlencode(prev_params)}")
                            ).classes("").style(ui_theme.button_ghost_styles(current_theme)):
                                pass

                        ui.label(f"Page {page} of {total_pages}").style(
                            f"font-size: 0.875rem; color: {scheme['text_muted']};"
                        )

                        if page < total_pages:
                            next_params = {"page": str(page + 1)}
                            if search:
                                next_params["search"] = search
                            if status:
                                next_params["status"] = status
                            with ui.button(
                                "Next",
                                icon="o_chevron_right",
                                on_click=lambda: ui.navigate.to(f"/books?{urllib_parse.urlencode(next_params)}")
                            ).classes("").style(ui_theme.button_ghost_styles(current_theme)):
                                pass

                        if page < total_pages:
                            next_params = {"page": str(page + 1)}
                            if search:
                                next_params["search"] = search
                            if status:
                                next_params["status"] = status
                            ui.button(
                                "Next",
                                icon="o_chevron_right",
                                on_click=lambda: ui.navigate.to(f"/books?{urllib_parse.urlencode(next_params)}")
                            ).props("flat")

    def confirm_delete_book(book_id: int) -> None:
        """Show confirmation dialog for deleting a book."""

        def do_delete():
            delete_book(book_id)
            ui.notify("Book deleted successfully", type="positive")
            ui.navigate.to("/books")

        with ui.dialog() as dialog, ui.card():
            ui.label("Are you sure you want to delete this book?")
            ui.label("This will also delete all chapters and cannot be undone.").style("font-size: 0.875rem; color: #9A948D")
            with ui.row().classes("mt-4 gap-2 justify-end"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button("Delete", on_click=lambda: [dialog.close(), do_delete()]).props("color=negative")
        dialog.open()

    @ui.page("/books/new")
    def new_book_page():
        """Create new book page - warm studio theme."""
        if not auth.is_authenticated():
            ui.navigate.to("/login")
            return

        user_id = auth.get_session("user_id")
        current_theme = preferences.Theme.LIGHT
        if user_id:
            current_theme = preferences.get_theme_for_user(user_id)

        scheme = preferences.Theme.SCHEMES.get(current_theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])

        render_header()

        page_style = f"background-color: {scheme['bg_primary']}; height: calc(100vh - 60px); overflow-y: auto;"

        with ui.column().classes("w-full scrollable-pane").style(page_style):
            with ui.column().classes("w-full max-w-2xl mx-auto p-8"):
                ui.label("New Book").style(
                    f"font-family: 'Merriweather', Georgia, serif; font-size: 2rem; font-weight: 700; color: {scheme['text_primary']};"
                )

                with ui.card().classes("w-full mt-4").style(ui_theme.card_styles(current_theme)):
                    with ui.column().classes("w-full gap-4"):
                        # Title input - themed
                        title_input = ui.input(
                            label="Title",
                            placeholder="Enter book title"
                        ).classes("w-full").style(
                            f"background-color: {scheme['bg_input']}; color: {scheme['text_primary']}; border: 1px solid {scheme['border_light']}; border-radius: 10px;"
                        )

                        # Author input - themed
                        author_input = ui.input(
                            label="Author",
                            placeholder="Enter author name"
                        ).classes("w-full").style(
                            f"background-color: {scheme['bg_input']}; color: {scheme['text_primary']}; border: 1px solid {scheme['border_light']}; border-radius: 10px;"
                        )

                        # Description textarea - themed
                        description_input = ui.textarea(
                            label="Description",
                            placeholder="Enter book description..."
                        ).classes("w-full").style(
                            f"background-color: {scheme['bg_input']}; color: {scheme['text_primary']}; border: 1px solid {scheme['border_light']}; border-radius: 10px; min-height: 120px;"
                        )

                        status_options = [
                            {"label": "Draft", "value": "draft"},
                            {"label": "In Progress", "value": "in_progress"},
                            {"label": "Completed", "value": "completed"},
                            {"label": "Archived", "value": "archived"},
                        ]
                        status_input = ui.select(
                            label="Status",
                            options=status_options,
                            value="draft",
                        ).classes("w-full").style(
                            f"background-color: {scheme['bg_input']}; color: {scheme['text_primary']}; border: 1px solid {scheme['border_light']}; border-radius: 10px;"
                        )

                        with ui.row().classes("mt-4 gap-3"):
                            with ui.button(
                                "Cancel",
                                on_click=lambda: ui.navigate.to("/books")
                            ).classes("").style(ui_theme.button_ghost_styles(current_theme)):
                                pass

                            def save_book():
                                title = title_input.value.strip()
                                if not title:
                                    ui.notify("Title is required", type="negative")
                                    return

                                new_book = create_book(
                                    title=title,
                                    author=author_input.value.strip() or None,
                                    description=description_input.value.strip() or None,
                                    status=status_input.value,
                                )
                                ui.notify("Book created successfully", type="positive")
                                ui.navigate.to(f"/book/{new_book.id}")

                            with ui.button(
                                "Save Book",
                                on_click=save_book
                            ).classes("").style(ui_theme.button_primary_styles()):
                                pass

    @ui.page("/book/{book_id}")
    def book_detail_page(book_id: int):
        """Book detail page with chapter management - warm studio theme."""
        if not auth.is_authenticated():
            ui.navigate.to("/login")
            return

        user_id = auth.get_session("user_id")
        current_theme = preferences.Theme.LIGHT
        if user_id:
            current_theme = preferences.get_theme_for_user(user_id)

        scheme = preferences.Theme.SCHEMES.get(current_theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])

        book = get_book_by_id(book_id)
        if not book:
            ui.notify("Book not found", type="negative")
            ui.navigate.to("/books")
            return

        # Load chapters
        chapters = get_chapters_for_book(book_id)

        render_header()

        page_style = f"background-color: {scheme['bg_primary']}; height: calc(100vh - 60px); overflow-y: auto;"

        with ui.column().classes("w-full scrollable-pane").style(page_style):
            with ui.column().classes("w-full max-w-4xl mx-auto p-8"):
                # Book header - warm card
                with ui.card().classes("w-full").style(ui_theme.card_styles(current_theme)):
                    with ui.row().classes("w-full justify-between items-start"):
                        with ui.column():
                            ui.label(book.title).style(
                                f"font-family: 'Merriweather', Georgia, serif; font-size: 2rem; font-weight: 700; color: {scheme['text_primary']};"
                            )
                            if book.author:
                                ui.label(f"by {book.author}").style(
                                    f"font-size: 1rem; color: {scheme['text_muted']};"
                                )

                        status_key = book.status.value
                        status_color_map = {
                            "draft": scheme["status_draft"],
                            "in_progress": scheme["status_in_progress"],
                            "completed": scheme["status_completed"],
                            "archived": scheme["status_archived"],
                        }
                        status_color = status_color_map.get(status_key, scheme["status_draft"])
                        ui.label(book.status.value.replace("_", " ").title()).style(
                            f"background-color: {status_color}22; color: {status_color}; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 500;"
                        )

                    if book.description:
                        ui.label(book.description).style(
                            f"font-family: 'Merriweather', Georgia, serif; margin-top: 1rem; color: {scheme['text_secondary']}; line-height: 1.7;"
                        )

                    with ui.row().classes("mt-4 gap-4"):
                        ui.label(f"{len(chapters)} chapters").style(f"font-size: 0.875rem; color: {scheme['text_muted']};")
                        ui.label(f"{book.word_count:,} words").style(f"font-size: 0.875rem; color: {scheme['text_muted']};")

                    with ui.row().classes("mt-4 gap-2"):
                        with ui.button(
                            "Edit Book",
                            icon="o_edit",
                            on_click=lambda: ui.navigate.to(f"/book/{book_id}/edit")
                        ).classes("").style(ui_theme.button_secondary_styles(current_theme)):
                            pass
                        with ui.button(
                            "Delete",
                            icon="o_delete",
                            on_click=lambda: confirm_delete_book(book_id)
                        ).classes("").style("background-color: transparent; color: #CA8B8B; border: none; border-radius: 9999px; padding: 0.5rem 1rem;"):
                            pass

                # Chapters section
                with ui.row().classes("w-full justify-between items-center mt-8 mb-4"):
                    ui.label("Chapters").style(
                        f"font-family: 'Merriweather', Georgia, serif; font-size: 1.5rem; font-weight: 700; color: {scheme['text_primary']};"
                    )
                    with ui.button(
                        "Add Chapter",
                        icon="o_add",
                        on_click=lambda: ui.navigate.to(f"/book/{book_id}/chapter/new")
                    ).classes("").style(ui_theme.button_primary_styles()):
                        pass

                if chapters:
                    with ui.column().classes("w-full gap-3"):
                        for i, chapter in enumerate(chapters, 1):
                            with ui.card().classes("w-full").style(ui_theme.card_styles(current_theme)):
                                with ui.row().classes("w-full justify-between items-center"):
                                    with ui.column():
                                        ui.label(f"Chapter {chapter.order}: {chapter.title}").style(
                                            f"font-family: 'Merriweather', Georgia, serif; font-size: 1.1rem; font-weight: 600; color: {scheme['text_primary']};"
                                        )
                                        ui.label(f"{chapter.word_count:,} words").style(
                                            f"font-size: 0.875rem; color: {scheme['text_muted']};"
                                        )

                                    with ui.row().classes("gap-2"):
                                        with ui.button(
                                            icon="o_edit",
                                            on_click=lambda c=chapter: ui.navigate.to(f"/book/{book_id}/chapter/{c.id}/edit")
                                        ).classes("").style(ui_theme.button_ghost_styles(current_theme)):
                                            pass
                                        with ui.button(
                                            icon="o_delete",
                                            on_click=lambda c=chapter: confirm_delete_chapter(c.id)
                                        ).classes("").style("background-color: transparent; color: #CA8B8B; border: none;"):
                                            pass

                else:
                    with ui.card().classes("w-full").style(ui_theme.card_styles(current_theme)):
                        ui.image("/static/svg/feather-quill.svg").style("width: 60px; height: 80px; margin: 0 auto 1rem; display: block;")
                        ui.label("No chapters yet").style(f"color: {scheme['text_muted']}; text-align: center; padding: 0.5rem 0 1.5rem; font-family: 'Merriweather', Georgia, serif; font-size: 1.1rem;")
                        with ui.button(
                            "Add Your First Chapter",
                            icon="o_add",
                            on_click=lambda: ui.navigate.to(f"/book/{book_id}/chapter/new")
                        ).classes("").style(ui_theme.button_primary_styles()):
                            pass

    def confirm_delete_chapter(book_id: int, chapter_id: int) -> None:
        """Show confirmation dialog for deleting a chapter."""

        def do_delete():
            delete_chapter(chapter_id)
            recalculate_book_word_count(book_id)
            ui.notify("Chapter deleted successfully", type="positive")
            ui.navigate.to(f"/book/{book_id}")

        with ui.dialog() as dialog, ui.card():
            ui.label("Are you sure you want to delete this chapter?")
            ui.label("This cannot be undone.").style("font-size: 0.875rem; color: #9A948D")
            with ui.row().classes("mt-4 gap-2 justify-end"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button("Delete", on_click=lambda: [dialog.close(), do_delete()]).props("color=negative")
        dialog.open()

    @ui.page("/book/{book_id}/edit")
    def edit_book_page(book_id: int):
        """Edit book page - warm studio theme."""
        if not auth.is_authenticated():
            ui.navigate.to("/login")
            return

        user_id = auth.get_session("user_id")
        current_theme = preferences.Theme.LIGHT
        if user_id:
            current_theme = preferences.get_theme_for_user(user_id)

        scheme = preferences.Theme.SCHEMES.get(current_theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])

        book = get_book_by_id(book_id)
        if not book:
            ui.notify("Book not found", type="negative")
            ui.navigate.to("/books")
            return

        render_header()

        page_style = f"background-color: {scheme['bg_primary']}; height: calc(100vh - 60px); overflow-y: auto;"

        with ui.column().classes("w-full scrollable-pane").style(page_style):
            with ui.column().classes("w-full max-w-2xl mx-auto p-8"):
                ui.label("Edit Book").style(
                    f"font-family: 'Merriweather', Georgia, serif; font-size: 2rem; font-weight: 700; color: {scheme['text_primary']};"
                )

                with ui.card().classes("w-full mt-4").style(ui_theme.card_styles(current_theme)):
                    with ui.column().classes("w-full gap-4"):
                        title_input = ui.input(
                            label="Title",
                            value=book.title,
                            placeholder="Enter book title"
                        ).classes("w-full").style(
                            f"background-color: {scheme['bg_input']}; color: {scheme['text_primary']}; border: 1px solid {scheme['border_light']}; border-radius: 10px;"
                        )

                        author_input = ui.input(
                            label="Author",
                            value=book.author or "",
                            placeholder="Enter author name"
                        ).classes("w-full").style(
                            f"background-color: {scheme['bg_input']}; color: {scheme['text_primary']}; border: 1px solid {scheme['border_light']}; border-radius: 10px;"
                        )

                        description_input = ui.textarea(
                            label="Description",
                            value=book.description or "",
                            placeholder="Enter book description..."
                        ).classes("w-full").style(
                            f"background-color: {scheme['bg_input']}; color: {scheme['text_primary']}; border: 1px solid {scheme['border_light']}; border-radius: 10px; min-height: 120px;"
                        )

                        status_options = [
                            {"label": "Draft", "value": "draft"},
                            {"label": "In Progress", "value": "in_progress"},
                            {"label": "Completed", "value": "completed"},
                            {"label": "Archived", "value": "archived"},
                        ]
                        status_input = ui.select(
                            label="Status",
                            options=status_options,
                            value=book.status.value,
                        ).classes("w-full").style(
                            f"background-color: {scheme['bg_input']}; color: {scheme['text_primary']}; border: 1px solid {scheme['border_light']}; border-radius: 10px;"
                        )

                        with ui.row().classes("mt-4 gap-3"):
                            with ui.button(
                                "Cancel",
                                on_click=lambda: ui.navigate.to(f"/book/{book_id}")
                            ).classes("").style(ui_theme.button_ghost_styles(current_theme)):
                                pass

                            def save_book():
                                title = title_input.value.strip()
                                if not title:
                                    ui.notify("Title is required", type="negative")
                                    return

                                update_book(
                                    book_id,
                                    title=title,
                                author=author_input.value.strip() or None,
                                description=description_input.value.strip() or None,
                                status=status_input.value,
                            )
                            ui.notify("Book updated successfully", type="positive")
                            ui.navigate.to(f"/book/{book_id}")

                        ui.button("Save Changes", on_click=save_book).props("color=primary")

    @ui.page("/book/{book_id}/chapter/new")
    def new_chapter_page(book_id: int):
        """Create new chapter page - warm studio theme."""
        if not auth.is_authenticated():
            ui.navigate.to("/login")
            return

        user_id = auth.get_session("user_id")
        current_theme = preferences.Theme.LIGHT
        if user_id:
            current_theme = preferences.get_theme_for_user(user_id)

        scheme = preferences.Theme.SCHEMES.get(current_theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])

        book = get_book_by_id(book_id)
        if not book:
            ui.notify("Book not found", type="negative")
            ui.navigate.to("/books")
            return

        # Get next chapter order
        chapters = get_chapters_for_book(book_id)
        next_order = max([c.order for c in chapters], default=0) + 1

        render_header()

        page_style = f"background-color: {scheme['bg_primary']}; height: calc(100vh - 60px); overflow-y: auto;"

        with ui.column().classes("w-full scrollable-pane").style(page_style):
            with ui.column().classes("w-full max-w-2xl mx-auto p-8"):
                ui.label(f"New Chapter for {book.title}").style(
                    f"font-family: 'Merriweather', Georgia, serif; font-size: 2rem; font-weight: 700; color: {scheme['text_primary']};"
                )

                with ui.card().classes("w-full mt-4").style(ui_theme.card_styles(current_theme)):
                    with ui.column().classes("w-full gap-4"):
                        title_input = ui.input(
                            label="Chapter Title",
                            placeholder="Enter chapter title"
                        ).classes("w-full").style(
                            f"background-color: {scheme['bg_input']}; color: {scheme['text_primary']}; border: 1px solid {scheme['border_light']}; border-radius: 10px;"
                        )

                        order_input = ui.number(
                            label="Chapter Number",
                            value=next_order,
                        ).classes("w-full").style(
                            f"background-color: {scheme['bg_input']}; color: {scheme['text_primary']}; border: 1px solid {scheme['border_light']}; border-radius: 10px;"
                        )

                        with ui.row().classes("mt-4 gap-3"):
                            with ui.button(
                                "Cancel",
                                on_click=lambda: ui.navigate.to(f"/book/{book_id}")
                            ).classes("").style(ui_theme.button_ghost_styles(current_theme)):
                                pass

                            def save_chapter():
                                title = title_input.value.strip()
                                if not title:
                                    ui.notify("Title is required", type="negative")
                                    return

                                chapter = create_chapter(
                                    book_id=book_id,
                                    title=title,
                                    order=int(order_input.value),
                                )
                                recalculate_book_word_count(book_id)
                                ui.notify("Chapter created successfully", type="positive")
                                ui.navigate.to(f"/book/{book_id}/chapter/{chapter.id}/edit")

                            with ui.button(
                                "Create Chapter",
                                on_click=save_chapter
                            ).classes("").style(ui_theme.button_primary_styles()):
                                pass

    @ui.page("/book/{book_id}/chapter/{chapter_id}/edit")
    def edit_chapter_page(book_id: int, chapter_id: int):
        """Edit chapter page - warm studio theme."""
        if not auth.is_authenticated():
            ui.navigate.to("/login")
            return

        user_id = auth.get_session("user_id")
        current_theme = preferences.Theme.LIGHT
        if user_id:
            current_theme = preferences.get_theme_for_user(user_id)

        scheme = preferences.Theme.SCHEMES.get(current_theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])

        book = get_book_by_id(book_id)
        if not book:
            ui.notify("Book not found", type="negative")
            ui.navigate.to("/books")
            return

        chapters = get_chapters_for_book(book_id)
        chapter = next((c for c in chapters if c.id == chapter_id), None)
        if not chapter:
            ui.notify("Chapter not found", type="negative")
            ui.navigate.to(f"/book/{book_id}")
            return

        render_header()

        page_style = f"background-color: {scheme['bg_primary']}; height: calc(100vh - 60px); overflow-y: auto;"

        with ui.column().classes("w-full scrollable-pane").style(page_style):
            with ui.column().classes("w-full max-w-4xl mx-auto p-8"):
                with ui.row().classes("w-full justify-between items-center"):
                    ui.label(f"Edit Chapter: {chapter.title}").style(
                        f"font-family: 'Merriweather', Georgia, serif; font-size: 1.75rem; font-weight: 700; color: {scheme['text_primary']};"
                    )
                    with ui.button(
                        "Back to Book",
                        icon="o_arrow_back",
                        on_click=lambda: ui.navigate.to(f"/book/{book_id}")
                    ).classes("").style(ui_theme.button_ghost_styles(current_theme)):
                        pass

                with ui.card().classes("w-full mt-4").style(ui_theme.card_styles(current_theme)):
                    with ui.column().classes("w-full gap-4"):
                        title_input = ui.input(
                            label="Chapter Title",
                            value=chapter.title,
                            placeholder="Enter chapter title"
                        ).classes("w-full").style(
                            f"background-color: {scheme['bg_input']}; color: {scheme['text_primary']}; border: 1px solid {scheme['border_light']}; border-radius: 10px;"
                        )

                        order_input = ui.number(
                            label="Chapter Number",
                            value=chapter.order,
                        ).classes("w-full").style(
                            f"background-color: {scheme['bg_input']}; color: {scheme['text_primary']}; border: 1px solid {scheme['border_light']}; border-radius: 10px;"
                        )

                        content_input = ui.textarea(
                            label="Chapter Content",
                            value=chapter.content or "",
                            placeholder="Write your chapter content here...",
                        ).classes("w-full").style(
                            f"background-color: {scheme['bg_input']}; color: {scheme['text_primary']}; border: 1px solid {scheme['border_light']}; border-radius: 10px; min-height: 300px; font-family: 'Merriweather', Georgia, serif; line-height: 1.7;"
                        )

                        # Word count display
                        def update_word_count():
                            content = content_input.value or ""
                            words = len(content.split())
                            word_count_label.set_text(f"Words: {words}")

                        content_input.on_value_change(update_word_count)

                        word_count_label = ui.label(f"Words: {chapter.word_count}").style(
                            f"font-size: 0.875rem; color: {scheme['text_muted']};"
                        )

                        with ui.row().classes("mt-4 gap-3"):
                            def save_chapter():
                                title = title_input.value.strip()
                                if not title:
                                    ui.notify("Title is required", type="negative")
                                    return

                                content = content_input.value or ""
                                word_count = len(content.split())

                                update_chapter(
                                    chapter_id,
                                    title=title,
                                    content=content,
                                    order=int(order_input.value),
                                    word_count=word_count,
                                )
                                recalculate_book_word_count(book_id)
                                ui.notify("Chapter updated successfully", type="positive")
                                ui.navigate.to(f"/book/{book_id}")

                            with ui.button(
                                "Save Changes",
                                on_click=save_chapter
                            ).classes("").style(ui_theme.button_primary_styles()):
                                pass


# =============================================================================
# Voice Studio Pages
# =============================================================================


def get_voice_for_provider(character: CharacterVoice, provider: TTSProviderType) -> str:
    """Get the voice ID for a specific provider."""
    if provider == TTSProviderType.MINIMAX:
        return character.minimax_voice_id or ""
    return character.elevenlabs_voice_id or ""


def render_voice_studio_header():
    """Render the Voice Studio header with navigation - theme-aware."""
    # Load Material Symbols Outlined font for line-art icons
    ui.add_head_html('''
        <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL@20..48,100..700,0..1&display=swap" rel="stylesheet">
        <style>
            html, body { overflow: hidden; height: 100vh; }
            .scrollable-pane { overflow-y: auto; height: 100%; }
            .q-page-container { overflow: hidden !important; }
        </style>
    ''')
    user_email = auth.get_session("user_email", "")
    user_avatar = auth.get_session("user_avatar", "")
    user_id = auth.get_session("user_id")

    # Get current theme
    current_theme = preferences.Theme.LIGHT
    if user_id:
        current_theme = preferences.get_theme_for_user(user_id)

    theme_icon = "dark_mode" if current_theme == preferences.Theme.LIGHT else "light_mode"
    theme_label = "Dark Mode" if current_theme == preferences.Theme.LIGHT else "Light Mode"

    # Get theme styles
    scheme = preferences.Theme.SCHEMES.get(current_theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])

    header_style = f"background-color: {scheme['bg_header']}; border-bottom: 1px solid {scheme['border_light']}; padding: 0.75rem 1.5rem; backdrop-filter: blur(10px); position: sticky; top: 0; z-index: 100;"

    with ui.header().classes("").style(header_style):
        with ui.row().classes("w-full justify-between items-center"):
            with ui.row().classes("items-center gap-4"):
                ui.label("🔊 Voice Studio").style(
                    f"font-family: 'Merriweather', Georgia, serif; font-size: 1.25rem; font-weight: 700; color: {scheme['text_primary']};"
                )

            with ui.row().classes("items-center gap-1"):
                nav_buttons = [
                    ("Dashboard", "dashboard", "/dashboard"),
                    ("Books", "library_books", "/books"),
                    ("Voice Studio", "record_voice_over", "/voice-studio"),
                    ("Backups", "backup", "/backups"),
                ]

                for label, icon, route in nav_buttons:
                    ui.button(
                        label,
                        icon=icon,
                        on_click=lambda r=route: ui.navigate.to(r)
                    ).props("flat dense").style(
                        f"background-color: transparent; color: {scheme['text_secondary']}; border: none; border-radius: 9999px; padding: 0.5rem 1rem; font-weight: 500; font-size: 0.875rem;"
                    )

                ui.separator().props("vertical").style(f"height: 24px; background-color: {scheme['border_light']}; margin: 0 0.5rem;")

                ui.button(
                    theme_label,
                    icon=theme_icon,
                    on_click=lambda: _toggle_theme()
                ).props("flat dense").style(
                    f"background-color: {scheme['bg_secondary']}; color: {scheme['text_secondary']}; border: 1px solid {scheme['border_light']}; border-radius: 9999px; padding: 0.5rem 1rem; font-weight: 500; font-size: 0.875rem;"
                )

                if user_avatar:
                    ui.avatar(source=user_avatar, size="sm").style("margin-left: 0.5rem;")
                else:
                    ui.avatar(user_email[0].upper() if user_email else "?").props("size=sm").style("margin-left: 0.5rem;")


@ui.page("/voice-studio")
def voice_studio_page():
    """Voice Studio - main page for TTS management - warm studio theme."""
    if not auth.is_authenticated():
        ui.navigate.to("/login")
        return

    user_id = auth.get_session("user_id")
    current_theme = preferences.Theme.LIGHT
    if user_id:
        current_theme = preferences.get_theme_for_user(user_id)

    scheme = preferences.Theme.SCHEMES.get(current_theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])

    render_voice_studio_header()

    page_style = f"background-color: {scheme['bg_primary']}; height: calc(100vh - 60px); overflow-y: auto;"

    with ui.column().classes("w-full scrollable-pane").style(page_style):
        with ui.column().classes("w-full max-w-6xl mx-auto p-8"):
            ui.label("Voice Studio").style(
                f"font-family: 'Merriweather', Georgia, serif; font-size: 2rem; font-weight: 700; color: {scheme['text_primary']};"
            )
            ui.label("Text-to-speech generation for your chapters").style(
                f"font-size: 1rem; color: {scheme['text_muted']}; margin-bottom: 2rem;"
            )

            # Check which providers are configured
            providers = tts.tts_manager.get_available_providers()

            if not providers:
                with ui.card().classes("w-full").style(ui_theme.card_styles(current_theme)):
                    ui.label("No TTS Providers Configured").style(
                        f"font-family: 'Merriweather', Georgia, serif; font-size: 1.25rem; font-weight: 600; color: {scheme['text_primary']};"
                    )
                    ui.label("Please set up your MiniMax and/or ElevenLabs API keys in the .env file.").style(
                        f"font-size: 0.875rem; color: {scheme['text_muted']}; margin-top: 0.5rem;"
                    )

            else:
                with ui.card().classes("w-full mb-6").style(ui_theme.card_styles(current_theme)):
                    ui.label("Available Providers").style(
                        f"font-size: 1rem; font-weight: 600; color: {scheme['text_primary']}; margin-bottom: 0.5rem;"
                    )
                    provider_names = ", ".join([p.value for p in providers])
                    ui.label(f"✓ {provider_names}").style(f"font-size: 0.875rem; color: {scheme['accent_green']};")

                # List books for voice generation
                ui.label("Select a Book to Narrate").style(
                    f"font-family: 'Merriweather', Georgia, serif; font-size: 1.25rem; font-weight: 600; color: {scheme['text_primary']}; margin-top: 2rem; margin-bottom: 1rem;"
                )

                books = get_all_books(page=1, search="", status_filter="")[0]

                if not books:
                    with ui.card().classes("w-full").style(ui_theme.card_styles(current_theme)):
                        ui.image("/static/svg/book-stack.svg").style("width: 80px; height: 80px; margin: 0 auto 1rem; display: block;")
                        ui.label("No books found").style(f"color: {scheme['text_muted']}; text-align: center; padding: 0.5rem 0 1.5rem; font-family: 'Merriweather', Georgia, serif; font-size: 1.1rem;")
                        with ui.button(
                            "Create Your First Book",
                            icon="o_add",
                            on_click=lambda: ui.navigate.to("/books/new")
                        ).classes("").style(ui_theme.button_primary_styles()):
                            pass
                else:
                    with ui.column().classes("w-full gap-4"):
                        for book in books:
                            with ui.card().classes("w-full").style(ui_theme.card_styles(current_theme)):
                                with ui.row().classes("w-full justify-between items-center"):
                                    with ui.column():
                                        ui.label(book.title).style(
                                            f"font-family: 'Merriweather', Georgia, serif; font-size: 1.1rem; font-weight: 600; color: {scheme['text_primary']};"
                                        )
                                        ui.label(f"{len(book.chapters)} chapters • {book.word_count:,} words").style(
                                            f"font-size: 0.875rem; color: {scheme['text_muted']};"
                                        )
                                    with ui.button(
                                        "Narrate Book",
                                        icon="o_play_arrow",
                                        on_click=lambda b=book: ui.navigate.to(f"/voice-studio/book/{b.id}")
                                    ).classes("").style(ui_theme.button_primary_styles()):
                                        pass


@ui.page("/voice-studio/book/{book_id}")
def voice_studio_book_page(book_id: int):
    """Voice Studio - per-book voice management - warm studio theme."""
    if not auth.is_authenticated():
        ui.navigate.to("/login")
        return

    user_id = auth.get_session("user_id")
    current_theme = preferences.Theme.LIGHT
    if user_id:
        current_theme = preferences.get_theme_for_user(user_id)

    scheme = preferences.Theme.SCHEMES.get(current_theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])

    book = get_book_by_id(book_id)
    if not book:
        ui.notify("Book not found", type="negative")
        ui.navigate.to("/voice-studio")
        return

    render_voice_studio_header()

    page_style = f"background-color: {scheme['bg_primary']}; height: calc(100vh - 60px); overflow-y: auto;"

    with ui.column().classes("w-full scrollable-pane").style(page_style):
        with ui.column().classes("w-full max-w-6xl mx-auto p-8"):
            with ui.row().classes("w-full justify-between items-center"):
                ui.label(f"Voice Studio: {book.title}").style(
                    f"font-family: 'Merriweather', Georgia, serif; font-size: 1.75rem; font-weight: 700; color: {scheme['text_primary']};"
                )
                with ui.button(
                    "← Back to Voice Studio",
                    icon="o_arrow_back",
                    on_click=lambda: ui.navigate.to("/voice-studio")
                ).classes("").style(ui_theme.button_ghost_styles(current_theme)):
                    pass

            # Provider selection
            providers = tts.tts_manager.get_available_providers()

            with ui.card().classes("w-full mt-6").style(ui_theme.card_styles(current_theme)):
                ui.label("Character Voices").style(
                    f"font-size: 1.1rem; font-weight: 600; color: {scheme['text_primary']}; margin-bottom: 1rem;"
                )

                db = get_session()

                # Get or create character voices for this book
                character_voices = db.query(CharacterVoice).filter(
                    CharacterVoice.book_id == book_id
                ).all()
                db.close()

                if character_voices:
                    for cv in character_voices:
                        with ui.card().classes("w-full mb-3").style(f"background-color: {scheme['bg_secondary']}; border: 1px solid {scheme['border_light']}; border-radius: 10px; padding: 1rem;"):
                            with ui.row().classes("w-full justify-between items-center"):
                                with ui.column():
                                    ui.label(cv.character_name).style(f"font-weight: 600; color: {scheme['text_primary']};")
                                    if cv.voice_name:
                                        ui.label(f"Voice: {cv.voice_name}").style(f"font-size: 0.875rem; color: {scheme['text_muted']};")
                                with ui.row().classes("gap-2"):
                                    if TTSProviderType.MINIMAX in providers:
                                        minimax_vid = cv.minimax_voice_id or "Not set"
                                        ui.label(f"MiniMax: {minimax_vid}").style(f"background-color: {scheme['accent_blue']}22; color: {scheme['accent_blue']}; padding: 0.25rem 0.5rem; border-radius: 6px; font-size: 0.75rem;")
                                    if TTSProviderType.ELEVENLABS in providers:
                                        elevenlabs_vid = cv.elevenlabs_voice_id or "Not set"
                                        ui.label(f"ElevenLabs: {elevenlabs_vid}").style(f"background-color: {scheme['accent_green']}22; color: {scheme['accent_green']}; padding: 0.25rem 0.5rem; border-radius: 6px; font-size: 0.75rem;")
                else:
                    ui.label("No character voices defined yet.").style(f"color: {scheme['text_muted']};")
                    ui.label("Add character voices when narrating chapters.").style(f"font-size: 0.875rem; color: {scheme['text_muted']};")

            # Chapters section
            ui.label("Chapters").style(
                f"font-family: 'Merriweather', Georgia, serif; font-size: 1.25rem; font-weight: 600; color: {scheme['text_primary']}; margin-top: 2rem; margin-bottom: 1rem;"
            )

            chapters = get_chapters_for_book(book_id)

            if not chapters:
                with ui.card().classes("w-full").style(ui_theme.card_styles(current_theme)):
                    ui.image("/static/svg/feather-quill.svg").style("width: 50px; height: 70px; margin: 0 auto 1rem; display: block;")
                    ui.label("No chapters in this book yet.").style(f"color: {scheme['text_muted']}; text-align: center; padding: 0.5rem 0 1.5rem; font-family: 'Merriweather', Georgia, serif; font-size: 1rem;")
            else:
                with ui.column().classes("w-full gap-3"):
                    for chapter in chapters:
                        with ui.card().classes("w-full").style(ui_theme.card_styles(current_theme)):
                            with ui.row().classes("w-full justify-between items-center"):
                                with ui.column():
                                    ui.label(f"Chapter {chapter.order}: {chapter.title}").style(f"font-weight: 600; color: {scheme['text_primary']};")
                                    ui.label(f"{chapter.word_count:,} words").style(f"font-size: 0.875rem; color: {scheme['text_muted']};")
                                with ui.row().classes("gap-2"):
                                    # Check if TTS job exists
                                    db = get_session()
                                    existing_job = db.query(TTSJob).filter(
                                        TTSJob.chapter_id == chapter.id
                                    ).order_by(TTSJob.created_at.desc()).first()
                                    db.close()

                                    if existing_job:
                                        status_color = {
                                            TTSJobStatus.COMPLETED: scheme["status_completed"],
                                            TTSJobStatus.FAILED: scheme["status_failed"],
                                            TTSJobStatus.PENDING: scheme["status_pending"],
                                            TTSJobStatus.PROCESSING: scheme["status_in_progress"],
                                        }.get(existing_job.status, scheme["status_draft"])
                                        ui.label(existing_job.status.value.replace("_", " ").title()).style(
                                            f"background-color: {status_color}22; color: {status_color}; padding: 0.25rem 0.5rem; border-radius: 6px; font-size: 0.75rem;"
                                        )

                                    with ui.button(
                                        "Narrate",
                                        icon="o_play_arrow",
                                        on_click=lambda c=chapter: ui.navigate.to(f"/voice-studio/book/{book_id}/chapter/{c.id}")
                                    ).classes("").style(ui_theme.button_primary_styles()):
                                        pass


@ui.page("/voice-studio/book/{book_id}/chapter/{chapter_id}")
def voice_studio_chapter_page(book_id: int, chapter_id: int):
    """Voice Studio - narrate a specific chapter."""
    if not auth.is_authenticated():
        ui.navigate.to("/login")
        return

    book = get_book_by_id(book_id)
    if not book:
        ui.notify("Book not found", type="negative")
        ui.navigate.to("/voice-studio")
        return

    chapter = get_chapter_with_tts_jobs(chapter_id)
    if not chapter or chapter.book_id != book_id:
        ui.notify("Chapter not found", type="negative")
        ui.navigate.to(f"/voice-studio/book/{book_id}")
        return

    user_id = auth.get_session("user_id")
    current_theme = preferences.Theme.LIGHT
    if user_id:
        current_theme = preferences.get_theme_for_user(user_id)

    scheme = preferences.Theme.SCHEMES.get(current_theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])

    render_voice_studio_header()

    with ui.column().classes("w-full max-w-6xl mx-auto p-8"):
        with ui.row().classes("w-full justify-between items-center"):
            ui.label(f"Narrate: {chapter.title}").classes("text-2xl font-bold")
            ui.button(
                "← Back to Book",
                icon="o_arrow_back",
                on_click=lambda: ui.navigate.to(f"/voice-studio/book/{book_id}")
            ).props("flat")

        # Chapter preview
        with ui.card().classes("w-full mt-4 p-6").style(f"border: 1px solid {scheme['border_light']}; border-radius: 16px;"):
            ui.label(f"Chapter {chapter.order}").style(f"font-size: 0.875rem; color: {scheme['text_muted']}")
            ui.label(chapter.title).classes("text-xl font-semibold")
            ui.label(f"{chapter.word_count:,} words").style(f"font-size: 0.875rem; color: {scheme['text_muted']}")

            if chapter.content:
                preview = chapter.content[:500] + "..." if len(chapter.content) > 500 else chapter.content
                with ui.card().classes("w-full mt-4 p-4").style(f"background-color: {scheme['bg_secondary']}; border: 1px solid {scheme['border_light']}; border-radius: 16px;"):
                    ui.label("Content Preview:").classes("text-sm font-semibold")
                    ui.label(preview).classes("text-sm")

        # Provider selection
        providers = tts.tts_manager.get_available_providers()

        with ui.card().classes("w-full mt-6 p-6").style(f"border: 1px solid {scheme['border_light']}; border-radius: 16px;"):
            ui.label("Narrate Chapter").classes("text-lg font-semibold mb-4")

            # Provider selector
            selected_provider = ui.select(
                label="TTS Provider",
                options=[{"label": p.value.title(), "value": p.value} for p in providers],
                value=providers[0].value if providers else None,
            ).classes("w-full").props("outlined")

            # Voice selector
            selected_voice = ui.select(
                label="Voice",
                options=[],
                value=None,
            ).classes("w-full").props("outlined")

            # Model selector
            selected_model = ui.select(
                label="Model",
                options=[
                    {"label": "Speech-02 HD (High Quality)", "value": "speech-02-hd"},
                    {"label": "Speech-02 Turbo (Fast)", "value": "speech-02-turbo"},
                ],
                value="speech-02-hd",
            ).classes("w-full").props("outlined")

            # Load voices when provider changes
            async def load_voices(provider_value):
                provider = TTSProviderType(provider_value)
                voices = await tts.tts_manager.list_voices(provider)
                if voices:
                    selected_voice.options = [
                        {"label": f"{v.name} ({v.voice_id})", "value": v.voice_id}
                        for v in voices
                    ]
                    if voices:
                        selected_voice.value = voices[0].voice_id
                else:
                    selected_voice.options = [{"label": "No voices available", "value": ""}]
                    selected_voice.value = ""

            async def on_provider_change(e):
                await load_voices(e.value)

            selected_provider.on_value_change(on_provider_change)

            # Load initial voices
            if providers:
                asyncio.create_task(load_voices(providers[0].value))

            # Narrate button
            status_label = ui.label("").classes("mt-4")

            async def narrate_chapter():
                if not chapter.content:
                    ui.notify("Chapter has no content to narrate", type="warning")
                    return

                provider_str = selected_provider.value
                voice_id = selected_voice.value
                model = selected_model.value

                if not voice_id:
                    ui.notify("Please select a voice", type="warning")
                    return

                provider = TTSProviderType(provider_str)
                status_label.text = "Generating speech..."
                ui.notify("Starting narration... This may take a moment.", type="info")

                try:
                    request = tts.TTSRequest(
                        text=chapter.content,
                        provider=provider,
                        voice_id=voice_id,
                        model=model,
                        speed=1.0,
                    )

                    response = await tts.tts_manager.generate_speech(request)

                    if response.error:
                        ui.notify(f"Error: {response.error}", type="negative")
                        status_label.text = ""
                        return

                    if response.audio_data:
                        # Save audio file
                        audio_path = tts.save_audio_file(
                            book_id=book_id,
                            chapter_id=chapter_id,
                            provider=provider,
                            audio_data=response.audio_data,
                            format="mp3",
                        )

                        # Create TTS job record
                        db = get_session()
                        job = TTSJob(
                            chapter_id=chapter_id,
                            provider=provider,
                            voice_id=voice_id,
                            model=model,
                            status=TTSJobStatus.COMPLETED,
                            audio_path=audio_path,
                            audio_duration=response.duration_seconds,
                            cost_tokens=response.cost_tokens,
                            completed_at=datetime.now(),
                        )
                        db.add(job)
                        db.commit()
                        db.close()

                        ui.notify("Narration complete! 🎉", type="positive")
                        status_label.text = f"Generated {len(response.audio_data):,} bytes"
                    else:
                        ui.notify("No audio generated", type="warning")
                        status_label.text = ""

                except Exception as e:
                    ui.notify(f"Narration failed: {str(e)}", type="negative")
                    status_label.text = ""

            ui.button(
                "🔊 Generate Narration",
                on_click=narrate_chapter,
            ).props("color=primary").classes("mt-4")

        # Existing TTS jobs
        if chapter.tts_jobs:
            with ui.card().classes("w-full mt-6 p-6").style(f"border: 1px solid {scheme['border_light']}; border-radius: 16px;"):
                ui.label("Previous Narrations").classes("text-lg font-semibold mb-4")

                for job in chapter.tts_jobs:
                    with ui.card().classes("w-full p-4 mb-3").style(f"background-color: {scheme['bg_secondary']}; border: 1px solid {scheme['border_light']}; border-radius: 16px;"):
                        with ui.row().classes("w-full justify-between items-center"):
                            with ui.column():
                                ui.label(f"Provider: {job.provider.value.title()}").classes("font-semibold")
                                ui.label(f"Voice: {job.voice_id}").style(f"font-size: 0.875rem; color: {scheme['text_muted']}")
                                ui.label(f"Model: {job.model}").style(f"font-size: 0.875rem; color: {scheme['text_muted']}")
                                if job.cost_tokens:
                                    ui.label(f"Cost: {job.cost_tokens} tokens").style(f"font-size: 0.75rem; color: {scheme['text_muted']}")
                            with ui.column().classes("items-end"):
                                status_color = {
                                    TTSJobStatus.COMPLETED: "positive",
                                    TTSJobStatus.FAILED: "negative",
                                    TTSJobStatus.PENDING: "warning",
                                    TTSJobStatus.PROCESSING: "info",
                                }.get(job.status, "grey")
                                ui.badge(
                                    job.status.value.replace("_", " ").title(),
                                    color=status_color
                                )
                                if job.audio_path and job.status == TTSJobStatus.COMPLETED:
                                    ui.button(
                                        "▶️ Play",
                                        on_click=lambda j=job: _play_audio(j.audio_path)
                                    ).props("flat size=sm").classes("mt-2")


def _play_audio(audio_path: str):
    """Play audio file in the UI."""
    if not audio_path:
        ui.notify("No audio file available", type="warning")
        return

    path = Path(audio_path)
    if not path.exists():
        ui.notify("Audio file not found", type="negative")
        return

    # Serve audio file
    from nicegui import ui as quasar_ui
    quasar_ui.audio(f"/static/audio/{path.name}").classes("w-full")


# =============================================================================
# Backup Management Pages
# =============================================================================


@ui.page("/backups")
def backups_page():
    """Backup management page - warm studio theme."""
    if not auth.is_authenticated():
        ui.navigate.to("/login")
        return

    user_id = auth.get_session("user_id")
    current_theme = preferences.Theme.LIGHT
    if user_id:
        current_theme = preferences.get_theme_for_user(user_id)

    scheme = preferences.Theme.SCHEMES.get(current_theme, preferences.Theme.SCHEMES[preferences.Theme.LIGHT])

    # Use the main header
    render_header()

    page_style = f"background-color: {scheme['bg_primary']}; height: calc(100vh - 60px); overflow-y: auto;"

    with ui.column().classes("w-full scrollable-pane").style(page_style):
        with ui.column().classes("w-full max-w-6xl mx-auto p-8"):
            with ui.row().classes("w-full justify-between items-center"):
                ui.label("Backup Management").style(
                    f"font-family: 'Merriweather', Georgia, serif; font-size: 2rem; font-weight: 700; color: {scheme['text_primary']};"
                )
                with ui.button(
                    "Create Backup",
                    icon="o_backup",
                    on_click=lambda: _create_backup()
                ).classes("").style(ui_theme.button_primary_styles()):
                    pass

            # Backup info
            last_backup = backup.get_last_backup_info()
            with ui.card().classes("w-full mt-4").style(ui_theme.card_styles(current_theme)):
                if last_backup:
                    ui.label(f"Last backup: {last_backup.get('created_at', 'unknown')}").style(f"font-size: 0.875rem; color: {scheme['text_muted']};")
                    ui.label(f"Size: {last_backup.get('size', 0):,} bytes").style(f"font-size: 0.875rem; color: {scheme['text_muted']};")
                else:
                    ui.label("No backups yet").style(f"color: {scheme['text_muted']};")

            # Backup list
            ui.label("Available Backups").style(
                f"font-family: 'Merriweather', Georgia, serif; font-size: 1.25rem; font-weight: 600; color: {scheme['text_primary']}; margin-top: 2rem; margin-bottom: 1rem;"
            )

            backups = backup.list_backups()

            if not backups:
                with ui.card().classes("w-full").style(ui_theme.card_styles(current_theme)):
                    ui.image("/static/svg/inkwell.svg").style("width: 60px; height: 60px; margin: 0 auto 1rem; display: block;")
                    ui.label("No backups available").style(f"color: {scheme['text_muted']}; text-align: center; font-family: 'Merriweather', Georgia, serif; font-size: 1.1rem; padding: 0.5rem 0 1rem;")
                    ui.label("Create your first backup to protect your data.").style(f"color: {scheme['text_muted']}; text-align: center; font-size: 0.875rem;")
                    ui.label("Create your first backup to protect your data.").style("text-align: center; margin-top: 0.5rem;")
            else:
                with ui.column().classes("w-full gap-3"):
                    for bk in backups[:10]:  # Show max 10
                        with ui.card().classes("w-full").style(ui_theme.card_styles(current_theme)):
                            with ui.row().classes("w-full justify-between items-center"):
                                with ui.column():
                                    ui.label(bk.get("book_title", "Unknown")).style(f"font-weight: 600; color: {scheme['text_primary']};")
                                    ui.label(f"Created: {bk.get('created_at', 'unknown')}").style(f"font-size: 0.875rem; color: {scheme['text_muted']};")
                                    ui.label(f"Size: {bk.get('size', 0):,} bytes").style(f"font-size: 0.75rem; color: {scheme['text_muted']};")
                                with ui.row().classes("gap-2"):
                                    # Verify button
                                    is_valid = backup.verify_backup(bk.get("path", ""))
                                    status_color = scheme["status_completed"] if is_valid else scheme["status_failed"]
                                    ui.label("✓ Valid" if is_valid else "✗ Invalid").style(
                                        f"background-color: {status_color}22; color: {status_color}; padding: 0.25rem 0.5rem; border-radius: 6px; font-size: 0.75rem;"
                                    )
                                    # Restore button
                                    with ui.button(
                                        "Restore",
                                        icon="o_restore",
                                        on_click=lambda b=bk: _confirm_restore(b)
                                    ).classes("").style(ui_theme.button_secondary_styles(current_theme)):
                                        pass
                                    # Delete button
                                    with ui.button(
                                        icon="o_delete",
                                        on_click=lambda b=bk: _confirm_delete_backup(b)
                                    ).classes("").style("background-color: transparent; color: #CA8B8B; border: none;"):
                                        pass

            # Cleanup info
            with ui.card().classes("w-full mt-8").style(ui_theme.card_styles(current_theme)):
                ui.label(f"Retention: Max {backup.MAX_BACKUPS} backups, {backup.MAX_AGE_DAYS} days").style(f"font-size: 0.875rem; color: {scheme['text_muted']};")

    # Refresh table
    def _create_backup():
        try:
            db_path = Path("./data/story_forge.db")
            if not db_path.exists():
                ui.notify("Database file not found", type="warning")
                return

            result = backup.create_backup(db_path, "story_forge")
            ui.notify(f"Backup created: {result['size']:,} bytes", type="positive")
            ui.navigate.to("/backups")
        except Exception as e:
            ui.notify(f"Backup failed: {e}", type="negative")

    def _confirm_restore(bk: dict):
        with ui.dialog() as dialog, ui.card():
            ui.label("⚠️ Restore Backup?").classes("text-xl font-bold")
            ui.label("This will replace your current database with:").classes("mt-4")
            ui.label(f"Backup from: {bk.get('created_at', 'unknown')}").classes("text-sm")
            ui.label("Any unsaved changes will be lost.").style(f"font-size: 0.875rem; color: {scheme['text_muted']}; margin-top: 1rem;")
            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button(
                    "Restore",
                    on_click=lambda: _do_restore(bk, dialog)
                ).props("color=negative")
        dialog.open()

    def _do_restore(bk: dict, dialog):
        try:
            db_path = Path("./data/story_forge.db")
            backup.restore_backup(bk.get("path"), db_path)
            ui.notify("Database restored successfully", type="positive")
            dialog.close()
        except Exception as e:
            ui.notify(f"Restore failed: {e}", type="negative")
            dialog.close()

    def _confirm_delete_backup(bk: dict):
        with ui.dialog() as dialog, ui.card():
            ui.label("⚠️ Delete Backup?").classes("text-xl font-bold")
            ui.label(f"Backup from: {bk.get('created_at', 'unknown')}").classes("mt-4")
            ui.label("This cannot be undone.").style("font-size: 0.875rem; color: #9A948D")
            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button(
                    "Delete",
                    on_click=lambda: _do_delete(bk, dialog)
                ).props("color=negative")
        dialog.open()

    def _do_delete(bk: dict, dialog):
        try:
            Path(bk.get("path", "")).unlink()
            ui.notify("Backup deleted", type="positive")
            dialog.close()
            ui.navigate.to("/backups")
        except Exception as e:
            ui.notify(f"Delete failed: {e}", type="negative")
            dialog.close()


# =============================================================================
# Audio Static File Serving
# =============================================================================


def setup_audio_routes(app):
    """Set up static audio file routes."""
    import fastapi.staticfiles

    # Mount audio directory for static serving
    audio_dir = Path("./data/audio")
    if audio_dir.exists():
        app.mount("/static/audio", fastapi.staticfiles.StaticFiles(directory=str(audio_dir)), name="audio")


def main():
    """Main entry point."""
    # Create the app
    create_app()

    # Serve static SVG files for illustrated empty states
    app.add_static_files("/static", "static")

    # Run the app
    port = int(os.environ.get("PORT", "8080"))
    ui.run(
        host="0.0.0.0",
        port=port,
        title=APP_TITLE,
        reload=False,
    )


if __name__ == "__main__":
    main()

