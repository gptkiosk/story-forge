from context_engine import _extract_characters, _normalize_refined_payload


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
