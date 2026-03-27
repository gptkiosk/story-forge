"""Background voice mapping utilities for Story Forge."""

from __future__ import annotations

import json
import re
import shutil
from difflib import SequenceMatcher
from datetime import datetime, timezone
from pathlib import Path

from db import Chapter, CharacterVoice, DATA_DIR, get_session

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
ATTRIBUTION_VERB_PATTERN = "|".join(ATTRIBUTION_VERBS)

LOW_SIGNAL_NAMES = {
    "The", "A", "An", "And", "But", "Or", "If", "In", "On", "At", "By", "For",
    "Of", "To", "From", "With", "Without", "As", "Into", "Chapter", "Book", "Part",
    "Scene", "This", "That", "These", "Those", "What", "When", "Where", "Why",
    "How", "Who", "Whom", "Which", "There", "Then", "Here", "After", "Before",
    "Because", "While", "Though", "Through", "Across", "Inside", "Outside", "Today",
    "Tomorrow", "Yesterday", "Morning", "Evening", "Night", "Day", "Year", "Years",
    "Month", "Months", "Week", "Weeks", "Yes", "No", "Okay", "Later", "Soon",
    "Suddenly", "Finally", "Meanwhile", "Still", "Everything", "Nothing", "Something",
    "Someone", "Everybody", "Nobody", "Implant", "Era", "Origins", "Back",
}
POV_VERBS = (
    "thought", "wondered", "felt", "knew", "remembered", "noticed", "watched",
    "saw", "heard", "feared", "hoped", "realized", "considered", "decided",
)
POV_VERB_PATTERN = "|".join(POV_VERBS)

QUOTE_PATTERN = re.compile(r'["“](.+?)["”]', re.DOTALL)
NAME_PATTERN = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b")
ATTRIBUTION_NAME_PATTERN = re.compile(
    rf'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b\s+(?:{ATTRIBUTION_VERB_PATTERN})\b'
)

DIALOGUE_COVERAGE_MIN_RATIO = 0.96
DIALOGUE_COVERAGE_MIN_LENGTH = 0.95


class VoiceMapValidationError(ValueError):
    """Raised when a saved voice map would lose chapter coverage."""


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


