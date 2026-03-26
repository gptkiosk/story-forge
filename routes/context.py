"""
Context engine routes for Story Forge API.
"""

from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from docx import Document

import context_engine
from .auth_utils import require_auth

router = APIRouter()
SUPPORTED_CONTEXT_EXTENSIONS = {".txt", ".md", ".docx"}
MAX_CONTEXT_UPLOAD_BYTES = 8 * 1024 * 1024


class ContextIngestRequest(BaseModel):
    title: str
    content_text: str
    source_filename: str | None = None
    refine_with_libby: bool = False


class ContextSummaryUpdateRequest(BaseModel):
    summary_text: str = ""
    characters: list[str] = []
    plot_threads: list[str] = []
    world_details: list[str] = []
    style_notes: list[str] = []


def _extract_uploaded_context_text(upload: UploadFile, file_bytes: bytes) -> tuple[str, str]:
    filename = upload.filename or "context-upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_CONTEXT_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported context file type. Use .txt, .md, or .docx.",
        )

    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded context file is empty.")

    if suffix == ".docx":
        try:
            document = Document(BytesIO(file_bytes))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Unable to read DOCX context file: {exc}")
        text = "\n\n".join(paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip())
    else:
        try:
            text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = file_bytes.decode("utf-8", errors="replace")

    cleaned = text.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Uploaded context file does not contain readable text.")

    return filename, cleaned


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
            refine_with_libby=body.refine_with_libby,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/{book_id}/ingest-file")
async def ingest_context_file(
    request: Request,
    book_id: int,
    title: str = Form(...),
    refine_with_libby: bool = Form(False),
    upload: UploadFile = File(...),
):
    require_auth(request)
    file_bytes = await upload.read()
    if len(file_bytes) > MAX_CONTEXT_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail="Context file is too large. Keep uploads under 8 MB for reliable parsing.",
        )

    source_filename, content_text = _extract_uploaded_context_text(upload, file_bytes)

    try:
        return context_engine.queue_context_ingestion(
            book_id=book_id,
            title=title.strip() or source_filename,
            content_text=content_text,
            source_filename=source_filename,
            refine_with_libby=refine_with_libby,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/{book_id}/refine")
def refine_context(request: Request, book_id: int):
    require_auth(request)
    try:
        return context_engine.queue_context_refinement(book_id)
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
