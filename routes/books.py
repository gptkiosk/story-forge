"""
Books routes for Story Forge API
"""
from fastapi import APIRouter, HTTPException, Request
from schemas import BookCreate, BookUpdate, BookResponse, BooksListResponse, ChapterCreate
from db_helpers import (
    get_all_books, get_book_by_id, create_book, update_book, delete_book,
    get_chapters_for_book, create_chapter, recalculate_book_word_count
)
from .auth_utils import require_auth

ITEMS_PER_PAGE = 12

router = APIRouter()


@router.get("", response_model=BooksListResponse)
def list_books(request: Request, page: int = 1, search: str = "", status: str = ""):
    """Get all books."""
    require_auth(request)

    books, total = get_all_books(
        search=search,
        status_filter=status,
        page=page
    )

    return BooksListResponse(
        books=[BookResponse(**b.__dict__) for b in books],
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

    return BookResponse(**book.__dict__)


@router.post("", response_model=BookResponse)
def create_book_route(request: Request, book: BookCreate):
    """Create a new book."""
    require_auth(request)

    new_book = create_book(
        title=book.title,
        description=book.synopsis,
        author=book.author,
        status=book.status.value if book.status else "draft"
    )

    return BookResponse(**new_book.__dict__)


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
    if book.genre is not None:
        kwargs["genre"] = book.genre
    if book.synopsis is not None:
        kwargs["synopsis"] = book.synopsis
    if book.status is not None:
        kwargs["status"] = book.status.value
    if book.notes is not None:
        kwargs["notes"] = book.notes
    if book.cover_image is not None:
        kwargs["cover_image"] = book.cover_image

    updated = update_book(book_id, **kwargs)
    if not updated:
        raise HTTPException(status_code=404, detail="Book not found")

    return BookResponse(**updated.__dict__)


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
    return [{
        "id": c.id,
        "title": c.title,
        "order": c.order,
        "word_count": c.word_count,
        "status": c.status.value if hasattr(c.status, 'value') else c.status,
        "created_at": c.created_at,
        "updated_at": c.updated_at
    } for c in chapters]


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

    return {
        "id": new_chapter.id,
        "title": new_chapter.title,
        "order": new_chapter.order,
        "word_count": new_chapter.word_count,
        "status": new_chapter.status.value if hasattr(new_chapter.status, 'value') else new_chapter.status,
        "created_at": str(new_chapter.created_at),
        "updated_at": str(new_chapter.updated_at)
    }
