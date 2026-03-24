"""
Libby integration module for Story Forge.

Libby is an OpenClaw publishing expert agent that helps with:
- Editing and making suggestions on submitted chapters
- Rewriting chapters based on feedback
- Generating chapters from story directions
- Maintaining story context across a novel-length work

Libby connects via her OpenClaw agent API endpoint.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

# Libby's OpenClaw agent endpoint
LIBBY_API_URL = os.environ.get("LIBBY_API_URL", "http://localhost:8100")
LIBBY_TIMEOUT = int(os.environ.get("LIBBY_TIMEOUT", "120"))


class SubmissionType:
    """Types of submissions Libby can process."""
    CHAPTER_REVIEW = "chapter_review"          # Submit finished chapter for editing/suggestions
    CHAPTER_REWRITE = "chapter_rewrite"        # Request chapter rewrite based on feedback
    STORY_DIRECTION = "story_direction"        # Submit story direction for chapter creation
    CONTEXT_UPDATE = "context_update"          # Update Libby's story context


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
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.api_url}/health")
                return response.status_code == 200
        except Exception:
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

    async def _send_request(self, endpoint: str, payload: dict) -> dict:
        """Send a request to Libby's API."""
        try:
            async with httpx.AsyncClient(timeout=float(self.timeout)) as client:
                response = await client.post(
                    f"{self.api_url}{endpoint}",
                    json=payload,
                )

                if response.status_code != 200:
                    return {
                        "success": False,
                        "error": f"Libby returned status {response.status_code}: {response.text}",
                    }

                return {
                    "success": True,
                    **response.json(),
                }

        except httpx.TimeoutException:
            return {
                "success": False,
                "error": "Libby is taking too long to respond. She may be processing a large request.",
            }
        except httpx.ConnectError:
            return {
                "success": False,
                "error": "Cannot reach Libby. Make sure she is running and LIBBY_API_URL is configured correctly.",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Error communicating with Libby: {str(e)}",
            }


# Global client instance
libby_client = LibbyClient()
