"""
Story Forge - Self-Publishing Dashboard
Main entry point for the NiceGUI application.
"""

import os
import asyncio
from pathlib import Path
from urllib import parse as urllib_parse

import nicegui as ui
import auth
from db import init_db, get_session, Book, Chapter, BookStatus

# Configure environment
DATA_DIR = Path("./data")
DATA_DIR.mkdir(exist_ok=True)

# Application configuration
APP_TITLE = "Story Forge"
APP_VERSION = "0.1.0"

# Pagination settings
ITEMS_PER_PAGE = 10


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
            db.func.sum(Book.word_count)
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
        books = query.order_by(Book.updated_at.desc()).offset(offset).limit(ITEMS_PER_PAGE).all()

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
    """Render the common header with navigation."""
    user_email = auth.get_session("user_email", "")
    user_avatar = auth.get_session("user_avatar", "")

    with ui.header().classes("bg-white shadow"):
        with ui.row().classes("w-full justify-between items-center px-4"):
            ui.label(APP_TITLE).classes("text-xl font-bold text-gray-800")

            with ui.row().classes("items-center gap-2"):
                ui.button(
                    "Dashboard",
                    on_click=lambda: ui.navigate.to("/dashboard"),
                    icon="dashboard"
                ).props("flat dense").classes("text-gray-600")
                ui.button(
                    "Books",
                    on_click=lambda: ui.navigate.to("/books"),
                    icon="library_books"
                ).props("flat dense").classes("text-gray-600")

                if user_avatar:
                    ui.avatar(source=user_avatar, size="sm")
                else:
                    ui.avatar(text=user_email[0].upper() if user_email else "?", size="sm")

                ui.button(
                    "Logout",
                    on_click=lambda: ui.navigate.to("/logout"),
                    icon="logout"
                ).props("flat dense color=negative")


# =============================================================================
# Page Routes
# =============================================================================

