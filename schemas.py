"""
Pydantic schemas for API responses.
Breaks circular SQLAlchemy relationships for JSON serialization.
"""

from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional


# =============================================================================
# User Schemas
# =============================================================================

class UserBase(BaseModel):
    email: str
    name: Optional[str] = None
    avatar_url: Optional[str] = None


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    provider: str
    created_at: datetime


# =============================================================================
# Book Schemas (NO circular back-refs)
# =============================================================================

class ChapterResponse(BaseModel):
    """Chapter schema WITHOUT book back-reference."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    book_id: int
    title: str
    content: Optional[str] = None
    order: int
    word_count: int
    is_published: int
    created_at: datetime
    updated_at: Optional[datetime] = None


class TTSJobResponse(BaseModel):
    """TTS job schema WITHOUT chapter back-reference."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    chapter_id: int
    provider: str
    voice_id: Optional[str] = None
    model: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    audio_path: Optional[str] = None
    audio_duration: Optional[int] = None
    cost_tokens: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class BookBase(BaseModel):
    title: str
    description: Optional[str] = None
    author: Optional[str] = None
    status: str = "draft"


class BookResponse(BookBase):
    """Book schema WITH chapters list (but chapters don't have book)."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    word_count: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    chapters: list[ChapterResponse] = []


class BookListResponse(BaseModel):
    """Simplified book for list views."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    title: str
    description: Optional[str] = None
    author: Optional[str] = None
    status: str
    word_count: int
    chapter_count: int
    created_at: datetime


class BookCreate(BookBase):
    pass


class BookUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    author: Optional[str] = None
    status: Optional[str] = None


# =============================================================================
# Chapter Schemas
# =============================================================================

class ChapterBase(BaseModel):
    title: str
    content: Optional[str] = None
    order: int
    word_count: int = 0


class ChapterResponseWithTTS(ChapterResponse):
    """Chapter with TTS jobs."""
    model_config = ConfigDict(from_attributes=True)
    
    tts_jobs: list[TTSJobResponse] = []


class ChapterCreate(ChapterBase):
    book_id: int


class ChapterUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    order: Optional[int] = None
    word_count: Optional[int] = None


# =============================================================================
# TTS Schemas
# =============================================================================

class TTSGenerateRequest(BaseModel):
    chapter_id: int
    provider: str = "minimax"
    voice_id: Optional[str] = None
    model: Optional[str] = "speech-02-hd"


class TTSJobCreate(BaseModel):
    chapter_id: int
    provider: str
    voice_id: Optional[str] = None
    model: Optional[str] = None


# =============================================================================
# Backup Schemas
# =============================================================================

class BackupResponse(BaseModel):
    path: str
    size: int
    created_at: str
    checksum: Optional[str] = None
    backup_type: str = "local"


class BackupListResponse(BaseModel):
    backups: list[BackupResponse]
    count: int


# =============================================================================
# Stats Schemas
# =============================================================================

class DashboardStats(BaseModel):
    book_count: int
    chapter_count: int
    total_words: int
    recent_books: list[BookListResponse] = []


# =============================================================================
# Helper Functions for Conversion
# =============================================================================

def to_book_list_item(book) -> BookListResponse:
    """Convert SQLAlchemy Book to BookListResponse for list display."""
    return BookListResponse(
        id=book.id,
        title=book.title,
        description=book.description,
        author=book.author,
        status=book.status.value if hasattr(book.status, 'value') else str(book.status),
        word_count=book.word_count,
        chapter_count=len(book.chapters) if book.chapters else 0,
        created_at=book.created_at,
    )


def to_chapter_response(chapter) -> ChapterResponse:
    """Convert SQLAlchemy Chapter to ChapterResponse."""
    return ChapterResponse(
        id=chapter.id,
        book_id=chapter.book_id,
        title=chapter.title,
        content=chapter.content,
        order=chapter.order,
        word_count=chapter.word_count,
        is_published=chapter.is_published,
        created_at=chapter.created_at,
        updated_at=chapter.updated_at,
    )


def to_chapter_response_with_tts(chapter) -> ChapterResponseWithTTS:
    """Convert SQLAlchemy Chapter to ChapterResponse with TTS jobs."""
    tts_jobs = [to_tts_job_response(tj) for tj in chapter.tts_jobs]
    return ChapterResponseWithTTS(
        id=chapter.id,
        book_id=chapter.book_id,
        title=chapter.title,
        content=chapter.content,
        order=chapter.order,
        word_count=chapter.word_count,
        is_published=chapter.is_published,
        created_at=chapter.created_at,
        updated_at=chapter.updated_at,
        tts_jobs=tts_jobs,
    )


def to_tts_job_response(tts_job) -> TTSJobResponse:
    """Convert SQLAlchemy TTSJob to TTSJobResponse."""
    return TTSJobResponse(
        id=tts_job.id,
        chapter_id=tts_job.chapter_id,
        provider=tts_job.provider.value if hasattr(tts_job.provider, 'value') else str(tts_job.provider),
        voice_id=tts_job.voice_id,
        model=tts_job.model,
        status=tts_job.status.value if hasattr(tts_job.status, 'value') else str(tts_job.status),
        error_message=tts_job.error_message,
        audio_path=tts_job.audio_path,
        audio_duration=tts_job.audio_duration,
        cost_tokens=tts_job.cost_tokens,
        created_at=tts_job.created_at,
        completed_at=tts_job.completed_at,
    )
