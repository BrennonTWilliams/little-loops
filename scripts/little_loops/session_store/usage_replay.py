"""Plan-then-execute usage replay writer (ENH-3770).

``writers._backfill_usage_events`` collects the logical usage requests a replay sees (it owns
native record decoding and the Codex turn state machine) and hands them here. Nothing is
written, priced or deleted until *every* participating request has been compared with the
committed observations: the replay set is grouped by native identity, normalized into
:class:`~little_loops.session_store.usage_reconcile.PlanFacts` and decided by the shared
policy table (:func:`~little_loops.session_store.usage_reconcile.decide`), and only then is
each :class:`~little_loops.session_store.usage_reconcile.PlannedAction` executed.

Consequences the issue requires and this module enforces:

* an unchanged, older or compatible-copy replay is a no-op -- no pricing, no ``UPDATE``;
* ingestion order (a larger raw id) is never evidence of a newer native snapshot -- only a
  strictly later native position inside a provably ordered, retained generation is;
* conflicting copies are all recognized before the first priced insert; a proved conflict
  demotes only the contradicted qualification (``provenance``/``usage_contract``), keeping
  row identity, numbers, cost, timestamps and supplier, and keeps the conflicting copy as
  unpriced unqualified audit evidence;
* raw-less input (no durable raw row id) is refused;
* anything unprovable is preserved untouched and reported as bounded pending work.

Recognition stays in :mod:`~little_loops.session_store.usage_proof` and the writers; this
module neither parses native records nor adds a second coalescing algorithm.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from little_loops.session_store.usage_proof import models_compatible
from little_loops.session_store.usage_reconcile import (
    Action,
    CommittedFacts,
    Conflict,
    Context,
    Overlap,
    PlanFacts,
    PlannedAction,
    Recovery,
    Relation,
    Retention,
    Witness,
    decide,
)
from little_loops.session_store.usage_source_state import (
    HeadState,
    ObservationWitness,
    QualificationDependency,
    invalidate_usage_dependencies,
    read_observation_witness,
    read_pending_recovery,
    read_source_head,
    storage_available,
    write_observation_witness,
)

if TYPE_CHECKING:
    from little_loops.session_store.writers import (
        UsageObservation,
        UsageReplayHolds,
        UsageReplayRecord,
        UsageSearchScope,
        _CodexCandidate,
        _CodexReplayState,
    )

logger = logging.getLogger(__name__)

_CHUNK = 500
_COLUMNS = (
    "id",
    "ts",
    "session_id",
    "model",
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "cost_usd",
    "channel",
    "provenance",
    "host",
    "observation_key",
    "usage_contract",
    "source_raw_event_id",
    "source_path",
    "source_line_no",
    "source_ordinal",
    "request_id",
    "turn_id",
)

# Bounded reasons a preserved scope is reported with (finite codes, never native content).
_CONFLICT_REASON = "native_conflict"


# -- Report ------------------------------------------------------------------


@dataclass
class Outcome:
    """Unresolved work one source accrued during a replay (bounded raw-id range + reasons)."""

    source_path: str
    kind: str  # "derive_gap" | "native_conflict"
    first_raw_id: int | None = None
    last_raw_id: int | None = None
    reasons: set[str] = field(default_factory=set)
    affected: set[int] = field(default_factory=set)

    def widen(self, raw_id: int | None) -> None:
        if raw_id is None:
            return
        self.first_raw_id = raw_id if self.first_raw_id is None else min(self.first_raw_id, raw_id)
        self.last_raw_id = raw_id if self.last_raw_id is None else max(self.last_raw_id, raw_id)


@dataclass
class ReplayReport:
    """What one guarded replay did and which scopes it left incomplete (ENH-3770)."""

    inserted: int = 0
    replaced: int = 0
    qualified: int = 0
    demoted: int = 0
    noop: int = 0
    refused: int = 0
    scanned_sources: set[str] = field(default_factory=set)
    outcomes: dict[tuple[str, str], Outcome] = field(default_factory=dict)

    def note(
        self,
        source_path: str | None,
        raw_id: int | None,
        reason: str,
        *,
        kind: str = "derive_gap",
        affected: Iterable[int] = (),
    ) -> None:
        if not source_path:
            return
        outcome = self.outcomes.setdefault(
            (source_path, kind), Outcome(source_path=source_path, kind=kind)
        )
        outcome.reasons.add(reason)
        outcome.affected.update(affected)
        outcome.widen(raw_id)

    @property
    def incomplete_sources(self) -> frozenset[str]:
        return frozenset(source for source, _ in self.outcomes)


# -- Committed observations ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class Committed:
    """One committed ``usage_events`` row as the planner sees it."""

    id: int
    ts: str | None
    session_id: str | None
    model: str | None
    components: tuple[Any, Any, Any, Any]
    cost_usd: float | None
    channel: str | None
    provenance: str | None
    host: str | None
    observation_key: str | None
    usage_contract: str | None
    source_raw_event_id: int | None
    source_path: str | None
    source_line_no: int | None
    source_ordinal: int | None
    request_id: str | None
    turn_id: str | None

    @property
    def qualified(self) -> bool:
        return self.provenance == "measured"

    @property
    def values5(self) -> tuple[Any, ...]:
        return (self.model, *self.components)

    def facts(self) -> CommittedFacts:
        keyed = self.observation_key is not None or self.request_id is not None
        return CommittedFacts(
            qualified=self.qualified, priced=self.cost_usd is not None, keyed=keyed
        )


def _committed(row: tuple[Any, ...]) -> Committed:
    return Committed(
        id=row[0],
        ts=row[1],
        session_id=row[2],
        model=row[3],
        components=(row[4], row[5], row[6], row[7]),
        cost_usd=row[8],
        channel=row[9],
        provenance=row[10],
        host=row[11],
        observation_key=row[12],
        usage_contract=row[13],
        source_raw_event_id=row[14],
        source_path=row[15],
        source_line_no=row[16],
        source_ordinal=row[17],
        request_id=row[18],
        turn_id=row[19],
    )


class CommittedIndex:
    """Committed non-live observations selected by native identity and exact raw link only."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.by_id: dict[int, Committed] = {}
        self.by_key: dict[str, Committed] = {}
        self.by_link: dict[int, Committed] = {}
        self.by_request: dict[str, list[Committed]] = {}

    def _add(self, row: Committed) -> None:
        if row.id in self.by_id:
            return
        self.by_id[row.id] = row
        if row.observation_key is not None:
            self.by_key[row.observation_key] = row
        if row.source_raw_event_id is not None:
            self.by_link[row.source_raw_event_id] = row
        if row.request_id is not None and row.channel == "rollout":
            self.by_request.setdefault(row.request_id, []).append(row)

    def load(
        self,
        *,
        keys: Iterable[str] = (),
        links: Iterable[int] = (),
        requests: Iterable[str] = (),
    ) -> None:
        columns = ", ".join(_COLUMNS)
        selectors: tuple[tuple[str, list[Any]], ...] = (
            ("observation_key", sorted(set(keys))),
            ("source_raw_event_id", sorted(set(links))),
            ("request_id", sorted(set(requests))),
        )
        for column, values in selectors:
            for start in range(0, len(values), _CHUNK):
                chunk = values[start : start + _CHUNK]
                marks = ", ".join("?" for _ in chunk)
                for row in self._conn.execute(
                    f"SELECT {columns} FROM usage_events WHERE channel IS NOT 'live' "
                    f"AND {column} IN ({marks})",
                    chunk,
                ):
                    self._add(_committed(tuple(row)))

    def ids(self) -> list[int]:
        return sorted(self.by_id)


