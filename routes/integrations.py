"""
Integration settings routes for Story Forge.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

import tts as tts_module
from integrations import (
    get_integration_status,
    get_settings,
    update_ai_settings,
    update_backup_settings,
    update_tts_settings,
)
from .auth_utils import require_auth

router = APIRouter()


class OpenClawSettingsRequest(BaseModel):
    agent_id: str = "libby"
    agent_name: str = "Libby"
    transport: str = "openclaw"


class OpenRouterSettingsRequest(BaseModel):
    base_url: str = "https://openrouter.ai/api/v1"
    model: str = "openai/gpt-4.1-mini"
    site_url: str = "http://localhost:5173"
    app_name: str = "Story Forge"
    api_key: str | None = None


class AISettingsRequest(BaseModel):
    provider: str = "openclaw"
    openclaw: OpenClawSettingsRequest = OpenClawSettingsRequest()
    openrouter: OpenRouterSettingsRequest = OpenRouterSettingsRequest()


class BackupGoogleDriveRequest(BaseModel):
    enabled: bool = False
    folder_name: str = "Story Forge Backups"


class BackupSettingsRequest(BaseModel):
    provider: str = "usb_ssd"
    usb_path: str = "/Volumes/xtra-ssd"
    google_drive: BackupGoogleDriveRequest = BackupGoogleDriveRequest()


class ElevenLabsSettingsRequest(BaseModel):
    enabled: bool = True
    api_key: str | None = None


class TTSSettingsRequest(BaseModel):
    provider: str = "elevenlabs"
    elevenlabs: ElevenLabsSettingsRequest = ElevenLabsSettingsRequest()


@router.get("")
def get_integrations(request: Request):
    require_auth(request)
    return {
        "settings": get_settings(),
        "status": get_integration_status(),
    }


@router.put("/ai")
def save_ai_settings(request: Request, body: AISettingsRequest):
    require_auth(request)
    try:
        return update_ai_settings(
            {
                "provider": body.provider,
                "openclaw": body.openclaw.model_dump(),
                "openrouter": {
                    "base_url": body.openrouter.base_url,
                    "model": body.openrouter.model,
                    "site_url": body.openrouter.site_url,
                    "app_name": body.openrouter.app_name,
                },
                "openrouter_api_key": body.openrouter.api_key,
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/backup")
def save_backup_settings(request: Request, body: BackupSettingsRequest):
    require_auth(request)
    try:
        return update_backup_settings(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/tts")
def save_tts_settings(request: Request, body: TTSSettingsRequest):
    require_auth(request)
    try:
        settings = update_tts_settings(
            {
                "provider": body.provider,
                "elevenlabs": {
                    "enabled": body.elevenlabs.enabled,
                },
                "elevenlabs_api_key": body.elevenlabs.api_key,
            }
        )
        if body.elevenlabs.api_key:
            tts_module.tts_manager._elevenlabs = tts_module.ElevenLabsProvider(api_key=body.elevenlabs.api_key)
        elif tts_module.tts_manager._elevenlabs is not None:
            tts_module.tts_manager._elevenlabs = tts_module.ElevenLabsProvider()
        return settings
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
