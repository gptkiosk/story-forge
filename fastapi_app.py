"""
FastAPI entry point for Story Forge API
Run with: uvicorn fastapi_app:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from routes.auth import router as auth_router
from routes.books import router as books_router
from routes.chapters import router as chapters_router
from routes.voice_studio import router as voice_studio_router
from routes.backups import router as backups_router
from routes.context import router as context_router
from routes.dashboard import router as dashboard_router
from routes.manuscript import router as manuscript_router

app = FastAPI(
    title="Story Forge API",
    description="Self-publishing dashboard API",
    version="1.0.0"
)

# Local-first access: allow localhost, LAN IPs, and Tailscale hostnames.
# Browsers do not allow "*" when credentials/cookies are enabled, so we use
# an explicit allow list plus a broad local-network regex instead.
LOCAL_NETWORK_ORIGIN_REGEX = (
    r"https?://("
    r"localhost|"
    r"127\.0\.0\.1|"
    r"0\.0\.0\.0|"
    r"10(?:\.\d{1,3}){3}|"
    r"192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2}|"
    r"(?:[A-Za-z0-9-]+\.)+[A-Za-z0-9-]*ts\.net"
    r")(:\d+)?$"
)

# CORS for Vue frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:4173",
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:4173",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
    ],
    allow_origin_regex=LOCAL_NETWORK_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for audio, SVG, etc.
static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

# Include routers
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(books_router, prefix="/api/books", tags=["books"])
app.include_router(chapters_router, prefix="/api/chapters", tags=["chapters"])
app.include_router(voice_studio_router, prefix="/api/voice-studio", tags=["voice-studio"])
app.include_router(backups_router, prefix="/api/backups", tags=["backups"])
app.include_router(context_router, prefix="/api/context", tags=["context"])
app.include_router(dashboard_router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(manuscript_router, prefix="/api/manuscript", tags=["manuscript"])


@app.on_event("startup")
def startup_event():
    """Initialize database tables on startup."""
    from context_db import init_context_db
    from db import engine, Base
    # Import all models to register them
    import db as db_module
    Base.metadata.create_all(bind=engine)
    init_context_db()


@app.get("/api/health")
def health_check():
    return {"status": "healthy"}


@app.get("/")
def root():
    return {"message": "Story Forge API", "version": "1.0.0"}
