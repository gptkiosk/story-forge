"""
Pydantic schemas for Story Forge API
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class BookStatus(str, Enum):
    draft = "draft"
    in_progress = "in_progress"
    completed = "completed"
    archived = "archived"


class ChapterStatus(str, Enum):
    draft = "draft"
    revision = "revision"
    final = "final"


class BookBase(BaseModel):
    title: str
    author: Optional[str] = ""
    genre: Optional[str] = ""
    synopsis: Optional[str] = ""
    status: BookStatus = BookStatus.draft


class BookCreate(BookBase):
    pass


class BookUpdate(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    genre: Optional[str] = None
    synopsis: Optional[str] = None
    status: Optional[BookStatus] = None
    notes: Optional[str] = None
    cover_image: Optional[str] = None


class BookResponse(BookBase):
    id: int
    cover_image: Optional[str] = None
    notes: str = ""
    word_count: int = 0
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class BooksListResponse(BaseModel):
    books: list[BookResponse]
    total: int
    page: int
    per_page: int


class ChapterBase(BaseModel):
    title: str
    content: str = ""
    order: int = 0
    status: ChapterStatus = ChapterStatus.draft
    notes: str = ""


class ChapterCreate(ChapterBase):
    pass


class ChapterUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    order: Optional[int] = None
    status: Optional[ChapterStatus] = None
    notes: Optional[str] = None


class ChapterResponse(ChapterBase):
    id: int
    book_id: int
    word_count: int
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class TTSJobResponse(BaseModel):
    id: int
    chapter_id: int
    provider: str
    voice_id: str
    status: str
    audio_url: Optional[str] = None
    duration_seconds: Optional[float] = None
    created_at: str


class DashboardStats(BaseModel):
    book_count: int
    chapter_count: int
    total_words: int


class BackupResponse(BaseModel):
    id: str
    filename: str
    size: int
    created_at: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    avatar: Optional[str] = None
