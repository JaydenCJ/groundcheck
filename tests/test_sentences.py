"""Sentence splitting: offsets must be exact, boundaries deterministic."""

from __future__ import annotations

from groundcheck.sentences import split_sentences


def _texts(text):
    return [text[s:e] for s, e in split_sentences(text)]


def test_simple_two_sentence_split():
    assert _texts("It works. It really does.") == ["It works.", "It really does."]


def test_spans_index_the_original_string():
    text = "  First one.   Second one!  "
    for s, e in split_sentences(text):
        assert text[s:e] == text[s:e].strip()
    assert _texts(text) == ["First one.", "Second one!"]


def test_abbreviations_and_initials_do_not_split():
    text = "See e.g. the appendix. Dr. Smith agrees."
    assert _texts(text) == ["See e.g. the appendix.", "Dr. Smith agrees."]
    assert _texts("J. Smith wrote it. True.") == ["J. Smith wrote it.", "True."]


def test_decimal_numbers_do_not_split():
    assert _texts("Latency is 3.5 ms today. Good.") == [
        "Latency is 3.5 ms today.",
        "Good.",
    ]


def test_question_and_exclamation_terminate():
    assert _texts("Is it fast? It is! Really.") == ["Is it fast?", "It is!", "Really."]


def test_closing_quote_stays_with_the_sentence():
    text = 'He said "stop." Then left.'
    assert _texts(text) == ['He said "stop."', "Then left."]


def test_blank_line_is_always_a_boundary():
    text = "no terminator here\n\nand a second block"
    assert _texts(text) == ["no terminator here", "and a second block"]


def test_list_items_are_separate_units():
    text = "- first point\n- second point\n1. third point\n"
    assert _texts(text) == ["- first point", "- second point", "1. third point"]


def test_heading_is_its_own_unit():
    text = "# Title\nBody sentence here."
    assert _texts(text) == ["# Title", "Body sentence here."]


def test_trailing_text_kept_and_empty_input_yields_nothing():
    assert _texts("Complete. and a dangling tail") == [
        "Complete.",
        "and a dangling tail",
    ]
    assert split_sentences("") == []
    assert split_sentences("\n\n  \n") == []
