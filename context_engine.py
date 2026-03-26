"""
Context engine service layer for Story Forge.
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
from collections import Counter
from datetime import datetime

from ai_providers import ai_provider_manager
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

COMMON_FALSE_NAMES = {
    "This", "That", "These", "Those", "What", "When", "Where", "Why", "How",
    "Who", "Whom", "Which", "There", "Then", "Here", "After", "Before",
    "Because", "While", "Though", "Through", "Across", "Inside", "Outside",
    "Today", "Tomorrow", "Yesterday", "Morning", "Evening", "Night", "Day",
    "Year", "Years", "Month", "Months", "Week", "Weeks", "Book", "Part",
    "Scene", "Origin", "Origins", "Era", "Implant", "Yes", "No", "Okay",
}

LOW_SIGNAL_CHARACTER_TERMS = {term.lower() for term in STOPWORDS | COMMON_FALSE_NAMES}
MAX_LIBBY_EXCERPT_CHARS = 12000

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
    counts: Counter[str] = Counter()
    display_names: dict[str, str] = {}

    for match in matches:
        normalized = match.strip(".,!?;:\"'()[]{}")
        lowered = normalized.lower()
        if len(normalized) <= 2:
            continue
        if lowered in LOW_SIGNAL_CHARACTER_TERMS:
            continue
        if lowered in WORLD_KEYWORDS:
            continue
        if normalized.endswith(("Chapter", "Book", "Part", "Scene")):
            continue

        token_count = len(normalized.split())
        counts[lowered] += 1
        display_names.setdefault(lowered, normalized)

        if token_count == 1 and counts[lowered] == 1 and lowered.endswith(("ing", "ed")):
            counts[lowered] -= 1

    sorted_candidates = sorted(
        counts.items(),
        key=lambda item: (-item[1], display_names[item[0]]),
    )
    return [display_names[name] for name, count in sorted_candidates if count > 0][:12]


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


def _sanitize_refined_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        item = value.strip()
        if not item:
            continue
        lowered = item.lower()
        if lowered in LOW_SIGNAL_CHARACTER_TERMS:
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(item)
    return cleaned


def _normalize_refined_payload(payload: dict, fallback: dict) -> dict:
    return {
        "summary_text": str(payload.get("summary_text") or fallback["summary_text"]).strip(),
        "characters": _sanitize_refined_list(payload.get("characters")) or fallback["characters"],
        "plot_threads": _sanitize_refined_list(payload.get("plot_threads")) or fallback["plot_threads"],
        "world_details": _sanitize_refined_list(payload.get("world_details")) or fallback["world_details"],
        "style_notes": _sanitize_refined_list(payload.get("style_notes")) or fallback["style_notes"],
        "source_word_count": fallback["source_word_count"],
    }


def _extract_libby_payload(response: dict) -> dict | None:
    candidate_keys = ("context_summary", "refined_context", "summary", "result", "output", "data")
    for key in candidate_keys:
        value = response.get(key)
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                try:
                    parsed = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    return parsed
    return None


def _libby_excerpt(content_text: str) -> str:
    excerpt = content_text.strip()
    if len(excerpt) <= MAX_LIBBY_EXCERPT_CHARS:
        return excerpt
    return f"{excerpt[:MAX_LIBBY_EXCERPT_CHARS].rstrip()}\n\n[excerpt truncated for speed]"


def _refine_summary_with_libby(book_id: int, title: str, content_text: str, base_summary: dict) -> tuple[dict, str | None]:
    response = asyncio.run(
        ai_provider_manager.refine_context_summary(
            book_id=book_id,
            source_title=title,
            heuristic_summary=base_summary,
            source_excerpt=_libby_excerpt(content_text),
            source_word_count=base_summary["source_word_count"],
        )
    )
    if not response.get("success"):
        return base_summary, response.get("error") or "Libby refinement unavailable."

    payload = _extract_libby_payload(response)
    if payload is None:
        return base_summary, "Libby responded without a usable JSON context summary."

    return _normalize_refined_payload(payload, base_summary), None


def _save_context_result(book_id: int, summary: dict):
    session = get_context_session()
    try:
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
        ).count()
        existing_summary.source_word_count = summary["source_word_count"]
        session.commit()
    finally:
        session.close()

    from voice_mapping import sync_character_voices

    sync_character_voices(book_id)


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
                "source_type": latest_job.source_type,
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


def queue_context_ingestion(
    book_id: int,
    title: str,
    content_text: str,
    source_filename: str | None = None,
    refine_with_libby: bool = False,
) -> dict:
    if not context_db_enabled():
        raise RuntimeError("Context database is not configured")

    session = get_context_session()
    try:
        job = ContextIngestionJob(
            book_id=book_id,
            source_type="manuscript_text_libby_refine" if refine_with_libby else "manuscript_text",
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
        target=_run_ingestion_with_options,
        args=(job_id, book_id, title, source_filename, content_text, refine_with_libby),
        daemon=True,
    ).start()

    return {
        "id": job_id,
        "source_type": "manuscript_text_libby_refine" if refine_with_libby else "manuscript_text",
        "status": "queued",
        "progress_message": "Queued for context build...",
        "progress_percent": 0,
    }


def _run_ingestion_with_options(
    job_id: int,
    book_id: int,
    title: str,
    source_filename: str | None,
    content_text: str,
    refine_with_libby: bool,
):
    try:
        _set_job_progress(job_id, "processing", "Gaining context from manuscript...", 15)
        summary = _build_summary(content_text)

        _set_job_progress(job_id, "processing", "Keeping up with characters and plot threads...", 45)
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
            session.commit()
        finally:
            session.close()

        libby_warning: str | None = None
        if refine_with_libby:
            _set_job_progress(job_id, "processing", "Libby is refining context memory...", 72)
            summary, libby_warning = _refine_summary_with_libby(book_id, title, content_text, summary)

        _save_context_result(book_id, summary)

        completion_message = "Context ready for editing and export."
        if refine_with_libby:
            completion_message = (
                "Context refined with Libby and ready for editing."
                if libby_warning is None
                else f"Context ready using fast parse. Libby refine skipped: {libby_warning}"
            )
        _set_job_progress(job_id, "completed", completion_message, 100)
    except Exception as exc:
        _set_job_progress(job_id, "failed", "Context build failed.", 100, str(exc))


def queue_context_refinement(book_id: int) -> dict:
    if not context_db_enabled():
        raise RuntimeError("Context database is not configured")

    session = get_context_session()
    try:
        latest_document = session.query(ContextDocument).filter(
            ContextDocument.book_id == book_id
        ).order_by(ContextDocument.updated_at.desc()).first()
        existing_summary = session.query(ContextSummary).filter(ContextSummary.book_id == book_id).first()
        if latest_document is None or existing_summary is None:
            raise RuntimeError("No existing context source is available to refine yet")

        job = ContextIngestionJob(
            book_id=book_id,
            source_type="context_refinement",
            source_title=latest_document.title,
            source_filename=latest_document.source_filename,
            status="queued",
            progress_message="Queued for Libby context refinement...",
            progress_percent=0,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id
    finally:
        session.close()

    threading.Thread(
        target=_run_context_refinement,
        args=(job_id, book_id),
        daemon=True,
    ).start()

    return {
        "id": job_id,
        "source_type": "context_refinement",
        "status": "queued",
        "progress_message": "Queued for Libby context refinement...",
        "progress_percent": 0,
    }


def _run_context_refinement(job_id: int, book_id: int):
    try:
        _set_job_progress(job_id, "processing", "Loading existing context memory for Libby...", 20)
        session = get_context_session()
        try:
            latest_document = session.query(ContextDocument).filter(
                ContextDocument.book_id == book_id
            ).order_by(ContextDocument.updated_at.desc()).first()
            existing_summary = session.query(ContextSummary).filter(ContextSummary.book_id == book_id).first()
            if latest_document is None or existing_summary is None:
                raise RuntimeError("No existing context source is available to refine yet")

            base_summary = {
                "summary_text": existing_summary.summary_text or "",
                "characters": existing_summary.characters or [],
                "plot_threads": existing_summary.plot_threads or [],
                "world_details": existing_summary.world_details or [],
                "style_notes": existing_summary.style_notes or [],
                "source_word_count": existing_summary.source_word_count or latest_document.word_count,
            }
            source_title = latest_document.title
            content_text = latest_document.content_text
        finally:
            session.close()

        _set_job_progress(job_id, "processing", "Libby is deduplicating and refining context...", 70)
        refined_summary, libby_warning = _refine_summary_with_libby(book_id, source_title, content_text, base_summary)
        _save_context_result(book_id, refined_summary)
        if libby_warning:
            _set_job_progress(job_id, "completed", f"Context kept in fast mode. Libby refine skipped: {libby_warning}", 100)
        else:
            _set_job_progress(job_id, "completed", "Context refined with Libby.", 100)
    except Exception as exc:
        _set_job_progress(job_id, "failed", "Context refinement failed.", 100, str(exc))


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


def delete_context_for_book(book_id: int) -> None:
    if not context_db_enabled():
        return

    session = get_context_session()
    try:
        session.query(ContextIngestionJob).filter(ContextIngestionJob.book_id == book_id).delete()
        session.query(ContextDocument).filter(ContextDocument.book_id == book_id).delete()
        session.query(ContextSummary).filter(ContextSummary.book_id == book_id).delete()
        session.commit()
    finally:
        session.close()