# -- Targets -----------------------------------------------------------------


@dataclass(slots=True)
class ClaudeTarget:
    """One Claude-shaped assistant usage snapshot (payload-free)."""

    index: int
    replay: UsageReplayRecord
    observation: UsageObservation
    values: tuple[Any, ...]

    @property
    def raw_id(self) -> int | None:
        return self.replay.raw_event_id

    @property
    def source(self) -> str:
        return self.replay.source_label

    @property
    def key(self) -> str | None:
        return self.observation.observation_key

    @property
    def position(self) -> int | None:
        replay = self.replay
        return replay.ordinal if replay.ordinal is not None else replay.line_no


def claude_target(
    index: int, replay: UsageReplayRecord, observation: UsageObservation
) -> ClaudeTarget:
    """Build a payload-free Claude target so a large replay holds only what it plans with."""
    import dataclasses

    usage = observation.usage
    return ClaudeTarget(
        index=index,
        replay=dataclasses.replace(replay, payload={}),
        observation=observation,
        values=(
            observation.model,
            usage.get("input_tokens"),
            usage.get("output_tokens"),
            usage.get("cache_read_input_tokens"),
            usage.get("cache_creation_input_tokens"),
        ),
    )


@dataclass(slots=True)
class CodexTarget:
    """One Codex request candidate with the qualification the whole span proved."""

    index: int
    cand: _CodexCandidate
    components: tuple[Any, Any, Any, Any]
    complete: bool
    verified_host: bool
    verified_thread: bool
    measured: bool
    closure_ctx: tuple[int | None, int | None, int | None] | None = None

    @property
    def raw_id(self) -> int | None:
        return self.cand.record.raw_event_id

    @property
    def source(self) -> str:
        return self.cand.record.source_label

    @property
    def keyed(self) -> bool:
        return bool(self.cand.request_identity_basis == "native_response" and self.cand.request_id)


@dataclass(slots=True)
class Planned:
    """A target together with the action the policy table permits for it."""

    index: int
    kind: str  # "claude" | "codex"
    target: Any
    plan: PlannedAction
    committed: Committed | None = None
    demote: tuple[Committed, ...] = ()
    copy_needed: bool = False
    roles: frozenset[str] = frozenset({"model", "closure"})


# -- Planning context --------------------------------------------------------


def _held_kind(holds: UsageReplayHolds, source: str, host: str | None, channel: str) -> str | None:
    """``"population"`` for a wildcard/NULL-source hold, ``"source"`` for an exact one."""
    if any(
        (pop_host == "*" or pop_host == host) and (pop_channel == "*" or pop_channel == channel)
        for pop_host, pop_channel in holds.populations
    ):
        return "population"
    return "source" if source in holds.sources else None


