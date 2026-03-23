"""
Voice Studio / TTS routes for Story Forge API
"""
from fastapi import APIRouter, HTTPException, Request
from typing import Optional
from pydantic import BaseModel
from db_helpers import get_chapter_with_tts_jobs, get_tts_job, get_tts_jobs, delete_tts_job
from .auth_utils import require_auth

import tts as tts_module

router = APIRouter()


class GenerateRequest(BaseModel):
    chapter_id: int
    provider: str
    voice_id: str



@router.get("/providers")
def list_providers(request: Request):
    """Get available TTS providers."""
    require_auth(request)
    providers = tts_module.tts_manager.get_available_providers()
    return {"providers": providers}


@router.get("/voices/{provider}")
def list_voices(request: Request, provider: str):
    """Get available voices for a provider."""
    require_auth(request)
    try:
        voices = tts_module.tts_manager.get_voices(provider)
        return {"voices": voices}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/generate")
def generate_speech(request: Request, body: GenerateRequest):
    """Generate TTS audio for a chapter."""
    require_auth(request)

    # Verify chapter exists
    chapter = get_chapter_with_tts_jobs(body.chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    try:
        job = tts_module.tts_manager.queue_job(
            chapter_id=body.chapter_id,
            provider=body.provider,
            voice_id=body.voice_id
        )
        return {
            "id": job.id,
            "chapter_id": job.chapter_id,
            "provider": job.provider,
            "voice_id": job.voice_id,
            "status": job.status.value if hasattr(job.status, 'value') else job.status,
            "created_at": str(job.created_at)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


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
        "provider": job.provider,
        "voice_id": job.voice_id,
        "status": job.status.value if hasattr(job.status, 'value') else job.status,
        "audio_url": job.audio_url,
        "duration_seconds": job.duration_seconds,
        "created_at": str(job.created_at)
    }


@router.get("/jobs")
def list_jobs(request: Request, chapter_id: Optional[int] = None):
    """List TTS jobs."""
    require_auth(request)
    jobs = get_tts_jobs(chapter_id=chapter_id)
    return [{
        "id": j.id,
        "chapter_id": j.chapter_id,
        "provider": j.provider,
        "voice_id": j.voice_id,
        "status": j.status.value if hasattr(j.status, 'value') else j.status,
        "audio_url": j.audio_url,
        "duration_seconds": j.duration_seconds,
        "created_at": str(j.created_at)
    } for j in jobs]


@router.delete("/jobs/{job_id}")
def delete_job(request: Request, job_id: int):
    """Delete a TTS job."""
    require_auth(request)
    success = delete_tts_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "deleted"}
