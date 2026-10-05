"""ENH-3731: shared usage qualification core and its source-reader consumers."""

from __future__ import annotations

import itertools
import json
import math
import shutil
import sqlite3
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from little_loops.cli.ctx_stats import (
    _aggregate_usage_events,
    _aggregate_waste,
    _cache_rate_provenance,
    _compute_cache_rate_from_usage,
    _token_provenance,
    _waste_provenance,
)
from little_loops.history_reader import (
    UsageQualification,
    aggregate_usage,
    cost_attribution,
    qualify_usage,
    waste_attribution,
)
from little_loops.history_reader.usage import select_usage_coverage
from little_loops.session_store import (
    SessionHandle,
    backfill_raw_events,
    connect,
    ensure_db,
    rebuild,
    record_loop_run_summary,
)
from little_loops.session_store.lifecycle import refresh_usage_source
from little_loops.token_provenance import (
    AGGREGATE_COLUMNS,
    USAGE_QUALIFICATION_POLICY_VERSION,
    USAGE_QUALIFICATION_REASONS,
    ObservationGroup,
    counted_entry,
    same_metadata,
)

_CAPTURE = Path(__file__).parent / "fixtures" / "claude" / "transcript-v2.1.284.jsonl"
_CODEX = Path(__file__).parent / "fixtures" / "codex" / "rollout-exec-resume-v0.158.0.jsonl"


def _row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "provenance": "measured",
        "input_tokens": 10,
        "output_tokens": 2,
        "cache_read_input_tokens": 4,
        "cache_creation_input_tokens": 1,
        "cost_usd": 1.0,
    }
    row.update(overrides)
    return row


def _group(*rows: dict[str, Any]) -> ObservationGroup:
    group = ObservationGroup()
    for row in rows:
        group.add(row)
    return group


def _insert(db: Path, **row: Any) -> None:
    cols = {
        "ts": "2026-09-01T00:00:00Z",
        "model": "m1",
        "input_tokens": 10,
        "output_tokens": 2,
        "cache_read_input_tokens": 4,
        "cache_creation_input_tokens": 1,
        "cost_usd": 1.0,
        "provenance": "measured",
        **row,
    }
    ensure_db(db)
    conn = connect(db)
    try:
        conn.execute(
            f"INSERT INTO usage_events({', '.join(cols)}) VALUES({', '.join('?' * len(cols))})",
            list(cols.values()),
        )
        conn.commit()
    finally:
        conn.close()


