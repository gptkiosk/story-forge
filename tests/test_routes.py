"""
Route-level regression tests for Story Forge API.
"""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import db
import db_helpers
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
