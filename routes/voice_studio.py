"""
Voice Studio / TTS routes for Story Forge API
"""
from datetime import datetime
from io import BytesIO
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from typing import Any, Optional
from pydantic import BaseModel
import asyncio
import json
from ai_providers import ai_provider_manager
from context_engine import build_runtime_context_packet
from db_helpers import get_book_by_id, get_chapter_with_tts_jobs, get_chapters_for_book, get_tts_job, get_tts_jobs, delete_tts_job
from db import get_session, TTSJob, TTSJobStatus, TTSProviderType
from style_studio import build_style_context
from integrations import get_elevenlabs_api_key
from .auth_utils import require_auth

import tts as tts_module
from voice_mapping import (
    VoiceMapValidationError,
    load_book_voice_map,
    load_chapter_voice_map,
    rebuild_chapter_voice_map,
    update_book_voice_map,
    update_chapter_voice_map,
)

router = APIRouter()


class GenerateRequest(BaseModel):
    chapter_id: int
    provider: str = "elevenlabs"
    voice_id: str = ""
    model: Optional[str] = None


class BookVoiceMapUpdateRequest(BaseModel):
    characters: list[dict[str, Any]]
    narrator: Optional[dict[str, Any]] = None


class ChapterVoiceMapUpdateRequest(BaseModel):
    segments: list[dict[str, Any]]
    characters: Optional[list[dict[str, Any]]] = None
    narrator_speaker: Optional[str] = None


class PreviewRequest(BaseModel):
    provider: str = "elevenlabs"
    voice_id: str
    text: str
    model: Optional[str] = None
    speed: float = 1.0


def _resolve_voice_id_for_speaker(chapter_voice_map: dict, voice_roster: dict, speaker: str) -> str | None:
    normalized = (speaker or "").strip()
    if not normalized:
        return None

    if normalized == "Narrator":
        return (voice_roster.get("narrator") or {}).get("elevenlabs_voice_id")

    if normalized == (chapter_voice_map.get("narrator_speaker") or "").strip():
        for character in voice_roster.get("characters") or []:
            if (character.get("character_name") or "").strip() == normalized:
                return character.get("elevenlabs_voice_id")
        if normalized == "Narrator":
            return (voice_roster.get("narrator") or {}).get("elevenlabs_voice_id")

    for character in voice_roster.get("characters") or []:
        if (character.get("character_name") or "").strip() == normalized:
            return character.get("elevenlabs_voice_id")

    return None


def _build_segment_render_plan(chapter_voice_map: dict, voice_roster: dict) -> tuple[list[dict[str, Any]], list[str]]:
    missing: list[str] = []
    render_segments: list[dict[str, Any]] = []

    for segment in chapter_voice_map.get("segments") or []:
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        speaker = str(segment.get("speaker") or "").strip() or "Narrator"
        voice_id = _resolve_voice_id_for_speaker(chapter_voice_map, voice_roster, speaker)
        if not voice_id:
            missing.append(speaker)
            continue
        render_segments.append(
            {
                "speaker": speaker,
                "voice_id": voice_id,
                "text": text,
                "delivery_hint": str(segment.get("delivery_hint") or "neutral").strip() or "neutral",
            }
        )

    return render_segments, sorted({entry for entry in missing if entry})


