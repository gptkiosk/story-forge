from context_db import normalize_context_database_url


def test_normalize_context_database_url_rewrites_plain_postgres_scheme():
    url = "postgresql://story_forge:secret@localhost:54329/story_forge_context"
    assert normalize_context_database_url(url) == (
        "postgresql+psycopg://story_forge:secret@localhost:54329/story_forge_context"
    )


def test_normalize_context_database_url_preserves_explicit_driver_scheme():
    url = "postgresql+psycopg://story_forge:secret@localhost:54329/story_forge_context"
    assert normalize_context_database_url(url) == url
