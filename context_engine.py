"""
Context engine service layer for Story Forge.
"""

from __future__ import annotations

import re
import threading
from collections import Counter
from datetime import datetime

from context_db import (
    ContextDocument,
    ContextIngestionJob,
    ContextSummary,
    context_db_enabled,
    get_context_session,
)

STOPWORDS = {
    "The", "A", "An", "And", "But", "Or", "If", "In", "On", "At", "By",
    "For", "Of", "To", "From", "With", "Without", "As", "Into", "Chapter",
    "He", "She", "They", "We", "I", "It", "His", "Her", "Their", "Our",
}

WORLD_KEYWORDS = (
    "city", "kingdom", "planet", "ship", "station", "school", "village",
    "forest", "empire", "district", "colony", "temple", "academy", "world",
)


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _split_sentences(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p.strip()]


def _extract_characters(text: str) -> list[str]:
    matches = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b", text)
    counts = Counter(m for m in matches if m not in STOPWORDS and len(m) > 2)
    return [name for name, _ in counts.most_common(12)]


def _extract_plot_threads(paragraphs: list[str]) -> list[str]:
    threads: list[str] = []
    for para in paragraphs[:16]:
        sentences = _split_sentences(para)
        if sentences:
            threads.append(sentences[0][:240])
    unique_threads: list[str] = []
    for thread in threads:
        if thread not in unique_threads:
            unique_threads.append(thread)
    return unique_threads[:8]


def _extract_world_details(sentences: list[str]) -> list[str]:
    details: list[str] = []
    for sentence in sentences:
        lowered = sentence.lower()
        if any(keyword in lowered for keyword in WORLD_KEYWORDS):
            details.append(sentence[:240])
    return details[:8]


def _extract_style_notes(text: str, paragraphs: list[str]) -> list[str]:
    words = text.split()
    avg_para_words = int(sum(len(p.split()) for p in paragraphs) / max(len(paragraphs), 1))
    first_person_hits = len(re.findall(r"\b(I|we|my|our)\b", text))
    third_person_hits = len(re.findall(r"\b(he|she|they|his|her|their)\b", text, flags=re.IGNORECASE))
    pov = "first-person leaning" if first_person_hits > third_person_hits else "third-person leaning"
    tense = "present-tense leaning" if len(re.findall(r"\b(am|is|are|do|does)\b", text)) > len(re.findall(r"\b(was|were|did|had)\b", text)) else "past-tense leaning"
    return [
        f"Corpus size: {len(words):,} words across {len(paragraphs):,} paragraphs.",
        f"Average paragraph length: {avg_para_words} words.",
        f"Narrative voice appears {pov}.",
        f"Sentence construction appears {tense}.",
    ]


def _generate_summary_text(paragraphs: list[str], plot_threads: list[str], characters: list[str]) -> str:
    lead = " ".join(_split_sentences(" ".join(paragraphs[:3]))[:3]).strip()
    character_note = ", ".join(characters[:6]) if characters else "No major characters were auto-detected yet."
    thread_note = " ".join(plot_threads[:3]).strip()
    parts = [
        lead,
        f"Key characters in active memory: {character_note}.",
        thread_note,
    ]
    return "\n\n".join(part for part in parts if part)


def _build_summary(content_text: str) -> dict:
    paragraphs = _split_paragraphs(content_text)
    sentences = _split_sentences(content_text)
    characters = _extract_characters(content_text)
    plot_threads = _extract_plot_threads(paragraphs)
    world_details = _extract_world_details(sentences)
    style_notes = _extract_style_notes(content_text, paragraphs)
    return {
        "summary_text": _generate_summary_text(paragraphs, plot_threads, characters),
        "characters": characters,
        "plot_threads": plot_threads,
        "world_details": world_details,
        "style_notes": style_notes,
        "source_word_count": len(content_text.split()),
    }


def get_context_state(book_id: int) -> dict:
    if not context_db_enabled():
        return {
            "enabled": False,
            "status": "disabled",
            "summary": None,
            "latest_job": None,
            "documents": [],
        }

    session = get_context_session()
    try:
        summary = session.query(ContextSummary).filter(ContextSummary.book_id == book_id).first()
        latest_job = session.query(ContextIngestionJob).filter(
            ContextIngestionJob.book_id == book_id
        ).order_by(ContextIngestionJob.created_at.desc()).first()
        documents = session.query(ContextDocument).filter(
            ContextDocument.book_id == book_id
        ).order_by(ContextDocument.updated_at.desc()).limit(5).all()

        return {
            "enabled": True,
            "status": latest_job.status if latest_job else ("ready" if summary else "empty"),
            "summary": None if summary is None else {
                "summary_text": summary.summary_text,
                "characters": summary.characters or [],
                "plot_threads": summary.plot_threads or [],
                "world_details": summary.world_details or [],
                "style_notes": summary.style_notes or [],
                "source_document_count": summary.source_document_count,
                "source_word_count": summary.source_word_count,
                "updated_at": summary.updated_at.isoformat() if summary.updated_at else None,
            },
            "latest_job": None if latest_job is None else {
                "id": latest_job.id,
                "status": latest_job.status,
                "progress_message": latest_job.progress_message,
                "progress_percent": latest_job.progress_percent,
                "error_message": latest_job.error_message,
                "created_at": latest_job.created_at.isoformat() if latest_job.created_at else None,
                "updated_at": latest_job.updated_at.isoformat() if latest_job.updated_at else None,
                "completed_at": latest_job.completed_at.isoformat() if latest_job.completed_at else None,
            },
            "documents": [{
                "id": doc.id,
                "title": doc.title,
                "source_type": doc.source_type,
                "source_filename": doc.source_filename,
                "word_count": doc.word_count,
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
            } for doc in documents],
        }
    finally:
        session.close()


