"""Span extraction: quotes, claims, citations, and Markdown masking."""

from __future__ import annotations

from groundcheck.config import Config
from groundcheck.extract import extract_spans, find_citations, mask_markup


def kinds(spans):
    return [s.kind for s in spans]


def test_straight_and_curly_double_quotes_become_quote_spans():
    spans = extract_spans('The doc says "the cache is write-through here".')
    quote = [s for s in spans if s.kind == "quote"]
    assert len(quote) == 1
    assert quote[0].text == "the cache is write-through here"
    spans = extract_spans("It notes “expiry runs once per minute” today.")
    assert [s.text for s in spans if s.kind == "quote"] == [
        "expiry runs once per minute"
    ]


def test_short_quotes_are_not_standalone_spans():
    # "yes" is two-words-short of a checkable quote; the sentence remains a claim.
    spans = extract_spans('The reviewer wrote "fine" about the cache design work.')
    assert kinds(spans) == ["claim"]
    assert '"fine"' in spans[0].text or "fine" in spans[0].text


def test_sentence_containing_a_checked_quote_is_not_also_a_claim():
    spans = extract_spans(
        'According to the doc, "reads are served from the cache first" [1].'
    )
    assert kinds(spans) == ["quote"]


def test_blockquote_lines_are_one_quote_span():
    text = "Summary line first.\n\n> quoted line one\n> quoted line two\n"
    spans = extract_spans(text)
    quotes = [s for s in spans if s.kind == "quote"]
    assert len(quotes) == 1
    assert "quoted line one" in quotes[0].text
    assert "quoted line two" in quotes[0].text
    assert ">" not in quotes[0].text  # markers stripped from display text


def test_numeric_citation_attaches_to_the_sentence_spans():
    spans = extract_spans("The cache absorbed most of the read traffic [1].")
    assert spans[0].citations == ("1",)


def test_named_multi_and_footnote_citations():
    spans = extract_spans("Overages are invoiced in arrears monthly [pricing, 2].")
    assert spans[0].citations == ("pricing", "2")
    spans = extract_spans("Refunds are issued as account credit quickly [^3].")
    assert spans[0].citations == ("3",)


def test_task_boxes_and_markdown_links_are_not_citations():
    assert find_citations("- [x] done\n- [ ] todo\n") == []
    # [text](url) is a link; the label must not register as a citation.
    assert find_citations("see [the design doc](https://example.test/design)") == []


def test_fenced_and_inline_code_are_masked_and_never_checked():
    text = "Real claim about the cache expiry sweeper here.\n\n```\nfabricated code claim 999\n```\n"
    spans = extract_spans(text)
    assert len(spans) == 1
    assert "999" not in spans[0].text
    spans = extract_spans("Set the `cache_ttl_seconds` option to tune expiry behavior.")
    assert all("cache_ttl_seconds" not in s.text for s in spans)


def test_mask_markup_preserves_length_and_newlines():
    text = "a `code` b\n```\nx\ny\n```\nend https://example.test/path ok"
    masked = mask_markup(text)
    assert len(masked) == len(text)
    assert masked.count("\n") == text.count("\n")
    assert "example.test" not in masked


def test_questions_short_and_stopword_only_sentences_are_not_claims():
    assert extract_spans("Does the cache serve every read from memory first?") == []
    assert extract_spans("It works fine.") == []
    assert extract_spans("It is what it is and that is that.") == []


def test_spans_carry_one_based_lines_and_are_sorted_by_position():
    text = "intro line\n\nThe cache absorbed most read traffic in the load test.\n"
    assert extract_spans(text)[0].line == 3
    text = (
        'First real claim about cache expiry and sweepers here [1]. '
        'Then a quote: "reads are served from the cache" [2].'
    )
    spans = extract_spans(text)
    assert spans == sorted(spans, key=lambda s: (s.start, s.end))


def test_quotes_only_config_skips_claims():
    cfg = Config(check_claims=False)
    text = 'A checkable claim about the cache sweeper expiry. And "a quoted cache phrase here".'
    spans = extract_spans(text, cfg)
    assert kinds(spans) == ["quote"]


def test_unbalanced_stray_quote_does_not_capture_a_paragraph():
    text = 'A stray " mark.\n\nLater "a real quoted phrase here" appears.'
    spans = extract_spans(text)
    quotes = [s for s in spans if s.kind == "quote"]
    assert [q.text for q in quotes] == ["a real quoted phrase here"]
