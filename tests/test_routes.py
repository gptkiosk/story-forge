"""
Route-level regression tests for Story Forge API.
"""

from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import auth as auth_module
from ai_providers import ai_provider_manager
import context_engine
import db
import db_helpers
import integrations
import libby
import tts as tts_module
import backup as backup_module
from db import Base
from fastapi_app import app
from routes import libby_workflow as libby_workflow_routes
from routes import voice_studio as voice_studio_routes


def make_test_session_factory(tmp_path):
    db_path = tmp_path / "routes_test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


class TestBookAndChapterRoutes:
    def test_create_book_then_list_and_get(self, tmp_path, monkeypatch):
        test_session_local = make_test_session_factory(tmp_path)

        monkeypatch.setattr(db, "SessionLocal", test_session_local)
        monkeypatch.setattr(db_helpers, "get_session", test_session_local)

        client = TestClient(app)

        create_response = client.post(
            "/api/books",
            json={
                "title": "Route Health Book",
                "author": "Tester",
                "description": "Verifies create/list/get flow",
                "status": "draft",
            },
        )

        assert create_response.status_code == 200
        created_book = create_response.json()
        assert created_book["title"] == "Route Health Book"
        assert created_book["status"] == "draft"

        list_response = client.get("/api/books")
        assert list_response.status_code == 200
        listed_books = list_response.json()["books"]
        assert len(listed_books) == 1
        assert listed_books[0]["id"] == created_book["id"]
        assert listed_books[0]["title"] == "Route Health Book"

        get_response = client.get(f"/api/books/{created_book['id']}")
        assert get_response.status_code == 200
        fetched_book = get_response.json()
        assert fetched_book["id"] == created_book["id"]
        assert fetched_book["chapters"] == []

    def test_create_chapter_then_list_and_get(self, tmp_path, monkeypatch):
        test_session_local = make_test_session_factory(tmp_path)

        monkeypatch.setattr(db, "SessionLocal", test_session_local)
        monkeypatch.setattr(db_helpers, "get_session", test_session_local)

        client = TestClient(app)

        book_response = client.post(
            "/api/books",
            json={
                "title": "Chapter Route Book",
                "author": "Tester",
                "description": "Verifies chapter create flow",
                "status": "draft",
            },
        )
        assert book_response.status_code == 200
        book_id = book_response.json()["id"]

        chapter_response = client.post(
            f"/api/chapters/book/{book_id}",
            json={
                "title": "Chapter 1",
                "order": 1,
            },
        )

        assert chapter_response.status_code == 200
        created_chapter = chapter_response.json()
        assert created_chapter["book_id"] == book_id
        assert created_chapter["title"] == "Chapter 1"
        assert created_chapter["order"] == 1

        chapter_get_response = client.get(f"/api/chapters/{created_chapter['id']}")
        assert chapter_get_response.status_code == 200
        assert chapter_get_response.json()["id"] == created_chapter["id"]

        chapter_list_response = client.get(f"/api/books/{book_id}/chapters")
        assert chapter_list_response.status_code == 200
        listed_chapters = chapter_list_response.json()
        assert len(listed_chapters) == 1
        assert listed_chapters[0]["id"] == created_chapter["id"]


class TestAuthRoutes:
    def test_login_stores_return_to_and_callback_redirects_back(self, monkeypatch):
        auth_module.clear_session()
        def fake_get_login_url(include_drive=False, redirect_uri=None):
            requested_scopes = [auth_module.GOOGLE_DRIVE_SCOPE] if include_drive else []
            auth_module.set_session('oauth_requested_scopes', requested_scopes)
            return 'https://accounts.google.com/mock'

        monkeypatch.setattr(auth_module, 'get_login_url', fake_get_login_url)
        monkeypatch.setattr(auth_module, 'process_callback', lambda code, state: {'id': 'user-1'})

        client = TestClient(app)

        login_response = client.get(
            '/api/auth/login',
            params={'return_to': 'http://localhost:5173/integrations', 'connect_drive': 'true'},
            follow_redirects=False,
        )
        assert login_response.status_code in (302, 307)
        assert login_response.headers['location'] == 'https://accounts.google.com/mock'

        callback_response = client.get(
            '/api/auth/callback',
            params={'code': 'google-code', 'state': 'state-token'},
            follow_redirects=False,
        )
        assert callback_response.status_code in (302, 307)
        assert callback_response.headers['location'] == 'http://localhost:5173/integrations?drive_connected=1'

    def test_login_uses_request_host_for_oauth_redirect_uri(self, monkeypatch):
        auth_module.clear_session()
        captured = {}

        def fake_get_login_url(include_drive=False, redirect_uri=None):
            captured['redirect_uri'] = redirect_uri
            return 'https://accounts.google.com/mock'

        monkeypatch.setattr(auth_module, 'get_login_url', fake_get_login_url)

        client = TestClient(app)
        response = client.get(
            '/api/auth/login',
            params={'return_to': 'http://127.0.0.1:5173/login'},
            follow_redirects=False,
        )
        assert response.status_code in (302, 307)
        assert captured['redirect_uri'] == 'http://127.0.0.1:5173/api/auth/callback'



