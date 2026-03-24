# Story Forge Backend

Story Forge is a local-first publishing workflow backend for managing books, chapters, manuscript exports, backups, and text-to-speech generation.

The canonical app stack is now:

- FastAPI backend in this repo
- Vue 3 frontend in the companion `story-forge-frontend` repo
- Local Mac-hosted runtime
- SQLite for the current writing pipeline
- Local PostgreSQL planned for Libby/context ingestion state

## Current Features

- Book and chapter management via `/api/books` and `/api/chapters`
- Chapter editor workflow with automatic word-count updates
- Manuscript exports including single-file and multi-format package flows
- Local encrypted backups with optional USB SSD sync
- TTS provider management and audio generation for completed chapters
- Review-mode auth bypass for local development

## Current Architecture

- **API**: FastAPI
- **Frontend**: Vue 3 + TypeScript + Vite
- **Primary data store**: SQLite in WAL mode
- **Planned context store**: local PostgreSQL for Libby/context workflows
- **Auth**: Google OAuth plus local review-mode bypass
- **TTS secrets**: macOS Keychain
- **Backups**: local encrypted backups plus USB SSD mirror when mounted

## Running Locally

### Prerequisites

- Python 3.12+
- macOS Keychain access for encrypted secrets
- Optional Google OAuth credentials
- Optional TTS provider credentials

### Quick Start

```bash
git clone https://github.com/gptkiosk/story-forge.git
cd story-forge
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn fastapi_app:app --reload --port 8000
```

The frontend should point at `http://localhost:8000/api`.

### Environment Notes

- `REVIEW_MODE=true` enables local auth bypass.
- `STORY_FORGE_USB_PATH=/Volumes/xtra-ssd` overrides the default USB backup mount path.
- TTS provider keys can be set at runtime and are stored in macOS Keychain.

## Project Structure

```text
story-forge/
├── fastapi_app.py       # FastAPI entry point
├── routes/              # API routes
├── db.py                # SQLAlchemy models and encryption helpers
├── db_helpers.py        # Database access helpers
├── backup.py            # Local encrypted backup + USB sync
├── manuscript.py        # Manuscript export and package generation
├── tts.py               # TTS providers and audio persistence
├── libby.py             # Libby client integration scaffold
├── auth.py              # OAuth/session helpers
├── data/                # Local runtime data
└── tests/               # Test suite
```

## Near-Term Roadmap

- Finalize frontend support for selectable manuscript export formats
- Complete TTS testing workflow from chapter to playable audio
- Add async context ingestion for full-manuscript reference imports
- Add PostgreSQL-backed Libby/context state
- Add future-facing story-direction submission flow in the UI

## Legacy Status

- NiceGUI is being phased out and is no longer the canonical UI path.
- GCS and Cloud Run assumptions are not part of the active local-first workflow.
- Terraform files may remain as historical scaffolding, but they do not describe the current supported deployment target.