class _Ctx:
    def __init__(
        self,
        conn: sqlite3.Connection,
        holds: UsageReplayHolds,
        scope: UsageSearchScope,
        report: ReplayReport,
        run_id_for: Callable[[str], str | None],
    ) -> None:
        self.conn = conn
        self.holds = holds
        self.scope = scope
        self.report = report
        self.run_id_for = run_id_for
        self.index = CommittedIndex(conn)
        self.demoted: set[int] = set()
        self._overlap: dict[tuple[str, str | None, str, bool], Overlap] = {}
        self._supplier: dict[int, bool] = {}
        self._scheduled: set[int] = set()
        self._recovery: dict[str, int | None] = {}
        self._heads: dict[str, HeadState | None] = {}

    # -- committed state -----------------------------------------------------

    def load_demoted(self) -> None:
        """Observations an earlier proved conflict demoted (durable pending is authoritative)."""
        if not storage_available(self.conn):
            return
        ids = self.index.ids()
        for start in range(0, len(ids), _CHUNK):
            chunk = ids[start : start + _CHUNK]
            marks = ", ".join("?" for _ in chunk)
            for (affected,) in self.conn.execute(
                "SELECT DISTINCT affected_usage_event_id FROM usage_source_pending "
                f"WHERE kind = 'native_conflict' AND affected_usage_event_id IN ({marks})",
                chunk,
            ):
                self.demoted.add(affected)

    def is_demoted(self, row: Committed) -> bool:
        if row.id in self.demoted or row.id in self._scheduled:
            return True
        # A keyed Claude row is inserted measured; keyed + unknown can only be a demotion.
        return row.observation_key is not None and not row.qualified

    def schedule_demotion(self, rows: Iterable[Committed]) -> tuple[Committed, ...]:
        fresh = tuple(row for row in rows if row.qualified and not self.is_demoted(row))
        self._scheduled.update(row.id for row in fresh)
        return fresh

    # -- hold semantics ------------------------------------------------------

    def retention(self, source: str, host: str | None, channel: str) -> Retention:
        held = _held_kind(self.holds, source, host, channel) is not None
        return Retention.HELD_OR_PRUNED if held else Retention.FULL_UNHELD

    def overlap(self, source: str, host: str | None, channel: str, keyed: bool) -> Overlap:
        """Whether a held source's protected history could already represent a new request.

        An unheld source is exactly what the committed index shows. A wildcard/population
        hold or an unkeyed request on a held source cannot be proved distinct from rows
        whose raw evidence is gone; an exact-source hold with a keyed request is distinct
        unless that source still carries unkeyed legacy rows.
        """
        cache_key = (source, host, channel, keyed)
        cached = self._overlap.get(cache_key)
        if cached is not None:
            return cached
        kind = _held_kind(self.holds, source, host, channel)
        if kind is None:
            result = Overlap.NONE
        elif kind == "population" or not keyed:
            result = Overlap.AMBIGUOUS
        else:
            unkeyed = "request_id IS NULL" if channel == "rollout" else "observation_key IS NULL"
            row = self.conn.execute(
                "SELECT 1 FROM usage_events WHERE source_path = ? AND channel IS NOT 'live' "
                f"AND {unkeyed} LIMIT 1",
                (source,),
            ).fetchone()
            result = Overlap.AMBIGUOUS if row is not None else Overlap.NONE
        self._overlap[cache_key] = result
        return result

    def head(self, source: str) -> HeadState | None:
        if source not in self._heads:
            self._heads[source] = read_source_head(self.conn, source)
        return self._heads[source]

    def acquired(self, source: str, line_no: int | None) -> bool:
        """Whether a verified acquisition covers *line_no* of *source* (witness authority)."""
        from little_loops.session_store.usage_source_tracking import USAGE_ACQUISITION_VERSION

        head = self.head(source)
        return bool(
            head is not None
            and head.acquisition_version == USAGE_ACQUISITION_VERSION
            and head.acquired_line_no is not None
            and line_no is not None
            and line_no <= head.acquired_line_no
        )

    def recovery(self, source: str, line_no: int | None) -> Recovery:
        """Scoped original-source acquisition authority covering *line_no* of *source*.

        Only a verified ``OriginalAcquisition`` persisted by an explicit parser refresh counts,
        and only for the head's current generation/derive version and acquisition version,
        with the request inside the certified range. A marker, matching values or ordinary
        replay never create it.
        """
        if line_no is None or not storage_available(self.conn):
            return Recovery.NONE
        certified = self._recovery.get(source)
        if source not in self._recovery:
            certified = None
            head = read_source_head(self.conn, source)
            if head is not None:
                for item in read_pending_recovery(self.conn, source):
                    authority = item.original_acquisition
                    pending = item.pending
                    if (
                        authority is not None
                        and pending.kind == "refresh"
                        and pending.reason == "parser_refresh"
                        and pending.usage_pending
                        and pending.scope.generation_id == head.scope.generation_id
                        and pending.scope.derive_version == head.scope.derive_version
                        and authority.acquisition_version == head.acquisition_version
                    ):
                        certified = max(certified or 0, authority.line_no)
            self._recovery[source] = certified
        return (
            Recovery.AUTHORIZED if certified is not None and line_no <= certified else Recovery.NONE
        )

    def supplier_order_provable(self, row: Committed) -> bool:
        """Whether the committed supplier's native position can still be compared.

        The supplying raw row must still be retained, or an independently sufficient
        committed witness for the current source generation must establish its order.
        """
        cached = self._supplier.get(row.id)
        if cached is not None:
            return cached
        provable = False
        if row.source_raw_event_id is not None and row.source_path is not None:
            retained = self.conn.execute(
                "SELECT 1 FROM raw_events WHERE id = ? AND source_path = ?",
                (row.source_raw_event_id, row.source_path),
            ).fetchone()
            if retained is not None:
                provable = True
            elif storage_available(self.conn):
                witness = read_observation_witness(self.conn, row.id)
                head = read_source_head(self.conn, row.source_path)
                provable = bool(
                    head is not None
                    and witness.value_status == "known"
                    and witness.supplier_source_path == row.source_path
                    and witness.supplier_generation_id == head.scope.generation_id
                )
        self._supplier[row.id] = provable
        return provable

    # -- planned shorthands --------------------------------------------------

    def noop(self, target: Any, reason: str, kind: str = "claude") -> Planned:
        self.report.noop += 1
        return Planned(target.index, kind, target, PlannedAction(Action.NOOP, reason))

    def preserve(self, target: Any, reason: str, kind: str = "claude") -> Planned:
        self.report.note(target.source, target.raw_id, reason, kind="derive_gap")
        return Planned(
            target.index,
            kind,
            target,
            PlannedAction(Action.PRESERVE_PENDING, reason, pending=True),
        )

    def refuse(self, target: Any, kind: str = "claude") -> Planned:
        self.report.refused += 1
        return Planned(target.index, kind, target, PlannedAction(Action.REFUSE, "rawless_input"))


# -- Claude planning ----------------------------------------------------------


def _ordered(targets: list[ClaudeTarget]) -> bool:
    """Native order inside one source: strictly increasing positions and raw ids."""
    positions = [t.position for t in targets]
    ids = [t.raw_id for t in targets]
    known_positions = [p for p in positions if p is not None]
    known_ids = [i for i in ids if i is not None]
    if len(known_positions) != len(positions) or len(known_ids) != len(ids):
        return False
    return all(a < b for a, b in zip(known_positions, known_positions[1:], strict=False)) and all(
        a < b for a, b in zip(known_ids, known_ids[1:], strict=False)
    )


def _claude_relation(
    ctx: _Ctx, target: ClaudeTarget, row: Committed
) -> tuple[Relation, bool, bool]:
    """``(relation, same_supplier, cross_source_conflict)`` of *target* to committed *row*."""
    same_values = row.values5 == target.values
    if row.source_path != target.source:
        if same_values:
            return Relation.SAME, False, False
        return Relation.VALUES_DIFFER, False, True
    link = row.source_raw_event_id
    if link is not None and target.raw_id == link:
        return (Relation.SAME if same_values else Relation.VALUES_DIFFER), True, False
    if same_values:
        # Identical captured values need no order proof: nothing would change either way.
        return Relation.SAME, False, False
    position = row.source_line_no
    if link is None or position is None or target.position is None:
        return Relation.UNPROVEN, False, False
    if not ctx.supplier_order_provable(row):
        return Relation.UNPROVEN, False, False
    assert target.raw_id is not None
    if target.position == position:
        return Relation.UNPROVEN, False, False
    if target.position > position and target.raw_id > link:
        return Relation.NEWER, False, False
    if target.position < position and target.raw_id < link:
        return Relation.OLDER, False, False
    return Relation.UNPROVEN, False, False


def _claude_facts(
    ctx: _Ctx,
    target: ClaudeTarget,
    *,
    committed: Committed | None,
    relation: Relation,
    same_supplier: bool = True,
    conflict: Conflict = Conflict.NONE,
    identity_ok: bool = True,
) -> PlanFacts:
    replay = target.replay
    keyed = target.key is not None
    return PlanFacts(
        channel="transcript",
        keyed=keyed,
        raw_identity=target.raw_id is not None,
        identity_ok=identity_ok,
        qualified=target.observation.qualified,
        producer_replaces=True,
        committed=committed.facts() if committed is not None else None,
        relation=relation,
        conflict=conflict,
        overlap=ctx.overlap(target.source, replay.host, "transcript", keyed),
        retention=ctx.retention(target.source, replay.host, "transcript"),
        recovery=ctx.recovery(target.source, replay.line_no),
        acquired=ctx.acquired(target.source, replay.line_no),
        same_supplier=same_supplier,
    )


