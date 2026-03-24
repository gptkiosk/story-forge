# Story Forge Backend Code Standards

This document is the working contract for human and agent contributors in the `story-forge` backend repo.

## Core Rules

- Treat FastAPI as the canonical backend entrypoint.
- Keep the live API schema authoritative. Do not add legacy compatibility fields unless explicitly requested.
- Prefer small, additive changes over broad refactors during feature work.
- Keep local-first behavior intact: SQLite for the writing pipeline, PostgreSQL for context/state features, USB/local backup support, macOS Keychain for local secrets.

## Architecture

- `fastapi_app.py` owns app wiring, middleware, and router registration.
- `routes/` should stay thin and focus on request validation, auth checks, and response shaping.
- Business logic belongs in modules such as `backup.py`, `manuscript.py`, `tts.py`, `context_engine.py`, and `db_helpers.py`.
- Database model changes must be intentional and documented in `PROJECT_STATE.md` when they alter behavior or storage expectations.
- New local-only infrastructure should not silently reintroduce cloud assumptions.

## API Standards

- Keep route naming consistent with existing `/api/<resource>` patterns.
- Use Pydantic models for request validation instead of ad hoc dict parsing in routes.
- Return stable JSON shapes that match the frontend types in the companion repo.
- Prefer additive endpoints over changing an existing endpoint contract unless the frontend is updated in the same change.
- Auth checks must remain explicit in routes.

## Database Standards

- SQLite remains the source of truth for books, chapters, manuscripts, backups, and current writing workflow data.
- PostgreSQL-backed context data should stay isolated to context/Libby workflows unless we intentionally migrate more systems.
- Avoid lazy-loading pitfalls when returning ORM-backed data to API serializers.
- Do not store secrets in the application database.

## Background Work

- Async or threaded work must expose visible status to the UI when the user is waiting on it.
- Long-running jobs should be resumable or safely retryable where practical.
- Progress messages should be human-readable and helpful, not internal-only diagnostics.

## Testing

- Add or update route-level tests when new API endpoints are introduced.
- Run `pytest tests -q` before pushing backend changes.
- When a bug is fixed, prefer adding a regression test close to the affected route or module.
- If a change cannot be tested locally, note the gap explicitly in commit/handoff context.

## Style

- Follow existing Python style in the repo and keep code straightforward.
- Prefer descriptive helper functions over deeply nested route logic.
- Keep comments rare and useful.
- Avoid dead code and phase out NiceGUI-era remnants when touched.

## Multi-Agent Safety

- Do not revert unrelated changes in a dirty worktree.
- Keep commits scoped to one feature or fix when possible.
- Update docs when architecture or workflow assumptions change.
- Push working increments to `main` only after local verification passes.
