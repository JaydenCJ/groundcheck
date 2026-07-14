"""Minimal library-API example: gate a RAG answer in a test or CI step.

Run it from the repository root (no install needed, zero dependencies):

    PYTHONPATH=src python3 examples/ci_gate.py

It checks the bundled example answer against the example sources and exits
non-zero when any span is unsupported — exactly what you would do in a
pytest assertion or a pipeline step.
"""

from __future__ import annotations

import sys
from pathlib import Path

import groundcheck

HERE = Path(__file__).parent


def main() -> int:
    answer = (HERE / "answer.md").read_text(encoding="utf-8")
    sources = {
        p.stem: p.read_text(encoding="utf-8")
        for p in sorted((HERE / "sources").glob("*.md"))
    }

    report = groundcheck.check(answer, sources, answer_name="examples/answer.md")
    print(groundcheck.render_text(report))

    bad = [f for f in report.findings if f.verdict == groundcheck.UNSUPPORTED]
    if bad:
        noun = "span" if len(bad) == 1 else "spans"
        print(f"\ngate: {len(bad)} unsupported {noun} — failing", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
