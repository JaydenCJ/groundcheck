"""Command-line interface.

Two subcommands:

* ``groundcheck check ANSWER [SOURCE ...]`` — verify an answer against
  context files (or a JSON bundle) and exit non-zero when the ``--fail-on``
  gate trips, so it slots directly into CI.
* ``groundcheck spans ANSWER`` — show what would be checked (extracted
  quotes, claims, citations) without judging anything; the debugging view.

Exit codes: 0 = pass, 1 = findings at or above ``--fail-on``, 2 = usage or
input error. Nothing here touches the network.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from . import __version__
from .config import Config
from .extract import extract_spans
from .report import MISCITED, PARTIAL, UNSUPPORTED, render_text
from .verify import check

_SOURCE_SUFFIXES = (".md", ".markdown", ".txt", ".rst")


class CliError(Exception):
    """A user-facing input problem; maps to exit code 2."""


def _read_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    p = Path(path)
    try:
        return p.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise CliError(f"file not found: {path}")
    except IsADirectoryError:
        raise CliError(f"is a directory (use --context for directories): {path}")
    except UnicodeDecodeError:
        raise CliError(f"not valid UTF-8 text: {path}")


def _source_id(path: Path, taken: Dict[str, Path]) -> str:
    """Stable, human-friendly source id: the file stem, falling back to the
    full relative path on collision."""
    sid = path.stem
    if sid in taken and taken[sid] != path:
        sid = path.as_posix()
    return sid


def _collect_sources(
    files: Sequence[str], context_dirs: Sequence[str]
) -> List[Tuple[str, str]]:
    paths: List[Path] = []
    for f in files:
        paths.append(Path(f))
    for d in context_dirs:
        root = Path(d)
        if not root.is_dir():
            raise CliError(f"--context is not a directory: {d}")
        found = sorted(
            p for p in root.rglob("*") if p.is_file() and p.suffix in _SOURCE_SUFFIXES
        )
        if not found:
            raise CliError(f"--context contains no {'/'.join(_SOURCE_SUFFIXES)} files: {d}")
        paths.extend(found)

    sources: List[Tuple[str, str]] = []
    taken: Dict[str, Path] = {}
    for p in paths:
        text = _read_text(str(p))
        sid = _source_id(p, taken)
        taken[sid] = p
        sources.append((sid, text))
    return sources


def _load_bundle(path: str) -> Tuple[str, List[Tuple[str, str]]]:
    """A JSON bundle carries answer and sources in one file — the shape a
    RAG pipeline can dump per request: ``{"answer": "...", "sources":
    {"id": "text", ...}}`` (or a list of ``{"id", "text"}`` objects)."""
    try:
        data = json.loads(_read_text(path))
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid JSON bundle {path}: {exc}")
    if not isinstance(data, dict) or "answer" not in data or "sources" not in data:
        raise CliError(f'bundle {path} must be an object with "answer" and "sources"')
    answer = data["answer"]
    raw = data["sources"]
    sources: List[Tuple[str, str]] = []
    if isinstance(raw, dict):
        sources = [(str(k), str(v)) for k, v in raw.items()]
    elif isinstance(raw, list):
        for i, item in enumerate(raw):
            if not isinstance(item, dict) or "text" not in item:
                raise CliError(f'bundle {path}: sources[{i}] needs a "text" field')
            sources.append((str(item.get("id", i + 1)), str(item["text"])))
    else:
        raise CliError(f"bundle {path}: sources must be an object or a list")
    if not isinstance(answer, str):
        raise CliError(f"bundle {path}: answer must be a string")
    return answer, sources


def _config_from_args(args: argparse.Namespace) -> Config:
    return Config(
        min_quote_words=args.min_quote_words,
        claim_supported_threshold=args.supported_threshold,
        claim_partial_threshold=args.partial_threshold,
        check_claims=not args.quotes_only,
    )


def _cmd_check(args: argparse.Namespace) -> int:
    if args.bundle:
        if args.answer or args.sources or args.context:
            raise CliError("--bundle replaces the ANSWER/SOURCE arguments")
        answer, sources = _load_bundle(args.bundle)
        answer_name = args.bundle
    else:
        if not args.answer:
            raise CliError("missing ANSWER (a file path, or - for stdin)")
        answer = _read_text(args.answer)
        answer_name = "stdin" if args.answer == "-" else args.answer
        sources = _collect_sources(args.sources, args.context)
    if not sources:
        raise CliError("no sources given (pass files, --context DIR, or --bundle)")

    report = check(answer, sources, _config_from_args(args), answer_name=answer_name)

    if args.format == "json":
        print(report.to_json())
    else:
        print(render_text(report, verbose=args.verbose))

    if report.fails(args.fail_on):
        if args.format == "text":
            print(f"exit 1 (fail-on {args.fail_on})", file=sys.stderr)
        return 1
    return 0


def _cmd_spans(args: argparse.Namespace) -> int:
    answer = _read_text(args.answer)
    spans = extract_spans(answer, _config_from_args(args))
    if args.format == "json":
        print(
            json.dumps(
                [
                    {
                        "kind": s.kind,
                        "line": s.line,
                        "start": s.start,
                        "end": s.end,
                        "citations": list(s.citations),
                        "text": s.display_text(limit=2000),
                    }
                    for s in spans
                ],
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        return 0
    if not spans:
        print("no checkable spans found")
        return 0
    for s in spans:
        cites = f"  cites {', '.join(s.citations)}" if s.citations else ""
        print(f"  {s.kind:5}  L{s.line:<3} {s.display_text()}{cites}")
    print(f"{len(spans)} span{'s' if len(spans) != 1 else ''}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="groundcheck",
        description=(
            "Verify that quotes and claims in generated output actually appear "
            "in the provided context. Deterministic, offline, exit-code friendly."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"groundcheck {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_shared(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--format", choices=("text", "json"), default="text",
            help="output format (default: text)",
        )
        p.add_argument(
            "--min-quote-words", type=int, default=3, metavar="N",
            help="quotes shorter than N words are not checked standalone (default: 3)",
        )
        p.add_argument(
            "--supported-threshold", type=float, default=0.70, metavar="X",
            help="claim score at or above X is SUPPORTED (default: 0.70)",
        )
        p.add_argument(
            "--partial-threshold", type=float, default=0.40, metavar="X",
            help="claim score at or above X is PARTIAL (default: 0.40)",
        )
        p.add_argument(
            "--quotes-only", action="store_true",
            help="check quoted spans only, skip claim sentences",
        )

    p_check = sub.add_parser(
        "check", help="verify an answer against context sources"
    )
    p_check.add_argument(
        "answer", nargs="?", metavar="ANSWER",
        help="answer file to verify, or - for stdin",
    )
    p_check.add_argument(
        "sources", nargs="*", metavar="SOURCE", help="context source files"
    )
    p_check.add_argument(
        "--context", action="append", default=[], metavar="DIR",
        help="directory of context files (.md/.markdown/.txt/.rst), searched recursively",
    )
    p_check.add_argument(
        "--bundle", metavar="FILE.json",
        help='JSON bundle with {"answer": ..., "sources": ...} instead of files',
    )
    p_check.add_argument(
        "--fail-on",
        choices=(PARTIAL, MISCITED, UNSUPPORTED, "never"),
        default=UNSUPPORTED,
        help="exit 1 when any finding is at or above this verdict "
        "(default: unsupported)",
    )
    p_check.add_argument(
        "-v", "--verbose", action="store_true",
        help="show reasons and evidence for supported findings too",
    )
    add_shared(p_check)
    p_check.set_defaults(func=_cmd_check)

    p_spans = sub.add_parser(
        "spans", help="show extracted quotes/claims without checking them"
    )
    p_spans.add_argument(
        "answer", metavar="ANSWER", help="answer file to inspect, or - for stdin"
    )
    add_shared(p_spans)
    p_spans.set_defaults(func=_cmd_spans)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except CliError as exc:
        print(f"groundcheck: error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"groundcheck: error: {exc}", file=sys.stderr)
        return 2
    except BrokenPipeError:
        # Downstream pager/head closed the pipe: exit quietly, like grep.
        try:
            sys.stdout.close()
        except (BrokenPipeError, OSError, ValueError):
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())
