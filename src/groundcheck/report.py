"""Findings, reports, and their text/JSON renderings.

A ``Report`` is the complete, serializable result of one grounding check.
The JSON form has sorted keys and no floats beyond three decimal places, so
committing a report to git produces stable diffs, and the text form is what
the CLI prints. Neither rendering ever varies between runs on the same
input.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


def _collapse(text: str) -> str:
    """Collapse whitespace and heal the ``word .`` gaps left where quotes or
    citation markers were blanked out of a claim."""
    collapsed = " ".join(text.split())
    return re.sub(r"\s+([.,;:!?])", r"\1", collapsed)

SUPPORTED = "supported"
PARTIAL = "partial"
MISCITED = "miscited"
UNSUPPORTED = "unsupported"

#: Severity order used by ``--fail-on``: everything at or above the chosen
#: level fails the run. ``supported`` can never fail a run.
SEVERITY: Dict[str, int] = {SUPPORTED: 0, PARTIAL: 1, MISCITED: 2, UNSUPPORTED: 3}

_LABEL = {
    SUPPORTED: "SUPPORTED",
    PARTIAL: "PARTIAL",
    MISCITED: "MISCITED",
    UNSUPPORTED: "UNSUPPORTED",
}


@dataclass(frozen=True)
class Evidence:
    """Where in which source the best match was found."""

    source_id: str
    excerpt: str
    start: int  # char offset into the source text
    end: int


@dataclass(frozen=True)
class Finding:
    """The verdict for one extracted span."""

    kind: str  # "quote" | "claim"
    verdict: str  # one of SUPPORTED/PARTIAL/MISCITED/UNSUPPORTED
    text: str  # display text of the span
    start: int  # char offset into the answer
    end: int
    line: int  # 1-based line in the answer
    score: float  # 0..1 alignment score of the best window
    reason: str  # one human-readable line explaining the verdict
    citations: Tuple[str, ...] = ()
    missing: Tuple[str, ...] = ()  # content words absent from the evidence
    evidence: Optional[Evidence] = None

    @property
    def severity(self) -> int:
        return SEVERITY[self.verdict]

    def display_short(self, limit: int = 72) -> str:
        """Whitespace-collapsed, truncated span text for terminal output."""
        collapsed = _collapse(self.text)
        if len(collapsed) > limit:
            collapsed = collapsed[: limit - 1].rstrip() + "…"
        return collapsed


@dataclass(frozen=True)
class Report:
    """All findings for one answer, plus the source inventory."""

    findings: Tuple[Finding, ...]
    source_ids: Tuple[str, ...]
    answer_name: str = "answer"

    def counts(self) -> Dict[str, int]:
        out = {SUPPORTED: 0, PARTIAL: 0, MISCITED: 0, UNSUPPORTED: 0}
        for f in self.findings:
            out[f.verdict] += 1
        return out

    @property
    def support_ratio(self) -> float:
        """Fraction of checked spans that are fully supported (1.0 when the
        answer contained nothing checkable)."""
        if not self.findings:
            return 1.0
        supported = sum(1 for f in self.findings if f.verdict == SUPPORTED)
        return supported / len(self.findings)

    def worst_severity(self) -> int:
        return max((f.severity for f in self.findings), default=0)

    def fails(self, fail_on: str) -> bool:
        """True when any finding is at or above the ``fail_on`` verdict."""
        if fail_on == "never":
            return False
        return self.worst_severity() >= SEVERITY[fail_on]

    def to_dict(self) -> dict:
        counts = self.counts()
        return {
            "groundcheck": {"report_version": 1},
            "answer": self.answer_name,
            "sources": list(self.source_ids),
            "summary": {
                "spans": len(self.findings),
                "supported": counts[SUPPORTED],
                "partial": counts[PARTIAL],
                "miscited": counts[MISCITED],
                "unsupported": counts[UNSUPPORTED],
                "support_ratio": round(self.support_ratio, 3),
            },
            "findings": [
                {
                    "kind": f.kind,
                    "verdict": f.verdict,
                    "line": f.line,
                    "start": f.start,
                    "end": f.end,
                    "text": f.text if f.kind == "quote" else _collapse(f.text),
                    "score": round(f.score, 3),
                    "reason": f.reason,
                    "citations": list(f.citations),
                    "missing": list(f.missing),
                    "evidence": (
                        {
                            "source": f.evidence.source_id,
                            "excerpt": f.evidence.excerpt,
                            "start": f.evidence.start,
                            "end": f.evidence.end,
                        }
                        if f.evidence
                        else None
                    ),
                }
                for f in self.findings
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)


def render_text(report: Report, verbose: bool = False) -> str:
    """Human-readable rendering; one line per finding, worst news readable
    at a glance, evidence shown for anything that is not fully supported."""
    lines: List[str] = []
    n_spans = len(report.findings)
    n_sources = len(report.source_ids)
    names = f" ({', '.join(report.source_ids)})" if n_sources <= 4 else ""
    lines.append(
        f"{report.answer_name} — {n_spans} span{'s' if n_spans != 1 else ''} "
        f"checked against {n_sources} source{'s' if n_sources != 1 else ''}{names}"
    )
    lines.append("")
    for f in report.findings:
        label = _LABEL[f.verdict].ljust(11)
        shown = f'"{f.display_short()}"' if f.kind == "quote" else f.display_short()
        lines.append(f"  {label}  {f.kind:5}  L{f.line:<3} {shown}")
        if f.verdict != SUPPORTED or verbose:
            lines.append(f"{'':24}{f.reason}")
            if f.evidence and (verbose or f.verdict in (PARTIAL, MISCITED)):
                lines.append(
                    f"{'':24}evidence [{f.evidence.source_id}]: {f.evidence.excerpt}"
                )
    counts = report.counts()
    lines.append("")
    lines.append(
        f"{counts[SUPPORTED]} supported, {counts[PARTIAL]} partial, "
        f"{counts[MISCITED]} miscited, {counts[UNSUPPORTED]} unsupported "
        f"— support {round(report.support_ratio * 100)}%"
    )
    return "\n".join(lines)
