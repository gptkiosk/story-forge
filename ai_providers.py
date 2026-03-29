"""
AI provider routing for Story Forge.

Supports OpenClaw for Libby-based local workflows and OpenRouter as a hosted
fallback/provider for chapter ideation and context refinement.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from ai_prompt_contracts import (
    chapter_generation_task,
    context_refinement_task,
    illustration_prompt_task,
    next_chapter_ideas_task,
    shared_json_rules,
    voice_plan_refinement_task,
)
from integrations import get_ai_provider, get_openrouter_settings
from libby import libby_client


def _extract_json_payload(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if "\n" in stripped:
            stripped = stripped.split("\n", 1)[1]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        stripped = stripped[start:end + 1]
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ValueError("Model response was not a JSON object.")
    return parsed


class AIProviderManager:
    async def is_available(self) -> bool:
        provider = get_ai_provider()
        if provider == "openclaw":
            return await libby_client.is_available()
        if provider == "openrouter":
            settings = get_openrouter_settings()
            return bool(settings.get("api_key"))
        return False

    async def suggest_next_chapter_ideas(self, *, story_context: dict, chapter_count: int, current_book_title: str) -> dict:
        provider = get_ai_provider()
        if provider == "openclaw":
            return await libby_client.suggest_next_chapter_ideas(
                story_context=story_context,
                chapter_count=chapter_count,
                current_book_title=current_book_title,
            )
        return await self._openrouter_next_chapter_ideas(
            story_context=story_context,
            chapter_count=chapter_count,
            current_book_title=current_book_title,
        )

    async def submit_story_direction(self, *, story_direction: str, story_context: dict, chapter_title: str | None = None) -> dict:
        provider = get_ai_provider()
        if provider == "openclaw":
            return await libby_client.submit_story_direction(
                story_direction=story_direction,
                story_context=story_context,
                chapter_title=chapter_title,
            )
        return await self._openrouter_generate_chapter(
            story_direction=story_direction,
            story_context=story_context,
            chapter_title=chapter_title,
        )

    async def refine_context_summary(
        self,
        *,
        book_id: int,
        source_title: str,
        heuristic_summary: dict,
        source_excerpt: str,
        source_word_count: int,
    ) -> dict:
        provider = get_ai_provider()
        if provider == "openclaw":
            return await libby_client.refine_context_summary(
                book_id=book_id,
                source_title=source_title,
                heuristic_summary=heuristic_summary,
                source_excerpt=source_excerpt,
                source_word_count=source_word_count,
            )
        return await self._openrouter_refine_context(
            book_id=book_id,
            source_title=source_title,
            heuristic_summary=heuristic_summary,
            source_excerpt=source_excerpt,
            source_word_count=source_word_count,
        )

    async def refine_voice_plan(
        self,
        *,
        chapter_title: str,
        chapter_content: str,
        story_context: dict,
        voice_roster: dict,
        chapter_voice_map: dict,
    ) -> dict:
        provider = get_ai_provider()
        if provider == "openclaw":
            return await libby_client.refine_voice_plan(
                chapter_title=chapter_title,
                chapter_content=chapter_content,
                story_context=story_context,
                voice_roster=voice_roster,
                chapter_voice_map=chapter_voice_map,
            )
        return await self._openrouter_refine_voice_plan(
            chapter_title=chapter_title,
            chapter_content=chapter_content,
            story_context=story_context,
            voice_roster=voice_roster,
            chapter_voice_map=chapter_voice_map,
        )

    async def _chat_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        settings = get_openrouter_settings()
        api_key = settings.get("api_key", "")
        if not api_key:
            return {"success": False, "error": "OpenRouter API key is not configured."}

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if settings.get("site_url"):
            headers["HTTP-Referer"] = settings["site_url"]
        if settings.get("app_name"):
            headers["X-Title"] = settings["app_name"]

        payload = {
            "model": settings["model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.4,
            "response_format": {"type": "json_object"},
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{settings['base_url'].rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )
        except Exception as exc:
            return {"success": False, "error": f"OpenRouter request failed: {exc}"}

        if response.status_code != 200:
            return {"success": False, "error": f"OpenRouter error: {response.status_code} - {response.text}"}

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return {"success": True, "data": _extract_json_payload(content)}
        except Exception as exc:
            return {"success": False, "error": f"OpenRouter returned an unusable response: {exc}"}

    async def _openrouter_next_chapter_ideas(self, *, story_context: dict, chapter_count: int, current_book_title: str) -> dict:
        response = await self._chat_json(
            system_prompt=(
                f"You are a fiction continuity and plotting assistant. {shared_json_rules()} "
                f"{next_chapter_ideas_task()}"
            ),
            user_prompt=(
                f"Book title: {current_book_title}\n"
                f"Chapter count: {chapter_count}\n"
                f"Story context JSON:\n{json.dumps(story_context, ensure_ascii=True)}\n\n"
                "Return JSON with key ideas. It must be an array of exactly three objects. "
                "Each object must contain title, direction, and rationale."
            ),
        )
        if not response.get("success"):
            return response
        return {"success": True, "ideas": response["data"].get("ideas", [])}

    async def _openrouter_generate_chapter(self, *, story_direction: str, story_context: dict, chapter_title: str | None = None) -> dict:
        response = await self._chat_json(
            system_prompt=(
                f"You draft fiction chapters from outline direction. {shared_json_rules()} "
                f"{chapter_generation_task()}"
            ),
            user_prompt=(
                f"Requested chapter title: {chapter_title or ''}\n"
                f"Story direction: {story_direction}\n"
                f"Story context JSON:\n{json.dumps(story_context, ensure_ascii=True)}\n\n"
                "Return JSON with chapter_title and chapter_content."
            ),
        )
        if not response.get("success"):
            return response
        data = response["data"]
        return {
            "success": True,
            "chapter_title": data.get("chapter_title") or chapter_title or "Next Chapter",
            "chapter_content": data.get("chapter_content") or "",
        }

    async def _openrouter_refine_context(
        self,
        *,
        book_id: int,
        source_title: str,
        heuristic_summary: dict,
        source_excerpt: str,
        source_word_count: int,
    ) -> dict:
        response = await self._chat_json(
            system_prompt=(
                f"You refine fiction continuity memory. {shared_json_rules()} "
                f"{context_refinement_task()}"
            ),
            user_prompt=(
                f"Book id: {book_id}\n"
                f"Source title: {source_title}\n"
                f"Source word count: {source_word_count}\n"
                f"Heuristic summary JSON:\n{json.dumps(heuristic_summary, ensure_ascii=True)}\n\n"
                f"Source excerpt:\n{source_excerpt}\n\n"
                "Return JSON with summary_text, characters, plot_threads, world_details, style_notes."
            ),
        )
        if not response.get("success"):
            return response
        return {"success": True, "summary": response["data"]}

    async def _openrouter_refine_voice_plan(
        self,
        *,
        chapter_title: str,
        chapter_content: str,
        story_context: dict,
        voice_roster: dict,
        chapter_voice_map: dict,
    ) -> dict:
        response = await self._chat_json(
            system_prompt=(
                f"You refine voice assignments for a fiction audiobook workflow. {shared_json_rules()} "
                f"{voice_plan_refinement_task()}"
            ),
            user_prompt=(
                f"Chapter title: {chapter_title}\n"
                f"Chapter content:\n{chapter_content}\n\n"
                f"Story context JSON:\n{json.dumps(story_context, ensure_ascii=True)}\n\n"
                f"Voice roster JSON:\n{json.dumps(voice_roster, ensure_ascii=True)}\n\n"
                f"Current chapter voice map JSON:\n{json.dumps(chapter_voice_map, ensure_ascii=True)}\n\n"
                "Return JSON with narrator_speaker and segment_updates. "
                "segment_updates must be an array of objects with index, speaker, delivery_hint, and type. "
                "Cover every segment. Only change assignments, not text."
            ),
        )
        if not response.get("success"):
            return response
        data = response["data"]
        return {
            "success": True,
            "narrator_speaker": data.get("narrator_speaker") or "Narrator",
            "segment_updates": data.get("segment_updates") or [],
        }

    async def build_illustration_prompt(
        self,
        *,
        book_title: str,
        chapter_title: str | None,
        chapter_excerpt: str,
        scene_prompt: str,
        story_context: dict,
        style_studio: dict,
        illustration_studio: dict,
        provider_override: str | None = None,
    ) -> dict:
        provider = provider_override or get_ai_provider()
        if provider == "openclaw":
            return await libby_client.build_illustration_prompt(
                book_title=book_title,
                chapter_title=chapter_title,
                chapter_excerpt=chapter_excerpt,
                scene_prompt=scene_prompt,
                story_context=story_context,
                style_studio=style_studio,
                illustration_studio=illustration_studio,
            )
        response = await self._chat_json(
            system_prompt=(
                f"You build production-ready fiction illustration prompts. {shared_json_rules()} "
                f"{illustration_prompt_task()}"
            ),
            user_prompt=(
                f"Book title: {book_title}\n"
                f"Chapter title: {chapter_title or ''}\n"
                f"Chapter excerpt:\n{chapter_excerpt}\n\n"
                f"Scene prompt: {scene_prompt}\n\n"
                f"Story context JSON:\n{json.dumps(story_context, ensure_ascii=True)}\n\n"
                f"Style studio JSON:\n{json.dumps(style_studio, ensure_ascii=True)}\n\n"
                f"Illustration studio JSON:\n{json.dumps(illustration_studio, ensure_ascii=True)}\n\n"
                "Return JSON with prompt, caption, and negative_prompt."
            ),
        )
        if not response.get("success"):
            return response
        data = response["data"]
        return {
            "success": True,
            "prompt": data.get("prompt") or scene_prompt,
            "caption": data.get("caption") or (chapter_title or book_title),
            "negative_prompt": data.get("negative_prompt") or "",
        }


ai_provider_manager = AIProviderManager()