def _claude_conflict(
    ctx: _Ctx, target: ClaudeTarget, committed: Committed | None, link: Committed | None
) -> Planned:
    """A proved cross-source value conflict: demote only qualification, keep the copy."""
    demotable = committed is not None and committed.qualified and not ctx.is_demoted(committed)
    represented = link is not None or (committed is not None and committed.values5 == target.values)
    if represented and not demotable:
        state = Conflict.UNRESOLVED
        ctx.report.note(target.source, target.raw_id, _CONFLICT_REASON, kind="native_conflict")
        plan = decide(
            _claude_facts(ctx, target, committed=link, relation=Relation.SAME, conflict=state)
        )
        return Planned(target.index, "claude", target, plan, committed=link)
    demote = ctx.schedule_demotion([committed] if committed is not None else [])
    plan = decide(
        _claude_facts(
            ctx,
            target,
            committed=committed,
            relation=Relation.VALUES_DIFFER,
            conflict=Conflict.PROVED,
        )
    )
    return Planned(
        target.index,
        "claude",
        target,
        plan,
        committed=committed,
        demote=demote,
        copy_needed=not represented,
        roles=frozenset({"model", "closure"}),
    )


def _plan_claude_target(
    ctx: _Ctx,
    target: ClaudeTarget,
    committed: Committed | None,
    link: Committed | None,
    key_row: Committed | None,
) -> Planned:
    if committed is None:
        relation, same_supplier = Relation.NONE, True
    else:
        if key_row is not None and link is not None and link.id != key_row.id:
            return ctx.preserve(target, "link_key_mismatch")
        if committed is link and (
            committed.host != target.replay.host
            or committed.session_id != target.observation.session_id
            or committed.channel not in (None, "transcript")
        ):
            # An exact raw link with a disagreeing identity proves nothing about this request.
            return ctx.preserve(target, "identity_contradiction")
        relation, same_supplier, cross_conflict = _claude_relation(ctx, target, committed)
        if cross_conflict:
            return _claude_conflict(ctx, target, committed, link)
        if ctx.is_demoted(committed):
            # An already demoted row stays demoted: neither a newer snapshot nor an
            # original-source recovery nor an unchanged replay may re-promote or reprice it.
            # Different values are new evidence, kept as unpriced audit beside it.
            if committed.values5 != target.values:
                return _claude_conflict(ctx, target, committed, link)
            ctx.report.note(target.source, target.raw_id, _CONFLICT_REASON, kind="native_conflict")
            plan = decide(
                _claude_facts(
                    ctx,
                    target,
                    committed=committed,
                    relation=Relation.SAME,
                    same_supplier=same_supplier,
                    conflict=Conflict.UNRESOLVED,
                )
            )
            return Planned(target.index, "claude", target, plan, committed=committed)
    plan = decide(
        _claude_facts(
            ctx, target, committed=committed, relation=relation, same_supplier=same_supplier
        )
    )
    if plan.action is Action.PRESERVE_PENDING:
        ctx.report.note(target.source, target.raw_id, plan.reason)
    return Planned(target.index, "claude", target, plan, committed=committed)


def _plan_claude_key(
    ctx: _Ctx, key: str, by_source: dict[str, list[ClaudeTarget]]
) -> list[Planned]:
    # A source whose snapshots are not provably ordered can still be planned when they all
    # carry the same values (there is no "newer" to choose); otherwise the group is unproven.
    for targets in by_source.values():
        if not _ordered(targets) and len({t.values for t in targets}) > 1:
            return [ctx.preserve(t, "order_unproven") for ts in by_source.values() for t in ts]
    out: list[Planned] = []
    finals: dict[str, ClaudeTarget] = {}
    for source, targets in by_source.items():
        if not _ordered(targets):
            targets = sorted(targets, key=lambda t: t.raw_id or 0)
        out.extend(ctx.noop(t, "superseded_snapshot") for t in targets[:-1])
        finals[source] = targets[-1]
    ordered = sorted(finals.values(), key=lambda t: t.raw_id or 0)
    key_row = ctx.index.by_key.get(key)
    if len({t.values for t in ordered}) > 1:
        shared: set[tuple[Any, ...]] = set()
        for t in ordered:
            assert t.raw_id is not None
            if t.values in shared:
                # Identical to an earlier participant: it shares that value's representation.
                out.append(ctx.noop(t, "identical_copy"))
                continue
            shared.add(t.values)
            out.append(_claude_conflict(ctx, t, key_row, ctx.index.by_link.get(t.raw_id)))
        return out
    survivor = ordered[0]
    for t in ordered:
        assert t.raw_id is not None
        link = ctx.index.by_link.get(t.raw_id)
        committed = key_row if key_row is not None else link
        if committed is None and t is not survivor:
            out.append(ctx.noop(t, "identical_copy"))
            continue
        out.append(_plan_claude_target(ctx, t, committed, link, key_row))
    return out


def _plan_claude_audit(ctx: _Ctx, target: ClaudeTarget) -> Planned:
    assert target.raw_id is not None
    link = ctx.index.by_link.get(target.raw_id)
    replay = target.replay
    if link is None:
        relation, identity_ok = Relation.NONE, True
    else:
        identity_ok = (
            link.source_path == target.source
            and link.host == replay.host
            and link.session_id == target.observation.session_id
            and link.channel in (None, "transcript")
        )
        relation = Relation.SAME if link.values5 == target.values else Relation.VALUES_DIFFER
    plan = decide(
        _claude_facts(ctx, target, committed=link, relation=relation, identity_ok=identity_ok)
    )
    if plan.action is Action.PRESERVE_PENDING:
        ctx.report.note(target.source, target.raw_id, plan.reason)
    return Planned(target.index, "claude", target, plan, committed=link)


def plan_claude(ctx: _Ctx, targets: list[ClaudeTarget]) -> list[Planned]:
    planned: list[Planned] = []
    keyed: dict[str, dict[str, list[ClaudeTarget]]] = {}
    audits: list[ClaudeTarget] = []
    live: list[ClaudeTarget] = []
    for t in targets:
        ctx.report.scanned_sources.add(t.source)
        if t.raw_id is None:
            planned.append(ctx.refuse(t))
        elif not t.observation.identity_ok:
            planned.append(ctx.preserve(t, "identity_contradiction"))
        else:
            live.append(t)
            if t.key is None:
                audits.append(t)
            else:
                keyed.setdefault(t.key, {}).setdefault(t.source, []).append(t)
    ctx.index.load(keys=keyed, links=[t.raw_id for t in live if t.raw_id is not None])
    ctx.load_demoted()
    for key, by_source in keyed.items():
        planned.extend(_plan_claude_key(ctx, key, by_source))
    planned.extend(_plan_claude_audit(ctx, t) for t in audits)
    return planned


