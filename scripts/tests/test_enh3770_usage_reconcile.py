"""ENH-3770: the pure reconciliation action table (no SQL, pricing or I/O)."""

from __future__ import annotations

import dataclasses

import pytest

from little_loops.session_store.usage_reconcile import (
    Action,
    CommittedFacts,
    Conflict,
    Context,
    Evidence,
    Overlap,
    PlanFacts,
    Recovery,
    Relation,
    Retention,
    Witness,
    decide,
)

_AUDIT = CommittedFacts(qualified=False, priced=False, keyed=False)
_MEASURED = CommittedFacts(qualified=True, priced=True, keyed=True)
_UNPRICED_AUDIT = CommittedFacts(qualified=False, priced=False, keyed=True)


def _facts(**kw: object) -> PlanFacts:
    return dataclasses.replace(PlanFacts(), **kw)  # type: ignore[arg-type]


class TestInsertRows:
    def test_distinct_eligible_request_inserts_once_and_records_witness_when_acquired(self) -> None:
        plan = decide(_facts(acquired=True, qualified=True))
        assert (plan.action, plan.prices, plan.witness, plan.counts) == (
            Action.INSERT,
            True,
            Witness.SUPPLIER_CONTEXT,
            True,
        )

    def test_insert_without_acquired_scope_grants_no_witness(self) -> None:
        plan = decide(_facts(acquired=False, qualified=True))
        assert (plan.action, plan.witness) == (Action.INSERT, Witness.NONE)

    def test_first_time_unqualified_audit_inserts_without_an_acquired_head(self) -> None:
        plan = decide(_facts(keyed=False, acquired=False))
        assert (plan.action, plan.reason, plan.prices, plan.witness, plan.counts) == (
            Action.INSERT_AUDIT,
            "stored_raw_audit",
            True,
            Witness.NONE,
            True,
        )

    @pytest.mark.parametrize("keyed", [True, False])
    def test_ambiguous_protected_overlap_never_inserts(self, keyed: bool) -> None:
        plan = decide(_facts(keyed=keyed, overlap=Overlap.AMBIGUOUS))
        assert (plan.action, plan.pending, plan.prices) == (Action.PRESERVE_PENDING, True, False)

    def test_held_source_with_proved_distinct_request_still_inserts(self) -> None:
        plan = decide(_facts(retention=Retention.HELD_OR_PRUNED, overlap=Overlap.NONE))
        assert plan.action is Action.INSERT


class TestNoopRows:
    @pytest.mark.parametrize(
        ("relation", "reason"),
        [(Relation.SAME, "unchanged"), (Relation.OLDER, "older_snapshot")],
    )
    @pytest.mark.parametrize("committed", [_AUDIT, _MEASURED])
    def test_unchanged_or_older_replay_is_an_idempotent_noop(
        self, relation: Relation, reason: str, committed: CommittedFacts
    ) -> None:
        plan = decide(_facts(committed=committed, relation=relation))
        assert (plan.action, plan.reason) == (Action.NOOP, reason)
        assert (plan.prices, plan.witness, plan.pending, plan.mutates, plan.counts) == (
            False,
            Witness.PRESERVE,
            False,
            False,
            False,
        )

    def test_a_compatible_copy_from_another_supplier_never_promotes(self) -> None:
        plan = decide(
            _facts(
                channel="rollout",
                committed=_UNPRICED_AUDIT,
                relation=Relation.SAME,
                same_supplier=False,
                qualified=True,
                context=Context.COMPLETE,
            )
        )
        assert (plan.action, plan.reason) == (Action.NOOP, "identical_copy")
        assert plan.prices is False

    def test_identical_copy_cannot_promote_or_downgrade(self) -> None:
        # A measured row replayed by a copy that lacks context stays exactly as it is.
        plan = decide(
            _facts(
                committed=_MEASURED,
                relation=Relation.SAME,
                qualified=False,
                context=Context.MISSING,
            )
        )
        assert plan.action is Action.NOOP
        # And an unqualified committed row is not promoted by an unqualified copy.
        plan = decide(_facts(committed=_AUDIT, relation=Relation.SAME, qualified=False))
        assert plan.action is Action.NOOP


class TestReplaceRows:
    def test_strictly_newer_compatible_snapshot_replaces_once_with_atomic_witness(self) -> None:
        plan = decide(_facts(committed=_MEASURED, relation=Relation.NEWER, acquired=True))
        assert (plan.action, plan.prices, plan.witness, plan.counts) == (
            Action.REPLACE,
            True,
            Witness.REPLACE,
            False,
        )

    def test_replacement_without_acquired_authority_clears_the_stale_witness(self) -> None:
        plan = decide(_facts(committed=_MEASURED, relation=Relation.NEWER, acquired=False))
        assert (plan.action, plan.witness) == (Action.REPLACE, Witness.CLEAR)

    def test_producer_without_snapshot_replacement_preserves_pending(self) -> None:
        plan = decide(
            _facts(
                channel="rollout",
                committed=_MEASURED,
                relation=Relation.NEWER,
                producer_replaces=False,
            )
        )
        assert (plan.action, plan.reason) == (Action.PRESERVE_PENDING, "replacement_not_permitted")

    def test_generation_or_order_unproven_never_mutates(self) -> None:
        plan = decide(_facts(committed=_MEASURED, relation=Relation.UNPROVEN))
        assert (plan.action, plan.reason, plan.pending) == (
            Action.PRESERVE_PENDING,
            "order_unproven",
            True,
        )


