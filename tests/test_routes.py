"""
Route-level regression tests for Story Forge API.
"""

from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import context_engine
import db
import db_helpers
import libby
from db import Base
from fastapi_app import app


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
            "latest_job": None,
            "documents": [],
        }

        def fake_get_context_state(book_id):
            assert book_id == 42
            return context_state

        def fake_queue_context_ingestion(book_id, title, content_text, source_filename=None):
            assert book_id == 42
            assert title == "Book One"
            assert content_text == "Full manuscript text"
            assert source_filename == "book-one.txt"
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
            book_id, title, content_text, source_filename=None, refine_with_libby=False
        ):
            assert refine_with_libby is True
            return fake_queue_context_ingestion(book_id, title, content_text, source_filename)

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


class TestLibbyWorkflowRoutes:
    def test_next_chapter_ideas_and_generate(self, tmp_path, monkeypatch):
        test_session_local = make_test_session_factory(tmp_path)
        monkeypatch.setattr(db, "SessionLocal", test_session_local)
        monkeypatch.setattr(db_helpers, "get_session", test_session_local)

        monkeypatch.setattr(
            context_engine,
            "get_context_state",
            lambda book_id: {
                "enabled": True,
                "status": "ready",
                "summary": {
                    "summary_text": "Context summary",
                    "characters": ["Jamal", "Mira"],
                    "plot_threads": ["The station is unstable."],
                    "world_details": ["Europa colony rules are tightening."],
                    "style_notes": ["Propulsive pacing."],
                    "source_document_count": 1,
                    "source_word_count": 1600,
                    "updated_at": datetime.now().isoformat(),
                },
                "latest_job": None,
                "documents": [],
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
                        "type": "narration",
                        "speaker": "Narrator",
                        "text": "The corridor lights dimmed.",
                        "delivery_hint": "neutral",
                    },
                    {
                        "type": "dialogue",
                        "speaker": "Mira",
                        "text": "We are losing power.",
                        "delivery_hint": "quiet",
                    },
                ],
            },
        )
        assert save_chapter_map_response.status_code == 200
        saved_chapter_map = save_chapter_map_response.json()
        assert saved_chapter_map["segments"][1]["speaker"] == "Mira"
        assert saved_chapter_map["segments"][1]["delivery_hint"] == "quiet"
