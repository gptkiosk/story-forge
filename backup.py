"""
Backup module for Story Forge.
Provides encrypted SQLite backup and restore with local + USB SSD sync.

Local backups are encrypted with Fernet and stored in ./data/backups/.
When a USB SSD is mounted, backups are synced there for redundancy.
"""

import json
import gzip
import hashlib
import logging
import os
import sqlite3
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet
import keyring

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

PROJECT_ROOT = Path(__file__).parent
BACKUP_DIR = PROJECT_ROOT / "data" / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

KEYCHAIN_SERVICE = "story-forge"
KEYCHAIN_BACKUP_KEY = "backup-encryption-key"

# Backup retention
MAX_BACKUPS = 10
MAX_AGE_DAYS = 30

# USB SSD Configuration
USB_SSD_MOUNT = Path(os.environ.get("STORY_FORGE_USB_PATH", "/Volumes/xtra-ssd"))
USB_SSD_BACKUP_DIR = USB_SSD_MOUNT / "story-forge-backups"

SIDECAR_RELATIVE_PATHS = [
    Path("voice_maps"),
    Path("style_studio"),
    Path("integrations.json"),
]


# =============================================================================
# USB SSD Detection
# =============================================================================

def is_usb_ssd_available() -> bool:
    """Check if the USB SSD is mounted and writable."""
    return USB_SSD_MOUNT.exists() and USB_SSD_MOUNT.is_dir()


def ensure_usb_backup_dir() -> bool:
    """Create the backup directory on USB SSD if it doesn't exist."""
    if not is_usb_ssd_available():
        return False
    try:
        USB_SSD_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Failed to create USB backup dir: {e}")
        return False


# =============================================================================
# Encryption Utilities
# =============================================================================


def _get_or_create_backup_key() -> str:
    """Get backup encryption key from keychain or create new one."""
    key = keyring.get_password(KEYCHAIN_SERVICE, KEYCHAIN_BACKUP_KEY)
    if key is None:
        key = Fernet.generate_key().decode()
        keyring.set_password(KEYCHAIN_SERVICE, KEYCHAIN_BACKUP_KEY, key)
    return key


class BackupEncryptor:
    """Handles encryption/decryption of backup files."""

    def __init__(self):
        self._cipher: Fernet | None = None

    @property
    def cipher(self) -> Fernet:
        if self._cipher is None:
            key = _get_or_create_backup_key()
            self._cipher = Fernet(key.encode())
        return self._cipher

    def encrypt(self, data: bytes) -> bytes:
        return self.cipher.encrypt(data)

    def decrypt(self, data: bytes) -> bytes:
        return self.cipher.decrypt(data)


# Global encryptor instance
backup_encryptor = BackupEncryptor()


def _iter_sidecar_files() -> list[Path]:
    files: list[Path] = []
    for relative_path in SIDECAR_RELATIVE_PATHS:
        absolute_path = DATA_DIR / relative_path
        if absolute_path.is_file():
            files.append(absolute_path)
        elif absolute_path.is_dir():
            files.extend([path for path in absolute_path.rglob("*") if path.is_file()])
    return files


def _relative_to_data(path: Path) -> str:
    return path.relative_to(DATA_DIR).as_posix()


def _extract_sidecar_book_id(relative_path: str) -> int | None:
    parts = relative_path.split("/")
    for part in parts:
        if part.startswith("book_"):
            try:
                return int(part.split("_", 1)[1])
            except Exception:
                return None
    return None


def _collect_sidecars() -> dict[str, str]:
    return {
        _relative_to_data(path): path.read_bytes().hex()
        for path in _iter_sidecar_files()
    }


