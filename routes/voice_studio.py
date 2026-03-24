"""
Voice Studio / TTS routes for Story Forge API
"""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from typing import Optional
from pydantic import BaseModel
from db_helpers import get_chapter_with_tts_jobs, get_tts_job, get_tts_jobs, delete_tts_job
from db import get_session, TTSJob, TTSJobStatus, TTSProviderType
from .auth_utils import require_auth

import tts as tts_module

router = APIRouter()


class GenerateRequest(BaseModel):
    chapter_id: int
    provider: str = "elevenlabs"
    voice_id: str = ""
    model: Optional[str] = None


@router.get("/providers")
def list_providers(request: Request):
    """Get available TTS providers and their configuration status."""
    require_auth(request)
    manager = tts_module.tts_manager
    providers = []
    for p in tts_module.TTSProvider:
        providers.append({
            "id": p.value,
            "name": p.value.title(),
            "configured": manager.is_provider_configured(p),
            "models": manager.get_provider(p).get_available_models(),
        })
    return {"providers": providers}


@router.get("/voices/{provider}")
async def list_voices(request: Request, provider: str):
    """Get available voices for a provider."""
    require_auth(request)
    try:
        tts_provider = tts_module.TTSProvider(provider)
        voices = await tts_module.tts_manager.list_voices(tts_provider)
        return {"voices": [{
            "voice_id": v.voice_id,
            "name": v.name,
            "gender": v.gender,
            "language": v.language,
            "preview_url": v.preview_url,
            "is_cloned": v.is_cloned,
        } for v in voices]}
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


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

    manager = tts_module.tts_manager
    if not manager.is_provider_configured(tts_provider):
        raise HTTPException(
            status_code=400,
            detail=f"{body.provider} API key not configured. Set {body.provider.upper()}_API_KEY environment variable."
        )

    # Create TTS job record
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

    # Generate speech
    tts_request = tts_module.TTSRequest(
        text=chapter.content,
        provider=tts_provider,
        voice_id=body.voice_id,
        model=body.model or manager.get_provider(tts_provider).get_available_models()[0],
    )

    response = await manager.generate_speech(tts_request)

    # Update job with result
    session = get_session()
    try:
        job = session.query(TTSJob).filter(TTSJob.id == job_id).first()
        if response.error:
            job.status = TTSJobStatus.FAILED
            job.error_message = response.error
        else:
            # Save audio file
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
        }
    finally:
        session.close()


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

    try:
        import keyring
        keychain_key = f"story-forge-{provider}-api-key"
        keyring.set_password("story-forge", keychain_key, api_key)

        # Reinitialize the provider with new key
        manager = tts_module.tts_manager
        if provider == "minimax":
            manager._minimax = tts_module.MiniMaxProvider(api_key=api_key)
        elif provider == "elevenlabs":
            manager._elevenlabs = tts_module.ElevenLabsProvider(api_key=api_key)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

        return {"status": "configured", "provider": provider}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audio/{book_id}/{chapter_id}/{provider}")
def get_audio_file(request: Request, book_id: int, chapter_id: int, provider: str):
    """Serve a generated audio file."""
    require_auth(request)
    from fastapi.responses import FileResponse
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
