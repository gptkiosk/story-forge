"""
Database module for Story Forge.
Provides SQLAlchemy models, session factory, and encryption utilities.
"""

import keyring
from pathlib import Path
from typing import Generator

from sqlalchemy import text
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Float,
    ForeignKey,
    Enum as SQLEnum,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session
from sqlalchemy.sql import func
from cryptography.fernet import Fernet
import enum

# =============================================================================
# Configuration
# =============================================================================

DATA_DIR = Path("./data")
DATA_DIR.mkdir(exist_ok=True)

DATABASE_PATH = DATA_DIR / "story_forge.db"
KEYCHAIN_SERVICE = "story-forge"
KEYCHAIN_USERNAME = "db-encryption-key"

# Database URL
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"


# =============================================================================
# Encryption Utilities
# =============================================================================

def _get_or_create_encryption_key() -> str:
    """Get encryption key from keychain or create new one."""
    key = keyring.get_password(KEYCHAIN_SERVICE, KEYCHAIN_USERNAME)
    if key is None:
        key = Fernet.generate_key().decode()
        keyring.set_password(KEYCHAIN_SERVICE, KEYCHAIN_USERNAME, key)
    return key


class DatabaseEncryptor:
    """Handles encryption/decryption of sensitive fields."""

    def __init__(self):
        self._cipher: Fernet | None = None

    @property
    def cipher(self) -> Fernet:
        if self._cipher is None:
            key = _get_or_create_encryption_key()
            self._cipher = Fernet(key.encode())
        return self._cipher

    def encrypt(self, plaintext: str | None) -> str | None:
        """Encrypt plaintext string."""
        if plaintext is None:
            return None
        return self.cipher.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str | None) -> str | None:
        """Decrypt ciphertext string."""
        if ciphertext is None:
            return None
        return self.cipher.decrypt(ciphertext.encode()).decode()


# Global encryptor instance
encryptor = DatabaseEncryptor()


# =============================================================================
# SQLAlchemy Setup
# =============================================================================

# Create engine with WAL mode
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

# Enable WAL mode
with engine.connect() as conn:
    conn.execute(text("PRAGMA journal_mode=WAL"))
    conn.commit()

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# Base class for models
Base = declarative_base()


# =============================================================================
# ORM Models
# =============================================================================


