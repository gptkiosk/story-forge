import subprocess

import libby
from libby import LibbyClient, SubmissionType, extract_jsonish_payload, try_parse_json_block


def test_try_parse_json_block_handles_fenced_json():
    parsed = try_parse_json_block(
        """```json
{"chapter_title":"Chapter 2","chapter_content":"Draft body"}
```"""
    )
    assert parsed == {"chapter_title": "Chapter 2", "chapter_content": "Draft body"}


def test_openclaw_prompt_for_next_chapter_ideas_mentions_exact_shape():
    client = LibbyClient()
    prompt = client._build_openclaw_prompt(
        {
            "type": SubmissionType.NEXT_CHAPTER_IDEAS,
            "story_context": {"summary_text": "Context"},
        }
    )
    assert "exactly 3 next chapter ideas" in prompt
    assert '"ideas"' in prompt


def test_send_via_openclaw_parses_reply_json(monkeypatch):
    client = LibbyClient(timeout=5)

    monkeypatch.setattr(libby.shutil, "which", lambda name: "/opt/homebrew/bin/openclaw")

    class Result:
        returncode = 0
        stdout = '{"status":"completed","reply":"{\\"ideas\\":[{\\"title\\":\\"Option A\\",\\"direction\\":\\"Go left\\",\\"rationale\\":\\"Fits continuity\\"}]}"}'
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Result())

    response = client._send_via_openclaw({"type": SubmissionType.NEXT_CHAPTER_IDEAS})
    assert response["success"] is True
    assert response["ideas"][0]["title"] == "Option A"


def test_extract_jsonish_payload_reads_openclaw_message_content_blocks():
    payload = extract_jsonish_payload(
        {
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": '{"ideas":[{"title":"The First Volunteer","direction":"Go next","rationale":"Fits continuity"}]}',
                }
            ],
        }
    )
    assert payload["ideas"][0]["title"] == "The First Volunteer"


def test_extract_jsonish_payload_reads_openclaw_result_payloads():
    payload = extract_jsonish_payload(
        {
            "payloads": [
                {
                    "text": '{"ideas":[{"title":"Payload Idea","direction":"Next move","rationale":"Works now"}]}',
                    "mediaUrl": None,
                }
            ]
        }
    )
    assert payload["ideas"][0]["title"] == "Payload Idea"


def test_openclaw_available_uses_sessions_command(monkeypatch):
    client = LibbyClient()
    monkeypatch.setattr(libby.shutil, "which", lambda name: "/opt/homebrew/bin/openclaw")

    class Result:
        returncode = 0
        stdout = '{"count":2}'
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Result())
    assert client._openclaw_available() is True


def test_openclaw_prompt_for_story_direction_forbids_em_dashes_and_scene_breaks():
    client = LibbyClient()
    prompt = client._build_openclaw_prompt(
        {
            "type": SubmissionType.STORY_DIRECTION,
            "story_context": {"summary_text": "Context"},
        }
    )
    normalized = prompt.lower()
    assert "do not use em dashes" in normalized
    assert "do not use triple hyphen scene breaks" in normalized
