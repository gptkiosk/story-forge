"""
Tests for Story Forge database models and utilities.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db import (
    Base,
    Book,
    Chapter,
    TTSJob,
    BookStatus,
    TTSJobStatus,
    encryptor,
)


@pytest.fixture
def test_engine():
    """Create a test database engine."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class TestEncryption:
    """Test encryption utilities."""

    def test_encrypt_decrypt(self):
        """Test basic encryption/decryption."""
        original = "Hello, World!"
        encrypted = encryptor.encrypt(original)
        decrypted = encryptor.decrypt(encrypted)
        
        assert encrypted is not None
        assert encrypted != original
        assert decrypted == original

    def test_encrypt_none(self):
        """Test encrypting None returns None."""
        assert encryptor.encrypt(None) is None

    def test_decrypt_none(self):
        """Test decrypting None returns None."""
        assert encryptor.decrypt(None) is None


class TestBookModel:
    """Test Book model."""

    def test_create_book(self, test_engine):
        """Test creating a book."""
        book = Book(
            title="Test Book",
            description="A test book",
            author="Test Author",
            status=BookStatus.DRAFT,
        )
        test_engine.add(book)
        test_engine.commit()
        
        assert book.id is not None
        assert book.title == "Test Book"
        assert book.status == BookStatus.DRAFT

    def test_book_with_notes(self, test_engine):
        """Test encrypted notes field."""
        book = Book(
            title="Secret Book",
            notes="These are secret notes!",
        )
        test_engine.add(book)
        test_engine.commit()
        
        # Refresh to get from DB
        test_engine.refresh(book)
        
        # Notes should be encrypted in the DB
        assert book.notes_encrypted is not None
        assert book.notes_encrypted != book.notes
        
        # But accessible via property
        assert book.notes == "These are secret notes!"


class TestChapterModel:
    """Test Chapter model."""

    def test_create_chapter(self, test_engine):
        """Test creating a chapter."""
        book = Book(title="Test Book")
        test_engine.add(book)
        test_engine.commit()
        
        chapter = Chapter(
            book_id=book.id,
            title="Chapter 1",
            content="Once upon a time...",
            order=1,
        )
        test_engine.add(chapter)
        test_engine.commit()
        
        assert chapter.id is not None
        assert chapter.book_id == book.id
        assert chapter.order == 1

    def test_chapter_content_backup(self, test_engine):
        """Test encrypted content backup."""
        book = Book(title="Test Book")
        test_engine.add(book)
        test_engine.commit()
        
        chapter = Chapter(
            book_id=book.id,
            title="Chapter 1",
            content="Original content",
            order=1,
            content_backup="Backup content",
        )
        test_engine.add(chapter)
        test_engine.commit()
        
        test_engine.refresh(chapter)
        
        # Backup should be encrypted
        assert chapter.content_backup_encrypted is not None
        assert chapter.content_backup == "Backup content"


class TestTTSJobModel:
    """Test TTSJob model."""

    def test_create_tts_job(self, test_engine):
        """Test creating a TTS job."""
        book = Book(title="Test Book")
        test_engine.add(book)
        test_engine.commit()
        
        chapter = Chapter(
            book_id=book.id,
            title="Chapter 1",
            content="Content",
            order=1,
        )
        test_engine.add(chapter)
        test_engine.commit()
        
        job = TTSJob(
            chapter_id=chapter.id,
            voice_id="voice_123",
            model="speech-02-hd",
            status=TTSJobStatus.PENDING,
        )
        test_engine.add(job)
        test_engine.commit()
        
        assert job.id is not None
        assert job.chapter_id == chapter.id
        assert job.status == TTSJobStatus.PENDING


class TestRelationships:
    """Test model relationships."""

    def test_book_chapters_relationship(self, test_engine):
        """Test book has many chapters."""
        book = Book(title="Test Book")
        test_engine.add(book)
        test_engine.commit()
        
        chapter1 = Chapter(book_id=book.id, title="Ch 1", order=1)
        chapter2 = Chapter(book_id=book.id, title="Ch 2", order=2)
        test_engine.add_all([chapter1, chapter2])
        test_engine.commit()
        
        # Query book with chapters
        book = test_engine.query(Book).filter(Book.id == book.id).first()
        
        assert len(book.chapters) == 2
        assert book.chapters[0].title == "Ch 1"
        assert book.chapters[1].title == "Ch 2"

    def test_chapter_tts_jobs_relationship(self, test_engine):
        """Test chapter has many TTS jobs."""
        book = Book(title="Test Book")
        test_engine.add(book)
        test_engine.commit()
        
        chapter = Chapter(book_id=book.id, title="Ch 1", order=1, content="Test")
        test_engine.add(chapter)
        test_engine.commit()
        
        job1 = TTSJob(chapter_id=chapter.id, status=TTSJobStatus.PENDING)
        job2 = TTSJob(chapter_id=chapter.id, status=TTSJobStatus.COMPLETED)
        test_engine.add_all([job1, job2])
        test_engine.commit()
        
        # Query chapter with jobs
        chapter = test_engine.query(Chapter).filter(Chapter.id == chapter.id).first()
        
        assert len(chapter.tts_jobs) == 2

    def test_cascade_delete(self, test_engine):
        """Test cascading deletes work."""
        book = Book(title="Test Book")
        test_engine.add(book)
        test_engine.commit()
        
        chapter = Chapter(book_id=book.id, title="Ch 1", order=1, content="Test")
        test_engine.add(chapter)
        test_engine.commit()
        
        job = TTSJob(chapter_id=chapter.id, status=TTSJobStatus.PENDING)
        test_engine.add(job)
        test_engine.commit()
        
        # Delete book - should cascade delete chapter and job
        test_engine.delete(book)
        test_engine.commit()
        
        assert test_engine.query(Book).filter(Book.id == book.id).first() is None
        assert test_engine.query(Chapter).filter(Chapter.id == chapter.id).first() is None
        assert test_engine.query(TTSJob).filter(TTSJob.id == job.id).first() is None


class TestDatabaseInit:
    """Test database initialization."""

    def test_init_db_creates_tables(self, tmp_path):
        """Test init_db creates all tables."""
        from db import Base
        
        # Use a temp database
        db_path = tmp_path / "test.db"
        test_engine = create_engine(f"sqlite:///{db_path}")
        
        Base.metadata.create_all(bind=test_engine)
        
        # Check tables exist
        from sqlalchemy import inspect
        inspector = inspect(test_engine)
        tables = inspector.get_table_names()
        
        assert "books" in tables
        assert "chapters" in tables
        assert "tts_jobs" in tables


def test_get_user_preferences_returns_existing_row(test_engine):
    from db import UserPreference

    prefs = UserPreference(user_id=1, theme='dark')
    test_engine.add(prefs)
    test_engine.commit()

    stored = test_engine.query(UserPreference).filter(UserPreference.user_id == 1).first()
    assert stored is not None
    assert stored.theme == 'dark'
