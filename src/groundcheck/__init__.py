"""groundcheck — verify that quotes and claims in generated output actually
appear in the provided context, and flag the spans that do not.

Deterministic lexical alignment, standard library only. The one-call API:

    import groundcheck

    report = groundcheck.check(answer_text, {"design": design_doc})
    assert not report.fails("unsupported"), report.to_json()
"""

from .align import WindowMatch, best_window, find_exact, lcs_run
from .config import Config, DEFAULT_STOPWORDS
from .extract import Span, extract_spans
from .report import (
    MISCITED,
    PARTIAL,
    SEVERITY,
    SUPPORTED,
    UNSUPPORTED,
    Evidence,
    Finding,
    Report,
    render_text,
)
from .sentences import split_sentences
from .textnorm import Token, tokenize
from .verify import Source, check, resolve_citation

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "check",
    "extract_spans",
    "split_sentences",
    "tokenize",
    "best_window",
    "find_exact",
    "lcs_run",
    "resolve_citation",
    "render_text",
    "Config",
    "DEFAULT_STOPWORDS",
    "Source",
    "Span",
    "Token",
    "WindowMatch",
    "Evidence",
    "Finding",
    "Report",
    "SUPPORTED",
    "PARTIAL",
    "MISCITED",
    "UNSUPPORTED",
    "SEVERITY",
]
