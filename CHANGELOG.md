# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-13

### Added

- Deterministic tokenizer with offset-preserving normalization: Unicode
  NFKC, casefold, typographic quote/dash folding, thousands-separator
  stripping, percent detachment (`40%` aligns with `40 percent`), and a
  cheap possessive/plural fold.
- Rule-based sentence splitter with exact character offsets, abbreviation
  and initial handling, decimal protection, and Markdown-aware block
  boundaries (headings, list items, blockquotes).
- Span extraction: double-quoted spans (straight, curly, guillemets, CJK
  corner brackets) and Markdown blockquotes as **quotes**; declarative
  sentences with enough content words as **claims**; `[1]`, `[^2]`,
  `[doc-a]`, `【3】` citation markers attached to their sentence. Fenced and
  inline code, link targets, bare URLs, and HTML comments are masked and
  never checked.
- Lexical alignment engine: exact token-subsequence search for quotes, plus
  a bounded best-window scan scored by stopword-weighted coverage blended
  with contiguous-run length. Earliest window wins ties; results are
  byte-deterministic.
- Number anchoring: a claim whose words align but whose figures appear
  nowhere near the evidence is capped at `partial` and the absent figures
  are named in the reason.
- Citation verification: support must come from the cited source; support
  found only elsewhere — or a citation label resolving to no provided
  source — yields the dedicated `miscited` verdict.
- Report model with four verdicts (`supported`, `partial`, `miscited`,
  `unsupported`), per-finding evidence excerpts with source offsets, a
  sorted-keys JSON rendering (documented in `docs/output-format.md`), and a
  terminal rendering.
- `groundcheck` CLI: `check` (files, `--context` directories, stdin, or a
  single `--bundle` JSON file) with `--fail-on` severity gate, `--format
  text|json`, threshold flags, and `--quotes-only`; `spans` to preview what
  would be checked. Exit codes 0/1/2.
- One-call library API: `groundcheck.check(answer, sources)`.
- Runnable example corpus (`examples/`) covering all five archetype
  outcomes, a JSON bundle, and a CI-gate script.
- 90 offline deterministic tests and `scripts/smoke.sh` (prints `SMOKE OK`).

### Notes

- The repository ships no CI workflow; verification is local —
  `pip install -e '.[dev]' && pytest && bash scripts/smoke.sh`.

[0.1.0]: https://github.com/JaydenCJ/groundcheck/releases/tag/v0.1.0
