"""
Database helper functions for Story Forge API
These functions wrap the database session management for cleaner API routes.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import sqlalchemy
from sqlalchemy.orm import joinedload
import db
from db import Book, Chapter, BookStatus, TTSJob, TTSJobStatus, CharacterVoice, get_session


ITEMS_PER_PAGE = 10


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
        chapters = db.query(Chapter).filter(
            Chapter.book_id == book_id
        ).order_by(Chapter.order).all()
        return chapters
    finally:
        db.close()


def get_chapter_with_tts_jobs(chapter_id: int) -> Chapter | None:
    """Get a chapter with its TTS jobs loaded."""
    db = get_session()
    try:
        return db.query(Chapter).options(
            joinedload(Chapter.tts_jobs)
        ).filter(Chapter.id == chapter_id).first()
    finally:
        db.close()


def create_chapter(book_id: int, title: str, order: int = 0) -> Chapter:
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
            if key == "status" and isinstance(value, str):
                value = BookStatus(value)
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
    """Recalculate and update a book's word count based on its chapters."""
    db = get_session()
    try:
        book = db.query(Book).filter(Book.id == book_id).first()
        if not book:
            return 0

        chapters = db.query(Chapter).filter(Chapter.book_id == book_id).all()
        total_words = sum(c.word_count for c in chapters)
        book.word_count = total_words
        db.commit()
        return total_words
    finally:
        db.close()


# TTS Job helpers
def get_tts_job(job_id: int) -> TTSJob | None:
    """Get a TTS job by ID."""
    db = get_session()
    try:
        return db.query(TTSJob).filter(TTSJob.id == job_id).first()
    finally:
        db.close()


def get_tts_jobs(chapter_id: int = None) -> list[TTSJob]:
    """Get TTS jobs, optionally filtered by chapter."""
    db = get_session()
    try:
        query = db.query(TTSJob)
        if chapter_id:
            query = query.filter(TTSJob.chapter_id == chapter_id)
        return query.order_by(TTSJob.created_at.desc()).all()
    finally:
        db.close()


def delete_tts_job(job_id: int) -> bool:
    """Delete a TTS job."""
    db = get_session()
    try:
        job = db.query(TTSJob).filter(TTSJob.id == job_id).first()
        if not job:
            return False
        db.delete(job)
        db.commit()
        return True
    finally:
        db.close()
