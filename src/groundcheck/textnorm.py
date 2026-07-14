"""Deterministic text normalization and tokenization.

Everything groundcheck does downstream — quote lookup, claim alignment,
number anchoring — operates on the token stream produced here, so the rules
are deliberately boring and reproducible: Unicode NFKC, casefold, typographic
quote/dash unification, thousands-separator stripping, and a cheap
plural/possessive fold. No stemmer, no embeddings, no randomness: the same
input always yields the same tokens, byte for byte.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import List

# Typographic characters folded to their ASCII cousins before comparison.
# Generated answers are frequently written with curly quotes and en-dashes
# while the source corpus uses straight ones (or vice versa); treating them
# as different characters would fail every quote check for cosmetic reasons.
# Every mapping is one character -> one character, so folding never shifts
# offsets.
_CHAR_FOLD = {
    "‘": "'",  # left single quote
    "’": "'",  # right single quote / apostrophe
    "‚": "'",
    "‛": "'",
    "“": '"',  # left double quote
    "”": '"',  # right double quote
    "„": '"',
    "‟": '"',
    "«": '"',  # «
    "»": '"',  # »
    "‐": "-",
    "‑": "-",
    "‒": "-",
    "–": "-",  # en dash
    "—": "-",  # em dash
    "―": "-",
    "−": "-",  # minus sign
    " ": " ",  # no-break space
    " ": " ",
    " ": " ",
    " ": " ",
    " ": " ",
    "　": " ",  # ideographic space
}

_FOLD_TABLE = {ord(k): v for k, v in _CHAR_FOLD.items()}

_NUM = r"\d+(?:,\d{3})*(?:\.\d+)?"

# Order matters: percent-suffixed numbers first (so "40%" is one token), then
# plain numbers, then words (which may contain hyphens and apostrophes).
_TOKEN_RE = re.compile(
    rf"(?:{_NUM}) ?%|{_NUM}|\w+(?:['’\-]\w+)*",
    re.UNICODE,
)


def fold_chars(text: str) -> str:
    """Fold typographic quotes/dashes/spaces to ASCII, preserving length."""
    return text.translate(_FOLD_TABLE)


@dataclass(frozen=True)
class Token:
    """One word or number, with its position in the original text.

    ``text`` is the raw surface form, ``norm`` the normalized form used for
    display, and ``key`` the aggressive matching key (possessive/plural
    folded, thousands separators stripped) used for alignment.
    """

    text: str
    norm: str
    key: str
    start: int
    end: int
    is_number: bool


def _norm_number(raw: str) -> str:
    """Canonicalize a numeric surface form: ``1,000`` -> ``1000``,
    ``40 %`` -> ``40%``, ``3.50`` -> ``3.5``."""
    s = raw.replace(",", "").replace(" ", "")
    pct = s.endswith("%")
    if pct:
        s = s[:-1]
    try:
        value = float(s)
    except ValueError:
        return s + ("%" if pct else "")
    if value == int(value) and abs(value) < 1e15:
        s = str(int(value))
    else:
        s = repr(value)
    return s + ("%" if pct else "")


def _norm_word(raw: str) -> str:
    return unicodedata.normalize("NFKC", fold_chars(raw)).casefold()


def word_key(norm: str) -> str:
    """Matching key for a normalized word: fold possessives and cheap
    plurals so ``cache's``/``caches`` align with ``cache``.

    Both sides of every comparison go through the same fold, so the
    occasional non-word result (``this`` -> ``thi``) still matches itself
    and never collides with a real English stem in practice.
    """
    if norm.endswith("'s"):
        norm = norm[:-2]
    if len(norm) >= 4 and norm.endswith("s") and not norm.endswith("ss"):
        norm = norm[:-1]
    return norm


def number_key(norm: str) -> str:
    """Matching key for a number: drop the percent sign so ``40%`` in the
    answer aligns with ``40 percent`` (or a bare ``40``) in the source."""
    return norm[:-1] if norm.endswith("%") else norm


def tokenize(text: str) -> List[Token]:
    """Split ``text`` into word/number tokens with original char offsets.

    Punctuation is not tokenized: it can never cause a mismatch, which is
    exactly what a quote check wants when the answer re-punctuates a
    sentence it otherwise copied faithfully.
    """
    tokens: List[Token] = []
    for m in _TOKEN_RE.finditer(text):
        raw = m.group(0)
        is_number = raw[0].isdigit()
        if is_number:
            norm = _norm_number(raw)
            key = number_key(norm)
        else:
            norm = _norm_word(raw)
            key = word_key(norm)
        tokens.append(
            Token(
                text=raw,
                norm=norm,
                key=key,
                start=m.start(),
                end=m.end(),
                is_number=is_number,
            )
        )
    return tokens


def keys(tokens: List[Token]) -> List[str]:
    """Convenience: the matching-key sequence for a token list."""
    return [t.key for t in tokens]
