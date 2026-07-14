"""Shared fixtures: a small, deterministic RAG corpus used across suites."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make a plain `pytest` work from an uninstalled checkout (src/ layout).
_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

DESIGN = """\
# Cache design

Reads are served from a write-through cache in front of the primary store.
Cache entries expire after 300 seconds, and expiry is enforced by a background
sweeper that runs once per minute. During the 2025 load test the cache
absorbed 92% of read traffic at the p99 latency target of 12 ms.

Writes go straight to the primary store and invalidate the corresponding
cache entry in the same transaction.
"""

PRICING = """\
# Pricing and billing

Invoices are generated on the first business day of each month. The
enterprise plan is billed annually, and usage overages are invoiced in
arrears. Refunds are issued as account credit within 5 business days.
"""


@pytest.fixture()
def sources():
    """Ordered (id, text) pairs: [1] -> design, [2] -> pricing."""
    return [("design", DESIGN), ("pricing", PRICING)]
