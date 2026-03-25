"""
Provider settings and integration status for Story Forge.

This module keeps install-level integration settings in a local JSON file and
stores provider secrets in macOS Keychain when available.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

KEYCHAIN_SERVICE = "story-forge"
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
INTEGRATIONS_PATH = DATA_DIR / "integrations.json"

OPENROUTER_KEYCHAIN_KEY = "story-forge-openrouter-api-key"

DEFAULT_SETTINGS = {
    "ai": {
        "provider": "openclaw",
        "openclaw": {
            "agent_id": os.environ.get("LIBBY_AGENT_ID", "libby"),
            "agent_name": "Libby",
            "transport": os.environ.get("LIBBY_TRANSPORT", "openclaw"),
        },
        "openrouter": {
            "base_url": os.environ.get("OPENROUTER_API_URL", "https://openrouter.ai/api/v1"),
            "model": os.environ.get("OPENROUTER_MODEL", "openai/gpt-4.1-mini"),
            "site_url": os.environ.get("OPENROUTER_SITE_URL", "http://localhost:5173"),
            "app_name": os.environ.get("OPENROUTER_APP_NAME", "Story Forge"),
        },
    },
    "backup": {
        "provider": "usb_ssd",
        "usb_path": os.environ.get("STORY_FORGE_USB_PATH", "/Volumes/xtra-ssd"),
        "google_drive": {
            "enabled": False,
            "folder_name": "Story Forge Backups",
        },
    },
}


def _deep_merge(base: dict, updates: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_raw_settings() -> dict:
    if not INTEGRATIONS_PATH.exists():
        return copy.deepcopy(DEFAULT_SETTINGS)
    try:
        loaded = json.loads(INTEGRATIONS_PATH.read_text())
    except Exception:
        return copy.deepcopy(DEFAULT_SETTINGS)
    return _deep_merge(DEFAULT_SETTINGS, loaded if isinstance(loaded, dict) else {})


def _save_raw_settings(settings: dict) -> None:
    INTEGRATIONS_PATH.write_text(json.dumps(settings, indent=2, sort_keys=True))


def _get_secret(key: str) -> str:
    try:
        import keyring
        return keyring.get_password(KEYCHAIN_SERVICE, key) or ""
    except Exception:
        return ""


def _set_secret(key: str, value: str | None) -> None:
    try:
        import keyring
        if value:
            keyring.set_password(KEYCHAIN_SERVICE, key, value)
        else:
            try:
                keyring.delete_password(KEYCHAIN_SERVICE, key)
            except Exception:
                pass
    except Exception:
        pass


def get_settings() -> dict:
    settings = _load_raw_settings()
    sanitized = copy.deepcopy(settings)
    sanitized["ai"]["openrouter"]["api_key_configured"] = bool(_get_secret(OPENROUTER_KEYCHAIN_KEY))
    sanitized["backup"]["google_drive"]["coming_soon"] = False
    return sanitized


def update_ai_settings(payload: dict) -> dict:
    settings = _load_raw_settings()
    ai_settings = payload or {}
    provider = ai_settings.get("provider", settings["ai"]["provider"])
    if provider not in {"openclaw", "openrouter"}:
        raise ValueError("Unsupported AI provider.")

    next_settings = copy.deepcopy(settings)
    next_settings["ai"] = _deep_merge(next_settings["ai"], {k: v for k, v in ai_settings.items() if k != "openrouter_api_key"})
    next_settings["ai"]["provider"] = provider
    _save_raw_settings(next_settings)

    if "openrouter_api_key" in ai_settings:
        _set_secret(OPENROUTER_KEYCHAIN_KEY, ai_settings.get("openrouter_api_key"))

    return get_settings()["ai"]


def update_backup_settings(payload: dict) -> dict:
    settings = _load_raw_settings()
    backup_settings = payload or {}
    provider = backup_settings.get("provider", settings["backup"]["provider"])
    if provider not in {"local", "usb_ssd", "google_drive"}:
        raise ValueError("Unsupported backup provider.")

    next_settings = copy.deepcopy(settings)
    next_settings["backup"] = _deep_merge(next_settings["backup"], backup_settings)
    next_settings["backup"]["provider"] = provider
    _save_raw_settings(next_settings)
    return get_settings()["backup"]


def get_ai_provider() -> str:
    return get_settings()["ai"]["provider"]


def get_backup_provider() -> str:
    return get_settings()["backup"]["provider"]


def get_openclaw_settings() -> dict:
    return get_settings()["ai"]["openclaw"]


def get_openrouter_settings() -> dict:
    settings = get_settings()["ai"]["openrouter"]
    return {
        **settings,
        "api_key": _get_secret(OPENROUTER_KEYCHAIN_KEY),
    }


def get_integration_status() -> dict:
    settings = get_settings()
    ai_settings = settings["ai"]
    backup_settings = settings["backup"]

    import backup as backup_module
    import auth
    from libby import libby_client

    openclaw_available = False
    try:
        openclaw_available = libby_client._openclaw_available()
    except Exception:
        openclaw_available = False

    usb_available = backup_module.is_usb_ssd_available()

    return {
        "ai": {
            "provider": ai_settings["provider"],
            "openclaw": {
                **ai_settings["openclaw"],
                "available": openclaw_available,
            },
            "openrouter": {
                **{k: v for k, v in ai_settings["openrouter"].items() if k != "api_key"},
                "configured": ai_settings["openrouter"].get("api_key_configured", False),
            },
        },
        "backup": {
            "provider": backup_settings["provider"],
            "usb_ssd": {
                "path": backup_settings["usb_path"],
                "available": usb_available,
            },
            "google_drive": {
                **backup_settings["google_drive"],
                "configured": auth.has_google_drive_access(),
                "coming_soon": False,
            },
        },
    }
