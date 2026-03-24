"""
PostgreSQL-backed context engine persistence for Story Forge.
"""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy import JSON, Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.sql import func

load_dotenv()

ContextBase = declarative_base()


class ContextIngestionJob(ContextBase):
    __tablename__ = "context_ingestion_jobs"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    source_type = Column(String(50), nullable=False, default="manuscript_text")
    source_title = Column(String(255), nullable=True)
    source_filename = Column(String(255), nullable=True)
    status = Column(String(50), nullable=False, default="queued")
    progress_message = Column(String(255), nullable=True)
    progress_percent = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)


class ContextDocument(ContextBase):
    __tablename__ = "context_documents"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    source_type = Column(String(50), nullable=False, default="manuscript_text")
    source_filename = Column(String(255), nullable=True)
    content_text = Column(Text, nullable=False)
    word_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)


class ContextSummary(ContextBase):
    __tablename__ = "context_summaries"

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, nullable=False, unique=True, index=True)
    summary_text = Column(Text, nullable=False, default="")
    characters = Column(JSON, nullable=False, default=list)
    plot_threads = Column(JSON, nullable=False, default=list)
    world_details = Column(JSON, nullable=False, default=list)
    style_notes = Column(JSON, nullable=False, default=list)
    source_document_count = Column(Integer, nullable=False, default=0)
    source_word_count = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)


def get_context_database_url() -> str | None:
    explicit_url = os.environ.get("STORY_FORGE_CONTEXT_POSTGRES_URL")
    if explicit_url:
        return explicit_url

    host = os.environ.get("POSTGRES_HOST")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db_name = os.environ.get("POSTGRES_DB")
    user = os.environ.get("POSTGRES_USER")
    password = os.environ.get("POSTGRES_PASSWORD")
    if host and db_name and user and password:
        return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db_name}"

    return None


@lru_cache(maxsize=1)
def get_context_engine():
    db_url = get_context_database_url()
    if not db_url:
        return None
    return create_engine(db_url, pool_pre_ping=True, future=True)


@lru_cache(maxsize=1)
def get_context_session_factory():
    engine = get_context_engine()
    if engine is None:
        return None
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def context_db_enabled() -> bool:
    return get_context_engine() is not None


def init_context_db() -> bool:
    engine = get_context_engine()
    if engine is None:
        return False
    ContextBase.metadata.create_all(bind=engine)
    return True


def get_context_session() -> Session:
    session_factory = get_context_session_factory()
    if session_factory is None:
        raise RuntimeError("Context database is not configured")
    return session_factory()


def reset_context_db_state():
    get_context_engine.cache_clear()
    get_context_session_factory.cache_clear()