def _extract_attributed_names(text: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for match in ATTRIBUTION_NAME_PATTERN.findall(text or ""):
        normalized = match.strip(".,!?;:\"'()[]{}")
        lowered = normalized.lower()
        if not normalized or normalized in LOW_SIGNAL_NAMES or lowered in seen:
            continue
        seen.add(lowered)
        names.append(normalized)
    return names


def _extract_candidate_names(text: str) -> list[str]:
    counts: dict[str, int] = {}
    display: dict[str, str] = {}
    attributed = _extract_attributed_names(text)
    attributed_set = {name.lower() for name in attributed}

    for name in attributed:
        lowered = name.lower()
        counts[lowered] = counts.get(lowered, 0) + 4
        display.setdefault(lowered, name)

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
    results: list[str] = []
    for key, count in ranked:
        name = display[key]
        if count < 2 and " " not in name and key not in attributed_set:
            continue
        results.append(name)
    return results[:16]


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


def _normalize_excluded_names(entries: list[str] | None) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for entry in entries or []:
        value = str(entry or "").strip()
        if not value:
            continue
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(value)
    return normalized


def _serialize_character_voice(character_voice: CharacterVoice, existing_entry: dict | None = None) -> dict:
    return {
        "character_name": character_voice.character_name,
        "voice_name": character_voice.voice_name,
        "gender": character_voice.gender,
        "description": character_voice.description,
        "minimax_voice_id": character_voice.minimax_voice_id,
        "elevenlabs_voice_id": character_voice.elevenlabs_voice_id,
        "elevenlabs_voice_settings": _normalize_voice_settings((existing_entry or {}).get("elevenlabs_voice_settings")),
    }


def _normalize_narrator_payload(entry: dict | None) -> dict:
    entry = entry or {}
    return {
        "character_name": str(entry.get("character_name") or "Narrator").strip() or "Narrator",
        "elevenlabs_voice_id": str(entry.get("elevenlabs_voice_id") or "").strip() or None,
        "elevenlabs_voice_settings": _normalize_voice_settings(entry.get("elevenlabs_voice_settings")),
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
        existing_payload = _read_json(get_book_voice_map_path(book_id)) or {}
        existing_character_payloads = {
            str(entry.get("character_name") or "").strip().lower(): entry
            for entry in existing_payload.get("characters") or []
            if str(entry.get("character_name") or "").strip()
        }
        existing_narrator = existing_payload.get("narrator") or {}
        existing_excluded_names = _normalize_excluded_names(existing_payload.get("excluded_names"))
        excluded_name_keys = {entry.lower() for entry in existing_excluded_names}
        existing = session.query(CharacterVoice).filter(CharacterVoice.book_id == book_id).all()
        existing_map = {row.character_name.lower(): row for row in existing}

        candidates: list[str] = []
        seen_candidates: set[str] = set()
        chapter_texts = [
            (row.content or "").strip()
            for row in session.query(Chapter).filter(Chapter.book_id == book_id).all()
            if (row.content or "").strip()
        ]
        if chapter_content.strip():
            chapter_texts.append(chapter_content.strip())

        for source in (_extract_candidate_names("\n\n".join(chapter_texts)),):
            for name in source:
                lowered = name.lower()
                if lowered in seen_candidates or lowered in excluded_name_keys:
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
        rows = session.query(CharacterVoice).filter(CharacterVoice.book_id == book_id).all()
        row_map = {row.character_name.lower(): row for row in rows}
        ordered_rows: list[CharacterVoice] = []
        seen_order: set[str] = set()

        for entry in existing_payload.get("characters") or []:
            key = str(entry.get("character_name") or "").strip().lower()
            row = row_map.get(key)
            if not key or row is None or key in seen_order:
                continue
            ordered_rows.append(row)
            seen_order.add(key)

        remaining_rows = [row for key, row in row_map.items() if key not in seen_order]
        remaining_rows.sort(
            key=lambda row: (
                not bool(row.elevenlabs_voice_id or row.voice_name),
                row.character_name.lower(),
            )
        )
        ordered_rows.extend(remaining_rows)

        payload = {
            "book_id": book_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "characters": [
                _serialize_character_voice(row, existing_character_payloads.get(row.character_name.lower()))
                for row in ordered_rows
            ],
            "narrator": _normalize_narrator_payload(existing_narrator),
            "excluded_names": existing_excluded_names,
        }
        _write_json(get_book_voice_map_path(book_id), payload)
        return payload
    finally:
        session.close()


def update_book_voice_map(book_id: int, characters: list[dict], narrator: dict | None = None, excluded_names: list[str] | None = None) -> dict:
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

    existing_payload = _read_json(get_book_voice_map_path(book_id)) or {}
    existing_excluded_names = _normalize_excluded_names(existing_payload.get("excluded_names"))

    session = get_session()
    try:
        existing_rows = session.query(CharacterVoice).filter(CharacterVoice.book_id == book_id).all()
        existing_map = {row.character_name.lower(): row for row in existing_rows}
        submitted_names = {entry["character_name"].lower() for entry in cleaned_characters}

        removed_names: list[str] = []
        for lowered, row in existing_map.items():
            if lowered not in submitted_names:
                removed_names.append(row.character_name)
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
        next_excluded_names = _normalize_excluded_names((excluded_names or existing_excluded_names) + removed_names)
        cleaned_name_keys = {entry["character_name"].lower() for entry in cleaned_characters}
        next_excluded_names = [entry for entry in next_excluded_names if entry.lower() not in cleaned_name_keys]
        payload = {
            "book_id": book_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "characters": cleaned_characters,
            "narrator": _normalize_narrator_payload(narrator),
            "excluded_names": next_excluded_names,
        }
        _write_json(get_book_voice_map_path(book_id), payload)
        return payload
    finally:
        session.close()


def _find_speaker(before_window: str, after_window: str, known_names: list[str]) -> str:
    patterns = []
    for name in known_names:
        escaped = re.escape(name)
        patterns.append((name, rf"\b{escaped}\b[^\n.?!]{{0,40}}\b(?:{ATTRIBUTION_VERB_PATTERN})\b"))
        patterns.append((name, rf"\b(?:{ATTRIBUTION_VERB_PATTERN})\b[^\n.?!]{{0,40}}\b{escaped}\b"))

    for window in (after_window, before_window):
        for name, pattern in patterns:
            if re.search(pattern, window, flags=re.IGNORECASE):
                return name
    return "Narrator"


def _score_narration_focus(content: str, name: str) -> int:
    escaped = re.escape(name)
    score = 0
    score += len(re.findall(rf"\b{escaped}\b", content, flags=re.IGNORECASE)) * 2
    score += len(
        re.findall(
            rf"\b{escaped}\b[^\n.?!]{{0,60}}\b(?:{POV_VERB_PATTERN})\b",
            content,
            flags=re.IGNORECASE,
        )
    ) * 5
    score += len(
        re.findall(
            rf"\b(?:{POV_VERB_PATTERN})\b[^\n.?!]{{0,60}}\b{escaped}\b",
            content,
            flags=re.IGNORECASE,
        )
    ) * 3
    return score


def _infer_narrator_speaker(chapter_content: str, segments: list[dict], known_names: list[str]) -> str:
    narration_text = " ".join(
        str(segment.get("text") or "").strip()
        for segment in segments
        if segment.get("type") == "narration"
    )
    if not narration_text.strip() or not known_names:
        return "Narrator"

    dialogue_counts: dict[str, int] = {}
    for segment in segments:
        speaker = str(segment.get("speaker") or "").strip()
        if segment.get("type") == "dialogue" and speaker and speaker != "Narrator":
            dialogue_counts[speaker.lower()] = dialogue_counts.get(speaker.lower(), 0) + 1

    scored: list[tuple[str, int]] = []
    for name in known_names:
        score = _score_narration_focus(narration_text, name)
        score += dialogue_counts.get(name.lower(), 0)
        if score > 0:
            scored.append((name, score))

    if not scored:
        return "Narrator"

    scored.sort(key=lambda item: item[1], reverse=True)
    best_name, best_score = scored[0]
    second_score = scored[1][1] if len(scored) > 1 else 0
    if best_score >= 6 and best_score >= second_score + 2:
        return best_name
    return "Narrator"


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


def _normalize_coverage_text(value: str) -> str:
    sanitized = value.replace('“', ' ').replace('”', ' ').replace('"', ' ')
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    return sanitized


def _coverage_metrics(chapter_content: str, segments: list[dict]) -> tuple[float, float]:
    original = _normalize_coverage_text(chapter_content)
    combined = _normalize_coverage_text(' '.join(str(segment.get('text') or '').strip() for segment in segments))
    if not original:
        return 1.0, 1.0
    if not combined:
        return 0.0, 0.0
    return (
        len(combined) / max(len(original), 1),
        SequenceMatcher(None, original, combined).ratio(),
    )


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
    speaker = str(segment.get("speaker") or ("Narrator" if segment_type == "narration" else "Narrator")).strip() or "Narrator"
    if speaker == "unassigned_dialogue":
        speaker = "Narrator"
    return {
        "index": index,
        "type": segment_type,
        "speaker": speaker,
        "text": str(segment.get("text") or "").strip(),
        "delivery_hint": str(segment.get("delivery_hint") or "neutral").strip() or "neutral",
    }


def _finalize_segments(chapter_content: str, segments: list[dict]) -> list[dict]:
    finalized: list[dict] = []
    for index, segment in enumerate(segments, start=1):
        normalized = _normalize_segment(index, segment)
        if not normalized["text"]:
            continue
        finalized.append(normalized)

    length_ratio, similarity_ratio = _coverage_metrics(chapter_content, finalized)
    if length_ratio < DIALOGUE_COVERAGE_MIN_LENGTH or similarity_ratio < DIALOGUE_COVERAGE_MIN_RATIO:
        raise VoiceMapValidationError(
            f"Chapter voice plan does not fully cover the chapter text yet (coverage {similarity_ratio:.0%}). Adjust segments before saving."
        )
    return finalized


def _apply_narrator_speaker(segments: list[dict], narrator_speaker: str) -> list[dict]:
    target = narrator_speaker.strip() or "Narrator"
    updated: list[dict] = []
    for segment in segments:
        if segment.get("type") == "narration":
            updated.append({**segment, "speaker": target})
        else:
            updated.append(segment)
    return updated


def _count_unassigned_segments(segments: list[dict], characters: list[dict], narrator_speaker: str | None = None) -> int:
    valid_speakers = {
        "Narrator",
        (narrator_speaker or "Narrator").strip() or "Narrator",
    }
    for entry in characters or []:
        name = str(entry.get("character_name") or "").strip()
        if name:
            valid_speakers.add(name)

    count = 0
    for segment in segments or []:
        speaker = str(segment.get("speaker") or "").strip()
        if segment.get("type") == "dialogue" and (not speaker or speaker == "Narrator" or speaker == "unassigned_dialogue" or speaker not in valid_speakers):
            count += 1
    return count


def build_chapter_voice_map(book_id: int, chapter_id: int, chapter_title: str, chapter_content: str) -> dict:
    roster = sync_character_voices(book_id=book_id, chapter_content=chapter_content)
    known_names = [entry["character_name"] for entry in roster["characters"]]
    drafted_segments = _segment_text(chapter_content, known_names)
    narrator_speaker = _infer_narrator_speaker(chapter_content, drafted_segments, known_names)
    segments = _finalize_segments(chapter_content, _apply_narrator_speaker(drafted_segments, narrator_speaker))
    _, similarity_ratio = _coverage_metrics(chapter_content, segments)
    payload = {
        "book_id": book_id,
        "chapter_id": chapter_id,
        "chapter_title": chapter_title,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "characters": roster["characters"],
        "narrator_speaker": narrator_speaker,
        "segments": segments,
        "coverage_ratio": round(similarity_ratio, 4),
        "unassigned_segment_count": _count_unassigned_segments(segments, roster["characters"], narrator_speaker),
    }
    _write_json(get_chapter_voice_map_path(book_id, chapter_id), payload)
    return payload


def update_chapter_voice_map(
    book_id: int,
    chapter_id: int,
    chapter_title: str,
    chapter_content: str,
    segments: list[dict],
    characters: list[dict] | None = None,
    narrator_speaker: str | None = None,
) -> dict:
    roster = load_book_voice_map(book_id)
    roster_characters = roster.get("characters") or []
    if characters is not None:
        roster_characters = [_normalize_character_payload(entry) for entry in characters if entry]
    normalized_narrator = str(narrator_speaker or "Narrator").strip() or "Narrator"
    finalized_segments = _finalize_segments(chapter_content, _apply_narrator_speaker(segments, normalized_narrator))
    _, similarity_ratio = _coverage_metrics(chapter_content, finalized_segments)
    payload = {
        "book_id": book_id,
        "chapter_id": chapter_id,
        "chapter_title": chapter_title,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "characters": roster_characters,
        "narrator_speaker": normalized_narrator,
        "segments": finalized_segments,
        "coverage_ratio": round(similarity_ratio, 4),
        "unassigned_segment_count": _count_unassigned_segments(finalized_segments, roster_characters, normalized_narrator),
    }
    _write_json(get_chapter_voice_map_path(book_id, chapter_id), payload)
    return payload


def rebuild_chapter_voice_map(book_id: int, chapter_id: int, chapter_title: str, chapter_content: str) -> dict:
    path = get_chapter_voice_map_path(book_id, chapter_id)
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass
    return build_chapter_voice_map(book_id, chapter_id, chapter_title, chapter_content)


def load_book_voice_map(book_id: int) -> dict:
    path = get_book_voice_map_path(book_id)
    payload = _read_json(path)
    if payload is None:
        return sync_character_voices(book_id)
    payload["characters"] = [_normalize_character_payload(entry) for entry in payload.get("characters") or []]
    payload["narrator"] = _normalize_narrator_payload(payload.get("narrator"))
    payload["excluded_names"] = _normalize_excluded_names(payload.get("excluded_names"))
    return payload


def load_chapter_voice_map(book_id: int, chapter_id: int, chapter_title: str, chapter_content: str) -> dict:
    path = get_chapter_voice_map_path(book_id, chapter_id)
    payload = _read_json(path)
    if payload is None:
        return build_chapter_voice_map(book_id, chapter_id, chapter_title, chapter_content)
    payload["characters"] = [_normalize_character_payload(entry) for entry in payload.get("characters") or []]
    narrator_speaker = str(payload.get("narrator_speaker") or "Narrator").strip() or "Narrator"
    payload["narrator_speaker"] = narrator_speaker
    payload["segments"] = _finalize_segments(
        chapter_content,
        _apply_narrator_speaker(payload.get("segments") or [], narrator_speaker),
    )
    _, similarity_ratio = _coverage_metrics(chapter_content, payload["segments"])
    payload["coverage_ratio"] = round(similarity_ratio, 4)
    payload["unassigned_segment_count"] = _count_unassigned_segments(payload["segments"], payload["characters"], narrator_speaker)
    return payload


def delete_voice_maps_for_book(book_id: int) -> None:
    book_dir = VOICE_MAP_ROOT / f"book_{book_id}"
    try:
        shutil.rmtree(book_dir)
    except FileNotFoundError:
        return
    except OSError:
        return
