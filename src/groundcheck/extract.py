"""Span extraction: turn an answer into a list of checkable units.

Three things come out of an answer text:

* **quotes** — text between double quotation marks (straight, curly,
  guillemets, or CJK corner brackets) and Markdown blockquote runs. Quotes
  are promises of verbatim fidelity, so they get the strictest check.
* **claims** — declarative sentences with enough content words to be
  falsifiable. Quoted regions and citation markers are blanked out of the
  claim so nothing is checked twice.
* **citations** — ``[1]``, ``[^2]``, ``[doc-a]``, ``【3】`` markers, attached
  to the spans of the sentence they appear in, so a claim can be verified
  against the source it actually cites.

Markdown noise (fenced code, inline code, link targets, bare URLs, HTML
comments) is masked to spaces first — same string length, so every offset
still points into the original answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .config import Config
from .textnorm import fold_chars, tokenize
from .sentences import split_sentences

_FENCE_RE = re.compile(r"^(```|~~~).*?^\1[^\n]*$", re.MULTILINE | re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_LINK_TARGET_RE = re.compile(r"\]\((<[^>]*>|[^)\s]+)\)")
_BARE_URL_RE = re.compile(r"https?://[^\s)\]>]+")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# Citation labels: at least one digit or two+ characters, so Markdown task
# boxes ([x], [ ]) never register as citations.
_CITE_LABEL = r"[A-Za-z0-9][\w.\-]*"
_CITE_RE = re.compile(
    rf"\[\^?({_CITE_LABEL}(?:\s*,\s*{_CITE_LABEL})*)\](?!\()|【({_CITE_LABEL})】"
)

_CJK_QUOTE_RE = re.compile(r"「([^」\n]{1,600})」")
_BLOCKQUOTE_LINE_RE = re.compile(r"^\s{0,3}>")


@dataclass(frozen=True)
class Span:
    """A checkable unit of the answer.

    ``text`` is a same-length slice of the (blanked) answer for claims, or
    the inner quoted text for quotes; ``start``/``end``/``line`` locate the
    span in the original answer.
    """

    kind: str  # "quote" | "claim"
    text: str
    start: int
    end: int
    line: int
    citations: Tuple[str, ...] = ()

    def display_text(self, limit: int = 90) -> str:
        """Whitespace-collapsed text for human-readable reports."""
        collapsed = " ".join(self.text.split())
        collapsed = re.sub(r"\s+([.,;:!?])", r"\1", collapsed)
        if len(collapsed) > limit:
            collapsed = collapsed[: limit - 1].rstrip() + "…"
        return collapsed


def _mask(text: str, pattern: re.Pattern, group: int = 0) -> str:
    """Replace every match of ``pattern`` with spaces (newlines kept), so
    offsets and line numbers survive."""

    def blank(m: re.Match) -> str:
        s = m.group(0)
        gs, ge = m.start(group) - m.start(0), m.end(group) - m.start(0)
        return "".join(
            c if c == "\n" or not (gs <= i < ge) else " " for i, c in enumerate(s)
        )

    return pattern.sub(blank, text)


def mask_markup(text: str) -> str:
    """Blank out Markdown/HTML regions that are not prose. Length-preserving."""
    text = _mask(text, _FENCE_RE)
    text = _mask(text, _HTML_COMMENT_RE)
    text = _mask(text, _INLINE_CODE_RE)
    text = _mask(text, _LINK_TARGET_RE, group=1)
    text = _mask(text, _BARE_URL_RE)
    return text


def find_citations(masked: str) -> List[Tuple[int, int, Tuple[str, ...]]]:
    """Return ``(start, end, labels)`` for every citation marker."""
    out: List[Tuple[int, int, Tuple[str, ...]]] = []
    for m in _CITE_RE.finditer(masked):
        raw = m.group(1) or m.group(2)
        labels = tuple(part.strip().casefold() for part in raw.split(","))
        # Reject bare single letters without digits ("[x]" checkboxes, "[a]")
        labels = tuple(l for l in labels if len(l) > 1 or l.isdigit())
        if labels:
            out.append((m.start(), m.end(), labels))
    return out


def find_quotes(masked: str) -> List[Tuple[int, int, int, int]]:
    """Return ``(outer_start, outer_end, inner_start, inner_end)`` for each
    quoted region. Curly quotes and guillemets are folded to straight double
    quotes first; straight quotes pair up sequentially."""
    folded = fold_chars(masked)
    quotes: List[Tuple[int, int, int, int]] = []

    positions = [i for i, c in enumerate(folded) if c == '"']
    i = 0
    while i + 1 < len(positions):
        a, b = positions[i], positions[i + 1]
        inner = folded[a + 1 : b]
        # Refuse pairs that span a paragraph break or are implausibly long —
        # the opening mark was almost certainly a stray, so drop it and try
        # pairing again from the next mark instead of derailing everything.
        if "\n\n" in inner or len(inner) > 600 or not inner.strip():
            i += 1
            continue
        quotes.append((a, b + 1, a + 1, b))
        i += 2

    for m in _CJK_QUOTE_RE.finditer(folded):
        quotes.append((m.start(), m.end(), m.start(1), m.end(1)))

    quotes.sort()
    return quotes


def find_blockquotes(masked: str) -> List[Tuple[int, int]]:
    """Return ``(start, end)`` spans of consecutive ``>``-prefixed lines."""
    runs: List[Tuple[int, int]] = []
    pos = 0
    run_start: Optional[int] = None
    run_end = 0
    for line in masked.splitlines(keepends=True):
        line_start = pos
        pos += len(line)
        if _BLOCKQUOTE_LINE_RE.match(line) and line.lstrip(" >").strip():
            if run_start is None:
                run_start = line_start
            run_end = line_start + len(line.rstrip("\n"))
        elif line.strip() or run_start is None:
            if run_start is not None:
                runs.append((run_start, run_end))
                run_start = None
        # a blank line inside a blockquote run is tolerated
    if run_start is not None:
        runs.append((run_start, run_end))
    return runs


def _line_of(offsets: List[int], pos: int) -> int:
    """1-based line number of char ``pos`` given sorted newline offsets."""
    lo, hi = 0, len(offsets)
    while lo < hi:
        mid = (lo + hi) // 2
        if offsets[mid] < pos:
            lo = mid + 1
        else:
            hi = mid
    return lo + 1


def _blank_ranges(text: str, ranges: List[Tuple[int, int]]) -> str:
    chars = list(text)
    for start, end in ranges:
        for i in range(start, min(end, len(chars))):
            if chars[i] != "\n":
                chars[i] = " "
    return "".join(chars)


def extract_spans(answer: str, config: Optional[Config] = None) -> List[Span]:
    """Extract quote and claim spans from ``answer``, in document order."""
    cfg = config or Config()
    masked = mask_markup(answer)
    newline_offsets = [i for i, c in enumerate(answer) if c == "\n"]
    citations = find_citations(masked)
    sentence_spans = split_sentences(masked)

    def cites_in(start: int, end: int) -> Tuple[str, ...]:
        labels: List[str] = []
        for cs, _ce, ls in citations:
            if start <= cs < end:
                for l in ls:
                    if l not in labels:
                        labels.append(l)
        return tuple(labels)

    def sentence_around(pos: int) -> Optional[Tuple[int, int]]:
        for s, e in sentence_spans:
            if s <= pos < e:
                return (s, e)
        return None

    spans: List[Span] = []
    quote_ranges: List[Tuple[int, int]] = []

    if cfg.check_quotes:
        for outer_s, outer_e, inner_s, inner_e in find_quotes(masked):
            inner = masked[inner_s:inner_e]
            if len(tokenize(inner)) < cfg.min_quote_words:
                continue
            sent = sentence_around(outer_s)
            cite_end = sent[1] if sent else min(len(masked), outer_e + 40)
            cite_start = sent[0] if sent else outer_s
            spans.append(
                Span(
                    kind="quote",
                    text=answer[inner_s:inner_e],
                    start=outer_s,
                    end=outer_e,
                    line=_line_of(newline_offsets, outer_s),
                    citations=cites_in(cite_start, cite_end),
                )
            )
            quote_ranges.append((outer_s, outer_e))

        for bq_start, bq_end in find_blockquotes(masked):
            inner = masked[bq_start:bq_end]
            if len(tokenize(inner)) < cfg.min_quote_words:
                continue
            spans.append(
                Span(
                    kind="quote",
                    text=re.sub(r"(?m)^\s{0,3}>\s?", "", answer[bq_start:bq_end]),
                    start=bq_start,
                    end=bq_end,
                    line=_line_of(newline_offsets, bq_start),
                    citations=cites_in(bq_start, min(len(masked), bq_end + 40)),
                )
            )
            quote_ranges.append((bq_start, bq_end))

    if cfg.check_claims:
        cite_ranges = [(cs, ce) for cs, ce, _ in citations]
        blanked = _blank_ranges(masked, quote_ranges + cite_ranges)
        for sent_s, sent_e in sentence_spans:
            # A sentence carrying a checked quote is not re-checked as a
            # claim: the quote *is* the claim, and the leftover ("According
            # to the doc, …") is attribution scaffolding, not an assertion.
            if any(qs < sent_e and sent_s < qe for qs, qe in quote_ranges):
                continue
            sent_text = blanked[sent_s:sent_e]
            if masked[sent_s:sent_e].rstrip().endswith("?"):
                continue  # questions assert nothing
            tokens = tokenize(sent_text)
            if len(tokens) < cfg.min_claim_words:
                continue
            content = [t for t in tokens if not cfg.is_stopword(t.key)]
            if len(content) < cfg.min_claim_content_words:
                continue
            spans.append(
                Span(
                    kind="claim",
                    text=sent_text,
                    start=sent_s,
                    end=sent_e,
                    line=_line_of(newline_offsets, sent_s),
                    citations=cites_in(sent_s, sent_e),
                )
            )

    spans.sort(key=lambda s: (s.start, s.end))
    return spans