# -- Codex planning -----------------------------------------------------------


def _codex_match(row: Committed, target: CodexTarget) -> bool:
    """Whether committed *row* is compatible with *target* (model/context never invalidate)."""
    cand = target.cand
    if row.components != target.components:
        return False
    if row.turn_id != cand.turn_id or row.session_id != cand.thread_id:
        return False
    if row.host not in (None, cand.record.host):
        return False
    return models_compatible(row.model, cand.model)


def _codex_facts(
    ctx: _Ctx,
    target: CodexTarget,
    *,
    committed: Committed | None,
    relation: Relation,
    same_supplier: bool = True,
    conflict: Conflict = Conflict.NONE,
) -> PlanFacts:
    cand = target.cand
    host = cand.record.host
    context = (
        Context.COMPLETE
        if target.complete and cand.model and cand.closed and target.verified_thread
        else Context.MISSING
    )
    return PlanFacts(
        channel="rollout",
        keyed=target.keyed,
        raw_identity=target.raw_id is not None,
        qualified=target.measured,
        context=context,
        producer_replaces=False,
        committed=committed.facts() if committed is not None else None,
        relation=relation,
        conflict=conflict,
        overlap=ctx.overlap(target.source, host, "rollout", target.keyed),
        retention=ctx.retention(target.source, host, "rollout"),
        acquired=ctx.acquired(target.source, cand.record.line_no),
        same_supplier=same_supplier,
    )


def _codex_conflict(
    ctx: _Ctx, target: CodexTarget, group: list[Committed], link: Committed | None
) -> Planned:
    demotable = [row for row in group if row.qualified and not ctx.is_demoted(row)]
    represented = link is not None
    if represented and not demotable:
        ctx.report.note(target.source, target.raw_id, _CONFLICT_REASON, kind="native_conflict")
        plan = decide(
            _codex_facts(
                ctx, target, committed=link, relation=Relation.SAME, conflict=Conflict.UNRESOLVED
            )
        )
        return Planned(target.index, "codex", target, plan, committed=link)
    demote = ctx.schedule_demotion(demotable)
    plan = decide(
        _codex_facts(ctx, target, committed=None, relation=Relation.NONE, conflict=Conflict.PROVED)
    )
    cand = target.cand
    # Only the contradicted fact leaves the consumed frontier: when every other identity and
    # count agrees, the models alone disagree and the recorded closure stays valid.
    model_only = bool(group) and all(
        row.components == target.components
        and row.turn_id == cand.turn_id
        and row.session_id == cand.thread_id
        for row in group
    )
    return Planned(
        target.index,
        "codex",
        target,
        plan,
        demote=demote,
        copy_needed=not represented,
        roles=frozenset({"model"}) if model_only else frozenset({"model", "closure"}),
    )


def _plan_codex_one(ctx: _Ctx, target: CodexTarget) -> Planned:
    cand = target.cand
    if target.raw_id is None:
        return ctx.refuse(target, "codex")
    link = ctx.index.by_link.get(target.raw_id)
    group = list(ctx.index.by_request.get(cand.request_id or "", ())) if target.keyed else []
    if cand.conflict:
        return _codex_conflict(ctx, target, group, link)
    committed: Committed | None = None
    relation = Relation.NONE
    same_supplier = True
    if target.keyed and group:
        compat = [row for row in group if _codex_match(row, target)]
        if len(compat) != len(group):
            return _codex_conflict(ctx, target, group, link)
        committed = next((r for r in compat if r.source_raw_event_id == target.raw_id), compat[0])
        relation = Relation.SAME
        same_supplier = committed.source_raw_event_id == target.raw_id
    elif link is not None:
        committed = link
        relation = Relation.SAME if _codex_match(link, target) else Relation.VALUES_DIFFER
    conflict = (
        Conflict.UNRESOLVED
        if committed is not None and committed.id in ctx.demoted
        else Conflict.NONE
    )
    plan = decide(
        _codex_facts(
            ctx,
            target,
            committed=committed,
            relation=relation,
            same_supplier=same_supplier,
            conflict=conflict,
        )
    )
    if plan.action is Action.PRESERVE_PENDING:
        ctx.report.note(
            target.source,
            target.raw_id,
            plan.reason,
            kind="native_conflict" if plan.reason == "conflict_unresolved" else "derive_gap",
        )
    return Planned(target.index, "codex", target, plan, committed=committed)


def plan_codex(
    ctx: _Ctx,
    candidates: list[_CodexCandidate],
    states: dict[str, _CodexReplayState],
    first_index: int,
) -> list[Planned]:
    """Dedup by native identity inside the replay set, then compare with committed rows."""
    seen: dict[tuple[str, str], _CodexCandidate] = {}
    distinct: list[_CodexCandidate] = []
    for cand in candidates:
        if cand.request_identity_basis != "native_response" or not cand.request_id:
            distinct.append(cand)
            continue
        key = (cand.record.host or "", cand.request_id)
        earlier = seen.get(key)
        if earlier is None:
            seen[key] = cand
            distinct.append(cand)
        elif (
            earlier.thread_id == cand.thread_id
            and earlier.turn_id == cand.turn_id
            and earlier.usage == cand.usage
            and models_compatible(earlier.model, cand.model)
        ):
            continue
        else:
            earlier.conflict = True
            cand.conflict = True
            distinct.append(cand)
            logger.warning("Codex response_id conflict for %s; retaining uncertain rows", key)
    from little_loops.session_store.writers import _codex_components

    targets: list[CodexTarget] = []
    for offset, cand in enumerate(distinct):
        replay = cand.record
        state = states[replay.source_label]
        cand.closed = bool(cand.turn_id and cand.turn_id in state.closed_turns)
        input_tokens, output_tokens, cache_read, cache_write, complete = _codex_components(
            cand.usage
        )
        verified_host = replay.host == "codex" and replay.host_basis == "handle"
        verified_thread = bool(
            cand.thread_id and state.thread_id == cand.thread_id and verified_host
        )
        measured = bool(
            complete
            and cand.model
            and cand.closed
            and verified_thread
            and cand.request_identity_basis == "native_response"
            and not cand.conflict
        )
        targets.append(
            CodexTarget(
                index=first_index + offset,
                cand=cand,
                components=(input_tokens, output_tokens, cache_read, cache_write),
                complete=complete,
                verified_host=verified_host,
                verified_thread=verified_thread,
                measured=measured,
                closure_ctx=state.closure_ctx.get(cand.turn_id or ""),
            )
        )
        ctx.report.scanned_sources.add(replay.source_label)
    live = [t for t in targets if t.raw_id is not None]
    ctx.index.load(
        links=[t.raw_id for t in live if t.raw_id is not None],
        requests=[t.cand.request_id for t in live if t.keyed and t.cand.request_id],
    )
    ctx.load_demoted()
    return [_plan_codex_one(ctx, t) for t in targets]