class TestQualifyUsageMatrix:
    def test_measured_complete_row_is_eligible(self) -> None:
        result = qualify_usage(_group(_row()))
        assert result.eligible and result.reason is None
        assert result.provenance == "measured"
        assert (result.contributors, result.rejected_contributors) == (1, 0)
        assert result.policy_version == USAGE_QUALIFICATION_POLICY_VERSION == 1

    def test_estimated_complete_row_is_eligible_but_not_measured_only(self) -> None:
        group = _group(_row(provenance="estimated"))
        assert qualify_usage(group).eligible
        assert qualify_usage(group).provenance == "estimated"
        measured = qualify_usage(group, measured_only=True)
        assert measured.reason == "not_measured" and measured.rejected_contributors == 1

    def test_mixed_measured_and_estimated_is_labeled_mixed(self) -> None:
        group = _group(_row(), _row(provenance="estimated"))
        result = qualify_usage(group)
        assert result.eligible and result.provenance == "mixed"

    @pytest.mark.parametrize("provenance", ["unknown", None, "bogus"])
    def test_unknown_null_and_unrecognized_provenance_are_audit_only(
        self, provenance: str | None
    ) -> None:
        group = _group(_row(provenance=provenance))
        result = qualify_usage(group)
        assert result.reason == "unknown_provenance" and result.provenance == "unknown"
        assert group.total("input_tokens") is None
        assert group.audit_subtotal("input_tokens") == 10

    def test_numeric_cost_cannot_qualify_an_audit_only_row(self) -> None:
        group = _group(_row(provenance="unknown", cost_usd=1.0))
        assert group.total("cost_usd") is None
        assert group.audit_subtotal("cost_usd") == 1.0
        assert qualify_usage(group, require_cost=True).reason == "unknown_provenance"

    @pytest.mark.parametrize("column", AGGREGATE_COLUMNS[:4])
    def test_each_missing_token_component_rejects_the_row(self, column: str) -> None:
        group = _group(_row(**{column: None}), _row())
        result = qualify_usage(group)
        assert result.reason == "missing_token_component"
        assert result.rejected_contributors == 1
        assert result.counts(column).missing_count == 1
        for token in AGGREGATE_COLUMNS[:4]:
            assert group.total(token) is None

    @pytest.mark.parametrize("bad", [-1, 3.0, True, "7", float("nan")])
    def test_invalid_token_values_are_rejected_not_coerced(self, bad: Any) -> None:
        group = _group(_row(input_tokens=bad), _row(input_tokens=5))
        result = qualify_usage(group)
        assert result.reason == "invalid_token_component"
        counts = result.counts("input_tokens")
        assert (counts.known_count, counts.missing_count, counts.invalid_count) == (1, 0, 1)
        assert group.audit_subtotal("input_tokens") == 5

    def test_missing_cost_does_not_reject_token_row(self) -> None:
        group = _group(_row(cost_usd=None))
        assert qualify_usage(group).eligible
        assert group.total("input_tokens") == 10
        assert qualify_usage(group, require_cost=True).reason == "unpriced_contributor"
        assert group.total("cost_usd") is None

    @pytest.mark.parametrize("bad", [-0.5, True, "1.0", float("nan"), float("inf"), 10**400])
    def test_invalid_cost_values(self, bad: Any) -> None:
        group = _group(_row(cost_usd=bad), _row(cost_usd=2.0))
        result = qualify_usage(group, require_cost=True)
        assert result.reason == "invalid_cost"
        assert result.counts("cost_usd").invalid_count == 1
        assert qualify_usage(group).eligible
        assert group.audit_subtotal("cost_usd") == 2.0

    def test_empty_selection(self) -> None:
        group = ObservationGroup()
        for flags in ({}, {"require_cost": True}, {"measured_only": True}):
            result = qualify_usage(group, **flags)
            assert result.reason == "empty_selection" and result.contributors == 0
        assert group.total("input_tokens") is None
        assert group.audit_subtotal("input_tokens") is None

    def test_observed_zero_is_zero(self) -> None:
        group = _group(
            _row(
                input_tokens=0,
                output_tokens=0,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
                cost_usd=0.0,
            )
        )
        assert group.total("input_tokens") == 0 and group.total("cost_usd") == 0.0

    @pytest.mark.parametrize(
        ("coverage", "reason"),
        [("overlap_unresolved", "coverage_overlap_unresolved"), ("unknown", "coverage_unknown")],
    )
    def test_coverage_failure_wins_over_row_failures(self, coverage: str, reason: str) -> None:
        group = _group(
            _row(_coverage=coverage, _coverage_reason="prose; not a code", input_tokens=None)
        )
        assert qualify_usage(group).reason == reason
        assert group.total("input_tokens") is None

    def test_coverage_prose_never_enters_reason_codes(self) -> None:
        group = _group(_row(_coverage="unknown", _coverage_reason="live_replay_join_unproven"))
        assert qualify_usage(group).reason in USAGE_QUALIFICATION_REASONS

    def test_reason_precedence_is_insertion_order_independent(self) -> None:
        rows = [
            _row(output_tokens=None),
            _row(input_tokens=-1),
            _row(provenance="unknown"),
            _row(provenance="estimated", cost_usd=None),
        ]
        reasons = {
            qualify_usage(_group(*perm), require_cost=True, measured_only=True).reason
            for perm in itertools.permutations(rows)
        }
        assert reasons == {"missing_token_component"}
        reasons = {
            qualify_usage(_group(*perm), require_cost=True, measured_only=True).reason
            for perm in itertools.permutations(rows[2:])
        }
        assert reasons == {"unknown_provenance"}

    def test_flags_can_only_tighten(self) -> None:
        rows = [_row(), _row(provenance="estimated"), _row(cost_usd=None)]
        for subset in itertools.chain.from_iterable(
            itertools.combinations(rows, n) for n in range(1, 4)
        ):
            group = _group(*subset)
            base = qualify_usage(group)
            for flags in ({"require_cost": True}, {"measured_only": True}):
                tightened = qualify_usage(group, **flags)
                assert tightened.rejected_contributors >= base.rejected_contributors
                if not base.eligible:
                    assert not tightened.eligible

    def test_multiply_rejected_row_counts_once_and_partitions_counts(self) -> None:
        group = _group(
            _row(provenance="unknown", output_tokens=None, cost_usd=None),
            _row(input_tokens=-3, cost_usd=-1),
            _row(),
        )
        for flags in (
            {},
            {"require_cost": True},
            {"measured_only": True},
            {"require_cost": True, "measured_only": True},
        ):
            result = qualify_usage(group, **flags)
            assert result.rejected_contributors == 2
            for counts in result.component_counts:
                assert (
                    counts.known_count + counts.missing_count + counts.invalid_count
                    == result.contributors
                )
        assert [c.column for c in qualify_usage(group).component_counts] == list(AGGREGATE_COLUMNS)

    def test_result_is_immutable_and_snapshots_counts(self) -> None:
        group = _group(_row())
        result = qualify_usage(group)
        group.add(_row(output_tokens=None))
        assert result.eligible and result.contributors == 1
        assert result.counts("output_tokens").missing_count == 0
        with pytest.raises(FrozenInstanceError):
            result.eligible = False  # type: ignore[misc]
        assert isinstance(result, UsageQualification)

    def test_token_sums_are_exact_above_2_53(self) -> None:
        big = 2**53 + 1
        group = _group(_row(input_tokens=big), _row(input_tokens=1))
        assert group.total("input_tokens") == big + 1


