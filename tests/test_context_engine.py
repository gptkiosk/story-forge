from types import SimpleNamespace

from context_engine import (
    _build_runtime_context_packet_from_documents,
    _extract_characters,
    _normalize_refined_payload,
)


def test_extract_characters_filters_common_false_positive_words():
    text = (
        "The city gates opened as What and There faded from the sign. "
        "Jamal stepped beside Mira Chen while Captain Sol watched."
    )

    characters = _extract_characters(text)

    assert "Jamal" in characters
    assert "Mira Chen" in characters
    assert "Captain Sol" in characters
    assert "The" not in characters
    assert "What" not in characters
    assert "There" not in characters


def test_normalize_refined_payload_uses_fallback_for_invalid_lists():
    fallback = {
        "summary_text": "Base summary",
        "characters": ["Jamal"],
        "plot_threads": ["Base plot thread"],
        "world_details": ["Base world detail"],
        "style_notes": ["Base style note"],
        "source_word_count": 1200,
    }

    refined = _normalize_refined_payload(
        {
            "summary_text": "Refined summary",
            "characters": ["The", "Jamal"],
            "plot_threads": "not-a-list",
            "world_details": [],
            "style_notes": [],
        },
        fallback,
    )

    assert refined["summary_text"] == "Refined summary"
    assert refined["characters"] == ["Jamal"]
    assert refined["plot_threads"] == ["Base plot thread"]


def test_runtime_context_packet_suppresses_future_timeline_facts_but_keeps_style():
    prior_document = SimpleNamespace(
        title="Book 0 Notes",
        timeline_relation="prior_timeline",
        use_for_facts=1,
        use_for_style=1,
        word_count=1200,
        extracted_summary={
            "summary_text": "Arin uncovers the old station map.",
            "characters": ["Arin Vale"],
            "plot_threads": ["The station map points to a hidden gate."],
            "world_details": ["Europa Station is crumbling at the rim."],
            "style_notes": ["Measured suspense with clipped dialogue."],
            "source_word_count": 1200,
        },
    )
    future_document = SimpleNamespace(
        title="Book 3 Finale",
        timeline_relation="future_timeline",
        use_for_facts=0,
        use_for_style=1,
        word_count=1800,
        extracted_summary={
            "summary_text": "Commander Ilex reveals the crown protocol.",
            "characters": ["Commander Ilex"],
            "plot_threads": ["The crown protocol remakes the fleet."],
            "world_details": ["The royal archive burns over Mars."],
            "style_notes": ["Keeps the same reflective cadence."],
            "source_word_count": 1800,
        },
    )

    packet = _build_runtime_context_packet_from_documents([prior_document, future_document])

    assert "Arin Vale" in packet["characters"]
    assert "Commander Ilex" not in packet["characters"]
    assert packet["timeline_guidance"]["future_context_suppressed"] is True
    assert "Book 3 Finale" in packet["timeline_guidance"]["future_document_titles"]
    assert "reflective cadence" in " ".join(packet["style_notes"]).lower()
