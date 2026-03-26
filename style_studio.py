"""Book-level Style + Genre Studio utilities."""

from __future__ import annotations

import json
from pathlib import Path

from db import BookStyleProfile, DATA_DIR, get_session

STYLE_STUDIO_ROOT = DATA_DIR / "style_studio"

STYLE_TEMPLATES = [
    {
        "id": "luminous-minimalist",
        "name": "Luminous Minimalist",
        "description": "Lean sentences, emotional restraint, and clean image-led prose that lets silence carry weight.",
        "starter_markdown": """# Style DNA

- Keep sentences lean, exact, and image-forward.
- Let emotional force arrive through concrete detail rather than explanation.
- Prefer clarity, restraint, and quiet momentum over ornament.
- Use short reflective beats between sharp actions.
""",
    },
    {
        "id": "velvet-gothic",
        "name": "Velvet Gothic",
        "description": "Lush, atmospheric prose with elegant darkness, sensual imagery, and emotionally charged interiors.",
        "starter_markdown": """# Style DNA

- Build atmosphere before action so scenes arrive soaked in mood.
- Use tactile and sensory language with elegance, not clutter.
- Let beauty and dread live in the same sentence when useful.
- Interior reactions should feel intimate and slightly heightened.
""",
    },
    {
        "id": "kinetic-cinematic",
        "name": "Kinetic Cinematic",
        "description": "Fast, high-clarity storytelling with visual scene cuts, propulsive beats, and confident pacing.",
        "starter_markdown": """# Style DNA

- Keep scenes moving with strong verbs and visible motion.
- Make blocking easy to picture, almost shot-by-shot.
- End paragraphs on tension, reversal, or forward pull.
- Use dialogue and action to carry exposition whenever possible.
""",
    },
    {
        "id": "mythic-lyrical",
        "name": "Mythic Lyrical",
        "description": "Elevated, storybook-adjacent prose with symbolic resonance, elegant cadence, and timeless gravitas.",
        "starter_markdown": """# Style DNA

- Give the prose a measured cadence with occasional lyrical lift.
- Favor language that feels timeless, archetypal, and resonant.
- Let symbols, motifs, and repeated images deepen meaning across chapters.
- Maintain clarity even when the tone rises toward mythic.
""",
    },
    {
        "id": "intimate-wry",
        "name": "Intimate Wry",
        "description": "Close character voice with dry wit, emotional immediacy, and sharp observational humor.",
        "starter_markdown": """# Style DNA

- Stay close to the character's inner lens and judgments.
- Use wit as pressure release, not as constant punchline writing.
- Let observations reveal vulnerability and bias at the same time.
- Keep the voice agile, human, and slightly self-aware.
""",
    },
]

GENRE_TEMPLATES = [
    {
        "id": "epic-fantasy",
        "name": "Epic Fantasy",
        "description": "Layered world rules, legacy conflict, political tension, and mythic-scale consequences.",
        "starter_markdown": """# Genre Tropes

- Keep world rules internally consistent and visible through use, not lectures.
- Track factions, vows, legacies, and costs of power.
- Let personal choices echo into wider political or mythic stakes.
- Favor wonder with consequence over spectacle without fallout.
""",
    },
    {
        "id": "space-opera",
        "name": "Space Opera",
        "description": "High-stakes adventure, lived-in technology, faction conflict, and emotionally legible scale.",
        "starter_markdown": """# Genre Tropes

- Blend personal stakes with large-scale conflict.
- Make technology feel used, practical, and story-relevant.
- Track alliances, betrayals, command tension, and pressure-cooker decisions.
- Keep awe and momentum alive even during exposition.
""",
    },
    {
        "id": "romantic-suspense",
        "name": "Romantic Suspense",
        "description": "Escalating tension, emotional intimacy, danger, trust fractures, and charged proximity.",
        "starter_markdown": """# Genre Tropes

- Pair every escalation of danger with relationship consequences.
- Let trust, secrecy, and attraction evolve scene by scene.
- Use threat to sharpen character revelation, not replace it.
- Keep emotional beats and suspense beats feeding each other.
""",
    },
    {
        "id": "literary-mystery",
        "name": "Literary Mystery",
        "description": "Psychological depth, ambiguity, layered motive, and revelation through character observation.",
        "starter_markdown": """# Genre Tropes

- Build mystery through attention, omission, and implication.
- Let motive feel more important than plot mechanics alone.
- Keep ambiguity meaningful, not vague.
- Use revelation to deepen character truth as much as solve events.
""",
    },
    {
        "id": "thriller",
        "name": "Thriller",
        "description": "Urgent pacing, escalating danger, compressed decision windows, and hard narrative momentum.",
        "starter_markdown": """# Genre Tropes

- Compress time pressure and force difficult choices.
- End scenes with pressure, threat, or destabilizing discovery.
- Keep information flow tight and strategically timed.
- Let pace stay fast without losing coherence or emotional stakes.
""",
    },
]


