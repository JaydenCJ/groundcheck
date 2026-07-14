"""CLI behavior: arguments, exit codes, formats, and error handling."""

from __future__ import annotations

import json

import pytest

import groundcheck
from groundcheck.cli import main

ANSWER = (
    'The doc says "reads are served from a write-through cache" [1].\n\n'
    "Enterprise revenue grew 40% thanks to the new rebate program [1].\n"
)
SOURCE = (
    "Reads are served from a write-through cache in front of the primary "
    "store. Cache entries expire after 300 seconds.\n"
)


@pytest.fixture()
def project(tmp_path):
    answer = tmp_path / "answer.md"
    answer.write_text(ANSWER, encoding="utf-8")
    ctx = tmp_path / "docs"
    ctx.mkdir()
    (ctx / "design.md").write_text(SOURCE, encoding="utf-8")
    return tmp_path


def test_check_exits_1_on_unsupported_by_default(project, capsys):
    rc = main(["check", str(project / "answer.md"), str(project / "docs/design.md")])
    out = capsys.readouterr().out
    assert rc == 1
    assert "UNSUPPORTED" in out
    assert "SUPPORTED" in out


def test_check_exits_0_when_everything_is_supported(project, capsys):
    good = project / "good.md"
    good.write_text(
        'The doc says "reads are served from a write-through cache" [1].\n',
        encoding="utf-8",
    )
    rc = main(["check", str(good), str(project / "docs/design.md")])
    assert rc == 0
    assert "support 100%" in capsys.readouterr().out
    # -v also prints reason + evidence for supported findings.
    rc = main(["check", str(good), str(project / "docs/design.md"), "-v"])
    assert rc == 0
    assert "evidence [design]" in capsys.readouterr().out


def test_fail_on_never_reports_but_passes(project, capsys):
    rc = main(
        [
            "check",
            str(project / "answer.md"),
            str(project / "docs/design.md"),
            "--fail-on",
            "never",
        ]
    )
    assert rc == 0
    assert "UNSUPPORTED" in capsys.readouterr().out


def test_context_directory_is_searched_recursively(project, capsys):
    nested = project / "docs" / "sub"
    nested.mkdir()
    (nested / "extra.txt").write_text("Extra context here.", encoding="utf-8")
    rc = main(
        ["check", str(project / "answer.md"), "--context", str(project / "docs")]
    )
    assert rc == 1
    assert "2 sources" in capsys.readouterr().out


def test_json_format_is_valid_and_machine_readable(project, capsys):
    rc = main(
        [
            "check",
            str(project / "answer.md"),
            str(project / "docs/design.md"),
            "--format",
            "json",
        ]
    )
    assert rc == 1
    data = json.loads(capsys.readouterr().out)
    assert data["summary"]["spans"] == 2
    assert {f["verdict"] for f in data["findings"]} == {"supported", "unsupported"}


def test_stdin_answer_with_dash(project, capsys, monkeypatch):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(ANSWER))
    rc = main(["check", "-", str(project / "docs/design.md")])
    assert rc == 1
    assert "stdin — " in capsys.readouterr().out


def test_bundle_mode(tmp_path, capsys):
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        json.dumps({"answer": ANSWER, "sources": {"design": SOURCE}}),
        encoding="utf-8",
    )
    rc = main(["check", "--bundle", str(bundle)])
    assert rc == 1
    assert "design" in capsys.readouterr().out


def test_bundle_with_source_list_and_positional_conflict(tmp_path, capsys):
    bundle = tmp_path / "b.json"
    bundle.write_text(
        json.dumps({"answer": "x", "sources": [{"id": "a", "text": "y"}]}),
        encoding="utf-8",
    )
    rc = main(["check", "--bundle", str(bundle), "extra.md"])
    assert rc == 2
    assert "replaces" in capsys.readouterr().err


def test_usage_errors_exit_2_with_a_message(project, tmp_path, capsys):
    rc = main(["check", str(project / "nope.md"), str(project / "docs/design.md")])
    assert rc == 2
    assert "file not found" in capsys.readouterr().err

    rc = main(["check", str(project / "answer.md")])
    assert rc == 2
    assert "no sources" in capsys.readouterr().err

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    rc = main(["check", "--bundle", str(bad)])
    assert rc == 2
    assert "invalid JSON" in capsys.readouterr().err


def test_quotes_only_flag_skips_claims(project, capsys):
    rc = main(
        [
            "check",
            str(project / "answer.md"),
            str(project / "docs/design.md"),
            "--quotes-only",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0  # the fabricated claim is no longer checked
    assert "1 span" in out


def test_threshold_flags_change_verdicts(project, capsys):
    paraphrase = project / "para.md"
    paraphrase.write_text(
        "Entries in the cache expire after 300 seconds by design.\n",
        encoding="utf-8",
    )
    strict = main(
        [
            "check",
            str(paraphrase),
            str(project / "docs/design.md"),
            "--supported-threshold",
            "0.99",
            "--fail-on",
            "partial",
        ]
    )
    capsys.readouterr()
    lax = main(["check", str(paraphrase), str(project / "docs/design.md")])
    assert strict == 1
    assert lax == 0


def test_spans_subcommand_lists_extracted_spans(project, capsys):
    rc = main(["spans", str(project / "answer.md")])
    out = capsys.readouterr().out
    assert rc == 0
    assert "quote" in out and "claim" in out
    assert "2 spans" in out

    rc = main(["spans", str(project / "answer.md"), "--format", "json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert [s["kind"] for s in data] == ["quote", "claim"]
    assert all({"line", "start", "end", "citations"} <= set(s) for s in data)


def test_version_flag_matches_package(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"groundcheck {groundcheck.__version__}"


def test_source_id_collision_falls_back_to_path(tmp_path, capsys):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "doc.md").write_text("Alpha text here.", encoding="utf-8")
    (tmp_path / "b" / "doc.md").write_text("Beta text here.", encoding="utf-8")
    answer = tmp_path / "ans.md"
    answer.write_text("Alpha text here about many things and stuff.\n", encoding="utf-8")
    rc = main(
        [
            "check",
            str(answer),
            str(tmp_path / "a" / "doc.md"),
            str(tmp_path / "b" / "doc.md"),
            "--format",
            "json",
        ]
    )
    del rc
    data = json.loads(capsys.readouterr().out)
    assert len(data["sources"]) == 2
    assert len(set(data["sources"])) == 2
