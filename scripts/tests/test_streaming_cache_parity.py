"""Streaming-vs-blocking cache-accounting parity test (ENH-2479).

First streaming-parity test in this repo. No in-tree precedent for
live SDK + recorded-fixture diff gating; the recorded-diff strategy
locks the parity assertion to frozen baselines so CI runs without
ANTHROPIC_API_KEY and within the --timeout=120 per-test cap.

The 0.1% relative-tolerance assertion covers all four token fields
(input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens)
that the production aggregation block (fsm/executor.py:1462-1474)
sums into the action_complete payload. Three independent downstream
consumers (fsm/persistence.py:710-727 writer, fsm/cost_graph.py:184-254
reader, cli/loop/_helpers.py:1699-1702 table) read these fields with
no reconciliation layer — a cache_read-only gate would miss drift in
three of the four fields.

The recorded.jsonl files (one per trace) hold the raw upstream
stream-json events verbatim (init + result per turn, including the
cache_read_input_tokens upstream field name); expected.jsonl holds
the per-turn {create, stream} snapshots observed through both code
paths at recording time, using INTERNAL field names consistent with
the rename boundary at subprocess_utils.py:462-465. The test runtime
only loads both files and asserts the per-field diff; no anthropic
import is required at test time (rebuild.sh gates the SDK at
recording time only).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest  # noqa: I001  (re-sorted by ruff format)

# Fixture directory layout — parallel to scripts/tests/fixtures/harbor/
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "streaming_parity"

# Canonical trace IDs (locked; matches the three patterns in the issue
# "Trace selection" subsection and Decision 2 row schema)
TRACE_IDS: tuple[str, ...] = (
    "trace_a_static_prefix_stable_turn_2",
    "trace_b_write_then_read_across_tool_result",
    "trace_c_tool_result_only_cache_hit",
)

# All four token fields per Decision 1 (parity scope = all four)
TOKEN_FIELDS: tuple[str, ...] = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_creation_tokens",
)

# 0.1% relative tolerance per Decision 1; expressed as pytest.approx rel=
PARITY_REL_TOLERANCE: float = 0.001


def _read_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    """Read every JSONL row from `path`. Returns empty list if missing.

    Mirrors the helper shape at scripts/tests/test_fsm_signal_integration.py:165-169
    (empty-list-on-missing + skip-blank-lines convention).
    """
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Sanity-check class: fixture directory structure
# ---------------------------------------------------------------------------
# Models TestHarborFixtures (scripts/tests/test_benchmark_fragment.py:299-335).
# Discovers independently of the parametrize below so structural failures show
# up as named test cases, not as missing parametrize IDs.


class TestStreamingParityFixtures:
    """Verify the streaming-parity fixture directory has the correct structure."""

    @staticmethod
    def _fixtures_dir() -> Path:
        return Path(__file__).parent / "fixtures" / "streaming_parity"

    def test_fixtures_dir_exists(self) -> None:
        assert self._fixtures_dir().is_dir(), (
            f"missing fixtures dir: {self._fixtures_dir()} — ENH-2479 requires "
            "scripts/tests/fixtures/streaming_parity/ to be checked in."
        )

    def test_three_trace_directories_exist(self) -> None:
        fixtures = self._fixtures_dir()
        if not fixtures.is_dir():
            pytest.skip("fixtures dir absent — covered by test_fixtures_dir_exists")
        trace_dirs = sorted(d for d in fixtures.iterdir() if d.is_dir())
        assert len(trace_dirs) == 3, (
            f"expected 3 trace subdirs, found {len(trace_dirs)}: {[d.name for d in trace_dirs]}"
        )

    def test_each_trace_has_recorded_jsonl(self) -> None:
        fixtures = self._fixtures_dir()
        if not fixtures.is_dir():
            pytest.skip("fixtures dir absent — covered by test_fixtures_dir_exists")
        for d in sorted(fixtures.iterdir()):
            if d.is_dir():
                assert (d / "recorded.jsonl").exists(), (
                    f"recorded.jsonl missing in {d.name} — every trace must ship "
                    "the raw stream-json events alongside its expected.jsonl."
                )

    def test_each_trace_has_expected_jsonl(self) -> None:
        fixtures = self._fixtures_dir()
        if not fixtures.is_dir():
            pytest.skip("fixtures dir absent — covered by test_fixtures_dir_exists")
        for d in sorted(fixtures.iterdir()):
            if d.is_dir():
                assert (d / "expected.jsonl").exists(), (
                    f"expected.jsonl missing in {d.name} — every trace must ship "
                    "its per-turn {create, stream, diff_pct, phase} diff target."
                )

    def test_each_expected_jsonl_has_required_fields(self) -> None:
        """Schema check on each row: turn, model, create, stream, phase, diff_pct."""
        fixtures = self._fixtures_dir()
        if not fixtures.is_dir():
            pytest.skip("fixtures dir absent — covered by test_fixtures_dir_exists")
        for d in sorted(fixtures.iterdir()):
            if d.is_dir():
                expected = d / "expected.jsonl"
                if not expected.exists():
                    continue  # covered by test_each_trace_has_expected_jsonl
                rows = _read_jsonl_rows(expected)
                assert rows, f"expected.jsonl in {d.name} is empty"
                for idx, row in enumerate(rows):
                    assert {"turn", "model", "create", "stream", "phase"}.issubset(row.keys()), (
                        f"expected.jsonl row {idx} in {d.name} missing required fields"
                    )
                    for label in ("create", "stream"):
                        side = row[label]
                        assert set(TOKEN_FIELDS).issubset(side.keys()), (
                            f"expected.jsonl row {idx} in {d.name}: {label} missing "
                            f"one of {TOKEN_FIELDS}; got {list(side.keys())}"
                        )


# ---------------------------------------------------------------------------
# Parametrized parity test: 0.1% relative diff on all four token fields
# ---------------------------------------------------------------------------
# Trace IDs are HARDCODED (not Path.iterdir()) so the test FAILS at collection
# time when fixtures are missing — the desired TDD red-phase behavior. A
# glob-based parametrize would silently generate zero test cases when the
# fixtures dir is absent, masking the failure.


@pytest.mark.parametrize("trace_id", TRACE_IDS)
def test_streaming_vs_blocking_cache_parity(trace_id: str) -> None:
    """Assert 0.1% relative diff on all four token fields per turn.

    Per Decision 1: parity scope covers all four token fields, not cache_read
    only — drift in input_tokens / output_tokens / cache_creation_tokens
    would silently pass a cache_read-only gate, even though all three
    downstream consumers (persistence, cost_graph, _print_usage_summary)
    aggregate all four fields with no reconciliation layer.
    """
    trace_dir = FIXTURES_DIR / trace_id
    assert trace_dir.is_dir(), (
        f"trace fixture dir missing: {trace_dir}. ENH-2479 requires all 3 trace "
        f"subdirs under {FIXTURES_DIR}."
    )

    expected_rows = _read_jsonl_rows(trace_dir / "expected.jsonl")
    assert expected_rows, f"no expected.jsonl rows in {trace_id} — at least one turn required."

    for row_idx, row in enumerate(expected_rows):
        create_side = row["create"]
        stream_side = row["stream"]
        turn = row.get("turn", row_idx)
        for field in TOKEN_FIELDS:
            create_value = create_side[field]
            stream_value = stream_side[field]
            assert create_value == pytest.approx(stream_value, rel=PARITY_REL_TOLERANCE), (
                f"{trace_id} turn {turn} {field}: "
                f"create={create_value} stream={stream_value} "
                f"diff_pct={_diff_pct(create_value, stream_value):.6f} "
                f"(tolerance={PARITY_REL_TOLERANCE})"
            )


def _diff_pct(a: int, b: int) -> float:
    """Relative diff as a percentage: 100 * abs(a - b) / max(b, 1).

    Floors the denominator at 1 to keep diff bounded when both sides are zero.
    Used only for failure-message diagnostics (the actual assertion uses
    pytest.approx with rel=0.001).
    """
    return 100.0 * abs(a - b) / max(b, 1)
