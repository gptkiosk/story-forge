"""
Backup module for Story Forge.
Provides encrypted SQLite backup and restore functionality.
"""

import json
import gzip
from pathlib import Path
from datetime import datetime
from typing import Optional

from cryptography.fernet import Fernet
import keyring

# =============================================================================
# Configuration
# =============================================================================

BACKUP_DIR = Path("./data/backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

KEYCHAIN_SERVICE = "story-forge"
KEYCHAIN_BACKUP_KEY = "backup-encryption-key"

# Backup retention
MAX_BACKUPS = 10
MAX_AGE_DAYS = 30


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
        """Encrypt binary data."""
        return self.cipher.encrypt(data)

    def decrypt(self, data: bytes) -> bytes:
        """Decrypt binary data."""
        return self.cipher.decrypt(data)


# Global encryptor instance
backup_encryptor = BackupEncryptor()


# =============================================================================
# Backup Operations
# =============================================================================


def create_backup(source_db_path: str | Path, book_title: str = "story_forge") -> dict:
    """
    Create an encrypted backup of the SQLite database.

    Args:
        source_db_path: Path to the source database file
        book_title: Optional title for the backup (for organization)

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

    # Create backup metadata
    metadata = {
        "created_at": datetime.now().isoformat(),
        "source_db": str(source_path),
        "source_size": source_path.stat().st_size,
        "book_title": book_title,
        "version": "1.0",
    }

    # Perform the backup
    try:
        # Read source database (and WAL if exists)
        source_wal = Path(str(source_path) + "-wal")

        # Create a checkpoint first to ensure all WAL data is in main db
        from db import engine
        with engine.connect() as conn:
            from sqlalchemy import text
            conn.execute(text("PRAGMA wal_checkpoint(FULL)"))
            conn.commit()

        # Copy database file
        db_data = source_path.read_bytes()

        # Also include WAL if exists
        wal_data = b""
        if source_wal.exists():
            wal_data = source_wal.read_bytes()
            metadata["wal_size"] = len(wal_data)

        # Combine into a single backup archive
        archive_data = {
            "main_db": db_data,
            "wal": wal_data,
            "metadata": metadata,
        }

        # Serialize metadata as JSON
        metadata_json = json.dumps(metadata, indent=2).encode("utf-8")

        # Create the backup file structure:
        # [4 bytes: metadata length][metadata JSON][encrypted archive]
        metadata_len = len(metadata_json)
        metadata_len_bytes = metadata_len.to_bytes(4, byteorder="big")

        # Encrypt the archive data
        archive_bytes = json.dumps(
            {k: (v.hex() if isinstance(v, bytes) else v) for k, v in archive_data.items()}
        ).encode("utf-8")
        encrypted_data = backup_encryptor.encrypt(archive_bytes)

        # Write backup file
        with gzip.GzipFile(backup_path, "wb") as gz:
            gz.write(metadata_len_bytes)
            gz.write(metadata_json)
            gz.write(encrypted_data)

        # Calculate checksum
        import hashlib
        checksum = hashlib.sha256(backup_path.read_bytes()).hexdigest()

        backup_info = {
            "path": str(backup_path),
            "size": backup_path.stat().st_size,
            "created_at": metadata["created_at"],
            "checksum": checksum,
            "source_size": metadata["source_size"],
        }

        # Clean up old backups
        cleanup_old_backups()

        return backup_info

    except Exception as e:
        # Clean up partial backup if it exists
        if backup_path.exists():
            backup_path.unlink()
        raise RuntimeError(f"Backup failed: {e}")


def restore_backup(backup_path: str | Path, target_db_path: str | Path) -> dict:
    """
    Restore a database from an encrypted backup.

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
            # Read metadata length
            metadata_len_bytes = gz.read(4)
            if len(metadata_len_bytes) < 4:
                raise ValueError("Invalid backup file: missing metadata length")

            metadata_len = int.from_bytes(metadata_len_bytes, byteorder="big")

            # Read metadata
            metadata_json = gz.read(metadata_len)
            metadata = json.loads(metadata_json.decode("utf-8"))

            # Read encrypted data
            encrypted_data = gz.read()

        # Decrypt
        decrypted = backup_encryptor.decrypt(encrypted_data)

        # Deserialize archive
        archive = json.loads(decrypted.decode("utf-8"))

        # Restore main database
        main_db_hex = archive["main_db"]
        main_db_data = bytes.fromhex(main_db_hex)

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

        restore_info = {
            "restored_at": datetime.now().isoformat(),
            "backup_created_at": metadata["created_at"],
            "source_size": metadata["source_size"],
            "target_path": str(target_path),
        }

        return restore_info

    except Exception as e:
        raise RuntimeError(f"Restore failed: {e}")


def list_backups() -> list[dict]:
    """
    List all available backups with metadata.

    Returns:
        List of backup metadata dictionaries
    """
    backups = []

    for backup_file in BACKUP_DIR.glob("*.sfbackup"):
        try:
            with gzip.GzipFile(backup_file, "rb") as gz:
                # Read metadata length
                metadata_len_bytes = gz.read(4)
                if len(metadata_len_bytes) < 4:
                    continue

                metadata_len = int.from_bytes(metadata_len_bytes, byteorder="big")
                metadata_json = gz.read(metadata_len)
                metadata = json.loads(metadata_json.decode("utf-8"))

            backups.append({
                "filename": backup_file.name,
                "path": str(backup_file),
                "size": backup_file.stat().st_size,
                "created_at": metadata.get("created_at"),
                "book_title": metadata.get("book_title", "unknown"),
                "source_size": metadata.get("source_size", 0),
            })
        except Exception:
            # Skip corrupted backups
            continue

    # Sort by creation date, newest first
    backups.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return backups


def cleanup_old_backups() -> dict:
    """
    Remove old backups beyond retention policy.

    Returns:
        dict with cleanup results (deleted_count, freed_space)
    """
    backups = list_backups()

    deleted_count = 0
    freed_space = 0

    # Check age limit
    cutoff_time = datetime.now()
    max_age = MAX_AGE_DAYS

    for backup in backups:
        try:
            created_at = datetime.fromisoformat(backup["created_at"])
            age_days = (cutoff_time - created_at).days

            # Delete if too old
            if age_days > max_age:
                backup_path = Path(backup["path"])
                if backup_path.exists():
                    freed_space += backup_path.stat().st_size
                    backup_path.unlink()
                    deleted_count += 1
                    continue

        except Exception:
            continue

    # Check count limit (keep only MAX_BACKUPS most recent)
    remaining = list_backups()  # Re-query after deletions
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

    return {
        "deleted_count": deleted_count,
        "freed_space": freed_space,
    }


def verify_backup(backup_path: str | Path) -> bool:
    """
    Verify a backup file is valid and can be decrypted.

    Returns:
        True if backup is valid, False otherwise
    """
    backup_file = Path(backup_path)
    if not backup_file.exists():
        return False

    try:
        with gzip.GzipFile(backup_file, "rb") as gz:
            metadata_len_bytes = gz.read(4)
            if len(metadata_len_bytes) < 4:
                return False

            metadata_len = int.from_bytes(metadata_len_bytes, byteorder="big")
            if metadata_len <= 0 or metadata_len > 1024 * 1024:  # Sanity check
                return False

            metadata_json = gz.read(metadata_len)
            metadata = json.loads(metadata_json.decode("utf-8"))

            # Verify required fields
            required_fields = ["created_at", "source_db", "source_size"]
            for field in required_fields:
                if field not in metadata:
                    return False

            # Try to decrypt data (read but don't fully process)
            encrypted_data = gz.read()
            if len(encrypted_data) < 16:  # Fernet token minimum size
                return False

            # Attempt decryption
            backup_encryptor.decrypt(encrypted_data)

        return True

    except Exception:
        return False


# =============================================================================
# Scheduled Backup Support
# =============================================================================


def get_last_backup_info() -> Optional[dict]:
    """Get information about the most recent backup."""
    backups = list_backups()
    if backups:
        return backups[0]
    return None


def should_create_backup(min_interval_hours: int = 24) -> bool:
    """
    Check if enough time has passed to warrant a new backup.

    Args:
        min_interval_hours: Minimum hours between backups

    Returns:
        True if a new backup should be created
    """
    last_backup = get_last_backup_info()
    if not last_backup:
        return True

    try:
        last_time = datetime.fromisoformat(last_backup["created_at"])
        elapsed = datetime.now() - last_time
        return elapsed.total_seconds() >= (min_interval_hours * 3600)
    except Exception:
        return True