def create_app():
    """Create and configure the NiceGUI application."""
    import nicegui as ui

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
        """Login page with Google OAuth."""
        if auth.is_authenticated():
            ui.navigate.to("/dashboard")
            return

        with ui.column().classes("w-full h-screen justify-center items-center"):
            with ui.card().classes("w-96 p-8"):
                ui.label(APP_TITLE).classes("text-3xl font-bold text-center text-gray-800")
                ui.label(f"Version {APP_VERSION}").classes("text-sm text-gray-500 text-center")

                ui.separator()

                ui.label("Sign in to continue").classes("text-lg text-center mt-4")

                def go_to_google():
                    login_url = auth.get_login_url()
                    ui.navigate.to(login_url, new_tab=True)

                ui.button(
                    "Sign in with Google",
                    on_click=go_to_google,
                    icon="login"
                ).classes("w-full mt-4")

                ui.label(
                    "Secure authentication powered by Google OAuth 2.0"
                ).classes("text-xs text-gray-400 text-center mt-4")

    @ui.page("/auth/callback")
    def auth_callback_page():
        """OAuth callback handler."""
        query = ui.query_params
        code = query.get("code")
        state = query.get("state")
        error = query.get("error")

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

        # Header
        render_header()

        # Dashboard content
        with ui.column().classes("w-full max-w-6xl mx-auto p-8"):
            ui.label(f"Welcome back, {user_name}!").classes("text-3xl font-bold text-gray-800")
            ui.label("Your publishing overview").classes("text-gray-500 mb-8")

            # Stats cards
            book_count = get_book_count()
            chapter_count = get_chapter_count()
            total_words = get_total_word_count()

            with ui.row().classes("w-full gap-4 flex-wrap"):
                with ui.card().classes("flex-1 min-w-48 p-6"):
                    with ui.column().classes("items-center"):
                        ui.icon("library_books", size="xl", color="blue").classes("mb-2")
                        ui.label(str(book_count)).classes("text-4xl font-bold text-blue-600")
                        ui.label("Books").classes("text-lg font-semibold")
                        ui.label("in library").classes("text-sm text-gray-500")

                with ui.card().classes("flex-1 min-w-48 p-6"):
                    with ui.column().classes("items-center"):
                        ui.icon("article", size="xl", color="green").classes("mb-2")
                        ui.label(str(chapter_count)).classes("text-4xl font-bold text-green-600")
                        ui.label("Chapters").classes("text-lg font-semibold")
                        ui.label("written").classes("text-sm text-gray-500")

                with ui.card().classes("flex-1 min-w-48 p-6"):
                    with ui.column().classes("items-center"):
                        ui.icon("text_fields", size="xl", color="purple").classes("mb-2")
                        ui.label(f"{total_words:,}").classes("text-4xl font-bold text-purple-600")
                        ui.label("Words").classes("text-lg font-semibold")
                        ui.label("total").classes("text-sm text-gray-500")

            # Quick actions
            with ui.card().classes("mt-8 p-6 w-full"):
                ui.label("Quick Actions").classes("text-xl font-semibold mb-4")
                with ui.row().classes("gap-4 flex-wrap"):
                    ui.button(
                        "New Book",
                        icon="add",
                        on_click=lambda: ui.navigate.to("/books/new")
                    ).props("color=primary")
                    ui.button(
                        "View All Books",
                        icon="library_books",
                        on_click=lambda: ui.navigate.to("/books")
                    )

    @ui.page("/books")
    def books_page():
        """Books management page with search and pagination."""
        if not auth.is_authenticated():
            ui.navigate.to("/login")
            return

        # Get query params for pagination and filtering
        query_params = ui.query_params
        page = int(query_params.get("page", "1"))
        search = query_params.get("search", "")
        status = query_params.get("status", "")

        # Header
        render_header()

        # Books content
        with ui.column().classes("w-full max-w-6xl mx-auto p-8"):
            with ui.row().classes("justify-between items-center w-full mb-6"):
                ui.label("Books").classes("text-3xl font-bold")
                ui.button(
                    "New Book",
                    icon="add",
                    on_click=lambda: ui.navigate.to("/books/new")
                ).props("color=primary")

            # Search and filter bar
            with ui.card().classes("w-full p-4 mb-6"):
                with ui.row().classes("w-full gap-4 items-center"):
                    search_input = ui.input(
                        label="Search",
                        value=search,
                        placeholder="Search books..."
                    ).classes("flex-1").props("outlined dense")

                    status_options = [
                        {"label": "All Statuses", "value": ""},
                        {"label": "Draft", "value": "draft"},
                        {"label": "In Progress", "value": "in_progress"},
                        {"label": "Completed", "value": "completed"},
                        {"label": "Archived", "value": "archived"},
                    ]
                    status_select = ui.select(
                        label="Status",
                        options=status_options,
                        value=status,
                    ).classes("w-48").props("outlined dense")

                    def apply_filters():
                        params = {}
                        if search_input.value:
                            params["search"] = search_input.value
                        if status_select.value:
                            params["status"] = status_select.value
                        params["page"] = "1"
                        ui.navigate.to(f"/books?{urllib_parse.urlencode(params)}")

                    ui.button("Search", icon="search", on_click=apply_filters)

            # Get books
            books, total = get_all_books(search=search, status_filter=status, page=page)
            total_pages = (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

            # Books grid
            if books:
                with ui.row().classes("w-full gap-4 flex-wrap"):
                    for book in books:
                        status_colors = {
                            "draft": "grey",
                            "in_progress": "blue",
                            "completed": "green",
                            "archived": "grey-8",
                        }

                        with ui.card().classes("w-full md:w-80 p-4"):
                            with ui.column().classes("w-full"):
                                with ui.row().classes("w-full justify-between items-start"):
                                    ui.label(book.title).classes("text-lg font-semibold")
                                    from nicegui import ui as quasar_ui
                                    quasar_ui.QBadge(
                                        label=book.status.value.replace("_", " ").title(),
                                        color=status_colors.get(book.status.value, "grey"),
                                    )

                                if book.author:
                                    ui.label(f"by {book.author}").classes("text-sm text-gray-500")

                                if book.description:
                                    desc = book.description
                                    if len(desc) > 100:
                                        desc = desc[:100] + "..."
                                    ui.label(desc).classes("text-sm text-gray-600 mt-2")

                                with ui.row().classes("mt-4 gap-4 items-center"):
                                    ui.label(f"{len(book.chapters)} chapters").classes("text-xs text-gray-500")
                                    ui.label(f"{book.word_count:,} words").classes("text-xs text-gray-500")

                                with ui.row().classes("mt-4 gap-2"):
                                    ui.button(
                                        "View",
                                        icon="visibility",
                                        on_click=lambda b=book: ui.navigate.to(f"/book/{b.id}")
                                    ).props("flat dense size=sm")
                                    ui.button(
                                        "Edit",
                                        icon="edit",
                                        on_click=lambda b=book: ui.navigate.to(f"/book/{b.id}/edit")
                                    ).props("flat dense size=sm")
                                    ui.button(
                                        icon="delete",
                                        on_click=lambda b=book: confirm_delete_book(b.id)
                                    ).props("flat dense size=sm color=negative")

                # Pagination
                if total_pages > 1:
                    with ui.row().classes("w-full justify-center items-center mt-8 gap-2"):
                        if page > 1:
                            prev_params = {"page": str(page - 1)}
                            if search:
                                prev_params["search"] = search
                            if status:
                                prev_params["status"] = status
                            ui.button(
                                "Previous",
                                icon="chevron_left",
                                on_click=lambda: ui.navigate.to(f"/books?{urllib_parse.urlencode(prev_params)}")
                            ).props("flat")

                        ui.label(f"Page {page} of {total_pages}").classes("text-sm")

                        if page < total_pages:
                            next_params = {"page": str(page + 1)}
                            if search:
                                next_params["search"] = search
                            if status:
                                next_params["status"] = status
                            ui.button(
                                "Next",
                                icon="chevron_right",
                                on_click=lambda: ui.navigate.to(f"/books?{urllib_parse.urlencode(next_params)}")
                            ).props("flat")
            else:
                with ui.card().classes("w-full p-8"):
                    ui.label("No books found").classes("text-xl text-gray-500 text-center")
                    ui.label("Create your first book to get started!").classes("text-center mt-2")
                    ui.button(
                        "Create Book",
                        icon="add",
                        on_click=lambda: ui.navigate.to("/books/new")
                    ).props("color=primary").classes("mt-4")

    def confirm_delete_book(book_id: int) -> None:
        """Show confirmation dialog for deleting a book."""

        def do_delete():
            delete_book(book_id)
            ui.notify("Book deleted successfully", type="positive")
            ui.navigate.to("/books")

        with ui.dialog() as dialog, ui.card():
            ui.label("Are you sure you want to delete this book?")
            ui.label("This will also delete all chapters and cannot be undone.").classes("text-sm text-gray-500")
            with ui.row().classes("mt-4 gap-2 justify-end"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button("Delete", on_click=lambda: [dialog.close(), do_delete()]).props("color=negative")
        dialog.open()

    @ui.page("/books/new")
    def new_book_page():
        """Create new book page."""
        if not auth.is_authenticated():
            ui.navigate.to("/login")
            return

        render_header()

        with ui.column().classes("w-full max-w-2xl mx-auto p-8"):
            ui.label("New Book").classes("text-2xl font-bold")

            with ui.card().classes("w-full mt-4 p-6"):
                with ui.column().classes("w-full gap-4"):
                    title_input = ui.input(
                        label="Title",
                        placeholder="Enter book title"
                    ).classes("w-full").props("outlined")

                    author_input = ui.input(
                        label="Author",
                        placeholder="Enter author name"
                    ).classes("w-full").props("outlined")

                    description_input = ui.textarea(
                        label="Description",
                        placeholder="Enter book description"
                    ).classes("w-full").props("outlined")

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
                    ).classes("w-full").props("outlined")

                    with ui.row().classes("mt-4 gap-2"):
                        ui.button(
                            "Cancel",
                            on_click=lambda: ui.navigate.to("/books")
                        ).props("flat")

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

                        ui.button("Save Book", on_click=save_book).props("color=primary")

    @ui.page("/book/{book_id}")
    def book_detail_page(book_id: int):
        """Book detail page with chapter management."""
        if not auth.is_authenticated():
            ui.navigate.to("/login")
            return

        book = get_book_by_id(book_id)
        if not book:
            ui.notify("Book not found", type="negative")
            ui.navigate.to("/books")
            return

        # Load chapters
        chapters = get_chapters_for_book(book_id)

        render_header()

        with ui.column().classes("w-full max-w-4xl mx-auto p-8"):
            # Book header
            with ui.card().classes("w-full p-6"):
                with ui.row().classes("w-full justify-between items-start"):
                    with ui.column():
                        ui.label(book.title).classes("text-3xl font-bold")
                        if book.author:
                            ui.label(f"by {book.author}").classes("text-lg text-gray-500")

                    from nicegui import ui as quasar_ui
                    status_colors = {
                        "draft": "grey",
                        "in_progress": "blue",
                        "completed": "green",
                        "archived": "grey-8",
                    }
                    quasar_ui.QBadge(
                        label=book.status.value.replace("_", " ").title(),
                        color=status_colors.get(book.status.value, "grey"),
                    )

                if book.description:
                    ui.label(book.description).classes("mt-4 text-gray-600")

                with ui.row().classes("mt-4 gap-4"):
                    ui.label(f"{len(chapters)} chapters").classes("text-sm")
                    ui.label(f"{book.word_count:,} words").classes("text-sm")

                with ui.row().classes("mt-4 gap-2"):
                    ui.button(
                        "Edit Book",
                        icon="edit",
                        on_click=lambda: ui.navigate.to(f"/book/{book_id}/edit")
                    ).props("flat")
                    ui.button(
                        "Delete",
                        icon="delete",
                        on_click=lambda: confirm_delete_book(book_id)
                    ).props("flat color=negative")

            # Chapters section
            with ui.row().classes("w-full justify-between items-center mt-8 mb-4"):
                ui.label("Chapters").classes("text-2xl font-bold")
                ui.button(
                    "Add Chapter",
                    icon="add",
                    on_click=lambda: ui.navigate.to(f"/book/{book_id}/chapter/new")
                ).props("color=primary")

            if chapters:
                with ui.column().classes("w-full gap-2"):
                    for i, chapter in enumerate(chapters, 1):
                        with ui.card().classes("w-full p-4"):
                            with ui.row().classes("w-full justify-between items-center"):
                                with ui.column():
                                    ui.label(f"Chapter {chapter.order}: {chapter.title}").classes("text-lg font-semibold")
                                    ui.label(f"{chapter.word_count:,} words").classes("text-sm text-gray-500")

                                with ui.row().classes("gap-2"):
                                    ui.button(
                                        icon="edit",
                                        on_click=lambda c=chapter: ui.navigate.to(f"/book/{book_id}/chapter/{c.id}/edit")
                                    ).props("flat dense")
                                    ui.button(
                                        icon="delete",
                                        on_click=lambda c=chapter: confirm_delete_chapter(book_id, c.id)
                                    ).props("flat dense color=negative")
            else:
                with ui.card().classes("w-full p-8"):
                    ui.label("No chapters yet").classes("text-lg text-gray-500 text-center")
                    ui.label("Add your first chapter to start writing!").classes("text-center mt-2")

    def confirm_delete_chapter(book_id: int, chapter_id: int) -> None:
        """Show confirmation dialog for deleting a chapter."""

        def do_delete():
            delete_chapter(chapter_id)
            recalculate_book_word_count(book_id)
            ui.notify("Chapter deleted successfully", type="positive")
            ui.navigate.to(f"/book/{book_id}")

        with ui.dialog() as dialog, ui.card():
            ui.label("Are you sure you want to delete this chapter?")
            ui.label("This cannot be undone.").classes("text-sm text-gray-500")
            with ui.row().classes("mt-4 gap-2 justify-end"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button("Delete", on_click=lambda: [dialog.close(), do_delete()]).props("color=negative")
        dialog.open()

    @ui.page("/book/{book_id}/edit")
    def edit_book_page(book_id: int):
        """Edit book page."""
        if not auth.is_authenticated():
            ui.navigate.to("/login")
            return

        book = get_book_by_id(book_id)
        if not book:
            ui.notify("Book not found", type="negative")
            ui.navigate.to("/books")
            return

        render_header()

        with ui.column().classes("w-full max-w-2xl mx-auto p-8"):
            ui.label("Edit Book").classes("text-2xl font-bold")

            with ui.card().classes("w-full mt-4 p-6"):
                with ui.column().classes("w-full gap-4"):
                    title_input = ui.input(
                        label="Title",
                        value=book.title,
                        placeholder="Enter book title"
                    ).classes("w-full").props("outlined")

                    author_input = ui.input(
                        label="Author",
                        value=book.author or "",
                        placeholder="Enter author name"
                    ).classes("w-full").props("outlined")

                    description_input = ui.textarea(
                        label="Description",
                        value=book.description or "",
                        placeholder="Enter book description"
                    ).classes("w-full").props("outlined")

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
                    ).classes("w-full").props("outlined")

                    with ui.row().classes("mt-4 gap-2"):
                        ui.button(
                            "Cancel",
                            on_click=lambda: ui.navigate.to(f"/book/{book_id}")
                        ).props("flat")

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
        """Create new chapter page."""
        if not auth.is_authenticated():
            ui.navigate.to("/login")
            return

        book = get_book_by_id(book_id)
        if not book:
            ui.notify("Book not found", type="negative")
            ui.navigate.to("/books")
            return

        # Get next chapter order
        chapters = get_chapters_for_book(book_id)
        next_order = max([c.order for c in chapters], default=0) + 1

        render_header()

        with ui.column().classes("w-full max-w-2xl mx-auto p-8"):
            ui.label(f"New Chapter for {book.title}").classes("text-2xl font-bold")

            with ui.card().classes("w-full mt-4 p-6"):
                with ui.column().classes("w-full gap-4"):
                    title_input = ui.input(
                        label="Chapter Title",
                        placeholder="Enter chapter title"
                    ).classes("w-full").props("outlined")

                    order_input = ui.number(
                        label="Chapter Number",
                        value=next_order,
                    ).classes("w-full").props("outlined")

                    with ui.row().classes("mt-4 gap-2"):
                        ui.button(
                            "Cancel",
                            on_click=lambda: ui.navigate.to(f"/book/{book_id}")
                        ).props("flat")

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

                        ui.button("Create Chapter", on_click=save_chapter).props("color=primary")

    @ui.page("/book/{book_id}/chapter/{chapter_id}/edit")
    def edit_chapter_page(book_id: int, chapter_id: int):
        """Edit chapter page."""
        if not auth.is_authenticated():
            ui.navigate.to("/login")
            return

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

        with ui.column().classes("w-full max-w-4xl mx-auto p-8"):
            with ui.row().classes("w-full justify-between items-center"):
                ui.label(f"Edit Chapter: {chapter.title}").classes("text-2xl font-bold")
                ui.button(
                    "Back to Book",
                    icon="arrow_back",
                    on_click=lambda: ui.navigate.to(f"/book/{book_id}")
                ).props("flat")

            with ui.card().classes("w-full mt-4 p-6"):
                with ui.column().classes("w-full gap-4"):
                    title_input = ui.input(
                        label="Chapter Title",
                        value=chapter.title,
                        placeholder="Enter chapter title"
                    ).classes("w-full").props("outlined")

                    order_input = ui.number(
                        label="Chapter Number",
                        value=chapter.order,
                    ).classes("w-full").props("outlined")

                    content_input = ui.textarea(
                        label="Chapter Content",
                        value=chapter.content or "",
                        placeholder="Write your chapter content here...",
                    ).classes("w-full").props("outlined")

                    # Word count display
                    def update_word_count():
                        content = content_input.value or ""
                        words = len(content.split())
                        word_count_label.set_text(f"Words: {words}")

                    content_input.on_value_change(update_word_count)

                    word_count_label = ui.label(f"Words: {chapter.word_count}").classes("text-sm text-gray-500")

                    with ui.row().classes("mt-4 gap-2"):
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

                        ui.button("Save Changes", on_click=save_chapter).props("color=primary")


def main():
    """Main entry point."""
    import nicegui as ui

    # Create the app
    create_app()

    # Configure UI
    ui.config.title = APP_TITLE
    ui.config.reload = False

    # Run the app
    port = int(os.environ.get("PORT", "8080"))
    ui.run(host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()

