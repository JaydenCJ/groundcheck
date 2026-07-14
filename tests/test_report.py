"""Report model: severity gates, ratios, JSON stability, text rendering."""

from __future__ import annotations

import json

import groundcheck as gc
from groundcheck.report import Finding, Report, render_text


def _finding(verdict, kind="claim", text="the cache absorbed traffic", line=1):
    return Finding(
        kind=kind,
        verdict=verdict,
        text=text,
        start=0,
        end=len(text),
        line=line,
        score=0.5,
        reason="test reason",
    )


def _report(*verdicts):
    return Report(
        findings=tuple(_finding(v) for v in verdicts),
        source_ids=("design", "pricing"),
        answer_name="answer.md",
    )


def test_severity_order_is_supported_partial_miscited_unsupported():
    assert (
        gc.SEVERITY[gc.SUPPORTED]
        < gc.SEVERITY[gc.PARTIAL]
        < gc.SEVERITY[gc.MISCITED]
        < gc.SEVERITY[gc.UNSUPPORTED]
    )


def test_fails_gates_at_and_above_the_chosen_verdict():
    report = _report(gc.SUPPORTED, gc.PARTIAL)
    assert report.fails("partial")
    assert not report.fails("miscited")
    assert not report.fails("unsupported")


def test_miscited_trips_the_miscited_and_partial_gates_only():
    report = _report(gc.MISCITED)
    assert report.fails("partial")
    assert report.fails("miscited")
    assert not report.fails("unsupported")


def test_fail_on_never_never_fails():
    assert not _report(gc.UNSUPPORTED).fails("never")


def test_support_ratio_counts_only_fully_supported():
    report = _report(gc.SUPPORTED, gc.PARTIAL, gc.UNSUPPORTED, gc.SUPPORTED)
    assert report.support_ratio == 0.5
    clean = _report(gc.SUPPORTED, gc.SUPPORTED)
    assert clean.support_ratio == 1.0
    assert not clean.fails("partial")


def test_empty_report_is_vacuously_supported():
    report = Report(findings=(), source_ids=("s",))
    assert report.support_ratio == 1.0
    assert report.worst_severity() == 0


def test_json_round_trips_and_has_sorted_keys():
    report = _report(gc.SUPPORTED, gc.UNSUPPORTED)
    text = report.to_json()
    data = json.loads(text)
    assert data["summary"]["spans"] == 2
    assert data["summary"]["unsupported"] == 1
    # sort_keys=True means re-serializing parsed data reproduces the text.
    assert json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) == text
    summary = _report(gc.SUPPORTED, gc.PARTIAL, gc.MISCITED).to_dict()
    assert summary["summary"] == {
        "spans": 3,
        "supported": 1,
        "partial": 1,
        "miscited": 1,
        "unsupported": 0,
        "support_ratio": 0.333,
    }
    assert summary["sources"] == ["design", "pricing"]


def test_render_text_shows_summary_line_and_labels():
    out = render_text(_report(gc.SUPPORTED, gc.UNSUPPORTED))
    assert "answer.md — 2 spans checked against 2 sources" in out
    assert "SUPPORTED" in out and "UNSUPPORTED" in out
    assert "1 supported, 0 partial, 0 miscited, 1 unsupported — support 50%" in out


def test_render_text_hides_reasons_for_supported_unless_verbose():
    quiet = render_text(_report(gc.SUPPORTED))
    loud = render_text(_report(gc.SUPPORTED), verbose=True)
    assert "test reason" not in quiet
    assert "test reason" in loud


def test_display_short_truncates_and_heals_blanked_punctuation():
    f = _finding(gc.SUPPORTED, text="word " * 40 + " .")
    short = f.display_short(limit=30)
    assert len(short) <= 30
    assert short.endswith("…")
    healed = _finding(gc.SUPPORTED, text="expires after 300 seconds   .")
    assert healed.display_short() == "expires after 300 seconds."