# -- Execution ---------------------------------------------------------------


def _price(ts: str, model: Any, components: tuple[Any, Any, Any, Any]) -> float | None:
    from little_loops.pricing import _event_date, estimate_cost_usd

    return estimate_cost_usd(
        str(model or ""),
        components[0],
        components[1],
        components[2],
        components[3],
        as_of=_event_date(ts),
    )


def _insert_claude(ctx: _Ctx, t: ClaudeTarget, *, priced: bool, audit_copy: bool) -> int:
    from little_loops.observability.tracing import vendor_for_runner

    replay, observation = t.replay, t.observation
    usage = observation.usage
    components = (
        usage.get("input_tokens"),
        usage.get("output_tokens"),
        usage.get("cache_read_input_tokens"),
        usage.get("cache_creation_input_tokens"),
    )
    cost = _price(replay.ts, observation.model, components) if priced else None
    qualified = observation.qualified and not audit_copy
    key = None if audit_copy else observation.observation_key
    cursor = ctx.conn.execute(
        "INSERT INTO usage_events(ts, session_id, model, state, input_tokens, "
        "output_tokens, cache_read_input_tokens, cache_creation_input_tokens, cost_usd, "
        "run_id, channel, provenance, host, provider_vendor, scope_kind, observed_at, "
        "observed_at_basis, host_basis, usage_contract, source_raw_event_id, "
        "source_path, source_line_no, observation_key) "
        "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'transcript', ?, ?, ?, 'request', "
        "?, ?, ?, ?, ?, ?, ?, ?)",
        (
            replay.ts,
            observation.session_id,
            observation.model,
            None,
            components[0],
            components[1],
            components[2],
            components[3],
            cost,
            ctx.run_id_for(replay.ts),
            "measured" if qualified else "unknown",
            replay.host,
            vendor_for_runner(replay.host) if replay.host else None,
            replay.ts or None,
            "event" if replay.ts else None,
            replay.host_basis,
            replay.usage_contract if qualified else None,
            replay.raw_event_id,
            replay.source_label,
            replay.line_no,
            key,
        ),
    )
    ctx.scope.mark(replay.source_label)
    ctx.report.inserted += 1
    return int(cursor.lastrowid or 0)


def _invalidate_dependents(ctx: _Ctx, row: Committed) -> None:
    """Completion that consumed *row* is stale once its value or qualification changes."""
    invalidate_usage_dependencies(
        ctx.conn, (row.id,), (), reason="reconcile", preserve_witness_ids=(row.id,)
    )


def _replace_claude(ctx: _Ctx, t: ClaudeTarget, row: Committed) -> None:
    _invalidate_dependents(ctx, row)
    replay, observation = t.replay, t.observation
    usage = observation.usage
    components = (
        usage.get("input_tokens"),
        usage.get("output_tokens"),
        usage.get("cache_read_input_tokens"),
        usage.get("cache_creation_input_tokens"),
    )
    cost = _price(replay.ts, observation.model, components)
    if (row.source_path, row.model, row.ts) != (replay.source_label, observation.model, replay.ts):
        ctx.scope.mark(row.source_path, replay.source_label)
    ctx.conn.execute(
        "UPDATE usage_events SET ts = ?, model = ?, input_tokens = ?, output_tokens = ?, "
        "cache_read_input_tokens = ?, cache_creation_input_tokens = ?, cost_usd = ?, "
        "run_id = ?, observed_at = ?, observed_at_basis = ?, source_raw_event_id = ?, "
        "source_path = ?, source_line_no = ?, provenance = ?, usage_contract = ? WHERE id = ?",
        (
            replay.ts,
            observation.model,
            components[0],
            components[1],
            components[2],
            components[3],
            cost,
            ctx.run_id_for(replay.ts),
            replay.ts or None,
            "event" if replay.ts else None,
            replay.raw_event_id,
            replay.source_label,
            replay.line_no,
            "measured",
            replay.usage_contract,
            row.id,
        ),
    )
    ctx.report.replaced += 1


def _supplier(
    ctx: _Ctx,
    source: str,
    host: str | None,
    session: str | None,
    line_no: int | None,
    ordinal: int | None,
    raw_id: int | None,
) -> dict[str, Any] | None:
    """Supplier fields of a witness, or ``None`` without a tracked head (no authority)."""
    head = ctx.head(source)
    if head is None or not storage_available(ctx.conn):
        return None
    return {
        "supplier_source_path": source,
        "supplier_host": host,
        "supplier_session_id": session,
        "supplier_generation_id": head.scope.generation_id,
        "supplier_derive_version": head.scope.derive_version,
        "supplier_line_no": line_no,
        "supplier_ordinal": ordinal,
        "supplier_raw_id": raw_id,
    }


def _witness_claude(ctx: _Ctx, usage_id: int, t: ClaudeTarget) -> None:
    """Record the actual supplier of a Claude observation (its qualification is self-contained)."""
    replay = t.replay
    supplier = _supplier(
        ctx,
        t.source,
        replay.host,
        t.observation.session_id,
        replay.line_no,
        replay.ordinal,
        replay.raw_event_id,
    )
    if supplier is None:
        return
    write_observation_witness(
        ctx.conn,
        ObservationWitness(
            usage_id,
            "known",
            "not_consumed" if t.observation.qualified else "unavailable",
            **supplier,
        ),
    )


def _codex_frontier(ctx: _Ctx, t: CodexTarget) -> tuple[QualificationDependency, ...] | None:
    """The model and closure rows a measured request actually consumed (None = incomplete)."""
    head = ctx.head(t.source)
    cand = t.cand
    if head is None or head.acquired_line_no is None:
        return None
    deps = []
    for role, position in (("model", cand.model_ctx), ("closure", t.closure_ctx)):
        if position is None or position[0] is None or position[0] < 1:
            return None
        if position[0] > head.acquired_line_no:
            return None  # context past the acquired range proves nothing under this authority
        deps.append(
            QualificationDependency(
                role=role,
                source_path=t.source,
                generation_id=head.scope.generation_id,
                derive_version=head.scope.derive_version,
                line_no=position[0],
                host=cand.record.host,
                session_id=cand.thread_id,
                ordinal=position[1],
                raw_event_id=position[2],
            )
        )
    return tuple(deps)