class TestCostArithmetic:
    def test_cost_total_is_order_independent(self) -> None:
        totals = set()
        for perm in itertools.permutations([1e16, 1.0, 1.0]):
            group = _group(*(_row(cost_usd=c) for c in perm))
            totals.add(group.total("cost_usd"))
            assert group.entry("cost_usd")["composition"]["measured"]["subtotal"] == (
                group.total("cost_usd")
            )
        assert len(totals) == 1

    def test_aggregate_overflow_blanks_only_cost(self) -> None:
        group = _group(_row(cost_usd=1e308), _row(cost_usd=1e308))
        entry = group.entry("cost_usd")
        assert group.total("cost_usd") is None
        assert qualify_usage(group, require_cost=True).reason == "invalid_cost"
        assert group.total("input_tokens") == 20
        assert group.audit_subtotal("cost_usd") is None
        assert entry["composition"]["measured"]["subtotal"] is None
        assert entry["known_count"] == 2 and entry["invalid_count"] == 0
        assert entry["rejected_contributors"] == 0
        assert json.dumps(entry, allow_nan=False)

    def test_boundary_overflow_is_permutation_stable(self) -> None:
        tiny = math.ulp(sys.float_info.max) / 4
        costs = [sys.float_info.max, tiny, tiny, tiny]
        verdicts = set()
        for perm in itertools.permutations(costs):
            group = _group(*(_row(cost_usd=c) for c in perm))
            verdicts.add((group.total("cost_usd"), qualify_usage(group, require_cost=True).reason))
        assert len(verdicts) == 1