def _studio_dir(book_id: int) -> Path:
    path = STYLE_STUDIO_ROOT / f"book_{book_id}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_style_profile_path(book_id: int) -> Path:
    return _studio_dir(book_id) / "style_profile.json"


def get_style_markdown_path(book_id: int) -> Path:
    return _studio_dir(book_id) / "style.md"


def get_genre_markdown_path(book_id: int) -> Path:
    return _studio_dir(book_id) / "genre.md"


def _find_template(templates: list[dict], template_id: str | None) -> dict | None:
    if not template_id:
        return None
    for template in templates:
        if template["id"] == template_id:
            return template
    return None


def _combine_guidance(style_markdown: str, genre_markdown: str) -> str:
    style_body = (style_markdown or "").strip()
    genre_body = (genre_markdown or "").strip()
    if style_body and genre_body:
        return f"{style_body}\n\n---\n\n{genre_body}"
    return style_body or genre_body


def _default_profile(book_id: int) -> dict:
    return {
        "book_id": book_id,
        "style_template_id": None,
        "genre_template_id": None,
        "style_template_name": None,
        "genre_template_name": None,
        "style_markdown": "",
        "genre_markdown": "",
        "combined_guidance": "",
        "updated_at": None,
        "templates": {
            "styles": STYLE_TEMPLATES,
            "genres": GENRE_TEMPLATES,
        },
    }


def get_style_profile(book_id: int) -> dict:
    session = get_session()
    try:
        row = session.query(BookStyleProfile).filter(BookStyleProfile.book_id == book_id).first()
        if row is None:
            profile = _default_profile(book_id)
            style_path = get_style_markdown_path(book_id)
            genre_path = get_genre_markdown_path(book_id)
            if style_path.exists():
                profile["style_markdown"] = style_path.read_text()
            if genre_path.exists():
                profile["genre_markdown"] = genre_path.read_text()
            profile["combined_guidance"] = _combine_guidance(profile["style_markdown"], profile["genre_markdown"])
            return profile

        return {
            "book_id": row.book_id,
            "style_template_id": row.style_template_id,
            "genre_template_id": row.genre_template_id,
            "style_template_name": row.style_template_name,
            "genre_template_name": row.genre_template_name,
            "style_markdown": row.style_markdown or "",
            "genre_markdown": row.genre_markdown or "",
            "combined_guidance": row.combined_guidance or _combine_guidance(row.style_markdown or "", row.genre_markdown or ""),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "templates": {
                "styles": STYLE_TEMPLATES,
                "genres": GENRE_TEMPLATES,
            },
        }
    finally:
        session.close()


def save_style_profile(
    book_id: int,
    *,
    style_template_id: str | None,
    genre_template_id: str | None,
    style_markdown: str,
    genre_markdown: str,
) -> dict:
    session = get_session()
    try:
        row = session.query(BookStyleProfile).filter(BookStyleProfile.book_id == book_id).first()
        if row is None:
            row = BookStyleProfile(book_id=book_id)
            session.add(row)

        style_template = _find_template(STYLE_TEMPLATES, style_template_id)
        genre_template = _find_template(GENRE_TEMPLATES, genre_template_id)
        combined_guidance = _combine_guidance(style_markdown, genre_markdown)

        row.style_template_id = style_template_id
        row.genre_template_id = genre_template_id
        row.style_template_name = style_template["name"] if style_template else None
        row.genre_template_name = genre_template["name"] if genre_template else None
        row.style_markdown = style_markdown
        row.genre_markdown = genre_markdown
        row.combined_guidance = combined_guidance

        session.commit()
        session.refresh(row)

        studio_dir = _studio_dir(book_id)
        get_style_markdown_path(book_id).write_text(style_markdown or "", encoding="utf-8")
        get_genre_markdown_path(book_id).write_text(genre_markdown or "", encoding="utf-8")
        get_style_profile_path(book_id).write_text(
            json.dumps(
                {
                    "book_id": book_id,
                    "style_template_id": style_template_id,
                    "genre_template_id": genre_template_id,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return get_style_profile(book_id)
    finally:
        session.close()


def delete_style_profile(book_id: int) -> None:
    studio_dir = STYLE_STUDIO_ROOT / f"book_{book_id}"
    if studio_dir.exists():
        for path in studio_dir.rglob("*"):
            if path.is_file():
                try:
                    path.unlink()
                except OSError:
                    pass
        for path in sorted(studio_dir.rglob("*"), reverse=True):
            if path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    pass
        try:
            studio_dir.rmdir()
        except OSError:
            pass


def build_style_context(book_id: int) -> dict:
    profile = get_style_profile(book_id)
    return {
        "style_template_name": profile.get("style_template_name"),
        "genre_template_name": profile.get("genre_template_name"),
        "style_markdown": profile.get("style_markdown") or "",
        "genre_markdown": profile.get("genre_markdown") or "",
        "combined_guidance": profile.get("combined_guidance") or "",
    }
