"""
Backups routes for Story Forge API
"""
from fastapi import APIRouter, HTTPException, Request
from .auth_utils import require_auth
from db import DATABASE_PATH
import backup as backup_module

router = APIRouter()


def _serialize_backup(backup: dict) -> dict:
    filename = backup.get("filename") or backup.get("id") or ""
    return {
        "id": filename,
        "filename": filename,
        "size": backup.get("size", 0),
        "created_at": backup.get("created_at"),
        "book_title": backup.get("book_title", "unknown"),
        "source": backup.get("source", "local"),
        "backup_type": backup.get("backup_type", "local"),
        "usb_synced": backup.get("usb_synced", False),
    }


@router.get("")
def list_backups(request: Request):
    """List all backups (local + USB SSD)."""
    require_auth(request)
    backups = backup_module.list_backups()
    return [_serialize_backup(b) for b in backups]


@router.post("")
def create_backup(request: Request):
    """Create a new backup (auto-syncs to USB SSD if available)."""
    require_auth(request)
    try:
        backup = backup_module.create_backup(str(DATABASE_PATH))
        return _serialize_backup(backup)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{backup_id}/restore")
def restore_backup(request: Request, backup_id: str):
    """Restore from a backup."""
    require_auth(request)
    try:
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
    success = backup_module.delete_backup(backup_id)
    if not success:
        raise HTTPException(status_code=404, detail="Backup not found")
    return {"status": "deleted"}


@router.get("/last")
def get_last_backup(request: Request):
    """Get info about the last backup."""
    require_auth(request)
    last_backup = backup_module.get_last_backup_info()
    if not last_backup:
        return {"last_backup": None}
    return {"last_backup": _serialize_backup(last_backup)}


@router.get("/status")
def get_backup_status(request: Request):
    """Get backup system status (USB SSD availability, counts, etc.)."""
    require_auth(request)
    return backup_module.get_backup_status()