def _witness_codex(ctx: _Ctx, usage_id: int, t: CodexTarget) -> None:
    replay = t.cand.record
    supplier = _supplier(
        ctx,
        t.source,
        replay.host,
        t.cand.thread_id,
        replay.line_no,
        replay.ordinal,
        replay.raw_event_id,
    )
    if supplier is None:
        return
    frontier = _codex_frontier(ctx, t) if t.measured else None
    write_observation_witness(
        ctx.conn,
        ObservationWitness(
            usage_id,
            "known",
            "known" if frontier is not None else "unavailable",
            qualification_dependencies=frontier or (),
            **supplier,
        ),
    )


def _requalify_witness(ctx: _Ctx, row: Committed, t: CodexTarget) -> None:
    """Context-only qualification: change the consumed frontier, never the value supplier."""
    if not storage_available(ctx.conn):
        return
    current = read_observation_witness(ctx.conn, row.id)
    frontier = _codex_frontier(ctx, t)
    if current.value_status != "known" or frontier is None:
        return
    write_observation_witness(
        ctx.conn,
        ObservationWitness(
            row.id,
            "known",
            "known",
            current.supplier_source_path,
            current.supplier_host,
            current.supplier_session_id,
            current.supplier_generation_id,
            current.supplier_derive_version,
            current.supplier_line_no,
            current.supplier_ordinal,
            current.supplier_raw_id,
            frontier,
        ),
    )


def _clear_witness(ctx: _Ctx, usage_id: int) -> None:
    """A changed value without acquired authority leaves no witness rather than a stale one."""
    if not storage_available(ctx.conn):
        return
    for table in ("usage_observation_dependencies", "usage_observation_witnesses"):
        ctx.conn.execute(f"DELETE FROM {table} WHERE usage_event_id = ?", (usage_id,))


def _qualify_claude(ctx: _Ctx, t: ClaudeTarget, row: Committed, *, priced: bool) -> None:
    """Original-source recovery: certify a linked audit row's qualification and key only."""
    replay, observation = t.replay, t.observation
    usage = observation.usage
    components = (
        usage.get("input_tokens"),
        usage.get("output_tokens"),
        usage.get("cache_read_input_tokens"),
        usage.get("cache_creation_input_tokens"),
    )
    _invalidate_dependents(ctx, row)
    cost = _price(replay.ts, observation.model, components) if priced else None
    ctx.conn.execute(
        "UPDATE usage_events SET provenance = 'measured', usage_contract = ?, "
        "observation_key = ?, cost_usd = COALESCE(cost_usd, ?) WHERE id = ?",
        (replay.usage_contract, observation.observation_key, cost, row.id),
    )
    ctx.report.qualified += 1


def _demote(ctx: _Ctx, rows: tuple[Committed, ...], roles: frozenset[str]) -> None:
    """Conservative qualification invalidation: provenance only; everything else survives."""
    if not rows:
        return
    invalidate_usage_dependencies(
        ctx.conn, (), (), reason="native_conflict", contradicted={row.id: roles for row in rows}
    )
    for row in rows:
        ctx.conn.execute(
            "UPDATE usage_events SET provenance = 'unknown', usage_contract = NULL WHERE id = ?",
            (row.id,),
        )
        ctx.demoted.add(row.id)
        ctx.report.demoted += 1
        ctx.report.note(
            row.source_path,
            row.source_raw_event_id,
            _CONFLICT_REASON,
            kind="native_conflict",
            affected=(row.id,),
        )


_CODEX_COLUMNS = (
    "ts",
    "session_id",
    "model",
    "state",
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "cost_usd",
    "run_id",
    "channel",
    "provenance",
    "host",
    "provider_vendor",
    "scope_kind",
    "observed_at",
    "observed_at_basis",
    "host_basis",
    "identity_basis",
    "turn_id",
    "request_id",
    "request_identity_basis",
    "stream_id",
    "source_ordinal",
    "source_line_no",
    "source_raw_event_id",
    "source_path",
)
_CODEX_INSERT = (
    f"INSERT INTO usage_events({', '.join(_CODEX_COLUMNS)}) "
    f"VALUES({', '.join('?' for _ in _CODEX_COLUMNS)})"
)


def _insert_codex(ctx: _Ctx, t: CodexTarget, *, priced: bool, measured: bool) -> int:
    """Insert one Codex request row; return its new row id."""
    from little_loops.observability.tracing import vendor_for_runner

    cand = t.cand
    replay = cand.record
    cost = (
        _price(replay.ts, cand.model, t.components) if priced and measured and cand.model else None
    )
    cursor = ctx.conn.execute(
        _CODEX_INSERT,
        (
            replay.ts,
            cand.thread_id,
            cand.model,
            None,
            t.components[0],
            t.components[1],
            t.components[2],
            t.components[3],
            cost,
            None,
            "rollout",
            "measured" if measured else "unknown",
            "codex" if t.verified_host else None,
            vendor_for_runner("codex") if t.verified_host else None,
            "request",
            replay.ts or None,
            "event" if replay.ts else None,
            replay.host_basis if t.verified_host else None,
            "host_observed" if t.verified_thread else None,
            cand.turn_id,
            cand.request_id,
            cand.request_identity_basis if t.verified_host else "unverified",
            cand.stream_id,
            replay.ordinal,
            replay.line_no,
            replay.raw_event_id,
            replay.source_label,
        ),
    )
    ctx.report.inserted += 1
    return int(cursor.lastrowid or 0)


def _qualify_codex(ctx: _Ctx, t: CodexTarget, row: Committed, *, priced: bool) -> None:
    """Context-only requalification: provenance, consumed model and a first price only."""
    cand = t.cand
    _invalidate_dependents(ctx, row)
    cost = _price(cand.record.ts, cand.model, t.components) if priced and cand.model else None
    ctx.conn.execute(
        "UPDATE usage_events SET provenance = 'measured', model = COALESCE(model, ?), "
        "cost_usd = COALESCE(cost_usd, ?), identity_basis = COALESCE(identity_basis, "
        "'host_observed') WHERE id = ?",
        (cand.model, cost, row.id),
    )
    ctx.report.qualified += 1