def _build_backup_manifest(source_db_path: str | Path, sidecars: dict[str, str] | None = None) -> dict:
    manifest = {
        "components": {
            "books": {"count": 0, "books": []},
            "chapters": {"count": 0, "chapters": []},
            "voice_rosters": {"count": 0, "book_ids": []},
            "style_studio": {"count": 0, "book_ids": []},
            "settings": {"has_user_preferences": False, "has_integrations": False},
        }
    }

    connection = sqlite3.connect(str(source_db_path))
    try:
        books = connection.execute(
            "SELECT id, title FROM books ORDER BY id"
        ).fetchall()
        manifest["components"]["books"] = {
            "count": len(books),
            "books": [{"id": row[0], "title": row[1]} for row in books[:100]],
        }

        chapters = connection.execute(
            "SELECT id, book_id, title, \"order\" FROM chapters ORDER BY book_id, \"order\", id"
        ).fetchall()
        manifest["components"]["chapters"] = {
            "count": len(chapters),
            "chapters": [
                {"id": row[0], "book_id": row[1], "title": row[2], "order": row[3]}
                for row in chapters[:200]
            ],
        }

        table_names = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        voice_book_ids = set()
        style_book_ids = set()
        if "character_voices" in table_names:
            voice_book_ids = {
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT book_id FROM character_voices ORDER BY book_id"
                ).fetchall()
            }
        if "book_style_profiles" in table_names:
            style_book_ids = {
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT book_id FROM book_style_profiles ORDER BY book_id"
                ).fetchall()
            }

        user_preferences_count = (
            connection.execute("SELECT COUNT(*) FROM user_preferences").fetchone()[0]
            if "user_preferences" in table_names
            else 0
        )
        manifest["components"]["settings"]["has_user_preferences"] = user_preferences_count > 0
    finally:
        connection.close()

    for relative_path in (sidecars or {}).keys():
        book_id = _extract_sidecar_book_id(relative_path)
        if relative_path.startswith("voice_maps/") and book_id is not None:
            voice_book_ids.add(book_id)
        if relative_path.startswith("style_studio/") and book_id is not None:
            style_book_ids.add(book_id)
        if relative_path == "integrations.json":
            manifest["components"]["settings"]["has_integrations"] = True

    manifest["components"]["voice_rosters"] = {
        "count": len(voice_book_ids),
        "book_ids": sorted(voice_book_ids),
    }
    manifest["components"]["style_studio"] = {
        "count": len(style_book_ids),
        "book_ids": sorted(style_book_ids),
    }
    return manifest


def _read_backup_archive(backup_path: str | Path) -> tuple[dict, dict]:
    backup_file = Path(backup_path)
    with gzip.GzipFile(backup_file, "rb") as gz:
        metadata_len_bytes = gz.read(4)
        if len(metadata_len_bytes) < 4:
            raise ValueError("Invalid backup file: missing metadata length")
        metadata_len = int.from_bytes(metadata_len_bytes, byteorder="big")
        metadata_json = gz.read(metadata_len)
        metadata = json.loads(metadata_json.decode("utf-8"))
        encrypted_data = gz.read()

    decrypted = backup_encryptor.decrypt(encrypted_data)
    archive = json.loads(decrypted.decode("utf-8"))
    return metadata, archive


def _restore_sidecars(sidecars: dict[str, str], components: set[str] | None = None, book_ids: set[int] | None = None) -> None:
    components = components or {"voice_rosters", "style_studio", "settings"}
    if not book_ids:
        if "voice_rosters" in components:
            shutil.rmtree(DATA_DIR / "voice_maps", ignore_errors=True)
        if "style_studio" in components:
            shutil.rmtree(DATA_DIR / "style_studio", ignore_errors=True)
        if "settings" in components:
            try:
                (DATA_DIR / "integrations.json").unlink()
            except FileNotFoundError:
                pass
    if "voice_rosters" in components and book_ids:
        for book_id in book_ids:
            shutil.rmtree(DATA_DIR / "voice_maps" / f"book_{book_id}", ignore_errors=True)
    if "style_studio" in components and book_ids:
        for book_id in book_ids:
            shutil.rmtree(DATA_DIR / "style_studio" / f"book_{book_id}", ignore_errors=True)

    for relative_path, hex_content in (sidecars or {}).items():
        book_id = _extract_sidecar_book_id(relative_path)
        if relative_path.startswith("voice_maps/"):
            if "voice_rosters" not in components:
                continue
            if book_ids and book_id is not None and book_id not in book_ids:
                continue
        elif relative_path.startswith("style_studio/"):
            if "style_studio" not in components:
                continue
            if book_ids and book_id is not None and book_id not in book_ids:
                continue
        elif relative_path == "integrations.json":
            if "settings" not in components:
                continue
        else:
            continue

        target = DATA_DIR / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(bytes.fromhex(hex_content))


