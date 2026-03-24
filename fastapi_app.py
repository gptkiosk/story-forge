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
from routes.dashboard import router as dashboard_router
from routes.manuscript import router as manuscript_router

app = FastAPI(
    title="Story Forge API",
    description="Self-publishing dashboard API",
    version="1.0.0"
)

# CORS for Vue frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:8080"],
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
app.include_router(dashboard_router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(manuscript_router, prefix="/api/manuscript", tags=["manuscript"])


@app.on_event("startup")
def startup_event():
    """Initialize database tables on startup."""
    from db import engine, Base
    # Import all models to register them
    import db as db_module
    Base.metadata.create_all(bind=engine)


@app.get("/api/health")
def health_check():
    return {"status": "healthy"}


@app.get("/")
def root():
    return {"message": "Story Forge API", "version": "1.0.0"}