def _build_story_context(book_id: int) -> dict:
    book = get_book_by_id(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return {
        "book": {
            "id": book.id,
            "title": book.title,
            "author": book.author,
            "description": book.description,
            "status": book.status.value if hasattr(book.status, "value") else str(book.status),
        },
        "context_summary": build_runtime_context_packet(book_id),
        "style_studio": build_style_context(book_id),
    }


def _apply_ai_voice_plan_updates(chapter_voice_map: dict, narrator_speaker: str, segment_updates: list[dict[str, Any]]) -> dict:
    update_map: dict[int, dict[str, Any]] = {}
    for update in segment_updates or []:
        try:
            index = int(update.get("index"))
        except Exception:
            continue
        if index <= 0:
            continue
        update_map[index] = update

    segments: list[dict[str, Any]] = []
    for segment in chapter_voice_map.get("segments") or []:
        index = int(segment.get("index") or len(segments) + 1)
        update = update_map.get(index, {})
        segments.append(
            {
                "index": index,
                "type": update.get("type") or segment.get("type") or "narration",
                "speaker": update.get("speaker") or segment.get("speaker") or "Narrator",
                "text": segment.get("text") or "",
                "delivery_hint": update.get("delivery_hint") or segment.get("delivery_hint") or "neutral",
            }
        )

    return {
        "narrator_speaker": narrator_speaker or chapter_voice_map.get("narrator_speaker") or "Narrator",
        "segments": segments,
    }


@router.get("/providers")
def list_providers(request: Request):
    """Get available TTS providers and their configuration status."""
    require_auth(request)
    manager = tts_module.tts_manager
    provider = tts_module.TTSProvider.ELEVENLABS
    return {
        "providers": [{
            "id": provider.value,
            "name": "ElevenLabs",
            "configured": manager.is_provider_configured(provider),
            "models": manager.get_provider(provider).get_available_models(),
        }]
    }


@router.get("/voices/{provider}")
async def list_voices(request: Request, provider: str):
    """Get available voices for a provider."""
    require_auth(request)
    if provider != "elevenlabs":
        raise HTTPException(status_code=400, detail="Only ElevenLabs is currently supported in Voice Studio.")

    tts_provider = tts_module.TTSProvider.ELEVENLABS
    if not get_elevenlabs_api_key():
        raise HTTPException(status_code=400, detail="ElevenLabs API key is not configured. Add it in Integrations.")

    try:
        voices = await tts_module.tts_manager.list_voices(tts_provider)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Unable to load ElevenLabs voices: {e}")

    if not voices:
        raise HTTPException(
            status_code=502,
            detail="ElevenLabs returned no voices. Check the API key in Integrations, and if you are using a scoped key make sure it has permission to list voices."
        )

    return {"voices": [{
        "voice_id": v.voice_id,
        "name": v.name,
        "gender": v.gender,
        "language": v.language,
        "preview_url": v.preview_url,
        "is_cloned": v.is_cloned,
    } for v in voices]}


@router.get("/books/{book_id}/voice-map")
def get_book_voice_map(request: Request, book_id: int):
    """Get the background character voice roster for a book."""
    require_auth(request)
    book = get_book_by_id(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return load_book_voice_map(book_id)


@router.put("/books/{book_id}/voice-map")
def save_book_voice_map(request: Request, book_id: int, body: BookVoiceMapUpdateRequest):
    """Save the background character voice roster for a book."""
    require_auth(request)
    book = get_book_by_id(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return update_book_voice_map(book_id=book_id, characters=body.characters, narrator=body.narrator)


@router.get("/chapters/{chapter_id}/voice-map")
def get_chapter_voice_map(request: Request, chapter_id: int):
    """Get the per-chapter voice plan for narration and dialogue."""
    require_auth(request)
    chapter = get_chapter_with_tts_jobs(chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return load_chapter_voice_map(
        book_id=chapter.book_id,
        chapter_id=chapter.id,
        chapter_title=chapter.title,
        chapter_content=chapter.content or "",
    )


@router.put("/chapters/{chapter_id}/voice-map")
def save_chapter_voice_map(request: Request, chapter_id: int, body: ChapterVoiceMapUpdateRequest):
    """Save the per-chapter voice plan for narration and dialogue."""
    require_auth(request)
    chapter = get_chapter_with_tts_jobs(chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    try:
        return update_chapter_voice_map(
            book_id=chapter.book_id,
            chapter_id=chapter.id,
            chapter_title=chapter.title,
            chapter_content=chapter.content or "",
            segments=body.segments,
            characters=body.characters,
            narrator_speaker=body.narrator_speaker,
        )
    except VoiceMapValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/chapters/{chapter_id}/voice-map/rebuild")
def rebuild_chapter_plan(request: Request, chapter_id: int):
    """Rebuild the chapter voice plan from the cleaned roster and current chapter text."""
    require_auth(request)
    chapter = get_chapter_with_tts_jobs(chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return rebuild_chapter_voice_map(
        book_id=chapter.book_id,
        chapter_id=chapter.id,
        chapter_title=chapter.title,
        chapter_content=chapter.content or "",
    )


@router.post("/chapters/{chapter_id}/voice-map/refine")
def refine_chapter_plan(request: Request, chapter_id: int):
    """Use the active AI provider to refine chapter narrator and dialogue assignments."""
    require_auth(request)
    chapter = get_chapter_with_tts_jobs(chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    chapter_voice_map = load_chapter_voice_map(
        book_id=chapter.book_id,
        chapter_id=chapter.id,
        chapter_title=chapter.title,
        chapter_content=chapter.content or "",
    )
    voice_roster = load_book_voice_map(chapter.book_id)
    story_context = _build_story_context(chapter.book_id)

    response = asyncio.run(
        ai_provider_manager.refine_voice_plan(
            chapter_title=chapter.title,
            chapter_content=chapter.content or "",
            story_context=story_context,
            voice_roster=voice_roster,
            chapter_voice_map=chapter_voice_map,
        )
    )
    if not response.get("success"):
        raise HTTPException(status_code=503, detail=response.get("error") or "AI voice-plan refinement is unavailable.")

    refined = _apply_ai_voice_plan_updates(
        chapter_voice_map=chapter_voice_map,
        narrator_speaker=str(response.get("narrator_speaker") or "Narrator"),
        segment_updates=response.get("segment_updates") or [],
    )
    try:
        return update_chapter_voice_map(
            book_id=chapter.book_id,
            chapter_id=chapter.id,
            chapter_title=chapter.title,
            chapter_content=chapter.content or "",
            segments=refined["segments"],
            characters=voice_roster.get("characters") or [],
            narrator_speaker=refined["narrator_speaker"],
        )
    except VoiceMapValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


async def _generate_preview_audio(request: Request, body: PreviewRequest):
    require_auth(request)

    preview_text = (body.text or "").strip()
    if not preview_text:
        raise HTTPException(status_code=400, detail="Preview text is required")
    if len(preview_text) > 900:
        raise HTTPException(status_code=400, detail="Preview text is too long for mic check")
    if not body.voice_id:
        raise HTTPException(status_code=400, detail="voice_id is required for mic check")

    try:
        tts_provider = tts_module.TTSProvider(body.provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {body.provider}")
    if tts_provider != tts_module.TTSProvider.ELEVENLABS:
        raise HTTPException(status_code=400, detail="Only ElevenLabs is currently supported in Voice Studio.")

    manager = tts_module.tts_manager
    if not manager.is_provider_configured(tts_provider):
        raise HTTPException(
            status_code=400,
            detail=f"{body.provider} API key not configured for mic check."
        )

    model = body.model or manager.get_provider(tts_provider).get_available_models()[0]
    response = await manager.generate_speech(
        tts_module.TTSRequest(
            text=preview_text,
            provider=tts_provider,
            voice_id=body.voice_id,
            model=model,
            speed=body.speed or 1.0,
        )
    )
    if response.error:
        raise HTTPException(status_code=502, detail=response.error)
    if not response.audio_data:
        raise HTTPException(status_code=502, detail="Provider returned no audio for mic check")

    return response.audio_data


@router.post("/preview")
async def preview_voice(request: Request, body: PreviewRequest):
    """Generate a short voice preview clip for mapping and mic checks."""
    audio_data = await _generate_preview_audio(request, body)
    return StreamingResponse(
        BytesIO(audio_data),
        media_type="audio/mpeg",
        headers={"Content-Disposition": 'inline; filename="voice-preview.mp3"'},
    )


@router.post("/generate")
async def generate_speech(request: Request, body: GenerateRequest):
    """Generate TTS audio for a chapter."""
    require_auth(request)

    chapter = get_chapter_with_tts_jobs(body.chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    if not chapter.content or not chapter.content.strip():
        raise HTTPException(status_code=400, detail="Chapter has no content to convert")

    try:
        tts_provider = tts_module.TTSProvider(body.provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {body.provider}")
    if tts_provider != tts_module.TTSProvider.ELEVENLABS:
        raise HTTPException(status_code=400, detail="Only ElevenLabs is currently supported in Voice Studio.")

    manager = tts_module.tts_manager
    if not manager.is_provider_configured(tts_provider):
        raise HTTPException(
            status_code=400,
            detail=f"{body.provider} API key not configured. Add it in Integrations.",
        )

    session = get_session()
    try:
        job = TTSJob(
            chapter_id=body.chapter_id,
            provider=TTSProviderType(body.provider),
            voice_id=body.voice_id or None,
            model=body.model or manager.get_provider(tts_provider).get_available_models()[0],
            status=TTSJobStatus.PROCESSING,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id
    finally:
        session.close()

    tts_request = tts_module.TTSRequest(
        text=chapter.content,
        provider=tts_provider,
        voice_id=body.voice_id,
        model=body.model or manager.get_provider(tts_provider).get_available_models()[0],
    )
    response = await manager.generate_speech(tts_request)

    session = get_session()
    try:
        job = session.query(TTSJob).filter(TTSJob.id == job_id).first()
        if response.error:
            job.status = TTSJobStatus.FAILED
            job.error_message = response.error
        else:
            audio_path = tts_module.save_audio_file(
                book_id=chapter.book_id,
                chapter_id=chapter.id,
                provider=tts_provider,
                audio_data=response.audio_data,
            )
            job.status = TTSJobStatus.COMPLETED
            job.audio_path = audio_path
            job.audio_duration = response.duration_seconds
            job.cost_tokens = response.cost_tokens
            job.completed_at = datetime.now()

        session.commit()
        session.refresh(job)

        return {
            "id": job.id,
            "chapter_id": job.chapter_id,
            "provider": job.provider.value,
            "voice_id": job.voice_id,
            "status": job.status.value,
            "audio_path": job.audio_path,
            "audio_duration": job.audio_duration,
            "error_message": job.error_message,
            "created_at": str(job.created_at),
            "completed_at": str(job.completed_at) if job.completed_at else None,
        }
    finally:
        session.close()


def _serialize_job(job: TTSJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "chapter_id": job.chapter_id,
        "provider": job.provider.value if hasattr(job.provider, "value") else str(job.provider),
        "voice_id": job.voice_id,
        "status": job.status.value if hasattr(job.status, "value") else str(job.status),
        "audio_path": job.audio_path,
        "audio_duration": job.audio_duration,
        "error_message": job.error_message,
        "created_at": str(job.created_at),
        "completed_at": str(job.completed_at) if job.completed_at else None,
    }


def _get_audiobook_path(book_id: int, provider: tts_module.TTSProvider, format: str = "mp3"):
    filepath = tts_module.AUDIO_DIR / f"book_{book_id}_audiobook_{provider.value}.{format}"
    return filepath if filepath.exists() else None


def _save_audiobook_file(book_id: int, provider: tts_module.TTSProvider, audio_data: bytes, format: str = "mp3") -> str:
    filepath = tts_module.AUDIO_DIR / f"book_{book_id}_audiobook_{provider.value}.{format}"
    filepath.write_bytes(audio_data)
    return str(filepath)


@router.get("/chapters/{chapter_id}/audio-review")
def get_chapter_audio_review(request: Request, chapter_id: int):
    """Return review metadata for the latest rendered chapter audio."""
    require_auth(request)
    chapter = get_chapter_with_tts_jobs(chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    latest_completed_job = None
    completed_jobs = [job for job in (chapter.tts_jobs or []) if str(getattr(job.status, 'value', job.status)) == 'completed']
    if completed_jobs:
        latest_completed_job = max(completed_jobs, key=lambda job: job.completed_at or job.created_at)

    audio_path = tts_module.get_audio_path(chapter.book_id, chapter.id, tts_module.TTSProvider.ELEVENLABS)
    return {
        "chapter_id": chapter.id,
        "book_id": chapter.book_id,
        "audio_available": bool(audio_path),
        "audio_updated_at": str(audio_path.stat().st_mtime) if audio_path else None,
        "latest_job": _serialize_job(latest_completed_job) if latest_completed_job else None,
    }


@router.post("/chapters/{chapter_id}/render")
async def render_chapter_from_voice_plan(request: Request, chapter_id: int):
    """Render chapter audio from the saved voice plan."""
    require_auth(request)

    chapter = get_chapter_with_tts_jobs(chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    chapter_voice_map = load_chapter_voice_map(
        book_id=chapter.book_id,
        chapter_id=chapter.id,
        chapter_title=chapter.title,
        chapter_content=chapter.content or "",
    )
    voice_roster = load_book_voice_map(chapter.book_id)
    render_segments, missing_speakers = _build_segment_render_plan(chapter_voice_map, voice_roster)

    if missing_speakers:
        raise HTTPException(
            status_code=400,
            detail=f"Assign voices before rendering. Missing voice IDs for: {', '.join(missing_speakers)}",
        )
    if not render_segments:
        raise HTTPException(status_code=400, detail="No renderable segments found in the saved chapter voice plan.")

    manager = tts_module.tts_manager
    tts_provider = tts_module.TTSProvider.ELEVENLABS
    if not manager.is_provider_configured(tts_provider):
        raise HTTPException(status_code=400, detail="ElevenLabs API key not configured in Integrations.")

    session = get_session()
    try:
        job = TTSJob(
            chapter_id=chapter.id,
            provider=TTSProviderType.ELEVENLABS,
            voice_id="voice-plan",
            model=manager.get_provider(tts_provider).get_available_models()[0],
            status=TTSJobStatus.PROCESSING,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id
    finally:
        session.close()

    combined_audio = bytearray()
    total_chars = 0
    response_error = None
    for segment in render_segments:
        segment_response = await manager.generate_speech(
            tts_module.TTSRequest(
                text=segment["text"],
                provider=tts_provider,
                voice_id=segment["voice_id"],
                model=manager.get_provider(tts_provider).get_available_models()[0],
            )
        )
        if segment_response.error or not segment_response.audio_data:
            response_error = segment_response.error or f"Failed to render segment for {segment['speaker']}"
            break
        combined_audio.extend(segment_response.audio_data)
        total_chars += len(segment["text"])

    session = get_session()
    try:
        job = session.query(TTSJob).filter(TTSJob.id == job_id).first()
        if response_error:
            job.status = TTSJobStatus.FAILED
            job.error_message = response_error
        else:
            audio_path = tts_module.save_audio_file(
                book_id=chapter.book_id,
                chapter_id=chapter.id,
                provider=tts_provider,
                audio_data=bytes(combined_audio),
            )
            job.status = TTSJobStatus.COMPLETED
            job.audio_path = audio_path
            job.cost_tokens = total_chars
            job.completed_at = datetime.now()
        session.commit()
        session.refresh(job)
        return _serialize_job(job)
    finally:
        session.close()


@router.get("/books/{book_id}/audiobook/status")
def get_audiobook_status(request: Request, book_id: int):
    """Return chapter-audio readiness and full-audiobook availability for a book."""
    require_auth(request)
    book = get_book_by_id(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    chapters = get_chapters_for_book(book_id)
    rendered_chapters: list[dict[str, Any]] = []
    missing_chapters: list[dict[str, Any]] = []
    for chapter in chapters:
        audio_path = tts_module.get_audio_path(book_id, chapter.id, tts_module.TTSProvider.ELEVENLABS)
        chapter_data = {
            "id": chapter.id,
            "order": chapter.order,
            "title": chapter.title,
        }
        if audio_path:
            chapter_data["audio_updated_at"] = str(audio_path.stat().st_mtime)
            rendered_chapters.append(chapter_data)
        else:
            missing_chapters.append(chapter_data)

    audiobook_path = _get_audiobook_path(book_id, tts_module.TTSProvider.ELEVENLABS)
    return {
        "book_id": book_id,
        "total_chapters": len(chapters),
        "rendered_chapters": rendered_chapters,
        "missing_chapters": missing_chapters,
        "ready_for_assembly": bool(chapters) and not missing_chapters,
        "audiobook_available": bool(audiobook_path),
        "audiobook_updated_at": str(audiobook_path.stat().st_mtime) if audiobook_path else None,
    }


@router.post("/books/{book_id}/audiobook/render")
def build_audiobook(request: Request, book_id: int):
    """Build a consolidated audiobook once every chapter has review audio."""
    require_auth(request)
    book = get_book_by_id(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    chapters = get_chapters_for_book(book_id)
    if not chapters:
        raise HTTPException(status_code=400, detail="Add chapters to this book before building the audiobook.")

    chapter_paths = []
    missing = []
    for chapter in chapters:
        audio_path = tts_module.get_audio_path(book_id, chapter.id, tts_module.TTSProvider.ELEVENLABS)
        if not audio_path:
            missing.append(f"{chapter.order}. {chapter.title}")
        else:
            chapter_paths.append(audio_path)

    if missing:
        raise HTTPException(
            status_code=400,
            detail="Render every chapter first before building the audiobook. Missing chapter audio for: " + ", ".join(missing),
        )

    combined_audio = b"".join(path.read_bytes() for path in chapter_paths)
    if not combined_audio:
        raise HTTPException(status_code=400, detail="No chapter audio files were available to combine.")

    audio_path = _save_audiobook_file(book_id, tts_module.TTSProvider.ELEVENLABS, combined_audio)
    return {
        "book_id": book_id,
        "audio_path": audio_path,
        "chapter_count": len(chapters),
        "built_at": str(datetime.now()),
    }


@router.get("/audio/books/{book_id}/{provider}")
def get_audiobook_file(request: Request, book_id: int, provider: str):
    """Serve a generated full-book audiobook file."""
    require_auth(request)
    try:
        tts_provider = tts_module.TTSProvider(provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    audio_path = _get_audiobook_path(book_id, tts_provider)
    if not audio_path:
        raise HTTPException(status_code=404, detail="Audiobook file not found")

    return FileResponse(str(audio_path), media_type="audio/mpeg")


@router.get("/jobs/{job_id}")
def get_job(request: Request, job_id: int):
    """Get TTS job status."""
    require_auth(request)
    job = get_tts_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "chapter_id": job.chapter_id,
        "provider": job.provider.value if hasattr(job.provider, 'value') else str(job.provider),
        "voice_id": job.voice_id,
        "status": job.status.value if hasattr(job.status, 'value') else str(job.status),
        "audio_path": job.audio_path,
        "audio_duration": job.audio_duration,
        "error_message": job.error_message,
        "created_at": str(job.created_at),
        "completed_at": str(job.completed_at) if job.completed_at else None,
    }


@router.get("/jobs")
def list_jobs(request: Request, chapter_id: Optional[int] = None):
    """List TTS jobs."""
    require_auth(request)
    jobs = get_tts_jobs(chapter_id=chapter_id)
    return [{
        "id": j.id,
        "chapter_id": j.chapter_id,
        "provider": j.provider.value if hasattr(j.provider, 'value') else str(j.provider),
        "voice_id": j.voice_id,
        "status": j.status.value if hasattr(j.status, 'value') else str(j.status),
        "audio_path": j.audio_path,
        "audio_duration": j.audio_duration,
        "error_message": j.error_message,
        "created_at": str(j.created_at),
        "completed_at": str(j.completed_at) if j.completed_at else None,
    } for j in jobs]


@router.post("/configure")
def configure_provider(request: Request, body: dict):
    """Configure a TTS provider API key (stored in keychain)."""
    require_auth(request)
    provider = body.get("provider")
    api_key = body.get("api_key")
    if not provider or not api_key:
        raise HTTPException(status_code=400, detail="provider and api_key required")
    if provider != "elevenlabs":
        raise HTTPException(status_code=400, detail="Only ElevenLabs is currently supported in Voice Studio.")

    try:
        import keyring
        keychain_key = f"story-forge-{provider}-api-key"
        keyring.set_password("story-forge", keychain_key, api_key)

        manager = tts_module.tts_manager
        manager._elevenlabs = tts_module.ElevenLabsProvider(api_key=api_key)

        return {"status": "configured", "provider": provider}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audio/{book_id}/{chapter_id}/{provider}")
def get_audio_file(request: Request, book_id: int, chapter_id: int, provider: str):
    """Serve a generated audio file."""
    require_auth(request)
    try:
        tts_provider = tts_module.TTSProvider(provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    audio_path = tts_module.get_audio_path(book_id, chapter_id, tts_provider)
    if not audio_path:
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(str(audio_path), media_type="audio/mpeg")


@router.delete("/jobs/{job_id}")
def delete_job(request: Request, job_id: int):
    """Delete a TTS job."""
    require_auth(request)
    success = delete_tts_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "deleted"}
