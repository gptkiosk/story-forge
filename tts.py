"""
TTS (Text-to-Speech) module for Story Forge.
Provides provider abstraction for MiniMax and ElevenLabs TTS services.
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import httpx

# =============================================================================
# Configuration
# =============================================================================

# Keychain for storing API keys
KEYCHAIN_SERVICE = "story-forge"

def _get_api_key(env_var: str, keychain_key: str) -> str:
    """Get API key from env var or keychain."""
    key = os.environ.get(env_var, "")
    if not key:
        try:
            import keyring
            key = keyring.get_password(KEYCHAIN_SERVICE, keychain_key) or ""
        except Exception:
            pass
    return key

# MiniMax API
MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
MINIMAX_API_URL = "https://api.minimax.io/v1"

# ElevenLabs API
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1"


class TTSProvider(Enum):
    """TTS provider enumeration."""
    MINIMAX = "minimax"
    ELEVENLABS = "elevenlabs"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class TTSRequest:
    """TTS generation request."""
    text: str
    provider: TTSProvider
    voice_id: str
    model: str = "speech-02-hd"  # MiniMax default
    speed: float = 1.0
    pitch: float = 0.0
    volume: float = 1.0
    format: str = "mp3"  # mp3, wav, flac
    sample_rate: int = 32000


@dataclass
class TTSResponse:
    """TTS generation response."""
    audio_data: bytes
    duration_seconds: Optional[int] = None
    cost_tokens: Optional[int] = None
    provider: Optional[TTSProvider] = None
    voice_id: Optional[str] = None
    model: Optional[str] = None
    error: Optional[str] = None


@dataclass
class VoiceInfo:
    """Voice information."""
    voice_id: str
    name: str
    provider: TTSProvider
    gender: Optional[str] = None
    language: Optional[str] = None
    preview_url: Optional[str] = None
    is_cloned: bool = False


# =============================================================================
# TTS Provider Abstraction
# =============================================================================


class TTSProviderBase(ABC):
    """Abstract base class for TTS providers."""

    @property
    @abstractmethod
    def provider(self) -> TTSProvider:
        """Return the provider type."""
        pass

    @abstractmethod
    async def generate_speech(self, request: TTSRequest) -> TTSResponse:
        """Generate speech from text."""
        pass

    @abstractmethod
    async def list_voices(self) -> list[VoiceInfo]:
        """List available voices."""
        pass

    @abstractmethod
    async def clone_voice(self, audio_sample: bytes, name: str) -> VoiceInfo:
        """Clone a voice from an audio sample."""
        pass

    @abstractmethod
    async def get_voice(self, voice_id: str) -> VoiceInfo:
        """Get information about a specific voice."""
        pass

    @abstractmethod
    def get_available_models(self) -> list[str]:
        """Get list of available models for this provider."""
        pass


# =============================================================================
# MiniMax TTS Provider
# =============================================================================


class MiniMaxProvider(TTSProviderBase):
    """MiniMax TTS provider implementation."""

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or _get_api_key("MINIMAX_API_KEY", f"{KEYCHAIN_SERVICE}-minimax-api-key")

    @property
    def provider(self) -> TTSProvider:
        return TTSProvider.MINIMAX

    def _get_headers(self) -> dict:
        """Get request headers."""
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def generate_speech(self, request: TTSRequest) -> TTSResponse:
        """Generate speech using MiniMax API."""
        if not self._api_key:
            return TTSResponse(
                audio_data=b"",
                error="MiniMax API key not configured"
            )

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                # Build request payload
                payload = {
                    "model": request.model,
                    "text": request.text,
                    "voice_setting": {
                        "voice_id": request.voice_id,
                        "speed": request.speed,
                        "pitch": request.pitch,
                        "volume": request.volume,
                    },
                    "audio_setting": {
                        "audio_format": request.format,
                        "sample_rate": request.sample_rate,
                    },
                }

                response = await client.post(
                    f"{MINIMAX_API_URL}/t2a_v2",
                    headers=self._get_headers(),
                    json=payload,
                )

                if response.status_code != 200:
                    return TTSResponse(
                        audio_data=b"",
                        error=f"MiniMax API error: {response.status_code} - {response.text}"
                    )

                data = response.json()

                # MiniMax returns base64 encoded audio
                import base64
                audio_b64 = data.get("data", {}).get("audio_file", "")
                audio_data = base64.b64decode(audio_b64) if audio_b64 else b""

                return TTSResponse(
                    audio_data=audio_data,
                    duration_seconds=data.get("data", {}).get("duration"),
                    cost_tokens=data.get("data", {}).get("chars_count"),
                    provider=self.provider,
                    voice_id=request.voice_id,
                    model=request.model,
                )

        except Exception as e:
            return TTSResponse(
                audio_data=b"",
                error=f"MiniMax generation failed: {str(e)}"
            )

    async def list_voices(self) -> list[VoiceInfo]:
        """List MiniMax voices."""
        # MiniMax has a set of built-in voices
        # In production, this would call the API to get user-created voices
        built_in_voices = [
            VoiceInfo(
                voice_id="male-qn-qingse",
                name="Qing Se (Male)",
                provider=self.provider,
                gender="male",
                language="zh",
                is_cloned=False,
            ),
            VoiceInfo(
                voice_id="female-tian-mei",
                name="Tian Mei (Female)",
                provider=self.provider,
                gender="female",
                language="zh",
                is_cloned=False,
            ),
            VoiceInfo(
                voice_id="male-qn-qingse",
                name="English Male",
                provider=self.provider,
                gender="male",
                language="en",
                is_cloned=False,
            ),
            VoiceInfo(
                voice_id="female-zh-CN",
                name="Chinese Female",
                provider=self.provider,
                gender="female",
                language="zh-CN",
                is_cloned=False,
            ),
        ]
        return built_in_voices

    async def clone_voice(self, audio_sample: bytes, name: str) -> VoiceInfo:
        """Clone a voice from audio sample."""
        # Voice cloning would require the voice_clone endpoint
        # For now, return a placeholder
        return VoiceInfo(
            voice_id=f"cloned_{name.lower().replace(' ', '_')}",
            name=f"Cloned: {name}",
            provider=self.provider,
            is_cloned=True,
        )

    async def get_voice(self, voice_id: str) -> VoiceInfo:
        """Get voice information."""
        voices = await self.list_voices()
        for voice in voices:
            if voice.voice_id == voice_id:
                return voice
        return VoiceInfo(
            voice_id=voice_id,
            name=voice_id,
            provider=self.provider,
        )

    def get_available_models(self) -> list[str]:
        """Get available MiniMax models."""
        return ["speech-02-hd", "speech-02-turbo"]


# =============================================================================
# ElevenLabs TTS Provider
# =============================================================================


class ElevenLabsProvider(TTSProviderBase):
    """ElevenLabs TTS provider implementation."""

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or _get_api_key("ELEVENLABS_API_KEY", f"{KEYCHAIN_SERVICE}-elevenlabs-api-key")

    @property
    def provider(self) -> TTSProvider:
        return TTSProvider.ELEVENLABS

    def _get_headers(self) -> dict:
        """Get request headers."""
        return {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }

    def _get_json_headers(self) -> dict:
        """Get JSON request headers for non-audio endpoints."""
        return {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def generate_speech(self, request: TTSRequest) -> TTSResponse:
        """Generate speech using ElevenLabs API."""
        if not self._api_key:
            return TTSResponse(
                audio_data=b"",
                error="ElevenLabs API key not configured"
            )

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                # ElevenLabs expects explicit output formatting and supported voice settings.
                payload = {
                    "text": request.text,
                    "model_id": request.model,
                    "voice_settings": {
                        "speed": request.speed,
                    },
                }

                response = await client.post(
                    f"{ELEVENLABS_API_URL}/text-to-speech/{request.voice_id}",
                    headers=self._get_headers(),
                    json=payload,
                    params={"output_format": "mp3_44100_128"},
                )

                if response.status_code != 200:
                    return TTSResponse(
                        audio_data=b"",
                        error=f"ElevenLabs API error: {response.status_code} - {response.text}"
                    )

                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    return TTSResponse(
                        audio_data=b"",
                        error=f"ElevenLabs returned JSON instead of audio: {response.text}"
                    )
                if not response.content:
                    return TTSResponse(
                        audio_data=b"",
                        error="ElevenLabs returned an empty audio payload"
                    )

                # ElevenLabs returns raw audio bytes
                return TTSResponse(
                    audio_data=response.content,
                    provider=self.provider,
                    voice_id=request.voice_id,
                    model=request.model,
                )

        except Exception as e:
            return TTSResponse(
                audio_data=b"",
                error=f"ElevenLabs generation failed: {str(e)}"
            )

    async def list_voices(self) -> list[VoiceInfo]:
        """List ElevenLabs voices."""
        if not self._api_key:
            return []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    "https://api.elevenlabs.io/v2/voices",
                    headers=self._get_json_headers(),
                    params={
                        "page_size": 100,
                        "include_total_count": "true",
                    },
                )

                if response.status_code != 200:
                    return []

                data = response.json()
                voices = []
                for v in data.get("voices", []):
                    voices.append(VoiceInfo(
                        voice_id=v.get("voice_id", ""),
                        name=v.get("name", "Unknown"),
                        provider=self.provider,
                        language=v.get("labels", {}).get("language"),
                        preview_url=v.get("preview_url"),
                        is_cloned=v.get("category") == "cloned",
                    ))
                return voices

        except Exception:
            return []

    async def clone_voice(self, audio_sample: bytes, name: str) -> VoiceInfo:
        """Clone a voice from audio sample."""
        if not self._api_key:
            return VoiceInfo(
                voice_id="",
                name=name,
                provider=self.provider,
                error="ElevenLabs API key not configured",
            )

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                files = {"audio": ("sample.mp3", audio_sample, "audio/mpeg")}
                data = {"name": name}

                response = await client.post(
                    f"{ELEVENLABS_API_URL}/voices/add",
                    headers={"xi-api-key": self._api_key},
                    files=files,
                    data=data,
                )

                if response.status_code != 200:
                    return VoiceInfo(
                        voice_id="",
                        name=name,
                        provider=self.provider,
                        error=f"Clone failed: {response.status_code}",
                    )

                result = response.json()
                return VoiceInfo(
                    voice_id=result.get("voice_id", ""),
                    name=result.get("name", name),
                    provider=self.provider,
                    is_cloned=True,
                )

        except Exception as e:
            return VoiceInfo(
                voice_id="",
                name=name,
                provider=self.provider,
                error=str(e),
            )

    async def get_voice(self, voice_id: str) -> VoiceInfo:
        """Get voice information."""
        if not self._api_key:
            return VoiceInfo(voice_id=voice_id, name=voice_id, provider=self.provider)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{ELEVENLABS_API_URL}/voices/{voice_id}",
                    headers=self._get_json_headers(),
                )

                if response.status_code != 200:
                    return VoiceInfo(voice_id=voice_id, name=voice_id, provider=self.provider)

                v = response.json()
                return VoiceInfo(
                    voice_id=v.get("voice_id", voice_id),
                    name=v.get("name", voice_id),
                    provider=self.provider,
                    language=v.get("labels", {}).get("language"),
                    preview_url=v.get("preview_url"),
                    is_cloned=v.get("category") == "cloned",
                )

        except Exception:
            return VoiceInfo(voice_id=voice_id, name=voice_id, provider=self.provider)

    def get_available_models(self) -> list[str]:
        """Get available ElevenLabs models."""
        return ["eleven_multilingual_v2", "eleven_turbo_v2_5"]


# =============================================================================
# TTS Manager
# =============================================================================


class TTSManager:
    """
    Manages TTS operations across multiple providers.
    Provides a unified interface for the Voice Studio.
    """

    def __init__(self):
        self._minimax: Optional[MiniMaxProvider] = None
        self._elevenlabs: Optional[ElevenLabsProvider] = None

    @property
    def minimax(self) -> MiniMaxProvider:
        """Get MiniMax provider instance."""
        if self._minimax is None:
            self._minimax = MiniMaxProvider()
        return self._minimax

    @property
    def elevenlabs(self) -> ElevenLabsProvider:
        """Get ElevenLabs provider instance."""
        if self._elevenlabs is None:
            self._elevenlabs = ElevenLabsProvider()
        return self._elevenlabs

    def get_provider(self, provider: TTSProvider) -> TTSProviderBase:
        """Get provider instance by type."""
        if provider == TTSProvider.MINIMAX:
            return self.minimax
        elif provider == TTSProvider.ELEVENLABS:
            return self.elevenlabs
        else:
            raise ValueError(f"Unknown provider: {provider}")

    async def generate_speech(self, request: TTSRequest) -> TTSResponse:
        """Generate speech using the specified provider."""
        provider = self.get_provider(request.provider)
        return await provider.generate_speech(request)

    async def list_voices(self, provider: TTSProvider) -> list[VoiceInfo]:
        """List voices for a provider."""
        p = self.get_provider(provider)
        return await p.list_voices()

    async def list_all_voices(self) -> dict[TTSProvider, list[VoiceInfo]]:
        """List all voices from all providers."""
        return {
            TTSProvider.MINIMAX: await self.minimax.list_voices(),
            TTSProvider.ELEVENLABS: await self.elevenlabs.list_voices(),
        }

    async def clone_voice(
        self,
        provider: TTSProvider,
        audio_sample: bytes,
        name: str,
    ) -> VoiceInfo:
        """Clone a voice."""
        p = self.get_provider(provider)
        return await p.clone_voice(audio_sample, name)

    def is_provider_configured(self, provider: TTSProvider) -> bool:
        """Check if a provider is configured with API keys."""
        if provider == TTSProvider.MINIMAX:
            return bool(self.minimax._api_key)
        elif provider == TTSProvider.ELEVENLABS:
            return bool(self.elevenlabs._api_key)
        return False

    def get_available_providers(self) -> list[TTSProvider]:
        """Get list of configured providers."""
        return [
            p for p in TTSProvider
            if self.is_provider_configured(p)
        ]


# Global TTS manager instance
tts_manager = TTSManager()


# =============================================================================
# Audio Storage
# =============================================================================

# Audio files directory
AUDIO_DIR = Path("./data/audio")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def save_audio_file(
    book_id: int,
    chapter_id: int,
    provider: TTSProvider,
    audio_data: bytes,
    format: str = "mp3",
) -> str:
    """Save audio data to file and return the path."""
    filename = f"book_{book_id}_chapter_{chapter_id}_{provider.value}.{format}"
    filepath = AUDIO_DIR / filename
    filepath.write_bytes(audio_data)

    # Try to backup to GCS (async-safe, won't block)
    try:
        import backup
        backup.backup_audio_to_gcs(filepath, book_id, chapter_id)
    except Exception:
        pass  # GCS backup is best-effort, don't fail if it doesn't work

    return str(filepath)


def get_audio_path(
    book_id: int,
    chapter_id: int,
    provider: TTSProvider,
    format: str = "mp3",
) -> Optional[Path]:
    """Get the path to an existing audio file."""
    filename = f"book_{book_id}_chapter_{chapter_id}_{provider.value}.{format}"
    filepath = AUDIO_DIR / filename
    if filepath.exists():
        return filepath
    return None


def delete_audio_file(
    book_id: int,
    chapter_id: int,
    provider: TTSProvider,
    format: str = "mp3",
) -> bool:
    """Delete an audio file."""
    filepath = get_audio_path(book_id, chapter_id, provider, format)
    if filepath:
        filepath.unlink()
        return True
    return False
