"""The shipped examples must keep doing exactly what the README promises."""

from __future__ import annotations

import json
from pathlib import Path

from groundcheck.cli import main

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "examples"


def test_example_answer_produces_the_documented_verdicts(capsys):
    rc = main(
        [
            "check",
            str(EXAMPLES / "answer.md"),
            "--context",
            str(EXAMPLES / "sources"),
            "--format",
            "json",
        ]
    )
    data = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert [f["verdict"] for f in data["findings"]] == [
        "supported",
        "supported",
        "miscited",
        "partial",
        "unsupported",
    ]
    assert data["summary"]["support_ratio"] == 0.4


def test_example_bundle_passes_clean(capsys):
    rc = main(["check", "--bundle", str(EXAMPLES / "bundle.json")])
    out = capsys.readouterr().out
    assert rc == 0
    assert "support 100%" in out


def test_example_spans_inventory_is_stable(capsys):
    rc = main(["spans", str(EXAMPLES / "answer.md")])
    out = capsys.readouterr().out
    assert rc == 0
    assert "5 spans" in out
