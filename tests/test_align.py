"""Alignment engine: exact search, windows, scoring, number anchors."""

from __future__ import annotations

from groundcheck.align import (
    WindowMatch,
    anchors_present,
    best_window,
    find_exact,
    lcs_run,
)
from groundcheck.config import Config
from groundcheck.textnorm import tokenize

CFG = Config()


def test_find_exact_and_lcs_run_primitives():
    hay = ["a", "b", "c", "d", "b", "c"]
    assert find_exact(["b", "c"], hay) == 1  # first occurrence wins
    assert find_exact(["c", "b"], hay) is None
    assert find_exact([], hay) is None
    assert find_exact(["a", "b", "c", "d", "b", "c", "x"], hay) is None
    # lcs_run measures *contiguous* overlap only.
    assert lcs_run(["a", "b", "c"], ["x", "a", "b", "y", "c"]) == 2
    assert lcs_run(["a", "b"], ["b", "a"]) == 1
    assert lcs_run([], ["a"]) == 0


def test_verbatim_needle_scores_exactly_one():
    hay = tokenize("The cache absorbed 92% of read traffic at the p99 target.")
    needle = tokenize("cache absorbed 92% of read traffic")
    m = best_window(needle, hay, CFG)
    assert m is not None and m.exact
    assert m.score == 1.0
    assert m.missing == ()


def test_repunctuated_and_recased_quote_is_still_exact():
    hay = tokenize('It said: "Reads are served from a write-through cache."')
    needle = tokenize("reads are served from a WRITE-THROUGH cache")
    m = best_window(needle, hay, CFG)
    assert m is not None and m.exact


def test_paraphrase_scores_between_zero_and_one():
    hay = tokenize(
        "Cache entries expire after 300 seconds, enforced by a background sweeper."
    )
    needle = tokenize("entries in the cache expire after 300 seconds")
    m = best_window(needle, hay, CFG)
    assert m is not None and not m.exact
    assert 0.5 < m.score < 1.0


def test_unrelated_text_scores_low():
    hay = tokenize("Invoices are generated on the first business day of each month.")
    needle = tokenize("the cache absorbed most read traffic during the load test")
    m = best_window(needle, hay, CFG)
    assert m is None or m.score < 0.3


def test_no_shared_content_words_returns_none():
    hay = tokenize("alpha beta gamma delta")
    needle = tokenize("the epsilon of zeta was theta")
    assert best_window(needle, hay, CFG) is None


def test_missing_lists_uncovered_content_words_in_span_order():
    hay = tokenize("The cache absorbed read traffic during the test.")
    needle = tokenize("the cache absorbed quarterly rebate traffic")
    m = best_window(needle, hay, CFG)
    assert m is not None
    assert list(m.missing) == ["quarterly", "rebate"]


def test_stopwords_barely_affect_the_score():
    hay = tokenize("cache absorbed traffic")
    with_stops = best_window(tokenize("the cache absorbed the traffic"), hay, CFG)
    without = best_window(tokenize("cache absorbed traffic"), hay, CFG)
    assert with_stops is not None and without is not None
    assert without.exact
    assert with_stops.score > 0.8  # missing "the" twice costs almost nothing


def test_earliest_window_wins_ties():
    hay = tokenize("cache miss here ... cache miss there")
    needle = tokenize("cache miss happened")
    m = best_window(needle, hay, CFG)
    assert m is not None
    assert m.start == 0


def test_alignment_is_deterministic():
    hay = tokenize(
        "During the 2025 load test the cache absorbed 92% of read traffic "
        "at the p99 latency target of 12 ms, then writes invalidated entries."
    )
    needle = tokenize("the cache absorbed 92% of traffic in the load test")
    runs = [best_window(needle, hay, CFG) for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]


def test_anchor_detection_flags_absent_numbers():
    hay = tokenize("During the load test the cache absorbed 92% of read traffic.")
    needle = tokenize("the cache absorbed 97% of read traffic")
    m = best_window(needle, hay, CFG)
    assert m is not None
    assert anchors_present(needle, hay, m, CFG) == ("97%",)


def test_anchor_nearby_but_outside_window_still_counts():
    # The figure sits a few tokens before the matched words; padding finds it.
    hay = tokenize(
        "It absorbed 92% overall. The cache served every read from memory."
    )
    needle = tokenize("the cache served 92% of every read from memory")
    m = best_window(needle, hay, CFG)
    assert m is not None
    assert anchors_present(needle, hay, m, CFG) == ()


def test_anchor_ignores_spans_without_numbers():
    hay = tokenize("cache absorbed traffic")
    needle = tokenize("cache absorbed traffic")
    m = best_window(needle, hay, CFG)
    assert m is not None
    assert anchors_present(needle, hay, m, CFG) == ()
    # WindowMatch itself is a plain value object.
    assert m == WindowMatch(0, 3, 1.0, 1.0, 1.0, True, ())
