# Story Forge Project State

This file is the current source of truth for the active Story Forge product direction.

## Canonical Stack

- Backend: FastAPI
- Frontend: Vue 3 + TypeScript + Vite
- Runtime: local Mac deployment
- Current writing datastore: SQLite
- Planned context datastore: local PostgreSQL
- Secrets: macOS Keychain
- Backup target: local disk with USB SSD mirror

## Product Focus

Story Forge is a publishing workflow application, not a general-purpose manuscript importer.

Primary workflows:

- Create and manage books
- Create and edit chapters
- Generate TTS audio from chapter content
- Export submission-ready manuscript packages
- Protect work with local encrypted backups

## Context and Libby Direction

- Libby is an OpenClaw publishing specialist agent used for editorial and generation workflows.
- Large manuscript ingestion is context-only and should not create normal editable books by default.
- Rewrite/import of a manuscript should be handled through a separate chapter-by-chapter pipeline.
- Context ingestion should be asynchronous and provide visible progress to the user.
- UI progress messaging should make long-running context work feel active and understandable.

## Data Direction

- SQLite remains the active store for books, chapters, TTS jobs, and backups.
- PostgreSQL will be introduced for context ingestion, summary state, and Libby workflow persistence.
- No legacy schema compatibility is required for removed frontend-only fields.

## UI Direction

- The frontend should normalize to the live backend schema.
- Removed legacy fields should not be preserved unless they support the forward path.
- Multi-format export should be selectable from the UI with checkbox-based package generation.
- Story-direction submission can appear in the UI as a future-facing option during testing.

## Git Workflow

- Changes are currently pushed directly to `master`.
- Only one active coding agent should modify the repo at a time to avoid collisions.
