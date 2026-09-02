"""Spike ACs: prove Option A's deterministic-only evidence bundle for FEAT-3182.

Builds a fixture archived-run directory mirroring the shape
`scaffold_verify.py`'s `_adversarial_states()`/`_criteria_states()` produce
(state.json with a `captured` map, events.jsonl with `evaluate` events
carrying `llm_model`, three `probe-*.json` files) and proves: LLM-sourced
fields never leak into `evidentiary`; every evidentiary entry traces to one
of the three allowed sources; reruns over unchanged inputs are byte-identical;
missing inputs produce explicit gaps instead of a silently smaller bundle;
the bundle is plain JSON with no custom types.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from .bundle import _EVIDENTIARY_SOURCES, assemble_bundle

FIXTURE_LOOP_RUNS_ROW = {
    "run_id": "2026-09-02T120000",
    "loop_name": "verify-feat-3182",
    "started_at": "2026-09-02T12:00:00+00:00",
    "ended_at": "2026-09-02T12:04:11+00:00",
    "final_state": "done",
    "iterations": 4,
    "terminated_by": "terminal",
    "error": None,
}

_STATE_JSON = {
    "loop_name": "verify-feat-3182",
    "captured": {
        "criterion-1": {
            "verdict": "yes",
            "reason": "Bundle contents are enumerable and source-traced.",
        },
        "criterion-2": {
            "verdict": "yes",
            "reason": "Reruns over unchanged inputs are byte-identical.",
        },
    },
}

_EVENTS_JSONL = "\n".join(
    json.dumps(e)
    for e in [
        {"event": "state_enter", "state": "verify-criterion-1"},
        {
            "event": "evaluate",
            "state": "verify-criterion-1",
            "llm_model": "claude-sonnet-5",
            "llm_prompt": "Does the bundle enumerate every entry's source?",
            "reason": "Every EvidenceEntry declares a source field.",
            "evidence": "bundle.py:EvidenceEntry.source",
            "raw": {"verdict": "yes"},
        },
        {"event": "state_enter", "state": "verify-criterion-2"},
        {
            "event": "evaluate",
            "state": "verify-criterion-2",
            "llm_model": "claude-sonnet-5",
            "llm_prompt": "Is the bundle reproducible?",
            "reason": "canonical_json() is deterministic across renders.",
            "evidence": "test_rerun_over_unchanged_inputs_is_byte_identical",
            "raw": {"verdict": "yes"},
        },
    ]
)

_PROBE_FILES = {
    "probe-boundary.json": {"probe_class": "boundary", "break_found": False},
    "probe-malformed.json": {"probe_class": "malformed", "break_found": False},
    "probe-failure.json": {"probe_class": "failure_mode", "break_found": False},
}


def build_fixture_run_dir(tmp_path: Path) -> Path:
    """Build a fixture archived-run directory under `tmp_path` and return it."""
    run_dir = tmp_path / "2026-09-02T120000-verify-feat-3182"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "state.json").write_text(json.dumps(_STATE_JSON), encoding="utf-8")
    (run_dir / "events.jsonl").write_text(_EVENTS_JSONL, encoding="utf-8")
    for name, content in _PROBE_FILES.items():
        (run_dir / name).write_text(json.dumps(content), encoding="utf-8")
    return run_dir


_GIT_FACTS = {"head_sha": "abc1234", "branch": "main"}


def test_llm_sourced_fields_never_land_in_evidentiary(tmp_path: Path) -> None:
    run_dir = build_fixture_run_dir(tmp_path)
    bundle = assemble_bundle(FIXTURE_LOOP_RUNS_ROW, run_dir, _GIT_FACTS)

    assert bundle.context_non_evidentiary, "fixture must exercise the LLM-sourced path"
    evidentiary_keys = {e.key for e in bundle.evidentiary}
    # Every captured verdict/reason and every evaluate.*.llm_model field must
    # be absent from evidentiary -- the segregation this spike proves.
    for entry in bundle.context_non_evidentiary:
        assert entry.key not in evidentiary_keys
        assert entry.llm_sourced is True
    assert not any(k.startswith("captured.") for k in evidentiary_keys)
    assert not any(k.startswith("evaluate.") for k in evidentiary_keys)


def test_every_evidentiary_entry_traces_to_deterministic_source(tmp_path: Path) -> None:
    run_dir = build_fixture_run_dir(tmp_path)
    bundle = assemble_bundle(FIXTURE_LOOP_RUNS_ROW, run_dir, _GIT_FACTS)

    assert bundle.evidentiary, "fixture must produce at least one evidentiary entry"
    for entry in bundle.evidentiary:
        assert entry.source in _EVIDENTIARY_SOURCES


def test_rerun_over_unchanged_inputs_is_byte_identical(tmp_path: Path) -> None:
    run_dir = build_fixture_run_dir(tmp_path)
    first = assemble_bundle(FIXTURE_LOOP_RUNS_ROW, run_dir, _GIT_FACTS).canonical_json()
    second = assemble_bundle(FIXTURE_LOOP_RUNS_ROW, run_dir, _GIT_FACTS).canonical_json()
    assert first == second


def test_missing_run_dir_produces_explicit_gap_not_silent_bundle(tmp_path: Path) -> None:
    absent_dir = tmp_path / "no-such-run"
    bundle = assemble_bundle(FIXTURE_LOOP_RUNS_ROW, absent_dir, _GIT_FACTS)

    assert bundle.has_gaps
    assert any(g.category == "missing_run_dir" for g in bundle.gaps)
    # Still has git + loop_runs evidence -- the gap is explicit, not a bundle
    # that just looks smaller with no indication why.
    assert any(e.source == "history_db_row" for e in bundle.evidentiary)


def test_missing_loop_runs_row_produces_explicit_gap(tmp_path: Path) -> None:
    run_dir = build_fixture_run_dir(tmp_path)
    bundle = assemble_bundle(None, run_dir, _GIT_FACTS)

    assert bundle.has_gaps
    assert any(g.category == "missing_loop_runs_row" for g in bundle.gaps)


def test_bundle_is_plain_json_no_custom_types(tmp_path: Path) -> None:
    run_dir = build_fixture_run_dir(tmp_path)
    bundle = assemble_bundle(FIXTURE_LOOP_RUNS_ROW, run_dir, _GIT_FACTS)

    # json.dumps with no default= succeeds only if every value is a plain
    # JSON-encodable type -- proves "readable without little-loops installed".
    reencoded = json.dumps(bundle.to_dict(), sort_keys=True)
    assert json.loads(reencoded) == bundle.to_dict()


def test_spike_does_not_import_production_session_store_or_fsm() -> None:
    """Isolation guard: the spike must not import the production modules it
    is proving a mechanism for -- it operates on plain fixture data only."""
    spike_dir = Path(__file__).parent
    forbidden = {"little_loops.session_store", "little_loops.fsm"}
    for py_file in spike_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                assert not any(name.startswith(f) for f in forbidden), (
                    f"{py_file.name} imports forbidden production module {name}"
                )
