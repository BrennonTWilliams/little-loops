"""Pure reconciliation policy for guarded usage replay (ENH-3770).

Replay writers never decide what to do with a recognized usage request; they normalize the
facts they can prove (native identity, order relation to the committed observation,
qualification context, evidence completeness, conflict and hold state) into a
:class:`PlanFacts` and *execute* the :class:`PlannedAction` that :func:`decide` returns.
This module is the single policy table the issue's "Reconciliation Actions" describes:

* no SQL, no pricing, no I/O and no second native recognition or coalescing algorithm --
  recognition stays in :mod:`~little_loops.session_store.usage_proof`;
* fail closed -- anything unprovable is ``PRESERVE_PENDING``: nothing is written, nothing is
  priced, and the affected scope stays durably retryable;
* a correspondence alone is never mutation permission: every write action names the exact
  evidence it needs and the witness effect that must land atomically with it.

Counts reported to callers increase only for :attr:`Action.INSERT` and
:attr:`Action.INSERT_AUDIT`; replacement, qualification, no-op, pending and conflict
invalidation contribute zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Action(StrEnum):
    """What the guarded writer may do with one logical request."""

    INSERT = "insert"
    INSERT_AUDIT = "insert_audit"
    NOOP = "noop"
    REPLACE = "replace"
    QUALIFY = "qualify"
    INVALIDATE_CONFLICT = "invalidate_conflict"
    PRESERVE_PENDING = "preserve_pending"
    REFUSE = "refuse"


class Relation(StrEnum):
    """How the retained target relates to the committed observation it corresponds to."""

    NONE = "none"  # no committed observation corresponds to the target
    SAME = "same"  # semantically unchanged (identity, values and position)
    OLDER = "older"  # the target is a proved older native snapshot
    NEWER = "newer"  # the target is a proved strictly newer compatible native snapshot
    VALUES_DIFFER = "values_differ"  # same position, different captured values (not newer)
    UNPROVEN = "unproven"  # generation/order cannot be proved (pruned or ambiguous supplier)


class Evidence(StrEnum):
    """Whether every bounded peer/conflict/identity input the action needs was collected."""

    COMPLETE = "complete"
    LIMITED = "limited"  # proof limit exceeded or required evidence unavailable


class Conflict(StrEnum):
    """Independent native identity/value/context conflict state of the target's population."""

    NONE = "none"
    PROVED = "proved"  # complete bounded proof of a conflict not yet recorded
    UNRESOLVED = "unresolved"  # the committed target is already demoted and still conflicts


class Overlap(StrEnum):
    """Whether protected (held/unkeyed/wildcard) rows could already represent the target."""

    NONE = "none"
    AMBIGUOUS = "ambiguous"


class Context(StrEnum):
    """Qualification-only context (model, turn closure) the target consumed."""

    COMPLETE = "complete"
    MISSING = "missing"
    CONTRADICTORY = "contradictory"


class Retention(StrEnum):
    """Whether the source is fully retained and unheld (the only gating qualification case)."""

    FULL_UNHELD = "full_unheld"
    HELD_OR_PRUNED = "held_or_pruned"


class Recovery(StrEnum):
    """Scoped original-source acquisition authority for a NULL-contract audit row."""

    NONE = "none"
    AUTHORIZED = "authorized"


class Witness(StrEnum):
    """Witness effect that must land atomically with the action."""

    NONE = "none"  # leave witnesses alone / grant no affirmative certificate
    SUPPLIER_CONTEXT = "supplier_context"  # record actual supplier and consumed context
    REPLACE = "replace"  # replace applied-value supplier and consumed context
    CLEAR = "clear"  # value changed without acquired authority: drop the stale witness
    CONTEXT = "context"  # record only the newly consumed qualification context
    PRESERVE = "preserve"  # keep supplier and frontier exactly as stored
    INVALIDATE = "invalidate"  # demote contradicted qualification facts only


@dataclass(frozen=True)
class CommittedFacts:
    """The committed observation a target corresponds to (by key or exact raw link)."""

    qualified: bool  # provenance measured under a persisted contract
    priced: bool  # a stored historical cost exists
    keyed: bool  # carries a native observation key


@dataclass(frozen=True)
class PlanFacts:
    """Normalized, already-proved inputs for one logical request."""

    channel: str = "transcript"  # "transcript" | "rollout"
    keyed: bool = True  # native key/request identity proved for the target
    raw_identity: bool = True  # durable raw row id (False for rawless direct-file input)
    identity_ok: bool = True  # envelope, payload and committed identity agree
    qualified: bool = False  # the target qualifies under retained evidence
    context: Context = Context.COMPLETE
    producer_replaces: bool = True  # the producer contract permits snapshot replacement
    committed: CommittedFacts | None = None
    relation: Relation = Relation.NONE
    evidence: Evidence = Evidence.COMPLETE
    conflict: Conflict = Conflict.NONE
    overlap: Overlap = Overlap.NONE
    retention: Retention = Retention.FULL_UNHELD
    recovery: Recovery = Recovery.NONE
    acquired: bool = False  # verified acquisition scope staged for this source
    same_supplier: bool = True  # the committed row's supplier is this very record


