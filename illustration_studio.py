"""Book-level Illustration Studio utilities and asset storage."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from db import BookIllustrationProfile, DATA_DIR, get_session

ILLUSTRATION_STUDIO_ROOT = DATA_DIR / "illustration_studio"

ILLUSTRATION_STYLE_TEMPLATES = [
    {
        "id": "storybook-watercolor",
        "name": "Storybook Watercolor",
        "description": "Painterly page-friendly illustrations with warm lighting, soft edges, and gentle emotional clarity.",
        "starter_markdown": """# Illustration Style DNA

- Render as a cohesive children's storybook illustration with watercolor softness.
- Keep silhouettes readable, expressions clear, and the focal action centered.
- Favor warm palette harmony, luminous highlights, and inviting scene depth.
- Avoid photorealism, harsh contrast, and visual clutter near the text area.
""",
    },
    {
        "id": "inked-graphic-tableau",
        "name": "Inked Graphic Tableau",
        "description": "Bold linework, graphic shapes, and confident blocking suited for stylized fiction interiors.",
        "starter_markdown": """# Illustration Style DNA

- Use elegant ink linework with strong silhouettes and graphic composition.
- Keep the scene highly legible at small EPUB dimensions.
- Favor visual storytelling through gesture, shape, and staging.
- Avoid muddy detail fields or backgrounds that compete with the subject.
""",
    },
    {
        "id": "luminous-fairytale",
        "name": "Luminous Fairytale",
        "description": "Dreamlike, enchanted illustration language with rich atmosphere and a polished painted finish.",
        "starter_markdown": """# Illustration Style DNA

- Treat the scene like a polished fairytale plate illustration.
- Use luminous atmosphere, magical depth, and elegant environmental storytelling.
- Let costume, props, and setting feel handcrafted and timeless.
- Keep faces expressive and age-appropriate rather than hyper-real.
""",
    },
    {
        "id": "cozy-cut-paper",
        "name": "Cozy Cut-Paper",
        "description": "Layered shapes, tactile textures, and friendly visual rhythm suited for playful read-aloud books.",
        "starter_markdown": """# Illustration Style DNA

- Build the scene with layered cut-paper or gouache-like shapes.
- Use simplified forms, tactile texture, and strong color blocking.
- Keep compositions playful, balanced, and easy for children to read.
- Favor charm, warmth, and visual clarity over realism.
""",
    },
    {
        "id": "cinematic-digital-paint",
        "name": "Cinematic Digital Paint",
        "description": "High-clarity narrative illustration with dynamic staging, controlled detail, and strong emotional focus.",
        "starter_markdown": """# Illustration Style DNA

- Render as a polished narrative illustration, not concept art or a film still.
- Keep staging dynamic and emotionally readable from one glance.
- Use controlled detail with a clean focal hierarchy and text-safe negative space.
- Avoid low-detail placeholders, fuzzy anatomy, or muddy lighting.
""",
    },
]

ILLUSTRATION_GENRE_TEMPLATES = [
    {
        "id": "picture-book-wonder",
        "name": "Picture Book Wonder",
        "description": "Illustration cues for page-turn discovery, emotional safety, and bright visual storytelling.",
        "starter_markdown": """# Genre Illustration Cues

- Compose for read-aloud pacing and page-turn curiosity.
- Keep emotional stakes clear, safe, and hopeful for young readers.
- Use objects, expressions, and motion that read instantly in a single spread.
- Favor delight, surprise, and warmth over menace.
""",
    },
    {
        "id": "middle-grade-adventure",
        "name": "Middle Grade Adventure",
        "description": "Adventure-forward visuals with friendship, bravery, and discoverable world details.",
        "starter_markdown": """# Genre Illustration Cues

- Emphasize action, curiosity, and the emotional world of the child protagonists.
- Keep world details imaginative but readable.
- Use energetic staging and expressive body language.
- Let danger feel adventurous rather than frighteningly graphic.
""",
    },
    {
        "id": "mythic-fantasy",
        "name": "Mythic Fantasy",
        "description": "Symbol-rich environments, elevated costume language, and wonder with consequence.",
        "starter_markdown": """# Genre Illustration Cues