class TestEntryMetadata:
    def test_availability_follows_value_and_never_partial(self) -> None:
        group = _group(_row(), _row(input_tokens=None))
        entry = group.entry("input_tokens")
        assert entry["availability"] == "unavailable"
        assert (entry["known_count"], entry["missing_count"]) == (1, 1)
        assert entry["qualification_reason"] == "missing_token_component"
        assert entry["rejected_contributors"] == 1
        ok = _group(_row()).entry("input_tokens")
        assert ok["availability"] == "available" and ok["qualification_reason"] is None

    def test_cost_entry_uses_cost_requirement(self) -> None:
        group = _group(_row(cost_usd=None))
        assert group.entry("input_tokens")["availability"] == "available"
        cost = group.entry("cost_usd")
        assert cost["availability"] == "unavailable"
        assert cost["qualification_reason"] == "unpriced_contributor"

    def test_same_metadata_distinguishes_new_keys_but_ignores_free_reason(self) -> None:
        base = counted_entry("m", provenance="measured", known=1, missing=0)
        assert same_metadata([base, {**base, "reason": "other prose"}])
        for key, value in (
            ("qualification_reason", "missing_token_component"),
            ("invalid_count", 1),
            ("rejected_contributors", 1),
        ):
            assert not same_metadata([base, {**base, key: value}])

    def test_reason_vocabulary_is_closed(self) -> None:
        assert "unrecognized_provenance" not in USAGE_QUALIFICATION_REASONS
        assert "zero_denominator" in USAGE_QUALIFICATION_REASONS
        assert "empty_selection" in USAGE_QUALIFICATION_REASONS


