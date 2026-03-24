# Story Forge Backend

Story Forge is a local-first publishing workflow backend for managing books, chapters, context memory, Libby-assisted drafting, manuscript exports, backups, and text-to-speech generation.

The canonical stack is:

- FastAPI backend in this repo
- Vue 3 frontend in the companion `story-forge-frontend` repo
- Local Mac runtime
- SQLite for the active writing pipeline
- Local PostgreSQL for context engine state
- OpenClaw agent transport for Libby workflows

## Current Capabilities

- Book and chapter CRUD
- Inline chapter drafting plus full chapter editor workflow
- Context-only manuscript ingestion with async progress
- Optional Libby-assisted context refinement
- Libby-assisted next chapter ideas and draft generation
- Multi-format manuscript export and export-package workflow
- Local encrypted backups with optional USB SSD mirror
- TTS provider configuration and audio generation
- Review-mode auth bypass for local development

## Architecture Overview

```mermaid
flowchart LR
    UI["Vue Frontend<br/>story-forge-frontend"] --> API["FastAPI Backend<br/>story-forge"]
    API --> SQLITE["SQLite<br/>books, chapters, exports, backups, TTS"]
    API --> PG["PostgreSQL<br/>context jobs, source docs, summaries"]
    API --> KEYCHAIN["macOS Keychain<br/>TTS secrets"]
    API --> USB["USB SSD Mirror<br/>optional backups"]
    API --> OPENCLAW["OpenClaw Agent Channel<br/>Libby"]
    OPENCLAW --> LIBBY["Libby Agent<br/>story engine / publisher"]
```

## Key Runtime Flows

### 1. Standard Writing Flow

```mermaid
flowchart TD
    A["User opens book"] --> B["Create or edit chapter"]
    B --> C["Save chapter to SQLite"]
    C --> D["Recalculate book word count"]
    D --> E["Chapter available for editing, export, TTS, and future approval flow"]
```

### 2. Context Engine Flow

```mermaid
flowchart TD
    A["Paste prior manuscript / concept text"] --> B["POST /api/context/{book_id}/ingest"]
    B --> C["Store source document in PostgreSQL"]
    C --> D["Fast heuristic context build"]
    D --> E{"Fast only or<br/>Fast + Libby?"}
    E -->|Fast| F["Save summary state"]
    E -->|Libby refine| G["Send structured refinement task to Libby via OpenClaw"]
    G --> F
    F --> H["Frontend polls job progress"]
    H --> I["Editable / exportable context summary"]
```

### 3. Libby Next Chapter Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant API
    participant Libby
    participant SQLite

    User->>Frontend: Open Chapters tab + Agent Help
    Frontend->>API: POST /api/books/{id}/next-chapter/ideas
    API->>Libby: Request 3 structured ideas via OpenClaw
    Libby-->>API: JSON ideas
    API-->>Frontend: ideas[]
    User->>Frontend: Choose idea or write freeform direction
    Frontend->>API: POST /api/books/{id}/next-chapter/generate
    API->>Libby: Request drafted chapter via OpenClaw
    Libby-->>API: chapter_title + chapter_content
    API-->>Frontend: draft payload
    User->>Frontend: Review/edit inline chapter draft
    Frontend->>API: Create + save chapter
    API->>SQLite: Persist chapter
```

## Repository Structure

```text
story-forge/
├── fastapi_app.py          # FastAPI entry point and router wiring
├── routes/                 # API route modules
│   ├── books.py
│   ├── chapters.py
│   ├── context.py
│   ├── libby_workflow.py
│   ├── manuscript.py
│   ├── backups.py
│   └── voice_studio.py
├── db.py                   # SQLite models and engine
├── db_helpers.py           # SQLite access helpers
├── context_db.py           # PostgreSQL context engine models and session setup
├── context_engine.py       # Context ingestion, refinement, export, job progress
├── libby.py                # OpenClaw-backed Libby transport and parsing
├── manuscript.py           # Export and manuscript package generation
├── backup.py               # Local encrypted backups + USB sync
├── tts.py                  # TTS provider logic and keychain integration
├── auth.py                 # OAuth/session helpers
├── requirements.txt        # Backend dependencies
├── tests/                  # Backend regression tests
└── data/                   # Local runtime SQLite data
```

## Data Boundaries

- SQLite is the source of truth for books, chapters, exports, TTS jobs, and backup-related app state.
- PostgreSQL is the source of truth for context ingestion jobs, context source documents, and context summaries.
- Libby is not treated as a database. She is an agent transport target used for refinement and drafting tasks.

## Libby Integration

Story Forge no longer assumes Libby is running as a custom HTTP server on `localhost:8100`.

Current behavior:

- Libby calls are routed through the local `openclaw` CLI
- Story Forge talks to Libby using the OpenClaw agent channel
- JSON-only prompts are used for context refinement, next-chapter ideas, and draft generation
- Chapter creation and chapter edits now build background voice-map JSON artifacts for Voice Studio, including a per-book character roster and a per-chapter narration/dialogue plan.
- Response parsing is hardened for OpenClaw’s nested `result.payloads[].text` output shape

## Running Locally

### Backend Only

```bash
git clone https://github.com/gptkiosk/story-forge.git
cd story-forge
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn fastapi_app:app --reload --port 8000
```

### Full Local App

Use the local launcher:

```bash
/Users/masterblaster/test-app.sh story-forge 8000 5173
```

That launcher currently:

- clones fresh app code into `/tmp`
- persists Story Forge test data outside `/tmp`
- provisions persistent PostgreSQL for context-engine testing
- can auto-use Colima/Docker for the Postgres sidecar path

## Environment Notes

- `REVIEW_MODE=true` enables local auth bypass.
- `STORY_FORGE_USB_PATH=/Volumes/xtra-ssd` overrides the default USB backup mount.
- `STORY_FORGE_CONTEXT_POSTGRES_URL` sets the context-engine PostgreSQL connection.
- `LIBBY_TRANSPORT=openclaw` is the supported Libby transport.
- `LIBBY_AGENT_ID=libby` selects the target OpenClaw agent.
- TTS provider keys are stored in macOS Keychain.

## Verification

Backend contributors should run:

```bash
pytest tests -q
```

## Contributor Notes

- Follow [CODE_STANDARDS.md](/Users/masterblaster/.openclaw/agents/lance/workspace/story-forge/CODE_STANDARDS.md) for backend coding, testing, and architecture expectations.
- Keep docs current when transport, storage, or workflow assumptions change.

## Legacy Status

- NiceGUI is legacy and no longer the supported UI path.
- GCS / Cloud Run assumptions are not part of the active local-first workflow.
- Terraform files may remain as historical scaffolding, but they do not describe the supported runtime.
