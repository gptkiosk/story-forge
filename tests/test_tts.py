from types import SimpleNamespace

import pytest

import tts


class FakeAsyncClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None, params=None):
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "params": params,
            }
        )
        return self.response


@pytest.mark.asyncio
async def test_elevenlabs_generation_uses_supported_payload(monkeypatch):
    response = SimpleNamespace(
        status_code=200,
        content=b"fake-mp3-audio",
        headers={"content-type": "audio/mpeg"},
        text="",
    )
    client = FakeAsyncClient(response)
    monkeypatch.setattr(tts.httpx, "AsyncClient", lambda timeout=120.0: client)

    provider = tts.ElevenLabsProvider(api_key="test-key")
    result = await provider.generate_speech(
        tts.TTSRequest(
            text="Mic check line",
            provider=tts.TTSProvider.ELEVENLABS,
            voice_id="voice_jamal",
            model="eleven_turbo_v2_5",
            speed=0.96,
        )
    )

    assert result.audio_data == b"fake-mp3-audio"
    assert client.calls
    call = client.calls[0]
    assert call["params"] == {"output_format": "mp3_44100_128"}
    assert call["json"]["voice_settings"] == {"speed": 0.96}
    assert "pitch" not in call["json"]["voice_settings"]
    assert call["headers"]["Accept"] == "audio/mpeg"


@pytest.mark.asyncio
async def test_elevenlabs_generation_rejects_json_payloads(monkeypatch):
    response = SimpleNamespace(
        status_code=200,
        content=b'{"detail":"bad response"}',
        headers={"content-type": "application/json"},
        text='{"detail":"bad response"}',
    )
    client = FakeAsyncClient(response)
    monkeypatch.setattr(tts.httpx, "AsyncClient", lambda timeout=120.0: client)

    provider = tts.ElevenLabsProvider(api_key="test-key")
    result = await provider.generate_speech(
        tts.TTSRequest(
            text="Mic check line",
            provider=tts.TTSProvider.ELEVENLABS,
            voice_id="voice_jamal",
            model="eleven_turbo_v2_5",
        )
    )

    assert result.error
    assert "JSON instead of audio" in result.error