class TestSourceFigures:
    def test_estimated_rows_publish_labeled_consumption(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        _insert(db, provenance="estimated", channel="live")
        (row,) = aggregate_usage(db=db)
        assert row["input_tokens"] == 10 and row["provenance"] == "estimated"
        assert row["qualification_reason"] is None

    def test_unknown_provenance_is_audit_only_in_every_reader(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        _insert(db, provenance=None, cost_usd=5.0)
        (agg,) = aggregate_usage(db=db)
        assert agg["input_tokens"] is None and agg["cost_usd"] is None
        assert agg["qualification_reason"] == "unknown_provenance"
        assert agg["cost_qualification_reason"] == "unknown_provenance"
        assert agg["channel_subtotals"]["live"]["input_tokens"] == 10
        (cost,) = cost_attribution("model", db=db)
        assert not [key for key in cost if key.startswith("gen_ai.usage.")]

    def test_measured_partial_row_with_numeric_cost_publishes_nothing(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        _insert(db, cache_creation_input_tokens=None, cost_usd=1.0)
        (agg,) = aggregate_usage(db=db)
        assert agg["input_tokens"] is None and agg["cost_usd"] is None
        assert agg["cache_creation_input_tokens_missing"] == 1
        result = _aggregate_usage_events(db)
        assert result is not None
        assert all(v is None for v in result["totals"].values())
        assert "partial" not in {e["availability"] for e in result["provenance"].values()}

    def test_complete_tokens_survive_missing_and_invalid_cost(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        _insert(db, cost_usd=None)
        _insert(db, cost_usd=-1.0)
        (agg,) = aggregate_usage(db=db)
        assert agg["input_tokens"] == 20 and agg["qualification_reason"] is None
        assert agg["cost_usd"] is None
        assert agg["cost_qualification_reason"] == "invalid_cost"
        assert agg["cost_usd_invalid"] == 1 and agg["cost_usd_missing"] == 1
        result = _aggregate_usage_events(db)
        assert result is not None and result["totals"]["input_tokens"] == 20
        entry = result["provenance"]["/usage_by_model/totals/cost_usd"]
        assert entry["availability"] == "unavailable"
        # Invalid and missing costs never enter the valid-value audit composition.
        assert entry["composition"] == {}

    def test_invalid_persisted_values_do_not_crash_readers(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        ensure_db(db)
        _insert(db, input_tokens=5)
        conn = sqlite3.connect(db)
        conn.execute(
            "INSERT INTO usage_events(ts, model, input_tokens, output_tokens, "
            "cache_read_input_tokens, cache_creation_input_tokens, provenance) "
            "VALUES('t', 'm1', 'abc', -2, 1.5, 1, 'measured')"
        )
        conn.commit()
        conn.close()
        (agg,) = aggregate_usage(db=db)
        assert agg["input_tokens"] is None
        assert agg["input_tokens_invalid"] == 1 and agg["output_tokens_invalid"] == 1
        assert agg["qualification_reason"] == "invalid_token_component"
        assert agg["channel_subtotals"]["live"]["input_tokens"] == 5
        result = _aggregate_usage_events(db)
        assert result is not None
        json.dumps(result, allow_nan=False)

    def test_pointers_agree_with_values_across_usage_by_model(self, tmp_path: Path) -> None:
        db = tmp_path / "h.db"
        _insert(db, model="a")
        _insert(db, model="b", provenance=None)
        _insert(db, model="c", output_tokens=None)
        result = _aggregate_usage_events(db)
        assert result is not None
        allowed = USAGE_QUALIFICATION_REASONS
        for pointer, entry in result["provenance"].items():
            parts = pointer.split("/")
            node = result
            for token in parts[2:]:
                node = node[token.replace("~1", "/").replace("~0", "~")]
            assert (node is not None) == (entry["availability"] == "available"), pointer
            assert (entry["qualification_reason"] is None) == (node is not None), pointer
            assert entry["qualification_reason"] in {None, *allowed}


def _waste_db(tmp_path: Path, rows: list[dict[str, Any]], *, wasted: bool = True) -> Path:
    db = tmp_path / "w.db"
    ensure_db(db)
    record_loop_run_summary(
        db,
        run_id="r1",
        loop_name="lp",
        terminated_by="max_steps" if wasted else "terminal",
        final_state=None if wasted else "done",
    )
    for row in rows:
        _insert(db, run_id="r1", **row)
    return db


class TestWaste:
    def test_observed_zero_denominator(self, tmp_path: Path) -> None:
        db = _waste_db(tmp_path, [{"input_tokens": 0, "output_tokens": 0}] * 2)
        (row,) = waste_attribution(db=db)
        assert row["tokens_total"] == 0 and row["tokens_wasted"] == 0
        assert row["waste_pct"] is None and row["qualification_reason"] is None
        assert row["waste_pct_qualification_reason"] == "zero_denominator"
        entries = _waste_provenance([row])
        total = entries["/waste/0/tokens_total"]
        ratio = entries["/waste/0/waste_pct"]
        assert total["availability"] == "available" and total["known_count"] == 2
        assert ratio["availability"] == "unavailable"
        assert (ratio["known_count"], ratio["missing_count"]) == (2, 0)
        assert ratio["qualification_reason"] == "zero_denominator"

    def test_positive_denominator_without_wasted_runs(self, tmp_path: Path) -> None:
        db = _waste_db(tmp_path, [{}], wasted=False)
        (row,) = waste_attribution(db=db)
        assert row["tokens_total"] == 12 and row["tokens_wasted"] == 0
        assert row["waste_pct"] == 0

    def test_missing_cache_only_rejects_both_figures(self, tmp_path: Path) -> None:
        db = _waste_db(tmp_path, [{"cache_read_input_tokens": None}])
        (row,) = waste_attribution(db=db)
        assert row["tokens_total"] is None and row["tokens_wasted"] is None
        assert row["tokens_total_missing"] == 0 and row["tokens_wasted_missing"] == 0
        assert row["qualification_reason"] == "missing_token_component"
        assert row["rejected_contributors"] == 1
        entries = _waste_provenance([row])
        ratio = entries["/waste/0/waste_pct"]
        assert (ratio["known_count"], ratio["missing_count"]) == (1, 0)
        assert ratio["qualification_reason"] == "missing_token_component"

    def test_malformed_non_wasted_pair_contributes_zero_but_rejects(self, tmp_path: Path) -> None:
        db = _waste_db(tmp_path, [{"input_tokens": None}], wasted=False)
        (row,) = waste_attribution(db=db)
        assert row["tokens_total"] is None and row["tokens_total_missing"] == 1
        assert row["tokens_wasted_missing"] == 0

    def test_null_plus_invalid_pairs_are_classified_once(self, tmp_path: Path) -> None:
        db = _waste_db(tmp_path, [{"input_tokens": None, "output_tokens": -1}])
        conn = sqlite3.connect(db)
        conn.execute(
            "INSERT INTO usage_events(ts, model, input_tokens, output_tokens, "
            "cache_read_input_tokens, cache_creation_input_tokens, provenance, run_id) "
            "VALUES('t', 'm', 3, -4, 0, 0, 'measured', 'r1')"
        )
        conn.commit()
        conn.close()
        (row,) = waste_attribution(db=db)
        assert (row["tokens_total_missing"], row["tokens_total_invalid"]) == (1, 1)
        assert (row["tokens_wasted_missing"], row["tokens_wasted_invalid"]) == (1, 1)
        entries = _waste_provenance([row])
        total = entries["/waste/0/tokens_total"]
        assert (total["known_count"], total["missing_count"], total["invalid_count"]) == (0, 1, 1)

    def test_unknown_provenance_blanks_waste(self, tmp_path: Path) -> None:
        db = _waste_db(tmp_path, [{"provenance": None}])
        (row,) = _aggregate_waste(db) or []
        assert row["tokens_total"] is None
        assert row["qualification_reason"] == "unknown_provenance"
        assert row["channel_subtotals"]["live"]["input_tokens"] == 10


def _captured_session(tmp_path: Path) -> tuple[Path, SessionHandle]:
    source = tmp_path / "session.jsonl"
    shutil.copyfile(_CAPTURE, source)
    session_id = json.loads(source.read_text(encoding="utf-8").splitlines()[0])["sessionId"]
    handle = SessionHandle("claude-code", session_id, source, tmp_path, source.stat().st_mtime)
    db = tmp_path / "history.db"
    ensure_db(db)
    assert refresh_usage_source(db, handle.path)["usage_events"] == 2
    return db, handle


def _update(db: Path, sql: str, *params: Any) -> None:
    conn = sqlite3.connect(db)
    conn.execute(sql, params)
    conn.commit()
    conn.close()


def _stored(db: Path, handle: SessionHandle) -> dict[str, Any]:
    result, diagnostic = _compute_cache_rate_from_usage(handle, db)
    assert diagnostic is None and result is not None
    return result


class TestStoredCacheRate:
    def test_complete_measured_session_publishes_rate_and_operands(self, tmp_path: Path) -> None:
        db, handle = _captured_session(tmp_path)
        result = _stored(db, handle)
        assert result["hit_rate_pct"] == 77 and result["qualification_reason"] is None
        assert result["rejected_contributors"] == 0
        assert result["counts"]["hit_rate_pct"] == {"known": 2, "missing": 0}
        assert result["invalid_counts"] == {"cache_read": 0, "cache_write": 0, "uncached": 0}
        entries = _cache_rate_provenance(result)
        assert {e["coverage"] for e in entries.values()} == {result["coverage"]}
        assert {e["availability"] for e in entries.values()} == {"available"}

    def test_missing_output_disqualifies_rate_but_keeps_truthful_counts(
        self, tmp_path: Path
    ) -> None:
        db, handle = _captured_session(tmp_path)
        _update(
            db,
            "UPDATE usage_events SET output_tokens = NULL WHERE id = "
            "(SELECT MIN(id) FROM usage_events)",
        )
        result = _stored(db, handle)
        assert result["hit_rate_pct"] is None
        assert result["cache_read"] is None and result["uncached"] is None
        assert result["qualification_reason"] == "missing_token_component"
        assert result["counts"]["cache_read"] == {"known": 2, "missing": 0}
        assert result["counts"]["hit_rate_pct"] == {"known": 1, "missing": 1}
        assert result["rejected_contributors"] == 1
        entries = _cache_rate_provenance(result)
        for entry in entries.values():
            assert entry["availability"] == "unavailable"
            assert entry["qualification_reason"] == "missing_token_component"
            assert "partial" != entry["availability"]
        assert entries["/cache_read_tokens"]["known_count"] == 2

    def test_unresolved_audit_sibling_blocks_a_measured_sibling(self, tmp_path: Path) -> None:
        db, handle = _captured_session(tmp_path)
        _update(
            db,
            "UPDATE usage_events SET provenance = NULL WHERE id = (SELECT MAX(id) FROM usage_events)",
        )
        result = _stored(db, handle)
        assert result["hit_rate_pct"] is None and result["cache_read"] is None
        assert result["qualification_reason"] == "unverified_usage"
        entries = _cache_rate_provenance(result)
        assert {e["qualification_reason"] for e in entries.values()} == {"unverified_usage"}

    def test_complete_estimated_rows_are_not_measured(self, tmp_path: Path) -> None:
        db, handle = _captured_session(tmp_path)
        _update(db, "UPDATE usage_events SET provenance = 'estimated'")
        result = _stored(db, handle)
        assert result["cache_read"] is None and result["hit_rate_pct"] is None
        assert result["qualification_reason"] == "unverified_usage"
        # General consumption still reads the same fixture as estimated numeric usage.
        rows = aggregate_usage(db=db)
        assert rows[0]["input_tokens"] == 18 and rows[0]["provenance"] == "estimated"

    def test_invalid_stored_value_is_not_coerced(self, tmp_path: Path) -> None:
        db, handle = _captured_session(tmp_path)
        _update(
            db,
            "UPDATE usage_events SET input_tokens = 'x' WHERE id = "
            "(SELECT MIN(id) FROM usage_events)",
        )
        result = _stored(db, handle)
        assert result["hit_rate_pct"] is None
        assert result["qualification_reason"] == "invalid_token_component"
        assert result["invalid_counts"]["uncached"] == 1
        assert result["counts"]["uncached"] == {"known": 1, "missing": 0}

    def test_zero_denominator_blanks_only_the_rate(self, tmp_path: Path) -> None:
        db, handle = _captured_session(tmp_path)
        _update(
            db,
            "UPDATE usage_events SET input_tokens = 0, output_tokens = 0, "
            "cache_read_input_tokens = 0, cache_creation_input_tokens = 0",
        )
        result = _stored(db, handle)
        assert result["hit_rate_pct"] is None
        assert result["qualification_reason"] == "zero_denominator"
        assert (result["cache_read"], result["cache_write"], result["uncached"]) == (0, 0, 0)
        entries = _cache_rate_provenance(result)
        assert entries["/cache_read_tokens"]["qualification_reason"] is None
        assert entries["/cache_read_tokens"]["availability"] == "available"
        assert entries["/cache_hit_rate_pct"]["availability"] == "unavailable"
        assert entries["/cache_hit_rate_pct"]["qualification_reason"] == "zero_denominator"

    def test_document_invariant_holds_for_stored_pointers(self, tmp_path: Path) -> None:
        db, handle = _captured_session(tmp_path)
        allowed = {*USAGE_QUALIFICATION_REASONS, "unverified_usage"}
        for sql in (
            "SELECT 1",
            "UPDATE usage_events SET provenance = NULL",
            "UPDATE usage_events SET output_tokens = NULL",
        ):
            _update(db, sql)
            result = _stored(db, handle)
            values = {
                "/cache_read_tokens": result["cache_read"],
                "/cache_write_tokens": result["cache_write"],
                "/uncached_tokens": result["uncached"],
                "/cache_hit_rate_pct": result["hit_rate_pct"],
            }
            entries = _token_provenance({"x": 1}, None, result, None, None, None)
            for pointer, value in values.items():
                entry = entries[pointer]
                assert (value is not None) == (entry["availability"] == "available")
                assert (value is None) == (entry["qualification_reason"] is not None)
                assert entry["qualification_reason"] in {None, *allowed}
                assert entry["coverage"] == result["coverage"]


class TestEstimatedCodexRolloutControl:
    def test_estimated_rollout_row_is_coverage_unknown_never_canonical(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "history.db"
        ensure_db(db)
        native = json.loads(_CODEX.read_text().splitlines()[0])["payload"]
        handle = SessionHandle("codex", native["id"], _CODEX, tmp_path, 1.0)
        backfill_raw_events(db, handles=[handle])
        rebuild(db)
        _update(db, "UPDATE usage_events SET provenance = 'estimated' WHERE channel = 'rollout'")
        with connect(db) as conn:
            selection = select_usage_coverage(conn, host="codex", session_id=native["id"])
        assert selection.coverage == "unknown"
        assert selection.reason == "rollout_request_identity_unverified"
        group = ObservationGroup()
        for row in selection.audit_rows:
            group.add(row)
        assert qualify_usage(group).reason == "coverage_unknown"


class TestStoredCacheCli:
    @staticmethod
    def _summary() -> dict[str, Any]:
        return {"total_in": 1, "total_out": 1, "cache_bytes": 0, "cache_hits": 0, "per_tool": {}}

    def test_zero_denominator_emits_no_unverified_warning_and_footnotes_reason(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        from little_loops.cli.ctx_stats import _render, main_ctx_stats
        from little_loops.logger import Logger

        db, handle = _captured_session(tmp_path)
        _update(
            db,
            "UPDATE usage_events SET input_tokens = 0, output_tokens = 0, "
            "cache_read_input_tokens = 0, cache_creation_input_tokens = 0",
        )
        monkeypatch.chdir(tmp_path)
        from unittest.mock import patch

        with patch("little_loops.cli.ctx_stats.detect_sessions", return_value=[handle]):
            assert main_ctx_stats(["--db", str(db), "--json"]) == 0
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["cache_rate_qualification_reason"] == "zero_denominator"
        assert payload["cache_read_tokens"] == 0 and payload["cache_hit_rate_pct"] is None
        assert "unverified" not in captured.err
        _render(self._summary(), Logger(use_color=False), None, _stored(db, handle))
        out = capsys.readouterr().out
        assert "n/a (zero usage)" in out
        assert "* qualification: zero_denominator" in out

    def test_unverified_provenance_is_named_in_stderr_and_text(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        from unittest.mock import patch

        from little_loops.cli.ctx_stats import _render, main_ctx_stats
        from little_loops.logger import Logger

        db, handle = _captured_session(tmp_path)
        _update(db, "UPDATE usage_events SET provenance = NULL")
        monkeypatch.chdir(tmp_path)
        with patch("little_loops.cli.ctx_stats.detect_sessions", return_value=[handle]):
            main_ctx_stats(["--db", str(db), "--json"])
        assert "producer usage identity or components are unverified" in capsys.readouterr().err
        _render(self._summary(), Logger(use_color=False), None, _stored(db, handle))
        out = capsys.readouterr().out
        assert "unavailable (usage unverified)" in out
        assert "* qualification: unverified_usage" in out

    def test_missing_component_is_distinguished_in_text(self, tmp_path: Path, capsys) -> None:
        from little_loops.cli.ctx_stats import _render
        from little_loops.logger import Logger

        db, handle = _captured_session(tmp_path)
        _update(db, "UPDATE usage_events SET output_tokens = NULL")
        _render(self._summary(), Logger(use_color=False), None, _stored(db, handle))
        out = capsys.readouterr().out
        assert "unavailable (missing usage component)" in out
        assert "excluded (missing usage component)" not in out
