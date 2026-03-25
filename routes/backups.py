"""
Backups routes for Story Forge API
"""
import asyncio
from fastapi import APIRouter, HTTPException, Request
import auth
from .auth_utils import require_auth
from db import DATABASE_PATH
import backup as backup_module
from integrations import get_backup_provider, get_settings
import google_drive_backup

router = APIRouter()


def _serialize_backup(backup: dict) -> dict:
    filename = backup.get("filename") or backup.get("id") or ""
    return {
        "id": backup.get("id") or filename,
        "filename": filename,
        "size": backup.get("size", 0),
        "created_at": backup.get("created_at"),
        "book_title": backup.get("book_title", "unknown"),
        "source": backup.get("source", "local"),
        "backup_type": backup.get("backup_type", "local"),
        "usb_synced": backup.get("usb_synced", False),
    }


def _apply_backup_settings() -> dict:
    settings = get_settings()["backup"]
    provider = settings["provider"]
    if provider == "local":
        backup_module.USB_SSD_MOUNT = backup_module.Path("/__disabled__")
    else:
        backup_module.USB_SSD_MOUNT = backup_module.Path(settings.get("usb_path") or "/Volumes/xtra-ssd")
    return settings


@router.get("")
def list_backups(request: Request):
    """List all backups (local + USB SSD)."""
    require_auth(request)
    _apply_backup_settings()
    settings = get_settings()["backup"]
    provider = settings["provider"]
    if provider == "google_drive":
        if not auth.has_google_drive_access():
            raise HTTPException(status_code=403, detail="Google Drive access has not been granted yet.")
        backups = asyncio.run(google_drive_backup.list_backups(settings["google_drive"]["folder_name"]))
    else:
        backups = backup_module.list_backups()
    return [_serialize_backup(b) for b in backups]


@router.post("")
def create_backup(request: Request):
    """Create a new backup (auto-syncs to USB SSD if available)."""
    require_auth(request)
    provider = get_backup_provider()
    _apply_backup_settings()
    if provider == "google_drive":
        settings = get_settings()["backup"]
        if not auth.has_google_drive_access():
            raise HTTPException(status_code=403, detail="Google Drive access has not been granted yet.")
    try:
        backup = backup_module.create_backup(str(DATABASE_PATH))
        if provider == "google_drive":
            backup = asyncio.run(
                google_drive_backup.upload_backup_file(
                    local_path=backup["path"],
                    filename=backup["filename"],
                    folder_name=settings["google_drive"]["folder_name"],
                )
            )
        return _serialize_backup(backup)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{backup_id}/restore")
def restore_backup(request: Request, backup_id: str):
    """Restore from a backup."""
    require_auth(request)
    _apply_backup_settings()
    provider = get_backup_provider()
    try:
        if provider == "google_drive":
            if not auth.has_google_drive_access():
                raise HTTPException(status_code=403, detail="Google Drive access has not been granted yet.")
            downloaded = asyncio.run(
                google_drive_backup.download_backup_file(
                    backup_id,
                    backup_module.BACKUP_DIR / f"gdrive_{backup_id}.sfbackup",
                )
            )
            result = backup_module.restore_local_backup(downloaded, DATABASE_PATH)
            return {"status": "restored", **result}
        result = backup_module.restore_backup(backup_id)
        return {"status": "restored", **result}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Backup not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{backup_id}")
def delete_backup(request: Request, backup_id: str):
    """Delete a backup from local and USB SSD."""
    require_auth(request)
    _apply_backup_settings()
    provider = get_backup_provider()
    if provider == "google_drive":
        if not auth.has_google_drive_access():
            raise HTTPException(status_code=403, detail="Google Drive access has not been granted yet.")
        asyncio.run(google_drive_backup.delete_backup_file(backup_id))
        return {"status": "deleted"}
    success = backup_module.delete_backup(backup_id)
    if not success:
        raise HTTPException(status_code=404, detail="Backup not found")
    return {"status": "deleted"}


@router.get("/last")
def get_last_backup(request: Request):
    """Get info about the last backup."""
    require_auth(request)
    _apply_backup_settings()
    last_backup = backup_module.get_last_backup_info()
    if not last_backup:
        return {"last_backup": None}
    return {"last_backup": _serialize_backup(last_backup)}


@router.get("/status")
def get_backup_status(request: Request):
    """Get backup system status (USB SSD availability, counts, etc.)."""
    require_auth(request)
    settings = _apply_backup_settings()
    status = backup_module.get_backup_status()
    status["provider"] = settings["provider"]
    status["google_drive"] = settings["google_drive"]
    status["google_drive"]["connected"] = auth.has_google_drive_access()
    return status
