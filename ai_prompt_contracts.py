"""
Shared Story Forge AI prompt contracts.

These helpers keep OpenRouter and Libby aligned on task framing so provider
switching feels more consistent.
"""

from __future__ import annotations


def shared_json_rules() -> str:
    return (
        "Return strict JSON only with no markdown fences or extra commentary. "
        "Do not invent facts beyond the supplied story context. "
        "Respect timeline guidance in the context packet and never surface future-only spoilers as present facts."
    )


def next_chapter_ideas_task() -> str:
    return (
        "Suggest exactly three distinct next-chapter scenarios. Preserve existing continuity, "
        "do not invent unsupported facts, and keep each scenario concise and actionable for drafting. "
        "If the context packet marks future chronology as suppressed, do not introduce future-only characters, reveals, "
        "relationships, or world changes."
    )


def chapter_generation_task() -> str:
    return (
        "Draft one chapter from the supplied story direction. Preserve continuity, tone, and character logic. "
        "Do not use em dashes and do not use triple hyphen scene breaks; replace them with commas, periods, or plain sentence transitions. "
        "If the context packet marks future chronology as suppressed, do not surface future-only characters, reveals, relationships, or world changes."
    )


def context_refinement_task() -> str:
    return (
        "Refine fiction continuity memory. Remove false character names, merge duplicate or alias names, keep only evidence-backed details, "
        "and stay concise. If a source is marked as future-timeline or style-only, keep it out of active factual continuity and use it only for style notes."
    )


def voice_plan_refinement_task() -> str:
    return (
        "Refine narrator and dialogue speaker assignments for a fiction chapter. Preserve the existing segment text exactly and do not merge, split, or rewrite segments. "
        "Use the cleaned roster, preserve continuity, and choose a chapter-level narration speaker when the chapter is strongly in one character's perspective. "
        "For every segment, choose the best speaker and delivery hint from: neutral, quiet, questioning, heightened, heavy. "
        "Narration should stay neutral by default, but shift when the prose clearly carries fear, grief, urgency, exhaustion, or a strong POV emotional charge. "
        "Dialogue should use delivery hints that reflect the line and nearby narration, not just punctuation."
    )


def illustration_prompt_task() -> str:
    return (
        "Build one polished book-illustration prompt from the supplied story context, chapter context, and illustration studio guidance. "
        "Keep continuity accurate, avoid future-only spoilers, and optimize for consistent recurring character appearance, wardrobe, setting logic, and tone. "
        "The prompt should be visual, concrete, and production-ready for a cost-conscious illustration model. "
        "Favor readable composition, clear focal hierarchy, and EPUB-friendly staging over excessive detail clutter."
    )