class TestQualifyRows:
    def _codex(self, **kw: object) -> PlanFacts:
        return _facts(
            channel="rollout",
            committed=_UNPRICED_AUDIT,
            relation=Relation.SAME,
            qualified=True,
            context=Context.COMPLETE,
            **kw,
        )

    def test_new_codex_closure_qualifies_the_same_row_once(self) -> None:
        plan = decide(self._codex())
        assert (plan.action, plan.reason, plan.witness, plan.counts) == (
            Action.QUALIFY,
            "closure_requalification",
            Witness.CONTEXT,
            False,
        )
        assert plan.prices is True  # previously unpriced -> priced at most once

    def test_legacy_rollout_audit_without_a_native_identity_is_never_promoted(self) -> None:
        plan = decide(
            dataclasses.replace(
                self._codex(),
                committed=CommittedFacts(qualified=False, priced=False, keyed=False),
            )
        )
        assert (plan.action, plan.reason) == (Action.NOOP, "legacy_audit_preserved")

    def test_already_priced_row_is_not_repriced_on_qualification(self) -> None:
        plan = decide(
            dataclasses.replace(
                self._codex(),
                committed=CommittedFacts(qualified=False, priced=True, keyed=True),
            )
        )
        assert (plan.action, plan.prices) == (Action.QUALIFY, False)

    @pytest.mark.parametrize("context", [Context.MISSING, Context.CONTRADICTORY])
    def test_missing_or_contradictory_context_blocks_promotion(self, context: Context) -> None:
        plan = decide(dataclasses.replace(self._codex(), context=context))
        assert plan.action is Action.NOOP

    def test_held_or_pruned_requalification_is_deferred_not_promoted(self) -> None:
        plan = decide(self._codex(retention=Retention.HELD_OR_PRUNED))
        assert (plan.action, plan.reason) == (Action.NOOP, "held_requalification_deferred")

    def test_matching_audit_recovery_needs_scoped_authority(self) -> None:
        base = _facts(
            channel="transcript",
            committed=_AUDIT,
            relation=Relation.SAME,
            qualified=True,
        )
        assert (
            decide(base).action is Action.NOOP
        )  # a marker/matching values alone are not authority
        assert decide(base).reason == "legacy_audit_preserved"
        plan = decide(dataclasses.replace(base, recovery=Recovery.AUTHORIZED))
        assert (plan.action, plan.reason, plan.witness) == (
            Action.QUALIFY,
            "original_source_recovery",
            Witness.CONTEXT,
        )

    def test_recovery_prices_an_unpriced_audit_at_most_once(self) -> None:
        priced = CommittedFacts(qualified=False, priced=True, keyed=False)
        plan = decide(
            _facts(
                committed=priced,
                relation=Relation.SAME,
                qualified=True,
                recovery=Recovery.AUTHORIZED,
            )
        )
        assert (plan.action, plan.prices) == (Action.QUALIFY, False)

    def test_contradictory_captured_values_stay_protected_and_incomplete(self) -> None:
        plan = decide(
            _facts(
                committed=_AUDIT,
                relation=Relation.VALUES_DIFFER,
                qualified=True,
                recovery=Recovery.AUTHORIZED,
            )
        )
        assert (plan.action, plan.reason, plan.pending, plan.prices) == (
            Action.PRESERVE_PENDING,
            "values_differ_at_position",
            True,
            False,
        )

    def test_an_already_qualified_row_is_never_requalified(self) -> None:
        plan = decide(
            _facts(
                channel="rollout",
                committed=_MEASURED,
                relation=Relation.SAME,
                qualified=True,
                context=Context.COMPLETE,
            )
        )
        assert plan.action is Action.NOOP


