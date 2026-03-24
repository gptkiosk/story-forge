"""
Chapters routes for Story Forge API
"""
from fastapi import APIRouter, HTTPException, Request
from schemas import ChapterCreate, ChapterUpdate, ChapterResponse, to_chapter_response
from db_helpers import (
    get_chapter_with_tts_jobs, create_chapter, update_chapter,
    delete_chapter, recalculate_book_word_count
)
from .auth_utils import require_auth

router = APIRouter()


@router.get("/{chapter_id}", response_model=ChapterResponse)
def get_chapter(request: Request, chapter_id: int):
    """Get a single chapter by ID."""
    require_auth(request)

    chapter = get_chapter_with_tts_jobs(chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    return to_chapter_response(chapter)


@router.post("/book/{book_id}", response_model=ChapterResponse)
def create_chapter_route(request: Request, book_id: int, chapter: ChapterCreate):
    """Create a new chapter for a book."""
    require_auth(request)

    new_chapter = create_chapter(
        book_id=book_id,
        title=chapter.title,
        order=chapter.order
    )

    recalculate_book_word_count(book_id)
    return to_chapter_response(new_chapter)


@router.put("/{chapter_id}", response_model=ChapterResponse)
def update_chapter_route(request: Request, chapter_id: int, chapter: ChapterUpdate):
    """Update an existing chapter."""
    require_auth(request)

    kwargs = {}
    if chapter.title is not None:
        kwargs["title"] = chapter.title
    if chapter.content is not None:
        kwargs["content"] = chapter.content
        # Auto-calculate word count from content
        kwargs["word_count"] = len(chapter.content.split()) if chapter.content.strip() else 0
    if chapter.order is not None:
        kwargs["order"] = chapter.order

    updated = update_chapter(chapter_id, **kwargs)
    if not updated:
        raise HTTPException(status_code=404, detail="Chapter not found")

    if chapter.content is not None:
        recalculate_book_word_count(updated.book_id)

    return to_chapter_response(updated)


@router.delete("/{chapter_id}")
def delete_chapter_route(request: Request, chapter_id: int):
    """Delete a chapter."""
    require_auth(request)

    chapter = get_chapter_with_tts_jobs(chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    book_id = chapter.book_id
    success = delete_chapter(chapter_id)
    if not success:
        raise HTTPException(status_code=404, detail="Chapter not found")

    recalculate_book_word_count(book_id)
    return {"status": "deleted"}