def inspect_local_backup(backup_path: str | Path) -> dict:
    metadata, archive = _read_backup_archive(backup_path)
    if metadata.get("manifest"):
        manifest = metadata["manifest"]
    else:
        source_db_path = _materialize_archive_db(archive)
        try:
            manifest = _build_backup_manifest(
                source_db_path=source_db_path,
                sidecars=archive.get("sidecars") or {},
            )
        finally:
            shutil.rmtree(source_db_path.parent, ignore_errors=True)
    return {
        "metadata": metadata,
        "manifest": manifest,
    }


def _materialize_archive_db(archive: dict) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="story_forge_backup_"))
    db_path = temp_dir / "backup.db"
    db_path.write_bytes(bytes.fromhex(archive["main_db"]))
    wal_hex = archive.get("wal") or ""
    if wal_hex:
        Path(str(db_path) + "-wal").write_bytes(bytes.fromhex(wal_hex))
    return db_path


def _copy_selected_rows(source_conn: sqlite3.Connection, target_conn: sqlite3.Connection, table: str, where_clause: str = "", params: tuple = ()) -> None:
    source_exists = source_conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    target_exists = target_conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if not source_exists or not target_exists:
        return
    rows = source_conn.execute(f"SELECT * FROM {table} {where_clause}", params).fetchall()
    if not rows:
        return
    column_info = source_conn.execute(f"PRAGMA table_info({table})").fetchall()
    columns = [info[1] for info in column_info]
    placeholders = ", ".join(["?"] * len(columns))
    quoted_columns = ", ".join(columns)
    target_conn.executemany(
        f"INSERT OR REPLACE INTO {table} ({quoted_columns}) VALUES ({placeholders})",
        rows,
    )


def restore_backup_selection(
    backup_path: str | Path,
    *,
    components: list[str],
    target_db_path: str | Path,
    book_ids: list[int] | None = None,
    chapter_ids: list[int] | None = None,
) -> dict:
    requested = set(components)
    allowed = {"books", "chapters", "voice_rosters", "style_studio", "settings"}
    if not requested or not requested.issubset(allowed):
        raise RuntimeError("Invalid restore component selection.")

    selected_book_ids = set(book_ids or [])
    selected_chapter_ids = set(chapter_ids or [])
    metadata, archive = _read_backup_archive(backup_path)
    source_db_path = _materialize_archive_db(archive)
    source_conn = sqlite3.connect(str(source_db_path))
    target_conn = sqlite3.connect(str(target_db_path))
    try:
        target_conn.execute("PRAGMA foreign_keys=OFF")

        if "books" in requested:
            if selected_book_ids:
                placeholders = ", ".join(["?"] * len(selected_book_ids))
                _copy_selected_rows(
                    source_conn,
                    target_conn,
                    "books",
                    f"WHERE id IN ({placeholders})",
                    tuple(sorted(selected_book_ids)),
                )
            else:
                _copy_selected_rows(source_conn, target_conn, "books")

        if "chapters" in requested:
            if selected_chapter_ids:
                placeholders = ", ".join(["?"] * len(selected_chapter_ids))
                chapter_rows = source_conn.execute(
                    f'SELECT book_id FROM chapters WHERE id IN ({placeholders})',
                    tuple(sorted(selected_chapter_ids)),
                ).fetchall()
                chapter_book_ids = {row[0] for row in chapter_rows}
                missing_books = chapter_book_ids - selected_book_ids
                if missing_books and "books" not in requested:
                    raise RuntimeError("Restoring chapters independently requires their parent books to already exist or be selected too.")
                _copy_selected_rows(
                    source_conn,
                    target_conn,
                    "chapters",
                    f'WHERE id IN ({placeholders})',
                    tuple(sorted(selected_chapter_ids)),
                )
            elif selected_book_ids:
                placeholders = ", ".join(["?"] * len(selected_book_ids))
                _copy_selected_rows(
                    source_conn,
                    target_conn,
                    "chapters",
                    f"WHERE book_id IN ({placeholders})",
                    tuple(sorted(selected_book_ids)),
                )
            else:
                _copy_selected_rows(source_conn, target_conn, "chapters")

        if "voice_rosters" in requested:
            if selected_book_ids:
                placeholders = ", ".join(["?"] * len(selected_book_ids))
                _copy_selected_rows(
                    source_conn,
                    target_conn,
                    "character_voices",
                    f"WHERE book_id IN ({placeholders})",
                    tuple(sorted(selected_book_ids)),
                )
            else:
                _copy_selected_rows(source_conn, target_conn, "character_voices")

        if "style_studio" in requested:
            if selected_book_ids:
                placeholders = ", ".join(["?"] * len(selected_book_ids))
                _copy_selected_rows(
                    source_conn,
                    target_conn,
                    "book_style_profiles",
                    f"WHERE book_id IN ({placeholders})",
                    tuple(sorted(selected_book_ids)),
                )
            else:
                _copy_selected_rows(source_conn, target_conn, "book_style_profiles")

        if "settings" in requested:
            _copy_selected_rows(source_conn, target_conn, "users")
            _copy_selected_rows(source_conn, target_conn, "user_preferences")

        target_conn.commit()
    finally:
        source_conn.close()
        target_conn.close()
        shutil.rmtree(source_db_path.parent, ignore_errors=True)

    _restore_sidecars(archive.get("sidecars") or {}, requested, selected_book_ids or None)

    return {
        "restored_at": datetime.now().isoformat(),
        "backup_created_at": metadata.get("created_at"),
        "components": sorted(requested),
        "book_ids": sorted(selected_book_ids),
        "chapter_ids": sorted(selected_chapter_ids),
    }