class TestConflictRows:
    def test_complete_conflict_proof_demotes_even_over_an_unchanged_numeric_target(self) -> None:
        plan = decide(
            _facts(
                channel="rollout",
                committed=_MEASURED,
                relation=Relation.SAME,
                conflict=Conflict.PROVED,
            )
        )
        assert (plan.action, plan.witness, plan.pending, plan.prices) == (
            Action.INVALIDATE_CONFLICT,
            Witness.INVALIDATE,
            True,
            False,
        )

    def test_conflict_proof_over_an_older_replay_still_demotes(self) -> None:
        plan = decide(
            _facts(committed=_MEASURED, relation=Relation.OLDER, conflict=Conflict.PROVED)
        )
        assert plan.action is Action.INVALIDATE_CONFLICT

    def test_first_derivation_conflict_is_detected_without_a_committed_row(self) -> None:
        plan = decide(_facts(committed=None, relation=Relation.NONE, conflict=Conflict.PROVED))
        assert plan.action is Action.INVALIDATE_CONFLICT
        assert plan.prices is False  # nothing is priced before the conflict is recognized

    def test_unresolved_conflict_blocks_replacement_and_requalification(self) -> None:
        for relation in (Relation.NEWER, Relation.SAME, Relation.OLDER):
            plan = decide(
                _facts(
                    channel="rollout",
                    committed=_UNPRICED_AUDIT,
                    relation=relation,
                    qualified=True,
                    conflict=Conflict.UNRESOLVED,
                )
            )
            assert (plan.action, plan.reason, plan.pending) == (
                Action.PRESERVE_PENDING,
                "conflict_unresolved",
                True,
            )

    def test_ordinary_older_replay_is_not_conflict_proof(self) -> None:
        plan = decide(_facts(committed=_MEASURED, relation=Relation.OLDER, conflict=Conflict.NONE))
        assert plan.action is Action.NOOP


class TestFailClosedRows:
    def test_rawless_direct_input_is_refused_before_everything_else(self) -> None:
        for conflict in Conflict:
            plan = decide(_facts(raw_identity=False, conflict=conflict, qualified=True))
            assert (plan.action, plan.prices, plan.witness, plan.pending) == (
                Action.REFUSE,
                False,
                Witness.NONE,
                False,
            )

    def test_identity_disagreement_cannot_manufacture_a_qualified_observation(self) -> None:
        for committed, relation in ((None, Relation.NONE), (_MEASURED, Relation.NEWER)):
            plan = decide(
                _facts(identity_ok=False, qualified=True, committed=committed, relation=relation)
            )
            assert (plan.action, plan.reason, plan.mutates, plan.prices) == (
                Action.PRESERVE_PENDING,
                "identity_contradiction",
                False,
                False,
            )

    @pytest.mark.parametrize(
        "relation",
        [Relation.NONE, Relation.SAME, Relation.OLDER, Relation.NEWER, Relation.VALUES_DIFFER],
    )
    def test_limited_evidence_permits_no_partial_plan(self, relation: Relation) -> None:
        committed = None if relation is Relation.NONE else _MEASURED
        plan = decide(_facts(evidence=Evidence.LIMITED, committed=committed, relation=relation))
        assert (plan.action, plan.reason, plan.pending, plan.prices, plan.mutates) == (
            Action.PRESERVE_PENDING,
            "evidence_limited",
            True,
            False,
            False,
        )

    def test_limited_evidence_never_demotes(self) -> None:
        plan = decide(
            _facts(evidence=Evidence.LIMITED, committed=_MEASURED, relation=Relation.SAME)
        )
        assert plan.action is not Action.INVALIDATE_CONFLICT

    def test_qualification_context_alone_does_not_block_an_audit_insert_or_noop(self) -> None:
        insert = decide(_facts(keyed=False, context=Context.MISSING))
        assert insert.action is Action.INSERT_AUDIT
        noop = decide(
            _facts(keyed=False, committed=_AUDIT, relation=Relation.SAME, context=Context.MISSING)
        )
        assert noop.action is Action.NOOP


class TestTableInvariants:
    @pytest.mark.parametrize("conflict", list(Conflict))
    @pytest.mark.parametrize("evidence", list(Evidence))
    @pytest.mark.parametrize("relation", list(Relation))
    @pytest.mark.parametrize("overlap", list(Overlap))
    @pytest.mark.parametrize("identity_ok", [True, False])
    def test_only_write_actions_mutate_and_only_inserts_count(
        self,
        conflict: Conflict,
        evidence: Evidence,
        relation: Relation,
        overlap: Overlap,
        identity_ok: bool,
    ) -> None:
        committed = None if relation is Relation.NONE else _UNPRICED_AUDIT
        plan = decide(
            _facts(
                conflict=conflict,
                evidence=evidence,
                relation=relation,
                overlap=overlap,
                identity_ok=identity_ok,
                committed=committed,
                qualified=True,
            )
        )
        if plan.counts:
            assert plan.action in {Action.INSERT, Action.INSERT_AUDIT}
        if plan.action in {Action.NOOP, Action.PRESERVE_PENDING, Action.REFUSE}:
            assert not plan.mutates and not plan.prices
        if plan.action is Action.PRESERVE_PENDING:
            assert plan.pending
        if plan.prices:
            assert plan.action in {
                Action.INSERT,
                Action.INSERT_AUDIT,
                Action.REPLACE,
                Action.QUALIFY,
            }
        # Anything that could be unsafe never writes without complete, conflict-free evidence.
        if evidence is Evidence.LIMITED or conflict is Conflict.UNRESOLVED:
            assert not plan.mutates

    def test_plans_are_frozen(self) -> None:
        plan = decide(_facts())
        with pytest.raises(dataclasses.FrozenInstanceError):
            plan.action = Action.NOOP  # type: ignore[misc]
