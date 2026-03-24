"""
Libby integration module for Story Forge.

Libby is an OpenClaw publishing expert agent that helps with:
- Editing and making suggestions on submitted chapters
- Rewriting chapters based on feedback
- Generating chapters from story directions
- Maintaining story context across a novel-length work

Libby connects via her OpenClaw agent API endpoint.
"""

import logging
import os
import shutil
import subprocess
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

LIBBY_TRANSPORT = os.environ.get("LIBBY_TRANSPORT", "openclaw")
LIBBY_API_URL = os.environ.get("LIBBY_API_URL", "http://localhost:8100")
LIBBY_TIMEOUT = int(os.environ.get("LIBBY_TIMEOUT", "120"))
LIBBY_AGENT_ID = os.environ.get("LIBBY_AGENT_ID", "libby")


class SubmissionType:
    """Types of submissions Libby can process."""
    CHAPTER_REVIEW = "chapter_review"          # Submit finished chapter for editing/suggestions
    CHAPTER_REWRITE = "chapter_rewrite"        # Request chapter rewrite based on feedback
    STORY_DIRECTION = "story_direction"        # Submit story direction for chapter creation
    CONTEXT_UPDATE = "context_update"          # Update Libby's story context
    CONTEXT_REFINEMENT = "context_refinement"  # Refine extracted story context
    NEXT_CHAPTER_IDEAS = "next_chapter_ideas"  # Generate next chapter scenarios