# =============================================================================
# Local Backup Operations
# =============================================================================


def create_local_backup(source_db_path: str | Path, book_title: str = "story_forge") -> dict:
    """
    Create an encrypted backup of the SQLite database.

    Args:
        source_db_path: Path to the source database file
        book_title: Optional title for the backup

    Returns:
        dict with backup metadata (path, size, timestamp, checksum)
    """
    source_path = Path(source_db_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Database file not found: {source_path}")

    # Generate backup filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sanitized_title = "".join(c if c.isalnum() else "_" for c in book_title)
    backup_filename = f"{sanitized_title}_{timestamp}.sfbackup"
    backup_path = BACKUP_DIR / backup_filename

    sidecars = _collect_sidecars()

    # Create backup metadata
    metadata = {
        "created_at": datetime.now().isoformat(),
        "source_db": str(source_path),
        "source_size": source_path.stat().st_size,
        "book_title": book_title,
        "version": "1.0",
        "backup_type": "local",
    }
    metadata["manifest"] = _build_backup_manifest(source_path, sidecars)

    try:
        # Create a checkpoint first to ensure all WAL data is in main db
        from db import engine
        with engine.connect() as conn:
            from sqlalchemy import text
            conn.execute(text("PRAGMA wal_checkpoint(FULL)"))
            conn.commit()

        # Read database file
        db_data = source_path.read_bytes()

        # Also include WAL if exists
        source_wal = Path(str(source_path) + "-wal")
        wal_data = b""
        if source_wal.exists():
            wal_data = source_wal.read_bytes()
            metadata["wal_size"] = len(wal_data)

        # Create backup archive
        archive_data = {
            "main_db": db_data,
            "wal": wal_data,
            "metadata": metadata,
            "sidecars": sidecars,
        }

        # Serialize metadata as JSON
        metadata_json = json.dumps(metadata, indent=2).encode("utf-8")

        # Create backup file structure:
        # [4 bytes: metadata length][metadata JSON][encrypted archive]
        metadata_len = len(metadata_json)
        metadata_len_bytes = metadata_len.to_bytes(4, byteorder="big")

        # Encrypt the archive data
        archive_bytes = json.dumps(
            {k: (v.hex() if isinstance(v, bytes) else v) for k, v in archive_data.items()}
        ).encode("utf-8")
        encrypted_data = backup_encryptor.encrypt(archive_bytes)

        # Write backup file (gzip compressed)
        with gzip.GzipFile(backup_path, "wb") as gz:
            gz.write(metadata_len_bytes)
            gz.write(metadata_json)
            gz.write(encrypted_data)

        # Calculate checksum
        checksum = hashlib.sha256(backup_path.read_bytes()).hexdigest()

        backup_info = {
            "path": str(backup_path),
            "filename": backup_filename,
            "size": backup_path.stat().st_size,
            "created_at": metadata["created_at"],
            "checksum": checksum,
            "source_size": metadata["source_size"],
            "backup_type": "local",
        }

        logger.info(f"Local backup created: {backup_path.name} ({backup_info['size']:,} bytes)")

        # Sync to USB SSD if available
        usb_synced = sync_to_usb(backup_path)
        if usb_synced:
            backup_info["usb_synced"] = True
            backup_info["usb_path"] = str(USB_SSD_BACKUP_DIR / backup_filename)

        return backup_info

    except Exception as e:
        if backup_path.exists():
            backup_path.unlink()
        raise RuntimeError(f"Local backup failed: {e}")


def restore_local_backup(backup_path: str | Path, target_db_path: str | Path) -> dict:
    """
    Restore a database from an encrypted local backup.

    Args:
        backup_path: Path to the backup file
        target_db_path: Path to restore the database to

    Returns:
        dict with restore metadata
    """
    backup_file = Path(backup_path)
    if not backup_file.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_file}")

    target_path = Path(target_db_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Read and decompress backup
        with gzip.GzipFile(backup_file, "rb") as gz:
            metadata_len_bytes = gz.read(4)
            if len(metadata_len_bytes) < 4:
                raise ValueError("Invalid backup file: missing metadata length")

            metadata_len = int.from_bytes(metadata_len_bytes, byteorder="big")
            metadata_json = gz.read(metadata_len)
            metadata = json.loads(metadata_json.decode("utf-8"))

            encrypted_data = gz.read()

        # Decrypt
        decrypted = backup_encryptor.decrypt(encrypted_data)
        archive = json.loads(decrypted.decode("utf-8"))

        # Restore main database
        main_db_data = bytes.fromhex(archive["main_db"])

        # Close existing connections
        from db import engine
        engine.dispose()

        # Write main database
        target_path.write_bytes(main_db_data)

        # Restore WAL if present
        wal_hex = archive.get("wal", "")
        if wal_hex:
            wal_path = Path(str(target_path) + "-wal")
            wal_path.write_bytes(bytes.fromhex(wal_hex))

        _restore_sidecars(archive.get("sidecars") or {})

        restore_info = {
            "restored_at": datetime.now().isoformat(),
            "backup_created_at": metadata["created_at"],
            "source_size": metadata["source_size"],
            "target_path": str(target_path),
        }

        logger.info(f"Local backup restored to: {target_path}")
        return restore_info

    except Exception as e:
        raise RuntimeError(f"Restore failed: {e}")


# =============================================================================
# USB SSD Sync Operations
# =============================================================================


def sync_to_usb(local_backup_path: Path) -> bool:
    """
    Copy a backup file to the USB SSD.

    Args:
        local_backup_path: Path to the local backup file

    Returns:
        True if successful, False otherwise
    """
    if not ensure_usb_backup_dir():
        logger.info("USB SSD not available, skipping sync")
        return False

    try:
        dest = USB_SSD_BACKUP_DIR / local_backup_path.name
        shutil.copy2(str(local_backup_path), str(dest))
        logger.info(f"Backup synced to USB SSD: {dest}")
        return True
    except Exception as e:
        logger.error(f"Failed to sync to USB SSD: {e}")
        return False


def sync_from_usb(backup_filename: str) -> Optional[Path]:
    """
    Copy a backup from USB SSD to local storage.

    Args:
        backup_filename: Name of the backup file

    Returns:
        Path to the local copy, or None if failed
    """
    if not is_usb_ssd_available():
        return None

    usb_path = USB_SSD_BACKUP_DIR / backup_filename
    if not usb_path.exists():
        return None

    try:
        local_path = BACKUP_DIR / backup_filename
        shutil.copy2(str(usb_path), str(local_path))
        logger.info(f"Backup synced from USB SSD: {local_path}")
        return local_path
    except Exception as e:
        logger.error(f"Failed to sync from USB SSD: {e}")
        return None


def list_usb_backups() -> list[dict]:
    """List backups on the USB SSD."""
    if not is_usb_ssd_available() or not USB_SSD_BACKUP_DIR.exists():
        return []

    backups = []
    for backup_file in USB_SSD_BACKUP_DIR.glob("*.sfbackup"):
        try:
            with gzip.GzipFile(backup_file, "rb") as gz:
                metadata_len_bytes = gz.read(4)
                if len(metadata_len_bytes) < 4:
                    continue
                metadata_len = int.from_bytes(metadata_len_bytes, byteorder="big")
                if metadata_len <= 0 or metadata_len > 1024 * 1024:
                    continue
                metadata_json = gz.read(metadata_len)
                metadata = json.loads(metadata_json.decode("utf-8"))

            backups.append({
                "filename": backup_file.name,
                "path": str(backup_file),
                "size": backup_file.stat().st_size,
                "created_at": metadata.get("created_at"),
                "book_title": metadata.get("book_title", "unknown"),
                "source_size": metadata.get("source_size", 0),
                "backup_type": "usb_ssd",
                "source": "usb_ssd",
            })
        except Exception:
            continue

    backups.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return backups


# =============================================================================
# Backup Management (Main Entry Points)
# =============================================================================


def create_backup(source_db_path: str | Path, book_title: str = "story_forge") -> dict:
    """
    Create a backup. Syncs to USB SSD if available.
    This is the main entry point for backup creation.
    """
    return create_local_backup(source_db_path, book_title)


def restore_backup(backup_id: str, target_db_path: str | Path = None) -> dict:
    """
    Restore a database from backup by backup ID (filename).

    Looks in local backups first, then USB SSD.
    """
    if target_db_path is None:
        target_db_path = DATA_DIR / "story_forge.db"

    # Try local first
    local_path = BACKUP_DIR / backup_id
    if local_path.exists():
        return restore_local_backup(local_path, target_db_path)

    # Try USB SSD
    if is_usb_ssd_available():
        usb_path = USB_SSD_BACKUP_DIR / backup_id
        if usb_path.exists():
            # Sync to local first, then restore
            synced = sync_from_usb(backup_id)
            if synced:
                return restore_local_backup(synced, target_db_path)

    raise FileNotFoundError(f"Backup not found: {backup_id}")


def delete_backup(backup_id: str) -> bool:
    """
    Delete a backup by filename from local and USB SSD.
    """
    deleted = False

    # Delete local
    local_path = BACKUP_DIR / backup_id
    if local_path.exists():
        local_path.unlink()
        deleted = True
        logger.info(f"Deleted local backup: {backup_id}")

    # Delete from USB SSD
    if is_usb_ssd_available() and USB_SSD_BACKUP_DIR.exists():
        usb_path = USB_SSD_BACKUP_DIR / backup_id
        if usb_path.exists():
            usb_path.unlink()
            deleted = True
            logger.info(f"Deleted USB backup: {backup_id}")

    return deleted


def list_local_backups() -> list[dict]:
    """List all local backups with metadata."""
    backups = []

    for backup_file in BACKUP_DIR.glob("*.sfbackup"):
        try:
            with gzip.GzipFile(backup_file, "rb") as gz:
                metadata_len_bytes = gz.read(4)
                if len(metadata_len_bytes) < 4:
                    continue
                metadata_len = int.from_bytes(metadata_len_bytes, byteorder="big")
                if metadata_len <= 0 or metadata_len > 1024 * 1024:
                    continue
                metadata_json = gz.read(metadata_len)
                metadata = json.loads(metadata_json.decode("utf-8"))

            backups.append({
                "filename": backup_file.name,
                "path": str(backup_file),
                "size": backup_file.stat().st_size,
                "created_at": metadata.get("created_at"),
                "book_title": metadata.get("book_title", "unknown"),
                "source_size": metadata.get("source_size", 0),
                "backup_type": metadata.get("backup_type", "local"),
                "source": "local",
            })
        except Exception:
            continue

    backups.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return backups


def list_backups() -> list[dict]:
    """List all backups (local and USB SSD)."""
    local = list_local_backups()
    usb = list_usb_backups()

    # Merge, deduplicating by filename (prefer local)
    seen = {b["filename"] for b in local}
    for b in usb:
        if b["filename"] not in seen:
            local.append(b)

    local.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return local


def cleanup_old_local_backups() -> dict:
    """Remove old local backups beyond retention policy."""
    backups = list_local_backups()

    deleted_count = 0
    freed_space = 0
    cutoff_time = datetime.now()

    for backup in backups:
        try:
            created_at = datetime.fromisoformat(backup["created_at"])
            age_days = (cutoff_time - created_at).days

            if age_days > MAX_AGE_DAYS:
                backup_path = Path(backup["path"])
                if backup_path.exists():
                    freed_space += backup_path.stat().st_size
                    backup_path.unlink()
                    deleted_count += 1
        except Exception:
            continue

    # Check count limit
    remaining = list_local_backups()
    if len(remaining) > MAX_BACKUPS:
        for backup in remaining[MAX_BACKUPS:]:
            try:
                backup_path = Path(backup["path"])
                if backup_path.exists():
                    freed_space += backup_path.stat().st_size
                    backup_path.unlink()
                    deleted_count += 1
            except Exception:
                continue

    logger.info(f"Cleanup: deleted {deleted_count} backups, freed {freed_space:,} bytes")
    return {"deleted_count": deleted_count, "freed_space": freed_space}


def verify_backup(backup_path: str | Path) -> bool:
    """Verify a backup file is valid and can be decrypted."""
    backup_file = Path(backup_path)
    if not backup_file.exists():
        return False

    try:
        with gzip.GzipFile(backup_file, "rb") as gz:
            metadata_len_bytes = gz.read(4)
            if len(metadata_len_bytes) < 4:
                return False

            metadata_len = int.from_bytes(metadata_len_bytes, byteorder="big")
            if metadata_len <= 0 or metadata_len > 1024 * 1024:
                return False

            metadata_json = gz.read(metadata_len)
            metadata = json.loads(metadata_json.decode("utf-8"))

            required_fields = ["created_at", "source_db", "source_size"]
            for field in required_fields:
                if field not in metadata:
                    return False

            encrypted_data = gz.read()
            if len(encrypted_data) < 16:
                return False

            backup_encryptor.decrypt(encrypted_data)

        return True
    except Exception:
        return False


# =============================================================================
# Backup Status / Info
# =============================================================================


def get_last_backup_info() -> Optional[dict]:
    """Get information about the most recent backup."""
    backups = list_backups()
    return backups[0] if backups else None


def get_backup_status() -> dict:
    """Get overall backup system status."""
    local_backups = list_local_backups()
    usb_available = is_usb_ssd_available()
    usb_backups = list_usb_backups() if usb_available else []

    return {
        "local_count": len(local_backups),
        "usb_ssd_available": usb_available,
        "usb_ssd_path": str(USB_SSD_MOUNT),
        "usb_count": len(usb_backups),
        "last_backup": local_backups[0] if local_backups else None,
    }


def should_create_backup(min_interval_hours: int = 24) -> bool:
    """Check if enough time has passed to warrant a new backup."""
    last_backup = get_last_backup_info()
    if not last_backup:
        return True

    try:
        created_at = last_backup.get("created_at")
        if not created_at:
            return True

        last_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        elapsed = datetime.now() - last_time
        return elapsed.total_seconds() >= (min_interval_hours * 3600)
    except Exception:
        return True


def run_scheduled_backup() -> dict:
    """Run a scheduled backup with cleanup."""
    logger.info("Starting scheduled backup...")

    result = {
        "timestamp": datetime.now().isoformat(),
        "success": True,
        "details": {},
    }

    cleanup = cleanup_old_local_backups()
    result["details"]["cleanup"] = cleanup

    if not should_create_backup():
        logger.info("Backup not needed yet (within interval)")
        result["details"]["skipped"] = True
        return result

    try:
        db_path = DATA_DIR / "story_forge.db"
        if not db_path.exists():
            logger.warning("Database not found, skipping backup")
            result["success"] = False
            result["details"]["error"] = "database_not_found"
            return result

        backup_info = create_backup(db_path, "story_forge")
        result["details"]["backup"] = backup_info
        logger.info(f"Scheduled backup completed: {backup_info.get('filename')}")

    except Exception as e:
        logger.error(f"Scheduled backup failed: {e}")
        result["success"] = False
        result["details"]["error"] = str(e)

    return result
