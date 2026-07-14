#!/usr/bin/env bash
# Smoke test for groundcheck: run the real CLI end-to-end on the shipped
# example — spans inventory, text report, JSON report, exit-code gates, and
# the JSON bundle mode. Self-contained: pure stdlib, no network, idempotent
# (works from a clean tree, no install required).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
if [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON="$ROOT/.venv/bin/python"
fi

# Zero runtime dependencies, so running from src/ needs no install.
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/groundcheck-smoke.XXXXXX")"
trap 'rm -rf "$WORKDIR"' EXIT

fail() { echo "SMOKE FAIL: $1" >&2; exit 1; }

echo "[smoke] python: $("$PYTHON" --version 2>&1)"

# 1. spans: the example answer yields exactly the documented inventory.
spans_out="$("$PYTHON" -m groundcheck spans "$ROOT/examples/answer.md")" \
  || fail "spans exited non-zero"
echo "$spans_out" | sed 's/^/[spans] /'
echo "$spans_out" | grep -q "5 spans" || fail "expected 5 spans in the example"

# 2. check (text): the five archetype verdicts, and exit 1 on the fabricated claim.
set +e
check_out="$("$PYTHON" -m groundcheck check "$ROOT/examples/answer.md" \
  --context "$ROOT/examples/sources" 2>/dev/null)"
check_rc=$?
set -e
echo "$check_out" | sed 's/^/[check] /'
[ "$check_rc" -eq 1 ] || fail "check should exit 1 on an unsupported span, got $check_rc"
echo "$check_out" | grep -q "SUPPORTED    quote" || fail "missing supported quote"
echo "$check_out" | grep -q "MISCITED" || fail "missing miscited quote"
echo "$check_out" | grep -q "97%" || fail "fabricated figure 97% not called out"
echo "$check_out" | grep -q "UNSUPPORTED" || fail "missing unsupported claim"
echo "$check_out" | grep -q "2 supported, 1 partial, 1 miscited, 1 unsupported" \
  || fail "summary line does not match the documented verdicts"

# 3. --fail-on never reports the same findings but exits 0.
"$PYTHON" -m groundcheck check "$ROOT/examples/answer.md" \
  --context "$ROOT/examples/sources" --fail-on never >/dev/null \
  || fail "--fail-on never should exit 0"

# 4. check (json): valid JSON with the expected summary, verified by stdlib json.
"$PYTHON" -m groundcheck check "$ROOT/examples/answer.md" \
  --context "$ROOT/examples/sources" --format json \
  >"$WORKDIR/report.json" 2>/dev/null || true
"$PYTHON" - "$WORKDIR/report.json" <<'PY' || fail "JSON report is wrong"
import json, sys
data = json.load(open(sys.argv[1]))
s = data["summary"]
assert s["spans"] == 5 and s["unsupported"] == 1 and s["miscited"] == 1, s
assert s["support_ratio"] == 0.4, s
PY

# 5. Determinism: two runs produce byte-identical JSON reports.
"$PYTHON" -m groundcheck check "$ROOT/examples/answer.md" \
  --context "$ROOT/examples/sources" --format json \
  >"$WORKDIR/report2.json" 2>/dev/null || true
cmp -s "$WORKDIR/report.json" "$WORKDIR/report2.json" \
  || fail "JSON reports differ between runs"
echo "[smoke] JSON report deterministic across runs"

# 6. Bundle mode: the clean example bundle passes with exit 0.
bundle_out="$("$PYTHON" -m groundcheck check --bundle "$ROOT/examples/bundle.json")" \
  || fail "bundle check should exit 0"
echo "$bundle_out" | grep -q "support 100%" || fail "bundle should be fully supported"

# 7. A fully grounded answer written on the fly passes.
cat >"$WORKDIR/good.md" <<'EOF'
The design doc states: "Reads are served from a write-through cache in front
of the primary store" [1].
EOF
"$PYTHON" -m groundcheck check "$WORKDIR/good.md" \
  "$ROOT/examples/sources/design.md" >/dev/null \
  || fail "fully grounded answer should exit 0"

# 8. --version agrees with the package version.
version_out="$("$PYTHON" -m groundcheck --version)"
pkg_version="$("$PYTHON" -c 'import groundcheck; print(groundcheck.__version__)')"
[ "$version_out" = "groundcheck $pkg_version" ] \
  || fail "--version mismatch: '$version_out' vs package '$pkg_version'"
"$PYTHON" -m groundcheck check --help | grep -q -- "--fail-on" \
  || fail "--help missing --fail-on"

echo "SMOKE OK"
