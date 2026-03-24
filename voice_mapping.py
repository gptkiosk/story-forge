"""Background voice mapping utilities for Story Forge."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from context_db import ContextSummary, context_db_enabled, get_context_session
from db import CharacterVoice, DATA_DIR, get_session

VOICE_MAP_ROOT = DATA_DIR / "voice_maps"

ELEVENLABS_DEFAULT_SETTINGS = {
    "stability": 1.0,
    "use_speaker_boost": True,
    "similarity_boost": 1.0,
    "style": 0.0,
    "speed": 1.0,
}

ATTRIBUTION_VERBS = (
    "said", "asked", "whispered", "murmured", "shouted", "yelled", "replied",
    "answered", "snapped", "sighed", "called", "cried", "warned", "added",
    "told", "muttered", "breathed", "growled", "laughed", "sobbed",
)

LOW_SIGNAL_NAMES = {
    "The", "A", "An", "And", "But", "Or", "If", "In", "On", "At", "By", "For",
    "Of", "To", "From", "With", "Without", "As", "Into", "Chapter", "Book", "Part",
    "Scene", "This", "That", "These", "Those", "What", "When", "Where", "Why",
    "How", "Who", "Whom", "Which", "There", "Then", "Here", "After", "Before",
    "Because", "While", "Though", "Through", "Across", "Inside", "Outside", "Today",
    "Tomorrow", "Yesterday", "Morning", "Evening", "Night", "Day", "Year", "Years",
    "Month", "Months", "Week", "Weeks", "Yes", "No", "Okay",
}

QUOTE_PATTERN = re.compile(r'["“](.+?)["”]', re.DOTALL)
NAME_PATTERN = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b")


def _book_dir(book_id: int) -> Path:
    path = VOICE_MAP_ROOT / f"book_{book_id}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_book_voice_map_path(book_id: int) -> Path:
    return _book_dir(book_id) / "voice_roster.json"


def get_chapter_voice_map_path(book_id: int, chapter_id: int) -> Path:
    chapter_dir = _book_dir(book_id) / "chapters"
    chapter_dir.mkdir(parents=True, exist_ok=True)
    return chapter_dir / f"chapter_{chapter_id}_voice_map.json"


def _extract_candidate_names(text: str) -> list[str]:
    counts: dict[str, int] = {}
    display: dict[str, str] = {}
    for raw in NAME_PATTERN.findall(text or ""):
        normalized = raw.strip(".,!?;:\"'()[]{}")
        lowered = normalized.lower()
        if len(normalized) <= 2:
            continue
        if normalized in LOW_SIGNAL_NAMES:
            continue
        if normalized.endswith(("Chapter", "Book", "Part", "Scene")):
            continue
        counts[lowered] = counts.get(lowered, 0) + 1
        display.setdefault(lowered, normalized)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], display[item[0]]))
    return [display[key] for key, count in ranked if count > 0][:16]


def _get_context_characters(book_id: int) -> list[str]:
    if not context_db_enabled():
        return []
    session = get_context_session()
    try:
        summary = session.query(ContextSummary).filter(ContextSummary.book_id == book_id).first()
        if not summary or not isinstance(summary.characters, list):
            return []
        return [str(name).strip() for name in summary.characters if str(name).strip()]
    finally:
        session.close()


def _normalize_voice_settings(settings: dict | None) -> dict:
    merged = dict(ELEVENLABS_DEFAULT_SETTINGS)
    if isinstance(settings, dict):
        for key in merged:
            if key in settings and settings[key] is not None:
                merged[key] = settings[key]
    return merged


def _normalize_character_payload(entry: dict) -> dict:
    return {
        "character_name": str(entry.get("character_name") or "").strip(),
        "voice_name": str(entry.get("voice_name") or "").strip() or None,
        "gender": str(entry.get("gender") or "").strip() or None,
        "description": str(entry.get("description") or "").strip() or None,
        "minimax_voice_id": str(entry.get("minimax_voice_id") or "").strip() or None,
        "elevenlabs_voice_id": str(entry.get("elevenlabs_voice_id") or "").strip() or None,
        "elevenlabs_voice_settings": _normalize_voice_settings(entry.get("elevenlabs_voice_settings")),
    }


def _serialize_character_voice(character_voice: CharacterVoice) -> dict:
    return {
        "character_name": character_voice.character_name,
        "voice_name": character_voice.voice_name,
        "gender": character_voice.gender,
        "description": character_voice.description,
        "minimax_voice_id": character_voice.minimax_voice_id,
        "elevenlabs_voice_id": character_voice.elevenlabs_voice_id,
        "elevenlabs_voice_settings": _normalize_voice_settings(None),
    }


def _write_json(path: Path, payload: dict):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=True))
    except OSError:
        return


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def sync_character_voices(book_id: int, chapter_content: str = "") -> dict:
    session = get_session()
    try:
        existing = session.query(CharacterVoice).filter(CharacterVoice.book_id == book_id).all()
        existing_map = {row.character_name.lower(): row for row in existing}

        candidates: list[str] = []
        seen_candidates: set[str] = set()
        for source in (_get_context_characters(book_id), _extract_candidate_names(chapter_content)):
            for name in source:
                lowered = name.lower()
                if lowered in seen_candidates:
                    continue
                seen_candidates.add(lowered)
                candidates.append(name)

        for name in candidates:
            lowered = name.lower()
            if lowered in existing_map:
                continue
            row = CharacterVoice(
                book_id=book_id,
                character_name=name,
                description="Auto-detected for voice mapping.",
            )
            session.add(row)
            existing_map[lowered] = row

        session.commit()
        rows = (
            session.query(CharacterVoice)
            .filter(CharacterVoice.book_id == book_id)
            .order_by(CharacterVoice.character_name.asc())
            .all()
        )
        payload = {
            "book_id": book_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "characters": [_serialize_character_voice(row) for row in rows],
            "narrator": {
                "character_name": "Narrator",
                "elevenlabs_voice_settings": _normalize_voice_settings(None),
            },
        }
        _write_json(get_book_voice_map_path(book_id), payload)
        return payload
    finally:
        session.close()


def update_book_voice_map(book_id: int, characters: list[dict], narrator: dict | None = None) -> dict:
    cleaned_characters = []
    seen: set[str] = set()
    for entry in characters:
        normalized = _normalize_character_payload(entry)
        if not normalized["character_name"]:
            continue
        lowered = normalized["character_name"].lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned_characters.append(normalized)

    session = get_session()
    try:
        existing_rows = session.query(CharacterVoice).filter(CharacterVoice.book_id == book_id).all()
        existing_map = {row.character_name.lower(): row for row in existing_rows}
        submitted_names = {entry["character_name"].lower() for entry in cleaned_characters}

        for lowered, row in existing_map.items():
            if lowered not in submitted_names:
                session.delete(row)

        for entry in cleaned_characters:
            lowered = entry["character_name"].lower()
            row = existing_map.get(lowered)
            if row is None:
                row = CharacterVoice(book_id=book_id, character_name=entry["character_name"])
                session.add(row)
            row.character_name = entry["character_name"]
            row.voice_name = entry["voice_name"]
            row.gender = entry["gender"]
            row.description = entry["description"]
            row.minimax_voice_id = entry["minimax_voice_id"]
            row.elevenlabs_voice_id = entry["elevenlabs_voice_id"]

        session.commit()
        payload = {
            "book_id": book_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "characters": cleaned_characters,
            "narrator": {
                "character_name": str((narrator or {}).get("character_name") or "Narrator").strip() or "Narrator",
                "elevenlabs_voice_settings": _normalize_voice_settings((narrator or {}).get("elevenlabs_voice_settings")),
            },
        }
        _write_json(get_book_voice_map_path(book_id), payload)
        return payload
    finally:
        session.close()


def _find_speaker(before_window: str, after_window: str, known_names: list[str]) -> str:
    verbs = "|".join(ATTRIBUTION_VERBS)

    def _match(window: str) -> str | None:
        for name in known_names:
            escaped = re.escape(name)
            patterns = (
                rf"\b{escaped}\b[^\n.?!]{{0,40}}\b(?:{verbs})\b",
                rf"\b(?:{verbs})\b[^\n.?!]{{0,40}}\b{escaped}\b",
            )
            if any(re.search(pattern, window, flags=re.IGNORECASE) for pattern in patterns):
                return name
        return None

    return _match(after_window) or _match(before_window) or "unassigned_dialogue"


def _guess_delivery(dialogue_text: str, context: str) -> str:
    lowered = f"{dialogue_text} {context}".lower()
    if any(word in lowered for word in ("whisper", "murmur", "breathed")):
        return "quiet"
    if any(word in lowered for word in ("shout", "yell", "cried", "growled", "snapped")) or "!" in dialogue_text:
        return "heightened"
    if "?" in dialogue_text:
        return "questioning"
    if any(word in lowered for word in ("sobbed", "crying", "sighed")):
        return "heavy"
    return "neutral"


def _segment_text(chapter_content: str, known_names: list[str]) -> list[dict]:
    content = (chapter_content or "").strip()
    if not content:
        return []

    segments: list[dict] = []
    last_end = 0
    for match in QUOTE_PATTERN.finditer(content):
        before = content[last_end:match.start()]
        quote_text = match.group(1).strip()
        after_window = content[match.end():match.end() + 140]
        next_quote_match = re.search(r'["“]', after_window)
        if next_quote_match:
            after_window = after_window[:next_quote_match.start()]
        before_window = before[-140:]

        narration = before.strip()
        if narration:
            segments.append({
                "index": len(segments) + 1,
                "type": "narration",
                "speaker": "Narrator",
                "text": narration,
                "delivery_hint": "neutral",
            })

        context_window = f"{before_window} {after_window}".strip()
        segments.append({
            "index": len(segments) + 1,
            "type": "dialogue",
            "speaker": _find_speaker(before_window, after_window, known_names),
            "text": quote_text,
            "delivery_hint": _guess_delivery(quote_text, context_window),
        })
        last_end = match.end()

    tail = content[last_end:].strip()
    if tail:
        segments.append({
            "index": len(segments) + 1,
            "type": "narration",
            "speaker": "Narrator",
            "text": tail,
            "delivery_hint": "neutral",
        })

    if not segments:
        return [{
            "index": 1,
            "type": "narration",
            "speaker": "Narrator",
            "text": content,
            "delivery_hint": "neutral",
        }]
    return segments


def _normalize_segment(index: int, segment: dict) -> dict:
    segment_type = str(segment.get("type") or "narration").strip().lower()
    if segment_type not in {"narration", "dialogue"}:
        segment_type = "narration"
    return {
        "index": index,
        "type": segment_type,
        "speaker": str(segment.get("speaker") or ("Narrator" if segment_type == "narration" else "unassigned_dialogue")).strip() or "Narrator",
        "text": str(segment.get("text") or "").strip(),
        "delivery_hint": str(segment.get("delivery_hint") or "neutral").strip() or "neutral",
    }


def build_chapter_voice_map(book_id: int, chapter_id: int, chapter_title: str, chapter_content: str) -> dict:
    roster = sync_character_voices(book_id=book_id, chapter_content=chapter_content)
    known_names = [entry["character_name"] for entry in roster["characters"]]
    payload = {
        "book_id": book_id,
        "chapter_id": chapter_id,
        "chapter_title": chapter_title,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "characters": roster["characters"],
        "segments": _segment_text(chapter_content, known_names),
    }
    _write_json(get_chapter_voice_map_path(book_id, chapter_id), payload)
    return payload


def update_chapter_voice_map(
    book_id: int,
    chapter_id: int,
    chapter_title: str,
    segments: list[dict],
    characters: list[dict] | None = None,
) -> dict:
    roster = load_book_voice_map(book_id)
    roster_characters = roster.get("characters") or []
    if characters is not None:
        roster_characters = [_normalize_character_payload(entry) for entry in characters if entry]
    payload = {
        "book_id": book_id,
        "chapter_id": chapter_id,
        "chapter_title": chapter_title,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "characters": roster_characters,
        "segments": [_normalize_segment(index, segment) for index, segment in enumerate(segments, start=1)],
    }
    _write_json(get_chapter_voice_map_path(book_id, chapter_id), payload)
    return payload


def load_book_voice_map(book_id: int) -> dict:
    path = get_book_voice_map_path(book_id)
    payload = _read_json(path)
    if payload is None:
        return sync_character_voices(book_id)
    payload["characters"] = [_normalize_character_payload(entry) for entry in payload.get("characters") or []]
    narrator = payload.get("narrator") or {}
    payload["narrator"] = {
        "character_name": str(narrator.get("character_name") or "Narrator").strip() or "Narrator",
        "elevenlabs_voice_settings": _normalize_voice_settings(narrator.get("elevenlabs_voice_settings")),
    }
    return payload


def load_chapter_voice_map(book_id: int, chapter_id: int, chapter_title: str, chapter_content: str) -> dict:
    path = get_chapter_voice_map_path(book_id, chapter_id)
    payload = _read_json(path)
    if payload is None:
        return build_chapter_voice_map(book_id, chapter_id, chapter_title, chapter_content)
    payload["characters"] = [_normalize_character_payload(entry) for entry in payload.get("characters") or []]
    payload["segments"] = [_normalize_segment(index, segment) for index, segment in enumerate(payload.get("segments") or [], start=1)]
    return payload