def _set_job_progress(job_id: int, status: str, message: str, percent: int, error: str | None = None):
    session = get_context_session()
    try:
        job = session.query(ContextIngestionJob).filter(ContextIngestionJob.id == job_id).first()
        if not job:
            return
        job.status = status
        job.progress_message = message
        job.progress_percent = percent
        job.error_message = error
        if status in {"completed", "failed"}:
            job.completed_at = datetime.now()
        session.commit()
    finally:
        session.close()


def _run_ingestion(job_id: int, book_id: int, title: str, source_filename: str | None, content_text: str):
    try:
        _set_job_progress(job_id, "processing", "Gaining context from manuscript...", 15)
        summary = _build_summary(content_text)

        _set_job_progress(job_id, "processing", "Keeping up with characters and plot threads...", 55)
        session = get_context_session()
        try:
            document = ContextDocument(
                book_id=book_id,
                title=title,
                source_type="manuscript_text",
                source_filename=source_filename,
                content_text=content_text,
                word_count=len(content_text.split()),
            )
            session.add(document)

            existing_summary = session.query(ContextSummary).filter(ContextSummary.book_id == book_id).first()
            if existing_summary is None:
                existing_summary = ContextSummary(book_id=book_id)
                session.add(existing_summary)

            existing_summary.summary_text = summary["summary_text"]
            existing_summary.characters = summary["characters"]
            existing_summary.plot_threads = summary["plot_threads"]
            existing_summary.world_details = summary["world_details"]
            existing_summary.style_notes = summary["style_notes"]
            existing_summary.source_document_count = session.query(ContextDocument).filter(
                ContextDocument.book_id == book_id
            ).count() + 1
            existing_summary.source_word_count = summary["source_word_count"]
            session.commit()
        finally:
            session.close()

        _set_job_progress(job_id, "completed", "Context ready for editing and export.", 100)
    except Exception as exc:
        _set_job_progress(job_id, "failed", "Context build failed.", 100, str(exc))


def queue_context_ingestion(book_id: int, title: str, content_text: str, source_filename: str | None = None) -> dict:
    if not context_db_enabled():
        raise RuntimeError("Context database is not configured")

    session = get_context_session()
    try:
        job = ContextIngestionJob(
            book_id=book_id,
            source_type="manuscript_text",
            source_title=title,
            source_filename=source_filename,
            status="queued",
            progress_message="Queued for context build...",
            progress_percent=0,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id
    finally:
        session.close()

    threading.Thread(
        target=_run_ingestion,
        args=(job_id, book_id, title, source_filename, content_text),
        daemon=True,
    ).start()

    return {
        "id": job_id,
        "status": "queued",
        "progress_message": "Queued for context build...",
        "progress_percent": 0,
    }


def update_context_summary(book_id: int, payload: dict) -> dict:
    if not context_db_enabled():
        raise RuntimeError("Context database is not configured")

    session = get_context_session()
    try:
        summary = session.query(ContextSummary).filter(ContextSummary.book_id == book_id).first()
        if summary is None:
            summary = ContextSummary(book_id=book_id)
            session.add(summary)

        summary.summary_text = payload.get("summary_text", summary.summary_text or "")
        summary.characters = payload.get("characters", summary.characters or [])
        summary.plot_threads = payload.get("plot_threads", summary.plot_threads or [])
        summary.world_details = payload.get("world_details", summary.world_details or [])
        summary.style_notes = payload.get("style_notes", summary.style_notes or [])
        session.commit()
        session.refresh(summary)

        return {
            "summary_text": summary.summary_text,
            "characters": summary.characters or [],
            "plot_threads": summary.plot_threads or [],
            "world_details": summary.world_details or [],
            "style_notes": summary.style_notes or [],
            "source_document_count": summary.source_document_count,
            "source_word_count": summary.source_word_count,
            "updated_at": summary.updated_at.isoformat() if summary.updated_at else None,
        }
    finally:
        session.close()


def export_context_summary(book_id: int) -> dict:
    state = get_context_state(book_id)
    if not state["enabled"]:
        raise RuntimeError("Context database is not configured")
    return {
        "book_id": book_id,
        "exported_at": datetime.now().isoformat(),
        "summary": state["summary"],
        "latest_job": state["latest_job"],
        "documents": state["documents"],
    }