class TestContextRoutes:
    def test_context_get_ingest_update_and_export(self, monkeypatch):
        client = TestClient(app)

        context_state = {
            "enabled": True,
            "status": "ready",
            "summary": {
                "summary_text": "Existing context summary",
                "characters": ["Ari Vale"],
                "plot_threads": ["The reactor mystery deepens."],
                "world_details": ["The colony ship drifts above Europa."],
                "style_notes": ["Third-person leaning."],
                "source_document_count": 1,
                "source_word_count": 1200,
                "updated_at": datetime.now().isoformat(),
            },
            "runtime_context": {
                "summary_text": "Active timeline-safe context",
                "characters": ["Ari Vale"],
                "plot_threads": ["The reactor mystery deepens."],
                "world_details": ["The colony ship drifts above Europa."],
                "style_notes": ["Third-person leaning."],
                "source_document_count": 1,
                "source_word_count": 1200,
                "timeline_guidance": {
                    "future_context_suppressed": True,
                    "future_document_titles": ["Book Three"],
                },
            },
            "latest_job": None,
            "documents": [],
        }

        def fake_get_context_state(book_id):
            assert book_id == 42
            return context_state

        def fake_queue_context_ingestion(
            book_id,
            title,
            content_text,
            source_filename=None,
            timeline_relation="current_book",
            chronology_label=None,
            use_for_facts=None,
            use_for_style=None,
        ):
            assert book_id == 42
            assert title == "Book One"
            assert content_text == "Full manuscript text"
            assert source_filename == "book-one.txt"
            assert timeline_relation == "future_timeline"
            assert chronology_label == "Occurs after Book Two"
            assert use_for_facts is False
            assert use_for_style is True
            context_state["latest_job"] = {
                "id": 9,
                "status": "queued",
                "progress_message": "Queued for context build...",
                "progress_percent": 0,
                "error_message": None,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "completed_at": None,
            }
            return context_state["latest_job"]

        def fake_queue_context_ingestion_with_refine(
            book_id,
            title,
            content_text,
            source_filename=None,
            refine_with_libby=False,
            timeline_relation="current_book",
            chronology_label=None,
            use_for_facts=None,
            use_for_style=None,
        ):
            assert refine_with_libby is True
            return fake_queue_context_ingestion(
                book_id,
                title,
                content_text,
                source_filename,
                timeline_relation,
                chronology_label,
                use_for_facts,
                use_for_style,
            )

        def fake_queue_context_refinement(book_id):
            assert book_id == 42
            return {
                "id": 10,
                "source_type": "context_refinement",
                "status": "queued",
                "progress_message": "Queued for Libby context refinement...",
                "progress_percent": 0,
            }

        def fake_update_context_summary(book_id, payload):
            assert book_id == 42
            context_state["summary"] = {
                **context_state["summary"],
                "summary_text": payload["summary_text"],
                "characters": payload["characters"],
                "plot_threads": payload["plot_threads"],
                "world_details": payload["world_details"],
                "style_notes": payload["style_notes"],
                "updated_at": datetime.now().isoformat(),
            }
            return context_state["summary"]

        def fake_export_context_summary(book_id):
            assert book_id == 42
            return {
                "book_id": book_id,
                "exported_at": datetime.now().isoformat(),
                "summary": context_state["summary"],
                "latest_job": context_state["latest_job"],
                "documents": context_state["documents"],
            }

        monkeypatch.setattr(context_engine, "get_context_state", fake_get_context_state)
        monkeypatch.setattr(context_engine, "queue_context_ingestion", fake_queue_context_ingestion_with_refine)
        monkeypatch.setattr(context_engine, "queue_context_refinement", fake_queue_context_refinement)
        monkeypatch.setattr(context_engine, "update_context_summary", fake_update_context_summary)
        monkeypatch.setattr(context_engine, "export_context_summary", fake_export_context_summary)

        get_response = client.get("/api/context/42")
        assert get_response.status_code == 200
        assert get_response.json()["summary"]["characters"] == ["Ari Vale"]

        ingest_response = client.post(
            "/api/context/42/ingest",
            json={
                "title": "Book One",
                "content_text": "Full manuscript text",
                "source_filename": "book-one.txt",
                "refine_with_libby": True,
                "timeline_relation": "future_timeline",
                "chronology_label": "Occurs after Book Two",
                "use_for_facts": False,
                "use_for_style": True,
            },
        )
        assert ingest_response.status_code == 200
        assert ingest_response.json()["status"] == "queued"

        refine_response = client.post("/api/context/42/refine")
        assert refine_response.status_code == 200
        assert refine_response.json()["source_type"] == "context_refinement"

        update_response = client.put(
            "/api/context/42/summary",
            json={
                "summary_text": "Revised summary",
                "characters": ["Ari Vale", "Mira Chen"],
                "plot_threads": ["The reactor mystery deepens."],
                "world_details": ["Europa colony law is tightening."],
                "style_notes": ["Propulsive pacing."],
            },
        )
        assert update_response.status_code == 200
        assert update_response.json()["summary_text"] == "Revised summary"
        assert update_response.json()["characters"] == ["Ari Vale", "Mira Chen"]

        export_response = client.get("/api/context/42/export")
        assert export_response.status_code == 200
        export_payload = export_response.json()
        assert export_payload["book_id"] == 42
        assert export_payload["summary"]["summary_text"] == "Revised summary"

    def test_context_file_upload_ingest_accepts_supported_text_files(self, monkeypatch):
        client = TestClient(app)
        captured = {}

        def fake_queue_context_ingestion(
            book_id,
            title,
            content_text,
            source_filename=None,
            refine_with_libby=False,
            timeline_relation="current_book",
            chronology_label=None,
            use_for_facts=None,
            use_for_style=None,
        ):
            captured.update(
                {
                    "book_id": book_id,
                    "title": title,
                    "content_text": content_text,
                    "source_filename": source_filename,
                    "refine_with_libby": refine_with_libby,
                    "timeline_relation": timeline_relation,
                    "chronology_label": chronology_label,
                    "use_for_facts": use_for_facts,
                    "use_for_style": use_for_style,
                }
            )
            return {"id": 99, "status": "queued", "progress_percent": 0}

        monkeypatch.setattr(context_engine, "queue_context_ingestion", fake_queue_context_ingestion)

        response = client.post(
            "/api/context/42/ingest-file",
            data={
                "title": "Uploaded Context",
                "refine_with_libby": "true",
                "timeline_relation": "prior_timeline",
                "chronology_label": "Happens before Book Two",
                "use_for_facts": "true",
                "use_for_style": "true",
            },
            files={"upload": ("series-notes.txt", b"Hero notes\nVillain notes", "text/plain")},
        )
        assert response.status_code == 200
        assert captured["book_id"] == 42
        assert captured["title"] == "Uploaded Context"
        assert captured["source_filename"] == "series-notes.txt"
        assert "Hero notes" in captured["content_text"]
        assert captured["refine_with_libby"] is True
        assert captured["timeline_relation"] == "prior_timeline"
        assert captured["chronology_label"] == "Happens before Book Two"
        assert captured["use_for_facts"] is True
        assert captured["use_for_style"] is True

    def test_context_file_upload_rejects_unsupported_types(self):
        client = TestClient(app)
        response = client.post(
            "/api/context/42/ingest-file",
            data={"title": "Bad Upload"},
            files={"upload": ("series-notes.pdf", b"%PDF-1.4", "application/pdf")},
        )
        assert response.status_code == 400
        assert "Unsupported context file type" in response.json()["detail"]


