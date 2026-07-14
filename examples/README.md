# groundcheck examples

A tiny RAG scenario: two context documents (`sources/design.md`,
`sources/pricing.md`) and a generated answer (`answer.md`) that gets four
things right-ish and one thing very wrong — a faithful quote, a paraphrased
claim, a quote attributed to the wrong source, a claim with a fabricated
figure, and a claim with no support at all.

From the repository root:

```bash
# See what would be checked (no verdicts yet)
PYTHONPATH=src python3 -m groundcheck spans examples/answer.md

# Check the answer against the source directory; exits 1 (unsupported span)
PYTHONPATH=src python3 -m groundcheck check examples/answer.md --context examples/sources

# Same, machine-readable
PYTHONPATH=src python3 -m groundcheck check examples/answer.md --context examples/sources --format json

# One-file mode: answer + sources in a single JSON bundle; exits 0
PYTHONPATH=src python3 -m groundcheck check --bundle examples/bundle.json

# Library API: gate an answer inside a test or CI step
PYTHONPATH=src python3 examples/ci_gate.py
```

With `pip install -e .` done, replace `PYTHONPATH=src python3 -m groundcheck`
with plain `groundcheck`.

Expected outcome for `answer.md`: 2 supported, 1 partial, 1 miscited,
1 unsupported — and exit code 1, because `--fail-on unsupported` is the
default.