@dataclass(frozen=True)
class PlannedAction:
    """The only mutation a writer may perform for one logical request."""

    action: Action
    reason: str
    prices: bool = False  # existing pricing semantics may run, at most once
    witness: Witness = Witness.NONE
    pending: bool = False  # the affected scope stays incomplete (bounded pending)

    @property
    def counts(self) -> bool:
        """Whether the action adds a new observation row to the caller's count."""
        return self.action in {Action.INSERT, Action.INSERT_AUDIT}

    @property
    def mutates(self) -> bool:
        """Whether the action writes to ``usage_events`` (witness-only effects excluded)."""
        return self.action in {
            Action.INSERT,
            Action.INSERT_AUDIT,
            Action.REPLACE,
            Action.QUALIFY,
            Action.INVALIDATE_CONFLICT,
        }


def _preserve(reason: str) -> PlannedAction:
    return PlannedAction(Action.PRESERVE_PENDING, reason, pending=True)


def _noop(reason: str) -> PlannedAction:
    return PlannedAction(Action.NOOP, reason, witness=Witness.PRESERVE)


def decide(facts: PlanFacts) -> PlannedAction:
    """Return the permitted action for *facts* (the issue's Reconciliation Actions table).

    Precedence, most restrictive first: rawless input is refused; incomplete evidence
    preserves; a complete native conflict proof demotes (an already-demoted unresolved
    conflict only preserves); identity disagreement and unproven order preserve with
    pending work; only then do insert, replacement, qualification and no-op rows apply. A larger ingestion id,
    equal numbers or a persisted marker never appear here -- the writer reduces them to a
    :class:`Relation` using native position, so they cannot grant permission.
    """
    if not facts.raw_identity:
        return PlannedAction(Action.REFUSE, "rawless_input")
    # An incomplete collection can neither demote nor certify: it outranks even a conflict
    # reading, because a conflict proof is only valid over its complete bounded evidence.
    if facts.evidence is Evidence.LIMITED:
        return _preserve("evidence_limited")
    if facts.conflict is Conflict.PROVED:
        return PlannedAction(
            Action.INVALIDATE_CONFLICT,
            "native_conflict",
            witness=Witness.INVALIDATE,
            pending=True,
        )
    if facts.conflict is Conflict.UNRESOLVED:
        return _preserve("conflict_unresolved")
    if not facts.identity_ok:
        return _preserve("identity_contradiction")
    if facts.relation is Relation.UNPROVEN:
        return _preserve("order_unproven")

    committed = facts.committed
    if committed is None or facts.relation is Relation.NONE:
        if facts.overlap is Overlap.AMBIGUOUS:
            return _preserve("overlap_ambiguous")
        if not facts.keyed:
            return PlannedAction(Action.INSERT_AUDIT, "stored_raw_audit", prices=True)
        return PlannedAction(
            Action.INSERT,
            "distinct_request",
            prices=True,
            witness=Witness.SUPPLIER_CONTEXT if facts.acquired else Witness.NONE,
        )

    if facts.relation is Relation.VALUES_DIFFER:
        return _preserve("values_differ_at_position")
    if facts.relation is Relation.NEWER:
        if not facts.producer_replaces:
            return _preserve("replacement_not_permitted")
        return PlannedAction(
            Action.REPLACE,
            "newer_snapshot",
            prices=True,
            witness=Witness.REPLACE if facts.acquired else Witness.CLEAR,
        )

    # SAME or OLDER: nothing newer to apply. The only permitted change is a separate
    # qualification action that preserves identity, numbers, timestamps, supplier and cost.
    if facts.relation is Relation.SAME and not facts.same_supplier:
        # A compatible copy shares the survivor's representation; it never promotes it.
        return _noop("identical_copy")
    if (
        facts.relation is Relation.SAME
        and not committed.qualified
        and facts.qualified
        and facts.context is Context.COMPLETE
    ):
        if facts.retention is not Retention.FULL_UNHELD:
            return _noop("held_requalification_deferred")
        if facts.channel == "rollout":
            if not committed.keyed:
                # A row without a native request identity is legacy audit evidence;
                # requalification never promotes it automatically.
                return _noop("legacy_audit_preserved")
            return PlannedAction(
                Action.QUALIFY,
                "closure_requalification",
                prices=not committed.priced,
                witness=Witness.CONTEXT,
            )
        if facts.recovery is Recovery.AUTHORIZED:
            return PlannedAction(
                Action.QUALIFY,
                "original_source_recovery",
                prices=not committed.priced,
                witness=Witness.CONTEXT,
            )
        return _noop("legacy_audit_preserved")
    return _noop("unchanged" if facts.relation is Relation.SAME else "older_snapshot")
