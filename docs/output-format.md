# groundcheck output format

`groundcheck check --format json` emits one JSON object per run. Keys are
sorted and floats are rounded to three decimals, so committing a report to
git yields stable diffs, and two runs on the same input are byte-identical.

## Top level

| Key | Type | Meaning |
|---|---|---|
| `groundcheck.report_version` | int | Format version; this document describes version **1** |
| `answer` | string | Name of the checked answer (file path, `stdin`, or bundle path) |
| `sources` | string[] | Ids of the context documents, in resolution order (`[1]` = first) |
| `summary` | object | Aggregate counts (below) |
| `findings` | object[] | One entry per checked span, in answer order |

## `summary`

| Key | Type | Meaning |
|---|---|---|
| `spans` | int | Number of checked spans |
| `supported` / `partial` / `miscited` / `unsupported` | int | Count per verdict |
| `support_ratio` | float | `supported / spans`; `1.0` when nothing was checkable |

## `findings[]`

| Key | Type | Meaning |
|---|---|---|
| `kind` | string | `quote` (verbatim promise) or `claim` (declarative sentence) |
| `verdict` | string | `supported`, `partial`, `miscited`, or `unsupported` |
| `line` | int | 1-based line of the span in the answer |
| `start` / `end` | int | Character offsets of the span in the answer |
| `text` | string | The span text (quotes: inner text; claims: sentence with quotes/markers blanked) |
| `score` | float | 0–1 alignment score of the best source window (`1.0` = verbatim) |
| `reason` | string | One human-readable line explaining the verdict |
| `citations` | string[] | Citation labels attached to the span (`"1"`, `"pricing"`, …) |
| `missing` | string[] | Content words absent from the best evidence window |
| `evidence` | object\|null | Best match: `source`, `excerpt`, `start`, `end` (offsets into the source text) |

## Verdict semantics

| Verdict | Trigger | Severity |
|---|---|---|
| `supported` | Quote found verbatim (token-wise), or claim score ≥ supported threshold with all figures present | 0 |
| `partial` | Near-match quote, claim in the partial band, or a claim whose words align but whose **numbers** are absent | 1 |
| `miscited` | Content is supported — but by a source other than the one cited, or the citation label resolves to no provided source | 2 |
| `unsupported` | No source window comes close | 3 |

`--fail-on VERDICT` exits 1 when any finding has severity at or above the
named verdict; `--fail-on never` always exits 0. Exit code 2 is reserved for
usage and input errors.

## Matching rules (what "verbatim" means)

Comparison happens on normalized word/number tokens: Unicode NFKC, casefold,
curly quotes/dashes folded to ASCII, punctuation ignored, thousands
separators stripped (`1,000` = `1000`), percent detached (`40%` matches
`40 percent`), possessives and cheap plurals folded (`cache's`/`caches` =
`cache`). A quote is *verbatim* when its token sequence appears contiguously
in a source — re-casing and re-punctuating a quote does not break it, but
swapping a single word does.
