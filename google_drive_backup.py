"""
Google Drive backup support for Story Forge.

Backups are still created as local encrypted `.sfbackup` files first, then
uploaded to a dedicated Google Drive folder when that provider is enabled.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx

import auth

DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3/files"
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


async def _authorized_headers() -> dict[str, str]:
    access_token = await auth.get_valid_access_token()
    return {"Authorization": f"Bearer {access_token}"}


def _raise_for_drive_error(response: httpx.Response) -> None:
    if response.is_success:
        return

    detail = None
    try:
        payload = response.json()
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        if isinstance(error, dict):
            detail = error.get("message")
            errors = error.get("errors")
            if not detail and isinstance(errors, list) and errors:
                first_error = errors[0]
                if isinstance(first_error, dict):
                    detail = first_error.get("message") or first_error.get("reason")
    except Exception:
        detail = None

    message = detail or response.text or f"Google Drive request failed with {response.status_code}."

    lowered = message.lower()
    if response.status_code == 403 and ("access not configured" in lowered or "google drive api" in lowered):
        raise RuntimeError(
            "Google Drive API is not enabled for this Google Cloud project yet. "
            "Enable the Google Drive API under APIs & Services and retry."
        )

    raise RuntimeError(f"Google Drive error ({response.status_code}): {message}")


async def ensure_backup_folder(folder_name: str) -> str:
    headers = await _authorized_headers()
    safe_folder_name = folder_name.replace("'", "\\'")
    query = (
        f"name = '{safe_folder_name}' and "
        f"mimeType = '{FOLDER_MIME_TYPE}' and trashed = false"
    )
    async with httpx.AsyncClient(timeout=60.0) as client:
        existing = await client.get(
            f"{DRIVE_API_BASE}/files",
            headers=headers,
            params={"q": query, "fields": "files(id,name)", "spaces": "drive"},
        )
        _raise_for_drive_error(existing)
        files = existing.json().get("files", [])
        if files:
            return files[0]["id"]

        created = await client.post(
            f"{DRIVE_API_BASE}/files",
            headers={**headers, "Content-Type": "application/json"},
            json={"name": folder_name, "mimeType": FOLDER_MIME_TYPE},
        )
        _raise_for_drive_error(created)
        return created.json()["id"]


async def upload_backup_file(local_path: str | Path, filename: str, folder_name: str) -> dict:
    file_path = Path(local_path)
    folder_id = await ensure_backup_folder(folder_name)
    headers = await _authorized_headers()
    boundary = f"storyforge-{uuid.uuid4().hex}"

    metadata = {
        "name": filename,
        "parents": [folder_id],
    }
    metadata_blob = json.dumps(metadata).encode("utf-8")
    file_blob = file_path.read_bytes()
    body = (
        f"--{boundary}\r\n"
        "Content-Type: application/json; charset=UTF-8\r\n\r\n"
    ).encode("utf-8") + metadata_blob + (
        f"\r\n--{boundary}\r\n"
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8") + file_blob + f"\r\n--{boundary}--\r\n".encode("utf-8")

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{DRIVE_UPLOAD_BASE}?uploadType=multipart&fields=id,name,createdTime,size",
            headers={
                **headers,
                "Content-Type": f'multipart/related; boundary="{boundary}"',
            },
            content=body,
        )
        _raise_for_drive_error(response)
        payload = response.json()
        return {
            "id": payload["id"],
            "filename": payload["name"],
            "created_at": payload.get("createdTime"),
            "size": int(payload.get("size") or 0),
            "source": "google_drive",
            "backup_type": "google_drive",
        }


async def list_backups(folder_name: str) -> list[dict]:
    folder_id = await ensure_backup_folder(folder_name)
    headers = await _authorized_headers()
    query = f"'{folder_id}' in parents and trashed = false"
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(
            f"{DRIVE_API_BASE}/files",
            headers=headers,
            params={
                "q": query,
                "orderBy": "createdTime desc",
                "fields": "files(id,name,createdTime,size)",
                "spaces": "drive",
            },
        )
        _raise_for_drive_error(response)
        files = response.json().get("files", [])
        return [
            {
                "id": item["id"],
                "filename": item["name"],
                "created_at": item.get("createdTime"),
                "size": int(item.get("size") or 0),
                "source": "google_drive",
                "backup_type": "google_drive",
            }
            for item in files
            if item.get("name", "").endswith(".sfbackup")
        ]


async def download_backup_file(file_id: str, target_path: str | Path) -> Path:
    headers = await _authorized_headers()
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.get(
            f"{DRIVE_API_BASE}/files/{file_id}",
            headers=headers,
            params={"alt": "media"},
        )
        _raise_for_drive_error(response)
        target.write_bytes(response.content)
        return target


async def delete_backup_file(file_id: str) -> None:
    headers = await _authorized_headers()
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.delete(f"{DRIVE_API_BASE}/files/{file_id}", headers=headers)
        _raise_for_drive_error(response)