def execute(ctx: _Ctx, planned: list[Planned]) -> int:
    """Execute the permitted actions in replay order; return newly inserted rows.

    Each write action carries the witness effect the policy table names, applied in the same
    transaction: a witness is recorded only where a verified acquisition covers the request,
    an unchanged row keeps its witnesses untouched, and a changed value without acquired
    authority drops the stale witness instead of leaving a false one.
    """
    count = 0
    for p in sorted(planned, key=lambda item: item.index):
        action = p.plan.action
        if action in {Action.NOOP, Action.PRESERVE_PENDING, Action.REFUSE}:
            continue
        witness = p.plan.witness
        if p.kind == "claude":
            t: ClaudeTarget = p.target
            if action in {Action.INSERT, Action.INSERT_AUDIT}:
                usage_id = _insert_claude(ctx, t, priced=p.plan.prices, audit_copy=False)
                if witness is Witness.SUPPLIER_CONTEXT:
                    _witness_claude(ctx, usage_id, t)
                count += 1
            elif action is Action.REPLACE:
                assert p.committed is not None
                _replace_claude(ctx, t, p.committed)
                if witness is Witness.REPLACE:
                    _witness_claude(ctx, p.committed.id, t)
                elif witness is Witness.CLEAR:
                    _clear_witness(ctx, p.committed.id)
            elif action is Action.QUALIFY:
                assert p.committed is not None
                _qualify_claude(ctx, t, p.committed, priced=p.plan.prices)
                if witness is Witness.CONTEXT and ctx.acquired(t.source, t.replay.line_no):
                    # Same supplier (exact raw link): record the qualification it now
                    # consumed -- self-contained, so an empty frontier -- under acquired authority.
                    _witness_claude(ctx, p.committed.id, t)
            elif action is Action.INVALIDATE_CONFLICT:
                _demote(ctx, p.demote, p.roles)
                if p.copy_needed:
                    _insert_claude(ctx, t, priced=False, audit_copy=True)
                    count += 1
                    ctx.report.note(t.source, t.raw_id, _CONFLICT_REASON, kind="native_conflict")
            continue
        ct: CodexTarget = p.target
        if action in {Action.INSERT, Action.INSERT_AUDIT}:
            usage_id = _insert_codex(ctx, ct, priced=p.plan.prices, measured=ct.measured)
            if witness is Witness.SUPPLIER_CONTEXT:
                _witness_codex(ctx, usage_id, ct)
            count += 1
        elif action is Action.QUALIFY:
            assert p.committed is not None
            _qualify_codex(ctx, ct, p.committed, priced=p.plan.prices)
            if witness is Witness.CONTEXT:
                _requalify_witness(ctx, p.committed, ct)
        elif action is Action.INVALIDATE_CONFLICT:
            _demote(ctx, p.demote, p.roles)
            if p.copy_needed:
                _insert_codex(ctx, ct, priced=False, measured=False)
                count += 1
                ctx.report.note(ct.source, ct.raw_id, _CONFLICT_REASON, kind="native_conflict")
    return count


def apply_replay(
    conn: sqlite3.Connection,
    claude_targets: list[ClaudeTarget],
    codex_candidates: list[_CodexCandidate],
    codex_states: dict[str, _CodexReplayState],
    *,
    holds: UsageReplayHolds,
    scope: UsageSearchScope,
    run_id_for: Callable[[str], str | None],
    report: ReplayReport | None = None,
    plan_out: list[Planned] | None = None,
) -> int:
    """Plan every collected request against committed observations, then execute the plan.

    With *plan_out* the planned actions are returned there and nothing is executed.
    """
    report = report if report is not None else ReplayReport()
    ctx = _Ctx(conn, holds, scope, report, run_id_for)
    planned = plan_claude(ctx, claude_targets)
    planned.extend(plan_codex(ctx, codex_candidates, codex_states, len(claude_targets)))
    if plan_out is not None:
        plan_out.extend(planned)
        return 0
    return execute(ctx, planned)


# -- Hold release -------------------------------------------------------------

_UNCHANGED_REASONS = frozenset({"unchanged", "superseded_snapshot", "identical_copy"})


def _target_qualified(planned: Planned) -> bool:
    target = planned.target
    return bool(target.observation.qualified if planned.kind == "claude" else target.measured)


def _hold_releasable(conn: sqlite3.Connection, source: str) -> bool:
    """Whether every observation the exact-source hold covers is reconstructible.

    The inventory is the committed population selected by the hold's own predicate
    (``source_path``; host and channel labels are ignored, so mixed rows are included), not
    the retained-candidate query: an observation whose raw evidence is gone is unmatched
    and keeps the hold. Release also needs a clean post-write retained proof, a plan in
    which every retained request is an unchanged, equally qualified representation of its
    committed row, and no unresolved obligation or conflict of any generation.
    """
    from little_loops.session_store.usage_proof import retention_reasons
    from little_loops.session_store.usage_proof_scope import (
        UsageProofLimit,
        UsageProofUnavailable,
        inspect_retained_source,
    )
    from little_loops.session_store.usage_source_state import pending_obligations
    from little_loops.session_store.writers import _backfill_usage_events

    if not storage_available(conn) or pending_obligations(conn, source):
        return False
    inventory = {
        row[0]: row[1:]
        for row in conn.execute(
            "SELECT id, observation_key, provenance FROM usage_events "
            "WHERE source_path = ? AND channel IS NOT 'live'",
            (source,),
        )
    }
    if any(key is not None and prov != "measured" for key, prov in inventory.values()):
        return False  # a demoted (conflict) row blocks release
    try:
        proofs = inspect_retained_source(conn, source)
    except (UsageProofLimit, UsageProofUnavailable):
        return False
    if retention_reasons(proofs):
        return False
    plans: list[Planned] = []
    cursor = conn.execute(
        "SELECT raw_line, source_path, host, host_basis, event_type, ts, session_id, line_no, "
        "ordinal, usage_contract, id FROM raw_events WHERE source_path = ? "
        "ORDER BY source_path, COALESCE(ordinal, line_no), line_no, id",
        (source,),
    )
    _backfill_usage_events(conn, cursor, plan_out=plans)
    matched: set[int] = set()
    for planned in plans:
        action = planned.plan
        if action.action is not Action.NOOP or action.reason not in _UNCHANGED_REASONS:
            return False
        committed = planned.committed
        if committed is None:
            continue
        if committed.qualified != _target_qualified(planned):
            return False
        if committed.source_path == source:
            matched.add(committed.id)
    return set(inventory) <= matched


def release_safe_holds(conn: sqlite3.Connection, sources: Iterable[str]) -> list[str]:
    """Delete the exact-source holds proved safe to lift; return the released sources.

    Runs in the caller's transaction. A NULL-source wildcard/population hold and every other
    source's protection are never touched.
    """
    released: list[str] = []
    for source in sorted(set(sources)):
        held = conn.execute(
            "SELECT 1 FROM usage_replay_holds WHERE source_path = ?", (source,)
        ).fetchone()
        if held is None or not _hold_releasable(conn, source):
            continue
        conn.execute("DELETE FROM usage_replay_holds WHERE source_path = ?", (source,))
        released.append(source)
    return released
