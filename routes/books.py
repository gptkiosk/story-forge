"""
Books routes for Story Forge API
"""
from fastapi import APIRouter, HTTPException, Request
from schemas import (
    BookCreate, BookUpdate, BookResponse, BookListResponse, ChapterCreate,
    to_book_response, to_chapter_response
)
from db_helpers import (
    get_all_books, get_book_by_id, create_book, update_book, delete_book,
    get_chapters_for_book, create_chapter, recalculate_book_word_count
)
from .auth_utils import require_auth

ITEMS_PER_PAGE = 12

router = APIRouter()


@router.get("", response_model=BookListResponse)
def list_books(request: Request, page: int = 1, search: str = "", status: str = ""):
    """Get all books."""
    require_auth(request)

    books, total = get_all_books(
        search=search,
        status_filter=status,
        page=page
    )

    return BookListResponse(
        books=[to_book_response(b) for b in books],
        total=total,
        page=page,
        per_page=ITEMS_PER_PAGE
    )


@router.get("/{book_id}", response_model=BookResponse)
def get_book(request: Request, book_id: int):
    """Get a single book by ID."""
    require_auth(request)

    book = get_book_by_id(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    return to_book_response(book)


@router.post("", response_model=BookResponse)
def create_book_route(request: Request, book: BookCreate):
    """Create a new book."""
    require_auth(request)

    new_book = create_book(
        title=book.title,
        description=book.description or book.synopsis or "",
        author=book.author or "",
        status=book.status.value if book.status else "draft"
    )

    return to_book_response(new_book)


@router.put("/{book_id}", response_model=BookResponse)
def update_book_route(request: Request, book_id: int, book: BookUpdate):
    """Update an existing book."""
    require_auth(request)

    # Build kwargs for update
    kwargs = {}
    if book.title is not None:
        kwargs["title"] = book.title
    if book.author is not None:
        kwargs["author"] = book.author
    if book.description is not None:
        kwargs["description"] = book.description
    if book.status is not None:
        kwargs["status"] = book.status

    updated = update_book(book_id, **kwargs)
    if not updated:
        raise HTTPException(status_code=404, detail="Book not found")

    return to_book_response(updated)


@router.delete("/{book_id}")
def delete_book_route(request: Request, book_id: int):
    """Delete a book and all its chapters."""
    require_auth(request)

    success = delete_book(book_id)
    if not success:
        raise HTTPException(status_code=404, detail="Book not found")

    return {"status": "deleted"}


@router.get("/{book_id}/chapters")
def get_book_chapters(request: Request, book_id: int):
    """Get all chapters for a book."""
    require_auth(request)

    chapters = get_chapters_for_book(book_id)
    return [to_chapter_response(c) for c in chapters]


@router.post("/{book_id}/chapters")
def create_book_chapter(request: Request, book_id: int, chapter: ChapterCreate):
    """Create a new chapter for a book."""
    require_auth(request)

    # Verify book exists
    book = get_book_by_id(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    new_chapter = create_chapter(
        book_id=book_id,
        title=chapter.title,
        order=chapter.order
    )

    # Recalculate word count
    recalculate_book_word_count(book_id)

    return to_chapter_response(new_chapter)