- Build a world that feels legendary, symbolic, and visually coherent.
- Use props, architecture, and costume to imply lore.
- Favor grandeur and atmosphere without making the frame visually noisy.
- Let magic feel integrated into the scene rather than pasted on top.
""",
    },
    {
        "id": "cozy-mystery",
        "name": "Cozy Mystery",
        "description": "Charming environments, clue-friendly composition, and gentle tension without visual harshness.",
        "starter_markdown": """# Genre Illustration Cues

- Keep the environment inviting even when the scene contains tension.
- Compose with clue visibility and spatial readability.
- Use mood, color, and arrangement to hint at secrets.
- Avoid grim, violent, or graphic imagery.
""",
    },
    {
        "id": "romantic-adventure",
        "name": "Romantic Adventure",
        "description": "Sweeping staging, expressive character focus, and tactile atmosphere with emotional pull.",
        "starter_markdown": """# Genre Illustration Cues

- Keep character expression and chemistry visible.
- Use scenic depth, weather, costume, and motion to heighten emotion.
- Favor elegance, momentum, and emotional readability.
- Avoid poster-like stiffness or generic stock poses.
""",
    },
]

ILLUSTRATION_SCENE_PRESETS = [
    {
        "id": "chapter-opener",
        "name": "Chapter Opener Plate",
        "description": "A strong opening visual for the chapter's key moment.",
        "starter_prompt": "Create a polished opening-plate illustration that captures the chapter's central emotional beat, the key location, and the main character focus in a single glance.",
    },
    {
        "id": "quiet-character-beat",
        "name": "Quiet Character Beat",
        "description": "A reflective illustration emphasizing mood, expression, and environment.",
        "starter_prompt": "Illustrate a quiet character beat with strong emotional expression, tactile surroundings, and clear visual storytelling that supports the prose without overwhelming it.",
    },
    {
        "id": "action-tableau",
        "name": "Action Tableau",
        "description": "A dynamic but readable narrative action image.",
        "starter_prompt": "Render the most dynamic action beat in the scene as a readable narrative tableau with clear body language, strong focal hierarchy, and clean staging.",
    },
    {
        "id": "world-detail-insert",
        "name": "World Detail Insert",
        "description": "A prop, setting, or magical detail image that enriches the book's world.",
        "starter_prompt": "Create a focused illustration of the most story-relevant object, room, artifact, or environmental detail so it deepens the world and reinforces the chapter mood.",
    },
    {
        "id": "storybook-spread",
        "name": "Storybook Spread",
        "description": "A wider composition intended to sit comfortably in EPUB layout.",
        "starter_prompt": "Create a wide storybook-friendly composition with clear subject placement, breathing room for surrounding text, and consistent illustration style across the whole book.",
    },
]


def _studio_dir(book_id: int) -> Path:
    path = ILLUSTRATION_STUDIO_ROOT / f"book_{book_id}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _generated_dir(book_id: int) -> Path:
    path = _studio_dir(book_id) / "generated"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_illustration_profile_path(book_id: int) -> Path:
    return _studio_dir(book_id) / "illustration_profile.json"


def get_illustration_style_markdown_path(book_id: int) -> Path:
    return _studio_dir(book_id) / "illustration_style.md"


def get_illustration_genre_markdown_path(book_id: int) -> Path:
    return _studio_dir(book_id) / "illustration_genre.md"


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
        "include_in_epub": False,
        "epub_layout": "full_width",
        "preferred_aspect_ratio": "4:3",
        "updated_at": None,
        "templates": {
            "styles": ILLUSTRATION_STYLE_TEMPLATES,
            "genres": ILLUSTRATION_GENRE_TEMPLATES,
            "scene_presets": ILLUSTRATION_SCENE_PRESETS,
        },
        "generated_assets": [],
    }


def _asset_from_metadata(relative_path: str, metadata: dict) -> dict:
    return {
        "asset_id": metadata.get("asset_id"),
        "book_id": metadata.get("book_id"),
        "chapter_id": metadata.get("chapter_id"),
        "chapter_title": metadata.get("chapter_title"),
        "scene_label": metadata.get("scene_label"),
        "scene_prompt": metadata.get("scene_prompt"),
        "final_prompt": metadata.get("final_prompt"),
        "caption": metadata.get("caption"),
        "provider": metadata.get("provider"),
        "model": metadata.get("model"),
        "aspect_ratio": metadata.get("aspect_ratio"),
        "epub_ready": metadata.get("epub_ready", True),
        "created_at": metadata.get("created_at"),
        "url_path": relative_path,
    }


def list_generated_assets(book_id: int) -> list[dict]:
    assets: list[dict] = []
    for metadata_path in sorted(_generated_dir(book_id).glob("*.json"), reverse=True):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        image_name = metadata.get("filename")
        if not image_name:
            continue
        image_path = _generated_dir(book_id) / image_name
        if not image_path.exists():
            continue
        relative_path = f"/api/books/{book_id}/illustration-studio/assets/{image_name}"
        assets.append(_asset_from_metadata(relative_path, metadata))
    assets.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return assets


def get_style_check_variants(style_template_id: str | None, genre_template_id: str | None) -> list[dict]:
    styles = ILLUSTRATION_STYLE_TEMPLATES
    if not styles:
        return []
    selected_index = 0
    for index, template in enumerate(styles):
        if template["id"] == style_template_id:
            selected_index = index
            break
    genre_template = _find_template(ILLUSTRATION_GENRE_TEMPLATES, genre_template_id)
    scene_seed = (
        "A child protagonist stands at the threshold of a strange discovery, the environment offering one clear focal wonder and enough surrounding detail to suggest the story world."
        if genre_template_id in {"picture-book-wonder", "middle-grade-adventure"}
        else "A central story moment is staged with strong emotional clarity, clear subject hierarchy, and visual storytelling that feels ready for a polished book interior."
    )
    variants = [0, 1, 2]
    output = []
    for offset in variants:
        template = styles[(selected_index + offset) % len(styles)]
        flavor = (
            f"{scene_seed} Render it in {template['name']} mode with {genre_template['name'] if genre_template else 'cross-genre'} cues, text-safe negative space, and consistent series branding."
        )
        output.append(
            {
                "id": template["id"],
                "label": "Current direction" if offset == 0 else f"Variant {offset + 1}",
                "template_name": template["name"],
                "genre_name": genre_template["name"] if genre_template else "Cross-genre default",
                "sample_prompt": flavor,
            }
        )
    return output


def get_illustration_profile(book_id: int) -> dict:
    session = get_session()
    try:
        row = session.query(BookIllustrationProfile).filter(BookIllustrationProfile.book_id == book_id).first()
        if row is None:
            profile = _default_profile(book_id)
            style_path = get_illustration_style_markdown_path(book_id)
            genre_path = get_illustration_genre_markdown_path(book_id)
            if style_path.exists():
                profile["style_markdown"] = style_path.read_text(encoding="utf-8")
            if genre_path.exists():
                profile["genre_markdown"] = genre_path.read_text(encoding="utf-8")
            profile["combined_guidance"] = _combine_guidance(profile["style_markdown"], profile["genre_markdown"])
            profile["generated_assets"] = list_generated_assets(book_id)
            profile["style_check_variants"] = get_style_check_variants(
                profile.get("style_template_id"),
                profile.get("genre_template_id"),
            )
            return profile

        profile = {
            "book_id": row.book_id,
            "style_template_id": row.style_template_id,
            "genre_template_id": row.genre_template_id,
            "style_template_name": row.style_template_name,
            "genre_template_name": row.genre_template_name,
            "style_markdown": row.style_markdown or "",
            "genre_markdown": row.genre_markdown or "",
            "combined_guidance": row.combined_guidance or _combine_guidance(row.style_markdown or "", row.genre_markdown or ""),
            "include_in_epub": bool(row.include_in_epub),
            "epub_layout": row.epub_layout or "full_width",
            "preferred_aspect_ratio": row.preferred_aspect_ratio or "4:3",
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "templates": {
                "styles": ILLUSTRATION_STYLE_TEMPLATES,
                "genres": ILLUSTRATION_GENRE_TEMPLATES,
                "scene_presets": ILLUSTRATION_SCENE_PRESETS,
            },
            "generated_assets": list_generated_assets(book_id),
        }
        profile["style_check_variants"] = get_style_check_variants(
            profile.get("style_template_id"),
            profile.get("genre_template_id"),
        )
        return profile
    finally:
        session.close()


def save_illustration_profile(
    book_id: int,
    *,
    style_template_id: str | None,
    genre_template_id: str | None,
    style_markdown: str,
    genre_markdown: str,
    include_in_epub: bool,
    epub_layout: str,
    preferred_aspect_ratio: str,
) -> dict:
    session = get_session()
    try:
        row = session.query(BookIllustrationProfile).filter(BookIllustrationProfile.book_id == book_id).first()
        if row is None:
            row = BookIllustrationProfile(book_id=book_id)
            session.add(row)

        style_template = _find_template(ILLUSTRATION_STYLE_TEMPLATES, style_template_id)
        genre_template = _find_template(ILLUSTRATION_GENRE_TEMPLATES, genre_template_id)
        combined_guidance = _combine_guidance(style_markdown, genre_markdown)

        row.style_template_id = style_template_id
        row.genre_template_id = genre_template_id
        row.style_template_name = style_template["name"] if style_template else None
        row.genre_template_name = genre_template["name"] if genre_template else None
        row.style_markdown = style_markdown
        row.genre_markdown = genre_markdown
        row.combined_guidance = combined_guidance
        row.include_in_epub = bool(include_in_epub)
        row.epub_layout = epub_layout or "full_width"
        row.preferred_aspect_ratio = preferred_aspect_ratio or "4:3"

        session.commit()
        session.refresh(row)

        get_illustration_style_markdown_path(book_id).write_text(style_markdown or "", encoding="utf-8")
        get_illustration_genre_markdown_path(book_id).write_text(genre_markdown or "", encoding="utf-8")
        get_illustration_profile_path(book_id).write_text(
            json.dumps(
                {
                    "book_id": book_id,
                    "style_template_id": style_template_id,
                    "genre_template_id": genre_template_id,
                    "include_in_epub": bool(include_in_epub),
                    "epub_layout": epub_layout or "full_width",
                    "preferred_aspect_ratio": preferred_aspect_ratio or "4:3",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return get_illustration_profile(book_id)
    finally:
        session.close()


def record_generated_asset(
    book_id: int,
    *,
    filename: str,
    image_bytes: bytes,
    chapter_id: int | None,
    chapter_title: str | None,
    scene_label: str,
    scene_prompt: str,
    final_prompt: str,
    caption: str,
    provider: str,
    model: str,
    aspect_ratio: str,
    epub_ready: bool = True,
) -> dict:
    generated_dir = _generated_dir(book_id)
    image_path = generated_dir / filename
    image_path.write_bytes(image_bytes)

    asset_id = Path(filename).stem
    metadata = {
        "asset_id": asset_id,
        "book_id": book_id,
        "chapter_id": chapter_id,
        "chapter_title": chapter_title,
        "scene_label": scene_label,
        "scene_prompt": scene_prompt,
        "final_prompt": final_prompt,
        "caption": caption,
        "provider": provider,
        "model": model,
        "aspect_ratio": aspect_ratio,
        "epub_ready": epub_ready,
        "filename": filename,
        "created_at": datetime.now().isoformat(),
    }
    (generated_dir / f"{asset_id}.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return _asset_from_metadata(f"/api/books/{book_id}/illustration-studio/assets/{filename}", metadata)


def build_illustration_context(book_id: int) -> dict:
    profile = get_illustration_profile(book_id)
    return {
        "style_template_name": profile.get("style_template_name"),
        "genre_template_name": profile.get("genre_template_name"),
        "style_markdown": profile.get("style_markdown") or "",
        "genre_markdown": profile.get("genre_markdown") or "",
        "combined_guidance": profile.get("combined_guidance") or "",
        "include_in_epub": bool(profile.get("include_in_epub")),
        "epub_layout": profile.get("epub_layout") or "full_width",
        "preferred_aspect_ratio": profile.get("preferred_aspect_ratio") or "4:3",
    }


def get_epub_illustrations_for_book(book_id: int) -> dict[int, dict]:
    profile = get_illustration_profile(book_id)
    if not profile.get("include_in_epub"):
        return {}
    chapter_assets: dict[int, dict] = {}
    for asset in reversed(list_generated_assets(book_id)):
        chapter_id = asset.get("chapter_id")
        if not chapter_id or not asset.get("epub_ready", True):
            continue
        chapter_assets[chapter_id] = asset
    return chapter_assets


def get_asset_path(book_id: int, filename: str) -> Path:
    return _generated_dir(book_id) / filename


def create_asset_filename() -> str:
    return f"{uuid.uuid4().hex}.png"


def delete_illustration_profile(book_id: int) -> None:
    studio_dir = ILLUSTRATION_STUDIO_ROOT / f"book_{book_id}"
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
