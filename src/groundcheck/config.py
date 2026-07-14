"""Tunable knobs for span extraction and alignment scoring.

All defaults are plain numbers chosen against the fixture corpus in
``tests/``; nothing here is learned or sampled. A ``Config`` is immutable so
a single instance can be shared across threads and reused between calls
without surprise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet

from .textnorm import word_key

# Function words that carry almost no evidential weight. Kept deliberately
# small: over-aggressive stopword lists make short factual claims
# unfalsifiable. The set is folded through the same key function as real
# tokens so lookups are consistent.
_STOPWORDS_RAW = (
    "a an the this that these those it its they them their he she his her "
    "i we you your our us me my "
    "is are was were be been being am do does did done has have had having "
    "will would can could should shall may might must "
    "and or but nor so yet if then than as of in on at by for with from to "
    "into onto over under about between during after before against "
    "not no also very just only both each all any some such more most other "
    "there here when where which who whom whose what how why while because "
    "per via due upon within without"
).split()

DEFAULT_STOPWORDS: FrozenSet[str] = frozenset(word_key(w) for w in _STOPWORDS_RAW)


@dataclass(frozen=True)
class Config:
    """Extraction and scoring parameters.

    Attributes:
        min_quote_words: quoted spans shorter than this (in word tokens) are
            not checked on their own; they stay part of the sentence claim.
        min_claim_words: sentences with fewer word tokens than this are
            skipped — too short to be a falsifiable claim.
        min_claim_content_words: of those, at least this many must be
            non-stopwords.
        quote_partial_threshold: a non-verbatim quote scoring at or above
            this is PARTIAL instead of UNSUPPORTED.
        claim_supported_threshold: claim score at or above this is SUPPORTED.
        claim_partial_threshold: claim score at or above this (but below
            supported) is PARTIAL.
        window_slack_min / window_slack_ratio: the source window scanned for
            a span of n tokens is ``n + max(min, n * ratio)`` tokens wide.
        anchor_padding: numbers must appear within this many tokens of the
            matched window to count as grounded.
        check_quotes / check_claims: toggle span kinds independently.
    """

    min_quote_words: int = 3
    min_claim_words: int = 5
    min_claim_content_words: int = 2
    quote_partial_threshold: float = 0.70
    claim_supported_threshold: float = 0.70
    claim_partial_threshold: float = 0.40
    window_slack_min: int = 4
    window_slack_ratio: float = 0.5
    anchor_padding: int = 15
    check_quotes: bool = True
    check_claims: bool = True
    stopwords: FrozenSet[str] = field(default=DEFAULT_STOPWORDS)

    def window_width(self, needle_len: int) -> int:
        """Window width used when scanning a source for a needle of
        ``needle_len`` tokens."""
        slack = max(self.window_slack_min, int(needle_len * self.window_slack_ratio))
        return needle_len + slack

    def is_stopword(self, key: str) -> bool:
        return key in self.stopwords
