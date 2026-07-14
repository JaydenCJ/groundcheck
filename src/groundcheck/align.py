"""Lexical alignment: find where (and how well) a span appears in a source.

This is the engine of groundcheck, and it is deliberately *not* a model.
A span is matched against a source by:

1. **Exact subsequence search** — the span's token keys appear contiguously
   in the source's token keys. Punctuation, casing, typographic quotes, and
   thousands separators have already been folded away, so this catches
   faithful quotes that were merely re-punctuated.
2. **Best-window scan** — every source position whose token matches a
   content token of the span opens a candidate window of bounded width; each
   window is scored by weighted token coverage (content words count, function
   words barely do) blended with the longest contiguous run shared with the
   span. Earliest window wins ties, so results are order-stable.

Everything is a pure function of its inputs: same span + same source =
same score, every time, on every machine.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .config import Config
from .textnorm import Token

_STOPWORD_WEIGHT = 0.15
_NUMBER_WEIGHT = 1.25
_COVERAGE_BLEND = 0.85  # score = blend*coverage + (1-blend)*contiguity


@dataclass(frozen=True)
class WindowMatch:
    """The best alignment of a span inside one source."""

    start: int  # token index in the source (inclusive)
    end: int  # token index in the source (exclusive)
    coverage: float  # weighted fraction of span tokens found in the window
    contiguity: float  # longest shared contiguous run / span length
    score: float  # blended 0..1 score
    exact: bool  # True when the span appears verbatim (token-wise)
    missing: Tuple[str, ...]  # surface forms of unmatched content tokens


def token_weight(token: Token, config: Config) -> float:
    if config.is_stopword(token.key):
        return _STOPWORD_WEIGHT
    if token.is_number:
        return _NUMBER_WEIGHT
    return 1.0


def find_exact(needle: Sequence[str], hay: Sequence[str]) -> Optional[int]:
    """First index where ``needle`` occurs contiguously in ``hay``."""
    n, h = len(needle), len(hay)
    if n == 0 or n > h:
        return None
    first = needle[0]
    for i in range(h - n + 1):
        if hay[i] == first and list(hay[i : i + n]) == list(needle):
            return i
    return None


def lcs_run(a: Sequence[str], b: Sequence[str]) -> int:
    """Length of the longest *contiguous* run common to ``a`` and ``b``.

    O(len(a)*len(b)) dynamic programming — spans are dozens of tokens and
    windows are bounded, so this stays trivially fast.
    """
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def _missing_surfaces(
    needle: Sequence[Token], window_counts: Counter, config: Config
) -> Tuple[str, ...]:
    """Surface forms of content tokens the window failed to cover, in span
    order, deduplicated."""
    remaining = Counter(window_counts)
    missing: List[str] = []
    seen = set()
    for tok in needle:
        if remaining[tok.key] > 0:
            remaining[tok.key] -= 1
            continue
        if config.is_stopword(tok.key):
            continue
        if tok.key not in seen:
            seen.add(tok.key)
            missing.append(tok.text)
    return tuple(missing)


def best_window(
    needle: Sequence[Token], hay: Sequence[Token], config: Config
) -> Optional[WindowMatch]:
    """Best-scoring alignment of ``needle`` within ``hay``, or ``None`` when
    no content token of the needle occurs in the hay at all."""
    if not needle or not hay:
        return None

    needle_keys = [t.key for t in needle]
    hay_keys = [t.key for t in hay]

    exact_at = find_exact(needle_keys, hay_keys)
    if exact_at is not None:
        return WindowMatch(
            start=exact_at,
            end=exact_at + len(needle_keys),
            coverage=1.0,
            contiguity=1.0,
            score=1.0,
            exact=True,
            missing=(),
        )

    content_keys = {t.key for t in needle if not config.is_stopword(t.key)}
    if not content_keys:
        content_keys = set(needle_keys)

    candidates = [i for i, k in enumerate(hay_keys) if k in content_keys]
    if not candidates:
        return None

    width = config.window_width(len(needle_keys))
    need_counts = Counter(needle_keys)
    weights: Dict[str, float] = {}
    total_weight = 0.0
    for tok in needle:
        w = token_weight(tok, config)
        weights.setdefault(tok.key, w)
        total_weight += w

    best: Optional[WindowMatch] = None
    for start in candidates:
        end = min(start + width, len(hay_keys))
        window_counts = Counter(hay_keys[start:end])
        matched_weight = sum(
            min(count, window_counts[key]) * weights[key]
            for key, count in need_counts.items()
        )
        coverage = matched_weight / total_weight if total_weight else 0.0
        run = lcs_run(needle_keys, hay_keys[start:end])
        contiguity = run / len(needle_keys)
        score = _COVERAGE_BLEND * coverage + (1.0 - _COVERAGE_BLEND) * contiguity
        if best is None or score > best.score + 1e-12:
            best = WindowMatch(
                start=start,
                end=end,
                coverage=round(coverage, 6),
                contiguity=round(contiguity, 6),
                score=round(min(score, 1.0), 6),
                exact=False,
                missing=_missing_surfaces(needle, window_counts, config),
            )
    return best


def anchors_present(
    needle: Sequence[Token],
    hay: Sequence[Token],
    match: WindowMatch,
    config: Config,
) -> Tuple[str, ...]:
    """Numeric tokens of the span that do **not** appear in (or near) the
    matched window. Numbers are the cheapest hallucination signal there is:
    a claim whose figure is absent from the evidence is not grounded, no
    matter how well the words around it align."""
    anchor_keys = [(t.key, t.text) for t in needle if t.is_number]
    if not anchor_keys:
        return ()
    lo = max(0, match.start - config.anchor_padding)
    hi = min(len(hay), match.end + config.anchor_padding)
    nearby = {t.key for t in hay[lo:hi]}
    missing: List[str] = []
    seen = set()
    for key, text in anchor_keys:
        if key not in nearby and key not in seen:
            seen.add(key)
            missing.append(text)
    return tuple(missing)
