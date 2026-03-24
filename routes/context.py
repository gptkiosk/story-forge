"""
Context engine routes for Story Forge API.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

import context_engine
from .auth_utils import require_auth

router = APIRouter()


class ContextIngestRequest(BaseModel):
    title: str
    content_text: str
    source_filename: str | None = None


class ContextSummaryUpdateRequest(BaseModel):
    summary_text: str = ""
    characters: list[str] = []
    plot_threads: list[str] = []
    world_details: list[str] = []
    style_notes: list[str] = []


@router.get("/{book_id}")
def get_context(request: Request, book_id: int):
    require_auth(request)
    return context_engine.get_context_state(book_id)


@router.post("/{book_id}/ingest")
def ingest_context(request: Request, book_id: int, body: ContextIngestRequest):
    require_auth(request)
    try:
        return context_engine.queue_context_ingestion(
            book_id=book_id,
            title=body.title,
            content_text=body.content_text,
            source_filename=body.source_filename,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.put("/{book_id}/summary")
def update_summary(request: Request, book_id: int, body: ContextSummaryUpdateRequest):
    require_auth(request)
    try:
        return context_engine.update_context_summary(book_id, body.model_dump())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/{book_id}/export")
def export_summary(request: Request, book_id: int):
    require_auth(request)
    try:
        return context_engine.export_context_summary(book_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
