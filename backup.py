"""
Backup module for Story Forge.
Provides encrypted SQLite backup and restore functionality with GCS sync.

Local backups are encrypted with Fernet and stored in ./data/backups/.
In production, backups are synced to Google Cloud Storage for redundancy.
"""

import json
import gzip
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet
import keyring

# Optional GCS imports - gracefully degrade if not installed
try:
    from google.cloud import storage
    from google.oauth2 import service_account
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False
    storage = None
    service_account = None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

BACKUP_DIR = Path("./data/backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

DATA_DIR = Path("./data")
DATA_DIR.mkdir(exist_ok=True)

KEYCHAIN_SERVICE = "story-forge"
KEYCHAIN_BACKUP_KEY = "backup-encryption-key"

# Backup retention
MAX_BACKUPS = 10
MAX_AGE_DAYS = 30

# GCS Configuration (from environment)
GCS_BUCKET_NAME = None  # Set via set_gcs_bucket() at runtime
GCS_PROJECT_ID = None  # Set via set_gcs_config() at runtime

# Backup prefixes in GCS
DATABASE_PREFIX = "database/"
AUDIO_PREFIX = "audio/"


# =============================================================================
# OpenClaw Secret Store Integration
# =============================================================================

def get_secret_from_openclaw(secret_name: str) -> Optional[str]:
    """
    Retrieve a secret from OpenClaw's secret store.

    In production, OpenClaw injects secrets as environment variables
    prefixed with OPENCLAW_SECRET_. This function checks both the
    environment and keychain for secrets.

    Args:
        secret_name: Name of the secret (e.g., "gcp-service-account-key")

    Returns:
        Secret value as string, or None if not found
    """
    # Check OpenClaw environment variable first
    import os
    env_key = f"OPENCLAW_SECRET_{secret_name.upper()}"
    secret = os.environ.get(env_key)
    if secret:
        logger.info(f"Retrieved secret '{secret_name}' from OpenClaw environment")
        return secret

    # Fall back to keychain
    keychain_key = f"{KEYCHAIN_SERVICE}-{secret_name}"
    secret = keyring.get_password(KEYCHAIN_SERVICE, keychain_key)
    if secret:
        logger.info(f"Retrieved secret '{secret_name}' from keychain")
        return secret

    return None


def get_gcp_credentials():
    """
    Get GCP credentials from OpenClaw secret store.

    Returns:
        service_account.Credentials object, or None if not available
    """
    if not GCS_AVAILABLE:
        logger.warning("GCS client library not installed")
        return None

    # Try to get service account key from OpenClaw
    sa_key_json = get_secret_from_openclaw("gcp-service-account-key")
    if not sa_key_json:
        logger.info("No GCP service account key found in OpenClaw")
        return None

    try:
        # Parse the JSON key
        sa_info = json.loads(sa_key_json)
        credentials = service_account.Credentials.from_service_account_info(sa_info)
        logger.info("GCP credentials loaded from OpenClaw secret store")
        return credentials
    except Exception as e:
        logger.error(f"Failed to parse GCP credentials: {e}")
        return None


# =============================================================================
# GCS Storage Client
# =============================================================================

def get_storage_client() -> Optional["storage.Client"]:
    """
    Get GCS storage client.

    Uses credentials from OpenClaw secret store if available,
    otherwise falls back to default authentication.

    Returns:
        GCS storage client, or None if not configured
    """
    if not GCS_AVAILABLE:
        logger.warning("Google Cloud Storage library not available")
        return None

    if not GCS_BUCKET_NAME:
        logger.debug("No GCS bucket configured")
        return None

    try:
        credentials = get_gcp_credentials()
        if credentials:
            client = storage.Client(
                project=GCS_PROJECT_ID,
                credentials=credentials
            )
        else:
            # Use default credentials (ADC)
            client = storage.Client(project=GCS_PROJECT_ID)

        # Verify connection
        client.get_bucket(GCS_BUCKET_NAME)
        logger.info(f"Connected to GCS bucket: {GCS_BUCKET_NAME}")
        return client

    except Exception as e:
        logger.error(f"Failed to connect to GCS: {e}")
        return None


def set_gcs_bucket(bucket_name: str, project_id: Optional[str] = None):
    """Set GCS bucket configuration at runtime."""
    global GCS_BUCKET_NAME, GCS_PROJECT_ID
    GCS_BUCKET_NAME = bucket_name
    GCS_PROJECT_ID = project_id
    logger.info(f"GCS bucket configured: {bucket_name}")


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
# Local Backup Operations
# =============================================================================


def create_local_backup(source_db_path: str | Path, book_title: str = "story_forge") -> dict:
    """
    Create an encrypted backup of the SQLite database (local storage).

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
        "backup_type": "local",
    }

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
        import hashlib
        checksum = hashlib.sha256(backup_path.read_bytes()).hexdigest()

        backup_info = {
            "path": str(backup_path),
            "size": backup_path.stat().st_size,
            "created_at": metadata["created_at"],
            "checksum": checksum,
            "source_size": metadata["source_size"],
            "backup_type": "local",
        }

        logger.info(f"Local backup created: {backup_path.name} ({backup_info['size']:,} bytes)")
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
            # Read metadata length
            metadata_len_bytes = gz.read(4)
            if len(metadata_len_bytes) < 4:
                raise ValueError("Invalid backup file: missing metadata length")

            metadata_len = int.from_bytes(metadata_len_bytes, byteorder="big")
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

        logger.info(f"Local backup restored to: {target_path}")
        return restore_info

    except Exception as e:
        raise RuntimeError(f"Restore failed: {e}")


# =============================================================================
# GCS Backup Operations
# =============================================================================


def upload_to_gcs(source_path: str | Path, gcs_blob_name: str) -> bool:
    """
    Upload a file to GCS bucket.

    Args:
        source_path: Local file path to upload
        gcs_blob_name: Destination blob name in GCS

    Returns:
        True if successful, False otherwise
    """
    client = get_storage_client()
    if not client:
        logger.warning("GCS client not available")
        return False

    try:
        bucket = client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(gcs_blob_name)

        blob.upload_from_filename(str(source_path))

        logger.info(f"Uploaded to GCS: gs://{GCS_BUCKET_NAME}/{gcs_blob_name}")
        return True

    except Exception as e:
        logger.error(f"Failed to upload to GCS: {e}")
        return False


def download_from_gcs(gcs_blob_name: str, target_path: str | Path) -> bool:
    """
    Download a file from GCS bucket.

    Args:
        gcs_blob_name: Blob name in GCS
        target_path: Local destination path

    Returns:
        True if successful, False otherwise
    """
    client = get_storage_client()
    if not client:
        logger.warning("GCS client not available")
        return False

    try:
        bucket = client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(gcs_blob_name)

        if not blob.exists():
            logger.warning(f"GCS blob not found: gs://{GCS_BUCKET_NAME}/{gcs_blob_name}")
            return False

        blob.download_to_filename(str(target_path))

        logger.info(f"Downloaded from GCS: gs://{GCS_BUCKET_NAME}/{gcs_blob_name}")
        return True

    except Exception as e:
        logger.error(f"Failed to download from GCS: {e}")
        return False


def create_gcs_backup(book_title: str = "story_forge") -> dict:
    """
    Create an encrypted backup and upload to GCS.

    This creates a local backup first, then syncs it to GCS.
    The GCS backup includes metadata for easy listing.

    Args:
        book_title: Title for the backup

    Returns:
        dict with backup metadata including GCS blob name
    """
    db_path = Path("./data/story_forge.db")
    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")

    # Create local backup first
    local_backup = create_local_backup(db_path, book_title)

    if not GCS_BUCKET_NAME:
        logger.info("No GCS bucket configured, backup is local only")
        return local_backup

    # Generate GCS blob name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sanitized_title = "".join(c if c.isalnum() else "_" for c in book_title)
    gcs_blob_name = f"{DATABASE_PREFIX}{sanitized_title}_{timestamp}.sfbackup"

    # Upload to GCS
    local_path = Path(local_backup["path"])
    if upload_to_gcs(local_path, gcs_blob_name):
        # Create metadata object
        metadata_blob_name = f"{DATABASE_PREFIX}{sanitized_title}_{timestamp}.metadata.json"
        metadata = {
            **local_backup,
            "gcs_blob": gcs_blob_name,
            "uploaded_at": datetime.now().isoformat(),
            "backup_type": "gcs",
        }

        bucket = get_storage_client().bucket(GCS_BUCKET_NAME)
        metadata_blob = bucket.blob(metadata_blob_name)
        metadata_blob.upload_from_string(
            json.dumps(metadata, indent=2),
            content_type="application/json"
        )

        local_backup["gcs_blob"] = gcs_blob_name
        local_backup["gcs_metadata_blob"] = metadata_blob_name
        local_backup["uploaded_at"] = metadata["uploaded_at"]
        local_backup["backup_type"] = "gcs"

        logger.info(f"GCS backup created: gs://{GCS_BUCKET_NAME}/{gcs_blob_name}")

    return local_backup


def backup_audio_to_gcs(audio_file_path: str | Path, book_id: int, chapter_id: int) -> dict:
    """
    Backup an audiobook file to GCS with metadata.

    Called automatically when TTS generation completes.

    Args:
        audio_file_path: Path to the audio file
        book_id: Book ID for organization
        chapter_id: Chapter ID for organization

    Returns:
        dict with backup metadata
    """
    audio_path = Path(audio_file_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    if not GCS_BUCKET_NAME:
        logger.info("No GCS bucket configured, skipping audio backup")
        return {"skipped": True, "reason": "no_gcs_bucket"}

    # Generate GCS blob name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    extension = audio_path.suffix
    gcs_blob_name = f"{AUDIO_PREFIX}book_{book_id}_chapter_{chapter_id}_{timestamp}{extension}"

    # Upload audio file
    if not upload_to_gcs(audio_path, gcs_blob_name):
        return {"skipped": True, "reason": "upload_failed"}

    # Create metadata
    metadata = {
        "audio_file": gcs_blob_name,
        "book_id": book_id,
        "chapter_id": chapter_id,
        "file_size": audio_path.stat().st_size,
        "backup_timestamp": datetime.now().isoformat(),
        "content_type": f"audio/{extension.lstrip('.')}",
    }

    # Upload metadata
    metadata_blob_name = f"{AUDIO_PREFIX}book_{book_id}_chapter_{chapter_id}_{timestamp}.metadata.json"
    bucket = get_storage_client().bucket(GCS_BUCKET_NAME)
    metadata_blob = bucket.blob(metadata_blob_name)
    metadata_blob.upload_from_string(
        json.dumps(metadata, indent=2),
        content_type="application/json"
    )

    logger.info(f"Audio backed up to GCS: gs://{GCS_BUCKET_NAME}/{gcs_blob_name}")

    return {
        "success": True,
        "gcs_blob": gcs_blob_name,
        "gcs_metadata_blob": metadata_blob_name,
        "file_size": metadata["file_size"],
    }


# =============================================================================
# Backup Management
# =============================================================================


def create_backup(source_db_path: str | Path, book_title: str = "story_forge") -> dict:
    """
    Create a backup. Uploads to GCS if configured, otherwise local only.

    This is the main entry point for backup creation.

    Args:
        source_db_path: Path to the database
        book_title: Title for the backup

    Returns:
        dict with backup metadata
    """
    if GCS_BUCKET_NAME:
        return create_gcs_backup(book_title)
    else:
        return create_local_backup(source_db_path, book_title)


def restore_backup(backup_path: str | Path, target_db_path: str | Path) -> dict:
    """
    Restore a database from backup.

    Can restore from local backup or GCS (if backup_path is a GCS URI).

    Args:
        backup_path: Path to the backup file, or GCS URI (gs://bucket/path)
        target_db_path: Path to restore the database to

    Returns:
        dict with restore metadata
    """
    backup_str = str(backup_path)

    # Check if it's a GCS URI
    if backup_str.startswith("gs://"):
        # Extract bucket and blob name
        parts = backup_str.replace("gs://", "").split("/", 1)
        bucket_name = parts[0]
        blob_name = parts[1] if len(parts) > 1 else ""

        # Download from GCS to temp file
        temp_path = BACKUP_DIR / f"temp_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sfbackup"

        client = get_storage_client()
        if client:
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            blob.download_to_filename(str(temp_path))

            result = restore_local_backup(temp_path, target_db_path)
            temp_path.unlink()  # Clean up temp file
            return result

        raise ValueError(f"Cannot restore from GCS: {backup_str}")

    return restore_local_backup(backup_path, target_db_path)


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
            })
        except Exception:
            continue

    backups.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return backups


def list_gcs_backups() -> list[dict]:
    """List all backups in GCS bucket."""
    if not GCS_BUCKET_NAME:
        return []

    client = get_storage_client()
    if not client:
        return []

    try:
        bucket = client.bucket(GCS_BUCKET_NAME)
        blobs = bucket.list_blobs(prefix=DATABASE_PREFIX)

        backups = []
        for blob in blobs:
            if blob.name.endswith(".metadata.json"):
                continue  # Skip metadata objects

            # Try to read metadata
            metadata_blob = bucket.blob(blob.name + ".metadata.json")
            if metadata_blob.exists():
                try:
                    metadata_str = metadata_blob.download_as_text()
                    metadata = json.loads(metadata_str)
                    backups.append(metadata)
                except Exception:
                    # Fallback to basic info
                    backups.append({
                        "gcs_blob": blob.name,
                        "size": blob.size,
                        "created": blob.time_created.isoformat() if blob.time_created else None,
                    })
            else:
                backups.append({
                    "gcs_blob": blob.name,
                    "size": blob.size,
                    "created": blob.time_created.isoformat() if blob.time_created else None,
                })

        backups.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return backups

    except Exception as e:
        logger.error(f"Failed to list GCS backups: {e}")
        return []


def list_backups() -> list[dict]:
    """List all backups (local and GCS)."""
    local = list_local_backups()
    gcs = list_gcs_backups() if GCS_BUCKET_NAME else []

    # Mark each with source
    for b in local:
        b["source"] = "local"
    for b in gcs:
        b["source"] = "gcs"

    return local + gcs


def cleanup_old_local_backups() -> dict:
    """
    Remove old local backups beyond retention policy.

    Returns:
        dict with cleanup results (deleted_count, freed_space)
    """
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
# Scheduled Backup Support
# =============================================================================


def get_last_backup_info() -> Optional[dict]:
    """Get information about the most recent backup."""
    backups = list_local_backups()
    if GCS_BUCKET_NAME:
        gcs_backups = list_gcs_backups()
        if gcs_backups:
            gcs_backups[0]["source"] = "gcs"
            if backups:
                # Compare timestamps
                if gcs_backups[0].get("created_at", "") > backups[0].get("created_at", ""):
                    return gcs_backups[0]
            else:
                return gcs_backups[0]

    if backups:
        backups[0]["source"] = "local"
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
        created_at = last_backup.get("created_at") or last_backup.get("created")
        if not created_at:
            return True

        last_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        elapsed = datetime.now() - last_time
        return elapsed.total_seconds() >= (min_interval_hours * 3600)
    except Exception:
        return True


def run_scheduled_backup() -> dict:
    """
    Run a scheduled backup with cleanup.

    This function is designed to be called by a scheduler
    (e.g., cron, OpenClaw cron job).

    Returns:
        dict with backup results
    """
    logger.info("Starting scheduled backup...")

    result = {
        "timestamp": datetime.now().isoformat(),
        "success": True,
        "details": {},
    }

    # Clean up old backups first
    cleanup = cleanup_old_local_backups()
    result["details"]["cleanup"] = cleanup

    # Check if we should create a new backup
    if not should_create_backup():
        logger.info("Backup not needed yet (within interval)")
        result["details"]["skipped"] = True
        return result

    # Create backup
    try:
        db_path = Path("./data/story_forge.db")
        if not db_path.exists():
            logger.warning("Database not found, skipping backup")
            result["success"] = False
            result["details"]["error"] = "database_not_found"
            return result

        backup_info = create_backup(db_path, "story_forge")
        result["details"]["backup"] = backup_info
        logger.info(f"Scheduled backup completed: {backup_info.get('path', backup_info.get('gcs_blob'))}")

    except Exception as e:
        logger.error(f"Scheduled backup failed: {e}")
        result["success"] = False
        result["details"]["error"] = str(e)

    return result
