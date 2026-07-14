"""The grounding engine: spans + sources -> a Report.

Verdict policy, applied per span:

* **quote** — an exact (token-wise) occurrence in a source is SUPPORTED.
  A near match at or above ``quote_partial_threshold`` is PARTIAL, with the
  words that differ listed. Anything else is UNSUPPORTED.
* **claim** — the best window score decides: >= ``claim_supported_threshold``
  is SUPPORTED, >= ``claim_partial_threshold`` is PARTIAL, below is
  UNSUPPORTED. A claim whose numbers are absent from the evidence is capped
  at PARTIAL — a right-sounding sentence with a fabricated figure is the
  canonical RAG hallucination.
* **citations** — when a span cites sources, support must come from a cited
  source. Support found only elsewhere, or a citation label that resolves to
  no provided source, yields MISCITED: the claim may be true, but the paper
  trail is wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence, Tuple, Union

from .align import WindowMatch, anchors_present, best_window
from .config import Config
from .extract import Span, extract_spans
from .report import (
    MISCITED,
    PARTIAL,
    SUPPORTED,
    UNSUPPORTED,
    Evidence,
    Finding,
    Report,
)
from .textnorm import Token, tokenize

_EXCERPT_LIMIT = 160


@dataclass
class Source:
    """One context document, tokenized once and reused for every span."""

    id: str
    text: str
    tokens: List[Token] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.tokens:
            self.tokens = tokenize(self.text)

    def excerpt(self, match: WindowMatch) -> Evidence:
        """Char-accurate excerpt of the matched window, collapsed to one
        line and truncated for display."""
        if not self.tokens or match.start >= len(self.tokens):
            return Evidence(source_id=self.id, excerpt="", start=0, end=0)
        start_char = self.tokens[match.start].start
        end_char = self.tokens[min(match.end, len(self.tokens)) - 1].end
        raw = " ".join(self.text[start_char:end_char].split())
        if len(raw) > _EXCERPT_LIMIT:
            raw = raw[: _EXCERPT_LIMIT - 1].rstrip() + "…"
        return Evidence(source_id=self.id, excerpt=raw, start=start_char, end=end_char)


SourcesInput = Union[Mapping[str, str], Sequence[Tuple[str, str]], Sequence[Source]]


def _coerce_sources(sources: SourcesInput) -> List[Source]:
    out: List[Source] = []
    if isinstance(sources, Mapping):
        out = [Source(id=str(k), text=v) for k, v in sources.items()]
    else:
        for item in sources:
            if isinstance(item, Source):
                out.append(item)
            else:
                sid, text = item
                out.append(Source(id=str(sid), text=text))
    if not out:
        raise ValueError("at least one source is required")
    seen: Dict[str, int] = {}
    for src in out:
        seen[src.id] = seen.get(src.id, 0) + 1
    dupes = [k for k, n in seen.items() if n > 1]
    if dupes:
        label = "ids" if len(dupes) > 1 else "id"
        raise ValueError(f"duplicate source {label}: {', '.join(sorted(dupes))}")
    return out


def resolve_citation(label: str, sources: List[Source]) -> Optional[Source]:
    """Map a citation label to a source: by id (case-insensitive), then by
    1-based position for purely numeric labels."""
    folded = label.casefold()
    for src in sources:
        if src.id.casefold() == folded:
            return src
    if folded.isdigit():
        idx = int(folded)
        if 1 <= idx <= len(sources):
            return sources[idx - 1]
    return None


@dataclass(frozen=True)
class _Scored:
    source: Source
    match: WindowMatch


def _best_over(
    needle: List[Token], sources: List[Source], config: Config
) -> Optional[_Scored]:
    best: Optional[_Scored] = None
    for src in sources:
        m = best_window(needle, src.tokens, config)
        if m is None:
            continue
        if best is None or m.score > best.match.score + 1e-12:
            best = _Scored(source=src, match=m)
    return best


def _fmt_missing(missing: Tuple[str, ...], limit: int = 4) -> str:
    shown = ", ".join(missing[:limit])
    if len(missing) > limit:
        shown += f", … (+{len(missing) - limit})"
    return shown


def _cited_names(labels: Tuple[str, ...]) -> str:
    return ", ".join(f"[{label}]" for label in labels)


def _judge_quote(
    span: Span,
    needle: List[Token],
    cited: List[Source],
    unresolved: Tuple[str, ...],
    all_sources: List[Source],
    config: Config,
) -> Finding:
    pool = cited if cited else all_sources
    best_in_pool = _best_over(needle, pool, config)
    best_global = (
        best_in_pool if pool is all_sources else _best_over(needle, all_sources, config)
    )

    def finding(verdict: str, scored: Optional[_Scored], reason: str) -> Finding:
        return Finding(
            kind="quote",
            verdict=verdict,
            text=" ".join(span.text.split()),
            start=span.start,
            end=span.end,
            line=span.line,
            score=scored.match.score if scored else 0.0,
            reason=reason,
            citations=span.citations,
            missing=scored.match.missing if scored else (),
            evidence=scored.source.excerpt(scored.match) if scored else None,
        )

    if best_in_pool and best_in_pool.match.exact:
        if unresolved:
            return finding(
                MISCITED,
                best_in_pool,
                f"verbatim in {best_in_pool.source.id}, but "
                f"{_cited_names(unresolved)} matches no provided source",
            )
        return finding(
            SUPPORTED, best_in_pool, f"verbatim match in {best_in_pool.source.id}"
        )
    if best_global and best_global.match.exact:
        # The quote exists — just not where the citation said.
        return finding(
            MISCITED,
            best_global,
            f"cited {_cited_names(span.citations)} but the verbatim match is in "
            f"{best_global.source.id}",
        )
    if best_in_pool and best_in_pool.match.score >= config.quote_partial_threshold:
        return finding(
            PARTIAL,
            best_in_pool,
            f"near match in {best_in_pool.source.id} "
            f"(score {best_in_pool.match.score:.2f}); quote differs on: "
            f"{_fmt_missing(best_in_pool.match.missing) or 'word order'}",
        )
    if best_in_pool:
        return finding(
            UNSUPPORTED,
            best_in_pool,
            f"no verbatim occurrence; best window in {best_in_pool.source.id} scores "
            f"{best_in_pool.match.score:.2f}, missing: "
            f"{_fmt_missing(best_in_pool.match.missing) or '—'}",
        )
    return finding(UNSUPPORTED, None, "no source contains any part of this quote")


def _judge_claim(
    span: Span,
    needle: List[Token],
    cited: List[Source],
    unresolved: Tuple[str, ...],
    all_sources: List[Source],
    config: Config,
) -> Finding:
    pool = cited if cited else all_sources
    best_in_pool = _best_over(needle, pool, config)
    best_global = (
        best_in_pool if pool is all_sources else _best_over(needle, all_sources, config)
    )

    def finding(verdict: str, scored: Optional[_Scored], reason: str) -> Finding:
        return Finding(
            kind="claim",
            verdict=verdict,
            text=span.text,
            start=span.start,
            end=span.end,
            line=span.line,
            score=scored.match.score if scored else 0.0,
            reason=reason,
            citations=span.citations,
            missing=scored.match.missing if scored else (),
            evidence=scored.source.excerpt(scored.match) if scored else None,
        )

    def grade(scored: _Scored) -> str:
        if scored.match.score >= config.claim_supported_threshold:
            return SUPPORTED
        if scored.match.score >= config.claim_partial_threshold:
            return PARTIAL
        return UNSUPPORTED

    if best_in_pool is not None:
        verdict = grade(best_in_pool)
        if verdict == SUPPORTED:
            missing_nums = anchors_present(
                needle, best_in_pool.source.tokens, best_in_pool.match, config
            )
            if missing_nums:
                return finding(
                    PARTIAL,
                    best_in_pool,
                    f"words align with {best_in_pool.source.id} "
                    f"(score {best_in_pool.match.score:.2f}) but the figure(s) "
                    f"{_fmt_missing(missing_nums)} appear nowhere near the evidence",
                )
            if unresolved:
                return finding(
                    MISCITED,
                    best_in_pool,
                    f"supported by {best_in_pool.source.id} "
                    f"(score {best_in_pool.match.score:.2f}), but "
                    f"{_cited_names(unresolved)} matches no provided source",
                )
            return finding(
                SUPPORTED,
                best_in_pool,
                f"supported by {best_in_pool.source.id} "
                f"(score {best_in_pool.match.score:.2f})",
            )

    # Not supported by the cited pool — is it supported anywhere else?
    if (
        cited
        and best_global is not None
        and best_global.source not in cited
        and best_global.match.score >= config.claim_supported_threshold
    ):
        return finding(
            MISCITED,
            best_global,
            f"cited {_cited_names(span.citations)} but the support is in "
            f"{best_global.source.id} (score {best_global.match.score:.2f})",
        )

    if best_in_pool is not None and grade(best_in_pool) == PARTIAL:
        return finding(
            PARTIAL,
            best_in_pool,
            f"best window in {best_in_pool.source.id} scores "
            f"{best_in_pool.match.score:.2f}; missing: "
            f"{_fmt_missing(best_in_pool.match.missing) or '—'}",
        )
    if best_in_pool is not None:
        return finding(
            UNSUPPORTED,
            best_in_pool,
            f"best window in {best_in_pool.source.id} scores only "
            f"{best_in_pool.match.score:.2f}; missing: "
            f"{_fmt_missing(best_in_pool.match.missing) or '—'}",
        )
    return finding(
        UNSUPPORTED, None, "no source mentions any content word of this claim"
    )


def check(
    answer: str,
    sources: SourcesInput,
    config: Optional[Config] = None,
    answer_name: str = "answer",
) -> Report:
    """Check every quote and claim in ``answer`` against ``sources``.

    ``sources`` may be a ``{id: text}`` mapping, a sequence of ``(id, text)``
    pairs, or prepared :class:`Source` objects. Returns a :class:`Report`;
    raises ``ValueError`` on empty or duplicate-id source sets.
    """
    cfg = config or Config()
    source_list = _coerce_sources(sources)
    findings: List[Finding] = []

    for span in extract_spans(answer, cfg):
        needle = tokenize(span.text)
        if not needle:
            continue
        cited: List[Source] = []
        unresolved: List[str] = []
        for label in span.citations:
            src = resolve_citation(label, source_list)
            if src is not None:
                if src not in cited:
                    cited.append(src)
            else:
                unresolved.append(label)
        judge = _judge_quote if span.kind == "quote" else _judge_claim
        findings.append(
            judge(span, needle, cited, tuple(unresolved), source_list, cfg)
        )

    return Report(
        findings=tuple(findings),
        source_ids=tuple(s.id for s in source_list),
        answer_name=answer_name,
    )