class TestIntegrationRoutes:
    def test_get_and_update_integrations(self, monkeypatch, tmp_path):
        settings_path = tmp_path / "integrations.json"
        monkeypatch.setattr(integrations, "INTEGRATIONS_PATH", settings_path)
        monkeypatch.setattr(integrations, "_get_secret", lambda key: "secret" if "openrouter" in key else "")
        monkeypatch.setattr(integrations, "_set_secret", lambda key, value: None)
        monkeypatch.setattr(libby.libby_client, "_openclaw_available", lambda: True)

        client = TestClient(app)

        get_response = client.get("/api/integrations")
        assert get_response.status_code == 200
        payload = get_response.json()
        assert payload["settings"]["ai"]["provider"] == "openclaw"

        ai_update = client.put(
            "/api/integrations/ai",
            json={
                "provider": "openrouter",
                "openclaw": {"agent_id": "libby", "agent_name": "Libby", "transport": "openclaw"},
                "openrouter": {
                    "base_url": "https://openrouter.ai/api/v1",
                    "model": "openai/gpt-4.1-mini",
                    "site_url": "http://localhost:5173",
                    "app_name": "Story Forge",
                    "api_key": "new-key",
                },
            },
        )
        assert ai_update.status_code == 200
        assert ai_update.json()["provider"] == "openrouter"

        backup_update = client.put(
            "/api/integrations/backup",
            json={
                "provider": "local",
                "usb_path": "/Volumes/test-ssd",
                "google_drive": {"enabled": False, "folder_name": "Story Forge Backups"},
            },
        )
        assert backup_update.status_code == 200
        assert backup_update.json()["provider"] == "local"