class SubmissionStatus:
    """Status of a submission to Libby."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    AWAITING_APPROVAL = "awaiting_approval"


# =============================================================================
# Libby Client
# =============================================================================


class LibbyClient:
    """Client for communicating with Libby's OpenClaw agent API."""

    def __init__(self, api_url: Optional[str] = None, timeout: int = LIBBY_TIMEOUT):
        self.api_url = api_url or LIBBY_API_URL
        self.timeout = timeout

    async def is_available(self) -> bool:
        """Check if Libby is reachable."""
        if LIBBY_TRANSPORT == "openclaw":
            return self._openclaw_available()
        return False

    async def submit_chapter_for_review(
        self,
        chapter_content: str,
        story_context: dict,
        instructions: Optional[str] = None,
    ) -> dict:
        """
        Submit a chapter to Libby for editorial review.

        Args:
            chapter_content: The chapter text to review
            story_context: Current story context (characters, plot, etc.)
            instructions: Optional specific instructions for Libby

        Returns:
            dict with Libby's response (suggestions, edits, etc.)
        """
        payload = {
            "type": SubmissionType.CHAPTER_REVIEW,
            "chapter_content": chapter_content,
            "story_context": story_context,
            "instructions": instructions or "Please review this chapter for consistency, pacing, and prose quality. Provide specific suggestions.",
            "timestamp": datetime.now().isoformat(),
        }

        return await self._send_request("/process", payload)

    async def submit_for_rewrite(
        self,
        chapter_content: str,
        story_context: dict,
        feedback: str,
    ) -> dict:
        """
        Submit a chapter to Libby for rewriting based on feedback.

        Args:
            chapter_content: The original chapter text
            story_context: Current story context
            feedback: What changes the author wants

        Returns:
            dict with Libby's rewritten chapter
        """
        payload = {
            "type": SubmissionType.CHAPTER_REWRITE,
            "chapter_content": chapter_content,
            "story_context": story_context,
            "feedback": feedback,
            "timestamp": datetime.now().isoformat(),
        }

        return await self._send_request("/process", payload)

    async def submit_story_direction(
        self,
        story_direction: str,
        story_context: dict,
        chapter_title: Optional[str] = None,
    ) -> dict:
        """
        Submit a story direction to Libby for chapter creation.

        Args:
            story_direction: Description of what should happen in the chapter
            story_context: Current story context
            chapter_title: Optional title for the chapter

        Returns:
            dict with Libby's generated chapter content
        """
        payload = {
            "type": SubmissionType.STORY_DIRECTION,
            "story_direction": story_direction,
            "story_context": story_context,
            "chapter_title": chapter_title,
            "timestamp": datetime.now().isoformat(),
        }

        return await self._send_request("/process", payload)

    async def suggest_next_chapter_ideas(
        self,
        *,
        story_context: dict,
        chapter_count: int,
        current_book_title: str,
    ) -> dict:
        payload = {
            "type": SubmissionType.NEXT_CHAPTER_IDEAS,
            "story_context": story_context,
            "chapter_count": chapter_count,
            "current_book_title": current_book_title,
            "instructions": (
                "Suggest exactly three distinct next-chapter scenarios for this book. "
                "Each scenario should be plausible from the current continuity, concise, "
                "and actionable for drafting. Return JSON with an ideas array. Each idea "
                "should include title, direction, and rationale."
            ),
            "timestamp": datetime.now().isoformat(),
        }
        return await self._send_request("/process", payload)

    async def update_context(self, story_context: dict, book_id: int) -> dict:
        """
        Push updated story context to Libby.

        Args:
            story_context: Full story context to update
            book_id: Book ID this context belongs to

        Returns:
            dict with confirmation
        """
        payload = {
            "type": SubmissionType.CONTEXT_UPDATE,
            "story_context": story_context,
            "book_id": book_id,
            "timestamp": datetime.now().isoformat(),
        }

        return await self._send_request("/context", payload)

    async def refine_context_summary(
        self,
        *,
        book_id: int,
        source_title: str,
        heuristic_summary: dict,
        source_excerpt: str,
        source_word_count: int,
    ) -> dict:
        """
        Ask Libby to normalize and refine a heuristic context summary.

        This keeps token usage lower than sending an entire manuscript while still
        giving Libby enough evidence to remove false positives and compress the
        result into a more useful continuity format.
        """
        payload = {
            "type": SubmissionType.CONTEXT_REFINEMENT,
            "book_id": book_id,
            "source_title": source_title,
            "source_word_count": source_word_count,
            "heuristic_summary": heuristic_summary,
            "source_excerpt": source_excerpt,
            "instructions": (
                "Refine this context summary for a fiction book. Remove false character "
                "names such as common capitalized words, merge duplicate or alias names, "
                "keep only evidence-backed facts, and return concise continuity memory. "
                "Do not invent details. Respond as JSON with keys: summary_text, "
                "characters, plot_threads, world_details, style_notes."
            ),
            "timestamp": datetime.now().isoformat(),
        }

        return await self._send_request("/process", payload)

    async def _send_request(self, endpoint: str, payload: dict) -> dict:
        """Send a request to Libby."""
        if LIBBY_TRANSPORT == "openclaw":
            return self._send_via_openclaw(payload)
        return {
            "success": False,
            "error": "Unsupported Libby transport. Configure LIBBY_TRANSPORT=openclaw.",
        }

    def _openclaw_available(self) -> bool:
        if shutil.which("openclaw") is None:
            return False
        try:
            result = subprocess.run(
                ["openclaw", "sessions", "--agent", LIBBY_AGENT_ID, "--json"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return result.returncode == 0 and '"count"' in result.stdout
        except Exception:
            return False

    def _send_via_openclaw(self, payload: dict) -> dict:
        if shutil.which("openclaw") is None:
            return {
                "success": False,
                "error": "OpenClaw CLI is not installed or not on PATH.",
            }

        prompt = self._build_openclaw_prompt(payload)
        try:
            result = subprocess.run(
                [
                    "openclaw",
                    "agent",
                    "--agent",
                    LIBBY_AGENT_ID,
                    "--message",
                    prompt,
                    "--timeout",
                    str(self.timeout),
                    "--json",
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout + 15,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Libby is taking too long to respond. She may be processing a large request.",
            }
        except Exception as exc:
            return {
                "success": False,
                "error": f"Error communicating with Libby through OpenClaw: {exc}",
            }

        if result.returncode != 0:
            error_text = (result.stderr or result.stdout or "").strip()
            return {
                "success": False,
                "error": error_text or "Libby agent command failed.",
            }

        try:
            response = self._parse_openclaw_result(result.stdout)
        except Exception as exc:
            return {
                "success": False,
                "error": f"Libby returned an unreadable response: {exc}",
            }

        return {
            "success": True,
            **response,
        }

    def _build_openclaw_prompt(self, payload: dict) -> str:
        request_type = payload.get("type")
        shared_rules = (
            "You are responding to Story Forge app traffic. "
            "Return JSON only, with no markdown fences or extra commentary. "
            "Do not invent facts beyond the supplied context."
        )

        if request_type == SubmissionType.CONTEXT_REFINEMENT:
            return (
                f"{shared_rules}\n\n"
                "Task: refine context memory.\n"
                "Output keys: summary_text, characters, plot_threads, world_details, style_notes.\n\n"
                f"Payload:\n{json_dumps(payload)}"
            )
        if request_type == SubmissionType.NEXT_CHAPTER_IDEAS:
            return (
                f"{shared_rules}\n\n"
                "Task: provide exactly 3 next chapter ideas.\n"
                "Output shape: {\"ideas\":[{\"title\":\"...\",\"direction\":\"...\",\"rationale\":\"...\"}]}\n\n"
                f"Payload:\n{json_dumps(payload)}"
            )
        if request_type == SubmissionType.STORY_DIRECTION:
            return (
                f"{shared_rules}\n\n"
                "Task: draft one chapter from the supplied story direction.\n"
                "Output shape: {\"chapter_title\":\"...\",\"chapter_content\":\"...\"}\n\n"
                f"Payload:\n{json_dumps(payload)}"
            )
        if request_type == SubmissionType.CHAPTER_REVIEW:
            return (
                f"{shared_rules}\n\n"
                "Task: review the chapter and return structured editorial notes as JSON.\n\n"
                f"Payload:\n{json_dumps(payload)}"
            )
        if request_type == SubmissionType.CHAPTER_REWRITE:
            return (
                f"{shared_rules}\n\n"
                "Task: rewrite the chapter based on the feedback.\n"
                "Output shape: {\"chapter_title\":\"...\",\"chapter_content\":\"...\"}\n\n"
                f"Payload:\n{json_dumps(payload)}"
            )
        if request_type == SubmissionType.CONTEXT_UPDATE:
            return (
                f"{shared_rules}\n\n"
                "Task: acknowledge context update and return JSON.\n\n"
                f"Payload:\n{json_dumps(payload)}"
            )
        return f"{shared_rules}\n\nPayload:\n{json_dumps(payload)}"

    def _parse_openclaw_result(self, stdout: str) -> dict:
        data = json_loads(stdout)
        for key in ("reply", "message"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                parsed = try_parse_json_block(value)
                if parsed is not None:
                    return parsed
                return {"output": value.strip()}
            if isinstance(value, dict):
                return value
        return data


def try_parse_json_block(value: str) -> dict | None:
    stripped = value.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            parsed = json_loads(stripped)
        except Exception:
            return None
        if isinstance(parsed, dict):
            return parsed
    return None


def json_dumps(value: dict) -> str:
    import json
    return json.dumps(value, indent=2, ensure_ascii=True)


def json_loads(value: str):
    import json
    return json.loads(value)


# Global client instance
libby_client = LibbyClient()
