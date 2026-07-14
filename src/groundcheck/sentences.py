"""Deterministic sentence splitting with character offsets.

A small rule-based splitter is all a grounding check needs: it must cut the
answer into checkable units without ever moving an offset, and it must do so
identically on every run. Rules: sentences end at ``.`` ``!`` ``?`` runs
followed by whitespace, except after known abbreviations, single-letter
initials, and decimal numbers. Blank lines, headings, list items, and
blockquote lines always start a new unit.
"""

from __future__ import annotations

import re
from typing import List, Tuple

# Abbreviations that end with a period but do not end a sentence. Stored
# lowercase, without the final period. Multi-dot forms keep interior dots.
_ABBREVIATIONS = frozenset(
    {
        "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
        "e.g", "i.e", "cf", "ca", "al", "fig", "no", "nos", "approx",
        "dept", "est", "inc", "ltd", "co", "corp", "u.s", "u.k", "u.n",
        "p", "pp", "vol", "sec", "eq", "ver", "rev", "resp",
    }
)

# A sentence terminator: punctuation run plus any closing quotes/brackets.
_END_RE = re.compile(r"[.!?]+[\"')\]]*")

# Lines that always start a new unit, regardless of the previous line.
_BLOCK_START_RE = re.compile(r"^\s{0,3}(?:[-*+]\s|\d{1,3}[.)]\s|#{1,6}\s|>)")

_WORD_BEFORE_RE = re.compile(r"([A-Za-z][A-Za-z.]*)$")


def _is_abbreviation(text: str, dot_pos: int) -> bool:
    """True if the period at ``dot_pos`` terminates an abbreviation or a
    single-letter initial (``J. Smith``) rather than a sentence."""
    before = text[max(0, dot_pos - 12) : dot_pos]
    m = _WORD_BEFORE_RE.search(before)
    if not m:
        return False
    word = m.group(1).rstrip(".")
    if len(word) == 1 and word.isupper():
        return True  # an initial: "J. Smith"
    return word.lower() in _ABBREVIATIONS


def _blocks(text: str) -> List[Tuple[int, int]]:
    """Split ``text`` into blocks: runs of lines separated by blank lines,
    with heading/list/blockquote lines forced into their own block."""
    blocks: List[Tuple[int, int]] = []
    start = None
    pos = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        line_start = pos
        pos += len(line)
        if not stripped:
            if start is not None:
                blocks.append((start, line_start))
                start = None
            continue
        if _BLOCK_START_RE.match(line):
            if start is not None:
                blocks.append((start, line_start))
            blocks.append((line_start, pos))
            start = None
            continue
        if start is None:
            start = line_start
    if start is not None:
        blocks.append((start, len(text)))
    return blocks


def split_sentences(text: str) -> List[Tuple[int, int]]:
    """Return ``(start, end)`` character spans of sentences in ``text``.

    Spans index the original string and are trimmed of surrounding
    whitespace. The concatenation of spans never overlaps and their order is
    ascending, so callers can rely on them as a partition of the prose.
    """
    spans: List[Tuple[int, int]] = []
    for block_start, block_end in _blocks(text):
        block = text[block_start:block_end]
        sent_start = 0
        for m in _END_RE.finditer(block):
            end = m.end()
            # Only a real boundary when followed by whitespace or block end.
            if end < len(block) and not block[end].isspace():
                continue
            first = m.group(0)[0]
            if first == "." and _is_abbreviation(block, m.start()):
                continue
            # "1. third point": the dot after a bare enumerator is part of
            # the list marker, not a sentence boundary.
            if first == "." and block[sent_start : m.start()].strip().isdigit():
                continue
            spans.append((block_start + sent_start, block_start + end))
            sent_start = end
        if sent_start < len(block) and block[sent_start:].strip():
            spans.append((block_start + sent_start, block_end))
    # Trim whitespace from both ends of every span.
    trimmed: List[Tuple[int, int]] = []
    for start, end in spans:
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if end > start:
            trimmed.append((start, end))
    return trimmed