class TestStyleStudioRoutes:
    def test_get_and_update_style_studio(self, tmp_path, monkeypatch):
        test_session_local = make_test_session_factory(tmp_path)

        monkeypatch.setattr(db, "SessionLocal", test_session_local)
        monkeypatch.setattr(db_helpers, "get_session", test_session_local)

        client = TestClient(app)

        book_response = client.post(
            "/api/books",
            json={
                "title": "Style Studio Book",
                "author": "Tester",
                "description": "Style route test",
                "status": "draft",
            },
        )
        book_id = book_response.json()["id"]

        get_response = client.get(f"/api/books/{book_id}/style-studio")
        assert get_response.status_code == 200
        assert get_response.json()["book_id"] == book_id

        update_response = client.put(
            f"/api/books/{book_id}/style-studio",
            json={
                "style_template_id": "luminous-minimalist",
                "genre_template_id": "space-opera",
                "style_markdown": "# Style DNA\n\n- Keep the prose clean.",
                "genre_markdown": "# Genre Tropes\n\n- Blend awe with danger.",
            },
        )
        assert update_response.status_code == 200
        payload = update_response.json()
        assert payload["style_template_id"] == "luminous-minimalist"
        assert payload["genre_template_id"] == "space-opera"
        assert "Keep the prose clean" in payload["combined_guidance"]


class TestBackupManifestRoutes:
    def test_get_backup_manifest(self, monkeypatch):
        expected = {
            "components": {
                "books": {"count": 1, "books": [{"id": 4, "title": "Manifest Book"}]},
                "chapters": {"count": 2, "chapters": [{"id": 7, "book_id": 4, "title": "Chapter 1", "order": 1}]},
                "voice_rosters": {"count": 1, "book_ids": [4]},
                "style_studio": {"count": 1, "book_ids": [4]},
                "settings": {"has_user_preferences": True, "has_integrations": True},
            }
        }

        monkeypatch.setattr(
            backup_module,
            "inspect_local_backup",
            lambda path: {"manifest": expected, "metadata": {"created_at": datetime.now().isoformat()}},
        )

        client = TestClient(app)
        response = client.get("/api/backups/example.sfbackup/manifest")
        assert response.status_code == 200
        assert response.json()["components"]["books"]["books"][0]["title"] == "Manifest Book"


class TestLibbyWorkflowRoutes:
    def test_next_chapter_ideas_and_generate(self, tmp_path, monkeypatch):
        test_session_local = make_test_session_factory(tmp_path)
        monkeypatch.setattr(db, "SessionLocal", test_session_local)
        monkeypatch.setattr(db_helpers, "get_session", test_session_local)

        monkeypatch.setattr(
            libby_workflow_routes,
            "build_runtime_context_packet",
            lambda book_id: {
                "summary_text": "Context summary",
                "characters": ["Jamal", "Mira"],
                "plot_threads": ["The station is unstable."],
                "world_details": ["Europa colony rules are tightening."],
                "style_notes": ["Propulsive pacing."],
                "source_document_count": 1,
                "source_word_count": 1600,
                "timeline_guidance": {"future_context_suppressed": False},
            },
        )

        async def fake_suggest_next_chapter_ideas(**kwargs):
            assert kwargs["chapter_count"] == 1
            return {
                "success": True,
                "ideas": [
                    {
                        "title": "Reactor Fracture",
                        "direction": "Jamal discovers the reactor sabotage points to someone inside the council.",
                        "rationale": "Escalates the core mystery while deepening political tension.",
                    },
                    {
                        "title": "Mira's Gamble",
                        "direction": "Mira takes an unauthorized trip into maintenance tunnels to verify a rumor.",
                        "rationale": "Keeps the story close to the main pair and raises risk.",
                    },
                    {
                        "title": "Signal from Europa",
                        "direction": "A coded transmission reveals a hidden survivor tied to book one's fallout.",
                        "rationale": "Links prior continuity into the next chapter cleanly.",
                    },
                ],
            }

        async def fake_submit_story_direction(**kwargs):
            assert "story_direction" in kwargs
            return {
                "success": True,
                "chapter_title": "Chapter 2 - Reactor Fracture",
                "chapter_content": "Jamal followed the humming conduit into the dark --- and when the alarms hit, he froze — just long enough to hear the whisper behind him.",
            }

        monkeypatch.setattr(libby.libby_client, "suggest_next_chapter_ideas", fake_suggest_next_chapter_ideas)
        monkeypatch.setattr(libby.libby_client, "submit_story_direction", fake_submit_story_direction)

        client = TestClient(app)

        book_response = client.post(
            "/api/books",
            json={
                "title": "Libby Workflow Book",
                "author": "Tester",
                "description": "Workflow test",
                "status": "draft",
            },
        )
        book_id = book_response.json()["id"]

        chapter_response = client.post(
            f"/api/chapters/book/{book_id}",
            json={"title": "Chapter 1", "order": 1},
        )
        assert chapter_response.status_code == 200

        ideas_response = client.post(f"/api/books/{book_id}/next-chapter/ideas", json={"refresh": True})
        assert ideas_response.status_code == 200
        ideas = ideas_response.json()["ideas"]
        assert len(ideas) == 3
        assert ideas[0]["title"] == "Reactor Fracture"

        generate_response = client.post(
            f"/api/books/{book_id}/next-chapter/generate",
            json={
                "direction": ideas[0]["direction"],
                "chapter_title": "Chapter 2 - Reactor Fracture",
            },
        )
        assert generate_response.status_code == 200
        generated = generate_response.json()
        assert generated["title"] == "Chapter 2 - Reactor Fracture"
        assert generated["content"].startswith("Jamal followed")
        assert "---" not in generated["content"]
        assert "—" not in generated["content"]
        assert generated["order"] == 2