class BookStatus(enum.Enum):
    """Book status enumeration."""
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class TTSJobStatus(enum.Enum):
    """TTS job status enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Book(Base):
    """Book model - represents a book project."""

    __tablename__ = "books"

    id = Column(Integer, primary_key=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    author = Column(String(250), nullable=True)
    
    # Encrypted fields for sensitive data
    notes_encrypted = Column(Text, nullable=True)
    
    # Metadata
    status = Column(
        SQLEnum(BookStatus),
        default=BookStatus.DRAFT,
        nullable=False,
    )
    word_count = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    chapters = relationship(
        "Chapter",
        back_populates="book",
        cascade="all, delete-orphan",
        order_by="Chapter.order",
    )

    @property
    def notes(self) -> str | None:
        """Decrypt and return notes."""
        return encryptor.decrypt(self.notes_encrypted)

    @notes.setter
    def notes(self, value: str | None):
        """Encrypt and store notes."""
        self.notes_encrypted = encryptor.encrypt(value)


class Chapter(Base):
    """Chapter model - represents a chapter within a book."""

    __tablename__ = "chapters"

    id = Column(Integer, primary_key=True)
    book_id = Column(
        Integer,
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=True)
    order = Column(Integer, nullable=False)
    
    # Encrypted content for draft/backup
    content_backup_encrypted = Column(Text, nullable=True)
    
    # Metadata
    word_count = Column(Integer, default=0)
    is_published = Column(Integer, default=0)  # Boolean as int
    
    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    book = relationship("Book", back_populates="chapters")
    tts_jobs = relationship(
        "TTSJob",
        back_populates="chapter",
        cascade="all, delete-orphan",
    )

    @property
    def content_backup(self) -> str | None:
        """Decrypt and return content backup."""
        return encryptor.decrypt(self.content_backup_encrypted)

    @content_backup.setter
    def content_backup(self, value: str | None):
        """Encrypt and store content backup."""
        self.content_backup_encrypted = encryptor.encrypt(value)


class TTSProviderType(enum.Enum):
    """TTS provider type enumeration."""
    MINIMAX = "minimax"
    ELEVENLABS = "elevenlabs"


class TTSJob(Base):
    """TTSJob model - represents a text-to-speech generation job."""

    __tablename__ = "tts_jobs"

    id = Column(Integer, primary_key=True)
    chapter_id = Column(
        Integer,
        ForeignKey("chapters.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    # Provider selection
    provider = Column(
        SQLEnum(TTSProviderType),
        default=TTSProviderType.MINIMAX,
        nullable=False,
    )
    
    # Job details
    voice_id = Column(String(100), nullable=True)
    model = Column(String(50), default="speech-02-hd")
    
    # Status tracking
    status = Column(
        SQLEnum(TTSJobStatus),
        default=TTSJobStatus.PENDING,
        nullable=False,
    )
    error_message = Column(Text, nullable=True)
    
    # Output
    audio_path = Column(String(1000), nullable=True)
    audio_duration = Column(Integer, nullable=True)  # seconds
    
    # Pricing
    cost_tokens = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    chapter = relationship("Chapter", back_populates="tts_jobs")


class CharacterVoice(Base):
    """CharacterVoice model - stores voice IDs for each TTS provider."""

    __tablename__ = "character_voices"

    id = Column(Integer, primary_key=True)
    book_id = Column(
        Integer,
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    # Character identifier
    character_name = Column(String(255), nullable=False)
    
    # Voice IDs for each provider
    minimax_voice_id = Column(String(100), nullable=True)
    elevenlabs_voice_id = Column(String(100), nullable=True)
    
    # Voice metadata
    voice_name = Column(String(255), nullable=True)
    gender = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)


class User(Base):
    """User model - represents an authenticated user via OAuth."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    
    # OAuth provider info
    provider = Column(String(50), nullable=False, default="google")
    provider_user_id = Column(String(255), nullable=False, unique=True)
    
    # User info from OAuth
    email = Column(String(255), nullable=False)
    name = Column(String(255), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    
    # Internal user identifier for single-user context
    internal_user_id = Column(String(100), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    last_login_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    preferences = relationship(
        "UserPreference",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )


class UserPreference(Base):
    """UserPreference model - stores UI preferences per user."""

    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    
    # Theme settings
    theme = Column(String(20), default="light")  # "light" or "dark"
    
    # Dashboard preferences
    dashboard_layout = Column(String(20), default="default")  # "default", "compact"
    
    # Chapter editor preferences
    editor_font_size = Column(Integer, default=16)  # 12-24
    editor_line_height = Column(Float, default=1.6)  # 1.2-2.0
    
    # Voice studio preferences
    default_tts_provider = Column(String(20), default="minimax")
    
    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="preferences")


# =============================================================================
# Session Management
# =============================================================================

def get_db() -> Generator[Session, None, None]:
    """
    Dependency for FastAPI to get database session.
    Yields a session and ensures it's closed after use.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session() -> Session:
    """
    Get a new database session.
    Use this for non-FastAPI contexts (e.g., background jobs, scripts).
    Remember to close the session when done.
    """
    return SessionLocal()


# =============================================================================
# Database Initialization
# =============================================================================

def init_db() -> None:
    """Initialize database - create all tables."""
    Base.metadata.create_all(bind=engine)


def drop_db() -> None:
    """Drop all tables - use with caution!"""
    Base.metadata.drop_all(bind=engine)


# =============================================================================
# Utility Functions
# =============================================================================

def get_book_with_chapters(book_id: int, session: Session) -> Book | None:
    """Get a book with all its chapters loaded."""
    return session.query(Book).filter(Book.id == book_id).first()


def get_chapter_with_tts_jobs(chapter_id: int, session: Session) -> Chapter | None:
    """Get a chapter with all its TTS jobs loaded."""
    return session.query(Chapter).filter(Chapter.id == chapter_id).first()
