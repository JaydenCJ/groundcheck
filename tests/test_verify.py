"""End-to-end verdict policy: the five archetypes plus citation handling."""

from __future__ import annotations

import pytest

import groundcheck as gc


def find(report, kind=None, verdict=None):
    out = [
        f
        for f in report.findings
        if (kind is None or f.kind == kind) and (verdict is None or f.verdict == verdict)
    ]
    return out


def test_verbatim_quote_is_supported_even_recased_and_repunctuated(sources):
    answer = 'The doc states: "Reads are served from a write-through cache in front of the primary store".'
    report = gc.check(answer, sources)
    (q,) = find(report, kind="quote")
    assert q.verdict == gc.SUPPORTED
    assert q.score == 1.0
    assert q.evidence.source_id == "design"
    recased = 'It says "reads are served from a WRITE-THROUGH cache, in front of the primary store!"'
    (q,) = find(gc.check(recased, sources), kind="quote")
    assert q.verdict == gc.SUPPORTED


def test_fabricated_quote_is_unsupported(sources):
    answer = '"The cache guarantees strict serializability across regions" the doc claims.'
    report = gc.check(answer, sources)
    (q,) = find(report, kind="quote")
    assert q.verdict == gc.UNSUPPORTED


def test_doctored_quote_is_partial_with_diff_words(sources):
    # One word swapped inside an otherwise verbatim quote.
    answer = '"Reads are served from a write-back cache in front of the primary store" it says.'
    report = gc.check(answer, sources)
    (q,) = find(report, kind="quote")
    assert q.verdict == gc.PARTIAL
    assert "write-back" in q.missing


def test_paraphrased_claim_is_supported(sources):
    answer = "Cache entries expire after 300 seconds, enforced by a background sweeper."
    report = gc.check(answer, sources)
    (c,) = find(report, kind="claim")
    assert c.verdict == gc.SUPPORTED
    assert c.evidence.source_id == "design"


def test_claim_with_wrong_figure_is_capped_at_partial(sources):
    answer = "The cache absorbed 97% of read traffic during the 2025 load test."
    report = gc.check(answer, sources)
    (c,) = find(report, kind="claim")
    assert c.verdict == gc.PARTIAL
    assert "97%" in c.reason


def test_claim_with_correct_figure_is_supported(sources):
    answer = "The cache absorbed 92% of read traffic during the 2025 load test."
    report = gc.check(answer, sources)
    (c,) = find(report, kind="claim")
    assert c.verdict == gc.SUPPORTED


def test_fully_fabricated_claim_is_unsupported(sources):
    answer = "Enterprise revenue grew 40% year over year thanks to the rebate program."
    report = gc.check(answer, sources)
    (c,) = find(report, kind="claim")
    assert c.verdict == gc.UNSUPPORTED
    assert c.score < 0.4


def test_quote_cited_to_wrong_source_is_miscited(sources):
    answer = (
        'Per the design doc, "Invoices are generated on the first business day '
        'of each month" [1].'
    )
    report = gc.check(answer, sources)
    (q,) = find(report, kind="quote")
    assert q.verdict == gc.MISCITED
    assert q.evidence.source_id == "pricing"
    assert "[1]" in q.reason


def test_quote_cited_to_right_source_is_supported(sources):
    by_number = '"Invoices are generated on the first business day of each month" [2].'
    (q,) = find(gc.check(by_number, sources), kind="quote")
    assert q.verdict == gc.SUPPORTED
    by_name = '"Invoices are generated on the first business day of each month" [PRICING].'
    (q,) = find(gc.check(by_name, sources), kind="quote")
    assert q.verdict == gc.SUPPORTED  # labels resolve case-insensitively


def test_citation_to_nonexistent_source_is_miscited(sources):
    answer = '"Invoices are generated on the first business day of each month" [7].'
    report = gc.check(answer, sources)
    (q,) = find(report, kind="quote")
    assert q.verdict == gc.MISCITED
    assert "[7]" in q.reason


def test_claim_supported_only_by_uncited_source_is_miscited(sources):
    answer = "Refunds are issued as account credit within 5 business days [1]."
    report = gc.check(answer, sources)
    (c,) = find(report, kind="claim")
    assert c.verdict == gc.MISCITED
    assert c.evidence.source_id == "pricing"


def test_uncited_claim_searches_all_sources(sources):
    answer = "Refunds are issued as account credit within 5 business days."
    report = gc.check(answer, sources)
    (c,) = find(report, kind="claim")
    assert c.verdict == gc.SUPPORTED
    assert c.evidence.source_id == "pricing"


def test_resolve_citation_by_position_and_id(sources):
    srcs = [gc.Source(id=i, text=t) for i, t in sources]
    assert gc.resolve_citation("1", srcs).id == "design"
    assert gc.resolve_citation("pricing", srcs).id == "pricing"
    assert gc.resolve_citation("Design", srcs).id == "design"
    assert gc.resolve_citation("3", srcs) is None
    assert gc.resolve_citation("nope", srcs) is None


def test_sources_accepted_as_mapping_pairs_and_objects(sources):
    answer = "Cache entries expire after 300 seconds, enforced by a background sweeper."
    as_pairs = gc.check(answer, sources)
    as_mapping = gc.check(answer, dict(sources))
    as_objects = gc.check(answer, [gc.Source(id=i, text=t) for i, t in sources])
    assert (
        as_pairs.findings == as_mapping.findings == as_objects.findings
    )


def test_empty_source_set_and_duplicate_ids_raise():
    with pytest.raises(ValueError, match="at least one source"):
        gc.check("Some checkable claim about caching goes here.", {})
    with pytest.raises(ValueError, match="duplicate source id"):
        gc.check("text", [("a", "x"), ("a", "y")])


def test_answer_with_nothing_checkable_passes_vacuously(sources):
    report = gc.check("OK.", sources)
    assert report.findings == ()
    assert report.support_ratio == 1.0
    assert not report.fails("partial")


def test_evidence_excerpt_quotes_the_actual_source_text(sources):
    answer = "Cache entries expire after 300 seconds, enforced by a background sweeper."
    (c,) = gc.check(answer, sources).findings
    assert "300 seconds" in c.evidence.excerpt
    # Evidence offsets index the source text itself.
    design_text = dict(sources)["design"]
    assert design_text[c.evidence.start : c.evidence.end].startswith("Cache entries")


def test_full_answer_report_matches_the_archetypes(sources):
    answer = (
        'The design doc says: "Reads are served from a write-through cache in '
        "front of the primary store\" [1].\n\n"
        "Cache entries expire after 300 seconds and a background sweeper "
        "enforces expiry once per minute [1].\n\n"
        'According to the billing doc, "Invoices are generated on the first '
        'business day of each month" [1].\n\n'
        "The cache absorbed 97% of read traffic during the 2025 load test [1].\n\n"
        "Enterprise revenue grew 40% year over year thanks to the new rebate "
        "program [2].\n"
    )
    report = gc.check(answer, sources)
    assert [f.verdict for f in report.findings] == [
        gc.SUPPORTED,
        gc.SUPPORTED,
        gc.MISCITED,
        gc.PARTIAL,
        gc.UNSUPPORTED,
    ]
    assert report.counts() == {
        gc.SUPPORTED: 2,
        gc.PARTIAL: 1,
        gc.MISCITED: 1,
        gc.UNSUPPORTED: 1,
    }
    assert report.support_ratio == pytest.approx(0.4)
    # And the whole report is byte-deterministic across runs.
    reruns = [gc.check(answer, sources).to_json() for _ in range(3)]
    assert reruns[0] == reruns[1] == reruns[2]