class TestVoiceMappingRoutes:
    def test_chapter_voice_map_tracks_characters_and_segments(self, tmp_path, monkeypatch):
        import voice_mapping

        test_session_local = make_test_session_factory(tmp_path)

        monkeypatch.setattr(db, "SessionLocal", test_session_local)
        monkeypatch.setattr(db_helpers, "get_session", test_session_local)
        monkeypatch.setattr(voice_mapping, "VOICE_MAP_ROOT", tmp_path / "voice_maps")
        monkeypatch.setattr(
            voice_studio_routes,
            "build_runtime_context_packet",
            lambda book_id: {
                "summary_text": "Voice context",
                "characters": ["Mira", "Jamal"],
                "plot_threads": ["The hatch is failing."],
                "world_details": [],
                "style_notes": ["Tight interior prose."],
                "source_document_count": 1,
                "source_word_count": 600,
                "timeline_guidance": {"future_context_suppressed": False},
            },
        )

        client = TestClient(app)

        book_response = client.post(
            "/api/books",
            json={
                "title": "Voice Map Book",
                "author": "Tester",
                "description": "Voice map test",
                "status": "draft",
            },
        )
        assert book_response.status_code == 200
        book_id = book_response.json()["id"]

        chapter_response = client.post(
            f"/api/chapters/book/{book_id}",
            json={"title": "Chapter 1", "order": 1},
        )
        assert chapter_response.status_code == 200
        chapter_id = chapter_response.json()["id"]

        update_response = client.put(
            f"/api/chapters/{chapter_id}",
            json={
                "content": 'Jamal scanned the corridor. "We are not alone," Mira whispered. "Stay close," Jamal said.',
            },
        )
        assert update_response.status_code == 200

        roster_response = client.get(f"/api/voice-studio/books/{book_id}/voice-map")
        assert roster_response.status_code == 200
        roster = roster_response.json()
        names = [entry["character_name"] for entry in roster["characters"]]
        assert "Jamal" in names
        assert "Mira" in names

        chapter_map_response = client.get(f"/api/voice-studio/chapters/{chapter_id}/voice-map")
        assert chapter_map_response.status_code == 200
        chapter_map = chapter_map_response.json()
        assert any(segment["type"] == "dialogue" for segment in chapter_map["segments"])
        assert any(segment["speaker"] == "Mira" for segment in chapter_map["segments"])
        assert chapter_map["narrator_speaker"] == "Narrator"

    def test_voice_roster_uses_book_chapters_only(self, tmp_path, monkeypatch):
        import voice_mapping

        test_session_local = make_test_session_factory(tmp_path)

        monkeypatch.setattr(db, "SessionLocal", test_session_local)
        monkeypatch.setattr(db_helpers, "get_session", test_session_local)
        monkeypatch.setattr(voice_mapping, "VOICE_MAP_ROOT", tmp_path / "voice_maps")

        client = TestClient(app)

        book_response = client.post(
            "/api/books",
            json={
                "title": "Roster Source Book",
                "author": "Tester",
                "description": "Roster source test",
                "status": "draft",
            },
        )
        book_id = book_response.json()["id"]

        chapter_response = client.post(
            f"/api/chapters/book/{book_id}",
            json={"title": "Chapter 1", "order": 1},
        )
        chapter_id = chapter_response.json()["id"]

        client.put(
            f"/api/chapters/{chapter_id}",
            json={
                "content": 'Jamal scanned the door. "We move now," Mira said.',
            },
        )

        roster_response = client.get(f"/api/voice-studio/books/{book_id}/voice-map")
        assert roster_response.status_code == 200
        names = [entry["character_name"] for entry in roster_response.json()["characters"]]
        assert "Jamal" in names
        assert "Mira" in names
        assert "Book One Hero" not in names
        assert "Series Villain" not in names


    def test_voice_map_save_routes_persist_manual_edits(self, tmp_path, monkeypatch):
        import voice_mapping

        test_session_local = make_test_session_factory(tmp_path)

        monkeypatch.setattr(db, "SessionLocal", test_session_local)
        monkeypatch.setattr(db_helpers, "get_session", test_session_local)
        monkeypatch.setattr(voice_mapping, "VOICE_MAP_ROOT", tmp_path / "voice_maps")

        client = TestClient(app)

        book_response = client.post(
            "/api/books",
            json={
                "title": "Voice Edit Book",
                "author": "Tester",
                "description": "Voice edit test",
                "status": "draft",
            },
        )
        assert book_response.status_code == 200
        book_id = book_response.json()["id"]

        chapter_response = client.post(
            f"/api/chapters/book/{book_id}",
            json={"title": "Chapter 1", "order": 1},
        )
        assert chapter_response.status_code == 200
        chapter_id = chapter_response.json()["id"]

        client.put(
            f"/api/chapters/{chapter_id}",
            json={
                "content": '"Status report," Jamal said. "We are losing power," Mira whispered.',
            },
        )

        save_roster_response = client.put(
            f"/api/voice-studio/books/{book_id}/voice-map",
            json={
                "characters": [
                    {
                        "character_name": "Jamal",
                        "voice_name": "Lead Voice",
                        "elevenlabs_voice_id": "voice_jamal",
                        "description": "Steady lead",
                        "elevenlabs_voice_settings": {"speed": 0.96},
                    },
                    {
                        "character_name": "Mira",
                        "voice_name": "Mira Voice",
                        "elevenlabs_voice_id": "voice_mira",
                    },
                ],
                "narrator": {
                    "character_name": "Narrator",
                    "elevenlabs_voice_settings": {"stability": 0.88},
                },
            },
        )
        assert save_roster_response.status_code == 200
        saved_roster = save_roster_response.json()
        assert saved_roster["characters"][0]["character_name"] == "Jamal"
        assert saved_roster["characters"][0]["elevenlabs_voice_id"] == "voice_jamal"
        assert saved_roster["narrator"]["elevenlabs_voice_settings"]["stability"] == 0.88

        save_chapter_map_response = client.put(
            f"/api/voice-studio/chapters/{chapter_id}/voice-map",
            json={
                "segments": [
                    {
                        "type": "dialogue",
                        "speaker": "Jamal",
                        "text": "Status report,",
                        "delivery_hint": "neutral",
                    },
                    {
                        "type": "narration",
                        "speaker": "Narrator",
                        "text": "Jamal said.",
                        "delivery_hint": "neutral",
                    },
                    {
                        "type": "dialogue",
                        "speaker": "Mira",
                        "text": "We are losing power,",
                        "delivery_hint": "quiet",
                    },
                    {
                        "type": "narration",
                        "speaker": "Narrator",
                        "text": "Mira whispered.",
                        "delivery_hint": "quiet",
                    },
                ],
            },
        )
        assert save_chapter_map_response.status_code == 200
        saved_chapter_map = save_chapter_map_response.json()
        assert saved_chapter_map["segments"][2]["speaker"] == "Mira"
        assert saved_chapter_map["segments"][2]["delivery_hint"] == "quiet"
        assert saved_chapter_map["narrator_speaker"] == "Narrator"
        assert saved_chapter_map["coverage_ratio"] >= 0.96

    def test_voice_roster_metadata_survives_sync_rebuild(self, tmp_path, monkeypatch):
        import voice_mapping

        test_session_local = make_test_session_factory(tmp_path)

        monkeypatch.setattr(db, "SessionLocal", test_session_local)
        monkeypatch.setattr(db_helpers, "get_session", test_session_local)
        monkeypatch.setattr(voice_mapping, "VOICE_MAP_ROOT", tmp_path / "voice_maps")

        client = TestClient(app)

        book_response = client.post(
            "/api/books",
            json={
                "title": "Roster Persistence Book",
                "author": "Tester",
                "description": "Roster persistence test",
                "status": "draft",
            },
        )
        book_id = book_response.json()["id"]

        chapter_response = client.post(
            f"/api/chapters/book/{book_id}",
            json={"title": "Chapter 1", "order": 1},
        )
        chapter_id = chapter_response.json()["id"]

        client.put(
            f"/api/chapters/{chapter_id}",
            json={"content": '"Ready?" Dad asked. "Ready," Tommy said.'},
        )

        save_roster_response = client.put(
            f"/api/voice-studio/books/{book_id}/voice-map",
            json={
                "characters": [
                    {
                        "character_name": "Dad",
                        "voice_name": "Roger",
                        "gender": "Laid-Back, Casual, Resonant",
                        "elevenlabs_voice_id": "CwhRBWXzGAHq8TQ4Fs17",
                        "description": "Warm father voice",
                        "elevenlabs_voice_settings": {"speed": 0.93, "stability": 0.82},
                    },
                    {
                        "character_name": "Tommy",
                        "voice_name": "Young Lead",
                        "elevenlabs_voice_id": "IKne3meq5aSn9XLyUdCD",
                        "elevenlabs_voice_settings": {"speed": 1.03},
                    },
                ],
                "narrator": {
                    "character_name": "Dad",
                    "elevenlabs_voice_settings": {"stability": 0.67, "speed": 0.97},
                },
            },
        )
        assert save_roster_response.status_code == 200

        rebuild_response = client.post(f"/api/voice-studio/chapters/{chapter_id}/voice-map/rebuild")
        assert rebuild_response.status_code == 200

        roster_response = client.get(f"/api/voice-studio/books/{book_id}/voice-map")
        assert roster_response.status_code == 200
        roster = roster_response.json()
        assert roster["characters"][0]["character_name"] == "Dad"
        assert roster["characters"][1]["character_name"] == "Tommy"
        dad = next(entry for entry in roster["characters"] if entry["character_name"] == "Dad")
        assert dad["voice_name"] == "Roger"
        assert dad["gender"] == "Laid-Back, Casual, Resonant"
        assert dad["elevenlabs_voice_id"] == "CwhRBWXzGAHq8TQ4Fs17"
        assert dad["elevenlabs_voice_settings"]["speed"] == 0.93
        assert roster["narrator"]["character_name"] == "Dad"
        assert roster["narrator"]["elevenlabs_voice_settings"]["stability"] == 0.67

    def test_rebuild_chapter_plan_uses_cleaned_roster_and_infers_pov_narrator(self, tmp_path, monkeypatch):
        import voice_mapping

        test_session_local = make_test_session_factory(tmp_path)

        monkeypatch.setattr(db, "SessionLocal", test_session_local)
        monkeypatch.setattr(db_helpers, "get_session", test_session_local)
        monkeypatch.setattr(voice_mapping, "VOICE_MAP_ROOT", tmp_path / "voice_maps")

        client = TestClient(app)

        book_response = client.post(
            "/api/books",
            json={
                "title": "POV Voice Book",
                "author": "Tester",
                "description": "POV narrator test",
                "status": "draft",
            },
        )
        book_id = book_response.json()["id"]

        chapter_response = client.post(
            f"/api/chapters/book/{book_id}",
            json={"title": "Chapter 1", "order": 1},
        )
        chapter_id = chapter_response.json()["id"]

        client.put(
            f"/api/chapters/{chapter_id}",
            json={
                "content": (
                    'Mira checked the corridor again. Mira felt the station shift beneath her boots. '
                    'Mira knew the breach was getting worse. "We need to move," Jamal said.'
                ),
            },
        )

        save_roster_response = client.put(
            f"/api/voice-studio/books/{book_id}/voice-map",
            json={
                "characters": [
                    {"character_name": "Mira", "elevenlabs_voice_id": "voice_mira"},
                    {"character_name": "Jamal", "elevenlabs_voice_id": "voice_jamal"},
                ],
                "narrator": {"character_name": "Narrator"},
            },
        )
        assert save_roster_response.status_code == 200

        rebuild_response = client.post(f"/api/voice-studio/chapters/{chapter_id}/voice-map/rebuild")
        assert rebuild_response.status_code == 200
        rebuilt_map = rebuild_response.json()
        assert rebuilt_map["narrator_speaker"] == "Mira"
        narration_speakers = {
            segment["speaker"]
            for segment in rebuilt_map["segments"]
            if segment["type"] == "narration"
        }
        assert narration_speakers == {"Mira"}

    def test_ai_refine_chapter_plan_updates_narrator_and_speakers(self, tmp_path, monkeypatch):
        import voice_mapping

        test_session_local = make_test_session_factory(tmp_path)

        monkeypatch.setattr(db, "SessionLocal", test_session_local)
        monkeypatch.setattr(db_helpers, "get_session", test_session_local)
        monkeypatch.setattr(voice_mapping, "VOICE_MAP_ROOT", tmp_path / "voice_maps")
        monkeypatch.setattr(
            voice_studio_routes,
            "build_runtime_context_packet",
            lambda book_id: {
                "summary_text": "Voice context",
                "characters": ["Mira", "Jamal"],
                "plot_threads": ["The hatch is failing."],
                "world_details": [],
                "style_notes": ["Tight interior prose."],
                "source_document_count": 1,
                "source_word_count": 600,
                "timeline_guidance": {"future_context_suppressed": False},
            },
        )

        async def fake_refine_voice_plan(**kwargs):
            assert kwargs["chapter_title"] == "Chapter 1"
            return {
                "success": True,
                "narrator_speaker": "Mira",
                "segment_updates": [
                    {"index": 1, "speaker": "Mira", "delivery_hint": "heavy", "type": "narration"},
                    {"index": 2, "speaker": "Jamal", "delivery_hint": "heightened", "type": "dialogue"},
                ],
            }

        monkeypatch.setattr(ai_provider_manager, "refine_voice_plan", fake_refine_voice_plan)

        client = TestClient(app)

        book_response = client.post(
            "/api/books",
            json={
                "title": "AI Voice Book",
                "author": "Tester",
                "description": "AI voice plan test",
                "status": "draft",
            },
        )
        book_id = book_response.json()["id"]

        chapter_response = client.post(
            f"/api/chapters/book/{book_id}",
            json={"title": "Chapter 1", "order": 1},
        )
        chapter_id = chapter_response.json()["id"]

        client.put(
            f"/api/chapters/{chapter_id}",
            json={
                "content": 'Mira pressed her palm against the hatch. "Move now," Jamal said.',
            },
        )

        client.put(
            f"/api/voice-studio/books/{book_id}/voice-map",
            json={
                "characters": [
                    {"character_name": "Mira", "elevenlabs_voice_id": "voice_mira"},
                    {"character_name": "Jamal", "elevenlabs_voice_id": "voice_jamal"},
                ],
                "narrator": {"character_name": "Narrator"},
            },
        )

        refine_response = client.post(f"/api/voice-studio/chapters/{chapter_id}/voice-map/refine")
        assert refine_response.status_code == 200
        refined_map = refine_response.json()
        assert refined_map["narrator_speaker"] == "Mira"
        assert refined_map["segments"][0]["speaker"] == "Mira"
        assert refined_map["segments"][1]["speaker"] == "Jamal"

    def test_voice_map_save_rejects_missing_coverage(self, tmp_path, monkeypatch):
        import voice_mapping

        test_session_local = make_test_session_factory(tmp_path)

        monkeypatch.setattr(db, "SessionLocal", test_session_local)
        monkeypatch.setattr(db_helpers, "get_session", test_session_local)
        monkeypatch.setattr(voice_mapping, "VOICE_MAP_ROOT", tmp_path / "voice_maps")

        client = TestClient(app)

        book_response = client.post(
            "/api/books",
            json={
                "title": "Voice Coverage Book",
                "author": "Tester",
                "description": "Coverage test",
                "status": "draft",
            },
        )
        book_id = book_response.json()["id"]

        chapter_response = client.post(
            f"/api/chapters/book/{book_id}",
            json={"title": "Chapter 1", "order": 1},
        )
        chapter_id = chapter_response.json()["id"]

        client.put(
            f"/api/chapters/{chapter_id}",
            json={
                "content": 'Jamal scanned the corridor. "We are not alone," Mira whispered. "Stay close," Jamal said.',
            },
        )

        save_response = client.put(
            f"/api/voice-studio/chapters/{chapter_id}/voice-map",
            json={
                "segments": [
                    {
                        "type": "dialogue",
                        "speaker": "Mira",
                        "text": "We are not alone.",
                        "delivery_hint": "quiet",
                    }
                ],
            },
        )
        assert save_response.status_code == 400
        assert "does not fully cover" in save_response.json()["detail"]

    def test_voice_preview_route_returns_audio_payload(self, monkeypatch):
        async def fake_generate_speech(request):
            assert request.voice_id == "voice_jamal"
            assert request.provider == tts_module.TTSProvider.ELEVENLABS
            assert request.text == "Mic check line"
            return tts_module.TTSResponse(
                audio_data=b"fake-audio",
                provider=request.provider,
                voice_id=request.voice_id,
                model=request.model,
            )

        monkeypatch.setattr(tts_module.tts_manager, "generate_speech", fake_generate_speech)
        monkeypatch.setattr(tts_module.tts_manager, "is_provider_configured", lambda provider: True)

        client = TestClient(app)
        response = client.post(
            "/api/voice-studio/preview",
            json={
                "provider": "elevenlabs",
                "voice_id": "voice_jamal",
                "text": "Mic check line",
                "speed": 0.98,
            },
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("audio/mpeg")
        assert response.content == b"fake-audio"


class TestBookDeletionRoutes:
    def test_delete_book_cleans_context_and_voice_maps(self, tmp_path, monkeypatch):
        from routes import books as books_routes

        test_session_local = make_test_session_factory(tmp_path)

        monkeypatch.setattr(db, "SessionLocal", test_session_local)
        monkeypatch.setattr(db_helpers, "get_session", test_session_local)

        cleanup_calls = {"context": [], "voice": []}
        monkeypatch.setattr(books_routes, "delete_context_for_book", lambda book_id: cleanup_calls["context"].append(book_id))
        monkeypatch.setattr(books_routes, "delete_voice_maps_for_book", lambda book_id: cleanup_calls["voice"].append(book_id))

        client = TestClient(app)
        book_response = client.post(
            "/api/books",
            json={
                "title": "Delete Me",
                "author": "Tester",
                "description": "Delete flow",
                "status": "draft",
            },
        )
        book_id = book_response.json()["id"]

        response = client.delete(f"/api/books/{book_id}")
        assert response.status_code == 200
        assert cleanup_calls["context"] == [book_id]
        assert cleanup_calls["voice"] == [book_id]
