"""Style + Genre Studio routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from db_helpers import get_book_by_id
from style_studio import get_style_profile, save_style_profile
from .auth_utils import require_auth

router = APIRouter()


class StyleStudioUpdateRequest(BaseModel):
    style_template_id: str | None = None
    genre_template_id: str | None = None
    style_markdown: str = ""
    genre_markdown: str = ""


@router.get("/{book_id}/style-studio")
def get_book_style_studio(request: Request, book_id: int):
    require_auth(request)
    book = get_book_by_id(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return get_style_profile(book_id)


@router.put("/{book_id}/style-studio")
def update_book_style_studio(request: Request, book_id: int, body: StyleStudioUpdateRequest):
    require_auth(request)
    book = get_book_by_id(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return save_style_profile(
        book_id,
        style_template_id=body.style_template_id,
        genre_template_id=body.genre_template_id,
        style_markdown=body.style_markdown,
        genre_markdown=body.genre_markdown,
    )
