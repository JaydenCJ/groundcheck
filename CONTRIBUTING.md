# Contributing to groundcheck

Thanks for your interest in contributing. Issues, discussions, and pull
requests are all welcome.

## Development setup

```bash
git clone https://github.com/JaydenCJ/groundcheck
cd groundcheck
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Running the checks

```bash
pytest                 # 90 unit + integration tests
bash scripts/smoke.sh  # end-to-end CLI smoke; must print SMOKE OK
```

Both must pass before a pull request is reviewed. The suite runs fully
offline, needs no API keys, and finishes in about a second.

## Ground rules

- **No new runtime dependencies.** The package is standard-library only;
  that is a feature. Test-only dependencies belong in the `dev` extra.
- **Determinism is the contract.** Same answer + same sources must produce a
  byte-identical JSON report on every machine, every run. No randomness, no
  wall-clock reads, no locale-dependent behavior in the matching path.
- **No models, no network.** groundcheck is a lexical checker by design;
  anything that needs weights, embeddings, or an API belongs in a different
  tool. Nothing may touch the network at any point.
- **Verdict changes need fixture evidence.** If a change moves any verdict
  in `tests/` or `examples/`, the pull request must show the before/after
  report and explain why the new verdict is more honest.
- **Every public API needs an English docstring and a test.** The examples
  in `examples/` are executed by `tests/test_examples.py`, so keep code and
  docs in sync.
- **Keep the three READMEs aligned.** `README.md`, `README.zh.md`, and
  `README.ja.md` share the same structure; update all three when you change
  one (English is the authoritative version).

## Reporting bugs

Please include the answer text, the source text(s), the exact command, and
the JSON report (`--format json`) — that is everything needed to reproduce a
verdict, since groundcheck is deterministic.

## Security

Please do not open public issues for security problems; use GitHub's private
vulnerability reporting on this repository instead.
