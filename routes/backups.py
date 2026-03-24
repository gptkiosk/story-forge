"""
Backups routes for Story Forge API
"""
from fastapi import APIRouter, HTTPException, Request
from .auth_utils import require_auth
from db import DATABASE_PATH
import backup as backup_module

router = APIRouter()


@router.get("")
def list_backups(request: Request):
    """List all backups."""
    require_auth(request)
    backups = backup_module.list_backups()
    return [{
        "id": b["id"],
        "filename": b["filename"],
        "size": b["size"],
        "created_at": b["created_at"]
    } for b in backups]


@router.post("")
def create_backup(request: Request):
    """Create a new backup."""
    require_auth(request)
    try:
        backup = backup_module.create_backup(str(DATABASE_PATH))
        # Map backup fields to API response
        return {
            "id": Path(backup["path"]).name,
            "filename": Path(backup["path"]).name,
            "size": backup["size"],
            "created_at": backup["created_at"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{backup_id}/restore")
def restore_backup(request: Request, backup_id: str):
    """Restore from a backup."""
    require_auth(request)
    try:
        backup_module.restore_backup(backup_id)
        return {"status": "restored"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{backup_id}")
def delete_backup(request: Request, backup_id: str):
    """Delete a backup."""
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
    return {"last_backup": last_backup}
