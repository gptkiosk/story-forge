"""
Dashboard routes for Story Forge API
"""
from fastapi import APIRouter, Request
from schemas import DashboardStats
from db_helpers import get_book_count, get_chapter_count, get_total_word_count

router = APIRouter()


@router.get("/stats", response_model=DashboardStats)
def get_stats(request: Request):
    """Get dashboard statistics."""
    # Dashboard stats are public (no auth required for now)
    book_count = get_book_count()
    chapter_count = get_chapter_count()
    total_words = get_total_word_count()

    return DashboardStats(
        book_count=book_count,
        chapter_count=chapter_count,
        total_words=total_words
    )
