"""Tier 0 verification trace set tests (ENH-2518).

Locks the Tier 0 trace set used to measure FEAT-2470's behavioral
quick-wins (EPIC-2456 Tier 0 success gate). The fixtures at
``scripts/tests/fixtures/tier0_traces/`` are the moving-target anchor:
any before/after delta is measured against this set, not against
whatever ``general-task-*`` runs happen to be on disk.

The set contains two single-model (``claude-sonnet-4-6``) general-task
runs whose ``usage.jsonl`` rows parse cleanly under
``CostReport.from_usage_jsonl`` (``scripts/little_loops/fsm/cost_graph.py:184-254``).
The ``>= 2`` count relaxation (vs the original 3-5 AC) reuses the
precedent at ``scripts/tests/test_policy_builder_corpus.py:51-52``;
the supposed third candidate
(``.loops/runs/general-task-20260530T143631/``) exists but is empty
(no ``usage.jsonl``, no artifacts).

The locked trace IDs are mirrored at module level so the parametrize
set is import-time safe (the tests fail with assertion errors when
the fixtures are missing, not collection-time ``ERROR`` from a
missing manifest file).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "tier0_traces"
MANIFEST_PATH = FIXTURES_DIR / "manifest.json"

# Mirror of the locked trace set (per ENH-2518 § Locked Trace Set).
# Parametrize uses this list directly so the test module loads
# cleanly before the fixtures exist (Red phase).
LOCKED_TRACE_IDS: tuple[str, ...] = (
    "general-task-20260608T194041",
    "general-task-20260619T225602",
)


def _load_manifest_or_skip() -> dict:
    """Load the manifest JSON. Test bodies call this so a missing
    manifest becomes an assertion failure (Red phase) rather than a
    collection-time error."""
    if not MANIFEST_PATH.exists():
        pytest.fail(
            f"Missing manifest fixture at {MANIFEST_PATH}; this test gates the "
            "Tier 0 trace set declared in ENH-2518."
        )
    return json.loads(MANIFEST_PATH.read_text())


def _load_envelope_or_skip(rel_path: str) -> dict:
    """Load a per-trace envelope; same Red-phase guarantee as
    ``_load_manifest_or_skip``."""
    path = FIXTURES_DIR / rel_path
    if not path.exists():
        pytest.fail(f"Missing per-trace fixture: {path}")
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# Manifest-level gates
# ---------------------------------------------------------------------------


def test_manifest_exists() -> None:
    """Manifest must exist before any other gate can run."""
    assert MANIFEST_PATH.exists(), (
        f"Missing manifest fixture at {MANIFEST_PATH}; this test gates the "
        "Tier 0 trace set declared in ENH-2518."
    )


def test_manifest_owner_and_tier() -> None:
    """``_meta.owner`` pins this artifact to ENH-2518; ``_meta.tier``
    pins it to ``tier-0``. Without both, the artifact is misfiled."""
    manifest = _load_manifest_or_skip()
    assert manifest["_meta"]["owner"] == "ENH-2518"
    assert manifest["_meta"]["tier"] == "tier-0"
    assert manifest["_meta"]["epic"] == "EPIC-2456"


def test_manifest_count_at_or_above_minimum() -> None:
    """``>= 2`` relaxation of the original 3-5 AC. See ENH-2518
    issue § Locked Trace Set."""
    manifest = _load_manifest_or_skip()
    traces = manifest["traces"]
    assert len(traces) >= 2, (
        f"expected >=2 traces for Tier 0, got {len(traces)}; see ENH-2518 § Locked Trace Set"
    )


def test_manifest_has_schema_version_envelope() -> None:
    """``_meta.schema_version`` is the forward-compat slot (FEAT-2478
    OTel extension, FEAT-2476 budget_accumulator). It must exist
    even before a bump is needed."""
    manifest = _load_manifest_or_skip()
    assert "schema_version" in manifest["_meta"]


def test_manifest_has_count_relaxation_note() -> None:
    """The ``>= 2`` deviation from the original 3-5 AC must be
    documented inline in the manifest, not buried in the issue."""
    manifest = _load_manifest_or_skip()
    assert "count_relaxation_note" in manifest["_meta"]


def test_manifest_traces_match_locked_set() -> None:
    """The manifest's trace set must agree with the locked IDs mirrored
    at module level. This catches drift between the issue-level
    LOCKED_TRACE_IDS and the on-disk manifest."""
    manifest = _load_manifest_or_skip()
    manifest_ids = tuple(t["id"] for t in manifest["traces"])
    assert set(manifest_ids) == set(LOCKED_TRACE_IDS), (
        f"manifest traces {manifest_ids} disagree with locked set "
        f"{LOCKED_TRACE_IDS}; see ENH-2518 § Locked Trace Set"
    )


# ---------------------------------------------------------------------------
# Per-trace gates (parametrize over the locked set, not the manifest,
# for Red-phase import safety)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("trace_id", LOCKED_TRACE_IDS)
def test_each_trace_fixture_exists(trace_id: str) -> None:
    """Each locked trace must have a co-located fixture JSON at
    ``<FIXTURES_DIR>/<trace_id>.json``."""
    path = FIXTURES_DIR / f"{trace_id}.json"
    assert path.exists(), f"missing per-trace fixture: {path}"


@pytest.mark.parametrize("trace_id", LOCKED_TRACE_IDS)
def test_each_trace_has_recorded_baseline(trace_id: str) -> None:
    """Each per-trace fixture must carry a recorded baseline cost
    (sanity ``> 0``), a clean ``has_unknown_model`` flag, and a
    reserved ``budget_accumulator`` envelope for FEAT-2476 forward-compat.

    The ``baseline_cost_usd > 0`` assertion catches two drift modes:
    (a) the fixture was hand-authored with a zero placeholder and
    never re-computed; (b) the pricing entry changed and the
    aggregator can no longer price the row.
    """
    envelope = _load_envelope_or_skip(f"{trace_id}.json")
    totals = envelope["totals"]
    assert totals["baseline_cost_usd"] > 0, (
        f"{trace_id}: baseline_cost_usd must be > 0 (computed via "
        "CostReport.from_usage_jsonl aggregation order)"
    )
    assert envelope["has_unknown_model"] is False, (
        f"{trace_id}: has_unknown_model must be False (single-model "
        "lock to claude-sonnet-4-6)"
    )
    assert envelope["budget_accumulator"] == {}, (
        f"{trace_id}: budget_accumulator must be {{}} (reserved for FEAT-2476)"
    )


@pytest.mark.parametrize("trace_id", LOCKED_TRACE_IDS)
def test_each_trace_has_per_state_aggregates(trace_id: str) -> None:
    """The ``states: {...}`` map is the F6 (ENH-2477) re-aggregation
    consumer's input. It must be non-empty and each entry must carry
    the locked per-state keys (mirroring ``PerStateCost.to_dict`` at
    ``scripts/little_loops/fsm/cost_graph.py:71-82``)."""
    envelope = _load_envelope_or_skip(f"{trace_id}.json")
    states = envelope.get("states", {})
    assert len(states) >= 1, f"{trace_id}: states map is empty"

    expected_keys = {
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
        "cost_usd",
    }
    for state_name, state_entry in states.items():
        missing = expected_keys - set(state_entry.keys())
        assert not missing, (
            f"{trace_id}['states']['{state_name}'] is missing keys: {sorted(missing)}"
        )


@pytest.mark.parametrize("trace_id", LOCKED_TRACE_IDS)
def test_each_trace_preserves_rfc3339_timestamps(trace_id: str) -> None:
    """Real ``usage.jsonl`` rows use ``+00:00`` suffix, NOT ``Z``.
    The fixture's ``rows`` field must preserve the on-disk format
    verbatim so downstream diffs stay byte-stable."""
    envelope = _load_envelope_or_skip(f"{trace_id}.json")
    rows = envelope.get("rows", [])
    assert len(rows) >= 1, f"{trace_id}: rows array is empty"
    for i, row in enumerate(rows):
        ts = row.get("timestamp", "")
        assert "+00:00" in ts or ts.endswith("Z"), (
            f"{trace_id} row {i}: timestamp {ts!r} is neither +00:00 nor Z"
        )
