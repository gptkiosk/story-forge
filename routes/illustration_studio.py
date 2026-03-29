"""Illustration Studio routes."""

from __future__ import annotations

import base64
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ai_providers import ai_provider_manager
from context_engine import build_runtime_context_packet
from db_helpers import get_book_by_id
from integrations import get_illustration_settings, get_openrouter_settings
from illustration_studio import (
    build_illustration_context,
    create_asset_filename,
    get_asset_path,
    get_illustration_profile,
    list_generated_assets,
    record_generated_asset,
    save_illustration_profile,
)
from style_studio import build_style_context
from .auth_utils import require_auth

router = APIRouter()


class IllustrationStudioUpdateRequest(BaseModel):
    style_template_id: str | None = None
    genre_template_id: str | None = None
    style_markdown: str = ""
    genre_markdown: str = ""
    include_in_epub: bool = False
    epub_layout: str = "full_width"
    preferred_aspect_ratio: str = "4:3"


class IllustrationGenerateRequest(BaseModel):
    chapter_id: int | None = None
    chapter_title: str | None = None
    chapter_excerpt: str = ""
    scene_label: str = "Chapter illustration"
    scene_prompt: str


def _build_prompt_fallback(
    *,
    book_title: str,
    chapter_title: str | None,
    scene_prompt: str,
    style_studio: dict,
    illustration_studio: dict,
) -> dict:
    combined_guidance = illustration_studio.get("combined_guidance") or style_studio.get("combined_guidance") or ""
    chapter_line = f"Chapter: {chapter_title}." if chapter_title else ""
    prompt = (
        f"Create a polished book illustration for {book_title}. {chapter_line} "
        f"Scene: {scene_prompt.strip()} "
        f"Visual guidance: {combined_guidance.strip()} "
        "Keep the composition readable for EPUB layout, preserve continuity, and avoid photorealistic or muddy results."
    ).strip()
    return {
        "prompt": prompt,
        "caption": chapter_title or book_title,
        "negative_prompt": "blurry, low detail, unreadable composition, modern UI elements, watermarks, text artifacts",
    }


async def _generate_with_openrouter(*, prompt: str, aspect_ratio: str) -> bytes:
    settings = get_illustration_settings()
    openrouter_settings = get_openrouter_settings()
    api_key = openrouter_settings.get("api_key", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="OpenRouter API key is not configured for Illustration Studio.")

    provider_settings = settings.get("openrouter", {})
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if openrouter_settings.get("site_url"):
        headers["HTTP-Referer"] = openrouter_settings["site_url"]
    if openrouter_settings.get("app_name"):
        headers["X-Title"] = openrouter_settings["app_name"]

    payload = {
        "model": provider_settings.get("model"),
        "prompt": prompt,
        "size": provider_settings.get("size", "1536x1024"),
        "n": 1,
        "response_format": "b64_json",
        "background": provider_settings.get("background", "opaque"),
    }
    if aspect_ratio:
        payload["aspect_ratio"] = aspect_ratio

    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(
            f"{openrouter_settings['base_url'].rstrip('/')}/images/generations",
            headers=headers,
            json=payload,
        )
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"OpenRouter image generation failed: {response.status_code} - {response.text}")
    data = response.json()
    items = data.get("data") or []
    if not items:
        raise HTTPException(status_code=502, detail="OpenRouter returned no illustration payload.")
    first = items[0]
    if first.get("b64_json"):
        return base64.b64decode(first["b64_json"])
    if first.get("url"):
        async with httpx.AsyncClient(timeout=180.0) as client:
            image_response = await client.get(first["url"])
        image_response.raise_for_status()
        return image_response.content
    raise HTTPException(status_code=502, detail="OpenRouter illustration response did not include image data.")


