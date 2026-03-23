"""
Chapters routes for Story Forge API
"""
from fastapi import APIRouter, HTTPException, Request
from schemas import ChapterCreate, ChapterUpdate, ChapterResponse
from db_helpers import (
    get_chapter_with_tts_jobs, create_chapter, update_chapter,
    delete_chapter, recalculate_book_word_count
)

router = APIRouter()



@router.get("/{chapter_id}", response_model=ChapterResponse)
def get_chapter(request: Request, chapter_id: int):
    """Get a single chapter by ID."""
    require_auth(request)

    chapter = get_chapter_with_tts_jobs(chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    return ChapterResponse(
        id=chapter.id,
        book_id=chapter.book_id,
        title=chapter.title,
        content=chapter.content or "",
        order=chapter.order,
        status=chapter.status.value if hasattr(chapter.status, 'value') else chapter.status,
        notes=chapter.notes or "",
        word_count=chapter.word_count,
        created_at=str(chapter.created_at),
        updated_at=str(chapter.updated_at)
    )


@router.post("/book/{book_id}", response_model=ChapterResponse)
def create_chapter_route(request: Request, book_id: int, chapter: ChapterCreate):
    """Create a new chapter for a book."""
    require_auth(request)

    new_chapter = create_chapter(
        book_id=book_id,
        title=chapter.title,
        order=chapter.order
    )

    # Update word count
    recalculate_book_word_count(book_id)

    return ChapterResponse(
        id=new_chapter.id,
        book_id=new_chapter.book_id,
        title=new_chapter.title,
        content=new_chapter.content or "",
        order=new_chapter.order,
        status=new_chapter.status.value if hasattr(new_chapter.status, 'value') else new_chapter.status,
        notes=new_chapter.notes or "",
        word_count=new_chapter.word_count,
        created_at=str(new_chapter.created_at),
        updated_at=str(new_chapter.updated_at)
    )


@router.put("/{chapter_id}", response_model=ChapterResponse)
def update_chapter_route(request: Request, chapter_id: int, chapter: ChapterUpdate):
    """Update an existing chapter."""
    require_auth(request)

    # Build kwargs for update
    kwargs = {}
    if chapter.title is not None:
        kwargs["title"] = chapter.title
    if chapter.content is not None:
        kwargs["content"] = chapter.content
    if chapter.order is not None:
        kwargs["order"] = chapter.order
    if chapter.status is not None:
        kwargs["status"] = chapter.status.value
    if chapter.notes is not None:
        kwargs["notes"] = chapter.notes

    updated = update_chapter(chapter_id, **kwargs)
    if not updated:
        raise HTTPException(status_code=404, detail="Chapter not found")

    # Recalculate word count if content changed
    if chapter.content is not None:
        recalculate_book_word_count(updated.book_id)

    return ChapterResponse(
        id=updated.id,
        book_id=updated.book_id,
        title=updated.title,
        content=updated.content or "",
        order=updated.order,
        status=updated.status.value if hasattr(updated.status, 'value') else updated.status,
        notes=updated.notes or "",
        word_count=updated.word_count,
        created_at=str(updated.created_at),
        updated_at=str(updated.updated_at)
    )


@router.delete("/{chapter_id}")
def delete_chapter_route(request: Request, chapter_id: int):
    """Delete a chapter."""
    require_auth(request)

    # Get book_id before deleting for word count recalc
    chapter = get_chapter_with_tts_jobs(chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    success = delete_chapter(chapter_id)
    if not success:
        raise HTTPException(status_code=404, detail="Chapter not found")

    # Recalculate word count
    recalculate_book_word_count(chapter.book_id)

    return {"status": "deleted"}