@router.get("/{book_id}/illustration-studio")
def get_book_illustration_studio(request: Request, book_id: int):
    require_auth(request)
    book = get_book_by_id(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return get_illustration_profile(book_id)


@router.put("/{book_id}/illustration-studio")
def update_book_illustration_studio(request: Request, book_id: int, body: IllustrationStudioUpdateRequest):
    require_auth(request)
    book = get_book_by_id(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return save_illustration_profile(
        book_id,
        style_template_id=body.style_template_id,
        genre_template_id=body.genre_template_id,
        style_markdown=body.style_markdown,
        genre_markdown=body.genre_markdown,
        include_in_epub=body.include_in_epub,
        epub_layout=body.epub_layout,
        preferred_aspect_ratio=body.preferred_aspect_ratio,
    )


@router.get("/{book_id}/illustration-studio/generated")
def get_generated_illustrations(request: Request, book_id: int):
    require_auth(request)
    book = get_book_by_id(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return {"assets": list_generated_assets(book_id)}


@router.post("/{book_id}/illustration-studio/generate")
async def generate_illustration(request: Request, book_id: int, body: IllustrationGenerateRequest):
    require_auth(request)
    book = get_book_by_id(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    if not body.scene_prompt.strip():
        raise HTTPException(status_code=400, detail="Add a scene prompt before generating an illustration.")

    try:
        story_context = build_runtime_context_packet(book_id)
    except Exception:
        story_context = {
            "summary_text": "",
            "characters": [],
            "plot_threads": [],
            "world_details": [],
            "style_notes": [],
            "source_document_count": 0,
            "source_word_count": 0,
        }
    style_context = build_style_context(book_id)
    illustration_context = build_illustration_context(book_id)
    illustration_settings = get_illustration_settings()
    prompt_provider = "openrouter" if illustration_settings.get("prompt_refiner") == "openrouter" else None
    prompt_result = await ai_provider_manager.build_illustration_prompt(
        book_title=book.title,
        chapter_title=body.chapter_title,
        chapter_excerpt=body.chapter_excerpt,
        scene_prompt=body.scene_prompt.strip(),
        story_context=story_context,
        style_studio=style_context,
        illustration_studio=illustration_context,
        provider_override=prompt_provider,
    )
    if prompt_result.get("success"):
        final_prompt = prompt_result.get("prompt") or body.scene_prompt.strip()
        caption = prompt_result.get("caption") or (body.chapter_title or book.title)
    else:
        fallback = _build_prompt_fallback(
            book_title=book.title,
            chapter_title=body.chapter_title,
            scene_prompt=body.scene_prompt.strip(),
            style_studio=style_context,
            illustration_studio=illustration_context,
        )
        final_prompt = fallback["prompt"]
        caption = fallback["caption"]

    image_bytes = await _generate_with_openrouter(
        prompt=final_prompt,
        aspect_ratio=illustration_context.get("preferred_aspect_ratio") or "4:3",
    )
    filename = create_asset_filename()
    asset = record_generated_asset(
        book_id,
        filename=filename,
        image_bytes=image_bytes,
        chapter_id=body.chapter_id,
        chapter_title=body.chapter_title,
        scene_label=body.scene_label.strip() or "Chapter illustration",
        scene_prompt=body.scene_prompt.strip(),
        final_prompt=final_prompt,
        caption=caption,
        provider=illustration_settings.get("provider", "openrouter"),
        model=illustration_settings.get("openrouter", {}).get("model", ""),
        aspect_ratio=illustration_context.get("preferred_aspect_ratio") or "4:3",
        epub_ready=True,
    )
    return {
        "asset": asset,
        "assets": list_generated_assets(book_id),
        "prompt_used": final_prompt,
    }


@router.get("/{book_id}/illustration-studio/assets/{filename}")
def get_generated_illustration_asset(request: Request, book_id: int, filename: str):
    require_auth(request)
    book = get_book_by_id(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    path = get_asset_path(book_id, filename)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Illustration asset not found")
    try:
        path.resolve().relative_to((Path(path).parent).resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")
    return FileResponse(str(path), media_type="image/png", filename=path.name)
