"""Dependency graph and bounded downstream leverage for the ``ll-next`` arena.

``DependencyGraph.from_issues`` ignores status and silently overwrites duplicate IDs, so
the arena builds its own light structure over **unique** node IDs:

* ``blocked_by`` / ``depends_on`` / ``blocks`` adjacency (one-sided ``blocks`` declarations
  are folded into ``blocked_by`` of the named target),
* per-node ``unresolved`` prerequisite evidence, where an edge is satisfied **only** by a
  known, unique ``done``/``cancelled`` issue (unknown IDs, ambiguous IDs, nonterminal and
  invalid-status prerequisites fail closed), and
* dependency-cycle diagnostics.

``downstream_leverage`` counts distinct downstream ``open``/``blocked`` non-EPIC issues with
an SCC-condensed DAG and constant-size (``cap + 1``) capped summaries computed with an
iterative Tarjan pass, so total work is linear in nodes + edges for a fixed cap. All work is
reported through an optional :class:`OpCounter` so performance checks can assert on
operation counts instead of wall-clock time.
"""

from __future__ import annotations

import heapq
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Protocol

from little_loops.next_arena.inputs import Diagnostic

if TYPE_CHECKING:
    from little_loops.next_arena.state import ProjectState, UnsupportedRelationship

#: Statuses that resolve a prerequisite edge.
TERMINAL_STATUSES: frozenset[str] = frozenset({"done", "cancelled"})
#: Statuses counted as downstream work by leverage.
LEVERAGE_COUNTED_STATUSES: frozenset[str] = frozenset({"open", "blocked"})
#: Default saturation cap for leverage (``count_lower_bound``).
DEFAULT_LEVERAGE_CAP = 10

# Prerequisite resolution reasons.
REASON_UNKNOWN = "unknown_issue"
REASON_AMBIGUOUS = "ambiguous_issue_id"
REASON_NOT_TERMINAL = "not_terminal"
REASON_INVALID_STATUS = "invalid_status"
REASON_UNANCHORED = "unanchored_source"
REASON_UNSUPPORTED_SHAPE = "unsupported_relationship_shape"

#: Diagnostic code for a live source declaring a mapping-valued relationship field.
UNSUPPORTED_SHAPE_CODE = "unsupported_dependency_shape"
#: At most this many characters of a captured raw mapping appear in any output.
UNSUPPORTED_RAW_EXCERPT_LIMIT = 512
#: Appended to human text when a raw excerpt was cut.
TRUNCATION_MARKER = "... [truncated]"


def raw_excerpt(raw: str) -> tuple[str, bool]:
    """The bounded excerpt of a captured raw mapping and whether it was truncated."""
    if len(raw) <= UNSUPPORTED_RAW_EXCERPT_LIMIT:
        return raw, False
    return raw[:UNSUPPORTED_RAW_EXCERPT_LIMIT], True


@dataclass
class OpCounter:
    """Mutable operation tally threaded through graph work (edge visits, merge elements)."""

    operations: int = 0

    def tick(self, amount: int = 1) -> None:
        """Add *amount* operations."""
        self.operations += amount


class GraphRecord(Protocol):
    """The slice of ``SourceRecord`` the graph builder reads."""

    @property
    def rel_path(self) -> str: ...

    @property
    def lifecycle_status(self) -> str: ...

    @property
    def blocked_by(self) -> tuple[str, ...]: ...

    @property
    def blocks(self) -> tuple[str, ...]: ...

    @property
    def depends_on(self) -> tuple[str, ...]: ...

    @property
    def issue_type(self) -> str | None: ...

    @property
    def unsupported_relationships(self) -> tuple[UnsupportedRelationship, ...]: ...


@dataclass(frozen=True)
class Prerequisite:
    """One unresolved prerequisite of a target.

    ``kind`` is ``blocked_by``, ``blocks`` (declared one-sided by the prerequisite) or
    ``depends_on``. ``prerequisite_id`` is ``None`` for an unanchored (numberless or
    colliding-inference) source that declared ``blocks`` on the target, and for unsupported
    input (``reason == REASON_UNSUPPORTED_SHAPE``: a mapping-valued field whose ``kind`` and
    declaring ``source_paths`` name where it came from).
    """

    kind: str
    prerequisite_id: str | None
    reason: str
    status: str | None
    source_paths: tuple[str, ...]


def _sorted_tuple(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


def _freeze_adjacency(adj: Mapping[str, Iterable[str]]) -> Mapping[str, tuple[str, ...]]:
    return MappingProxyType({k: _sorted_tuple(v) for k, v in sorted(adj.items())})


# ------------------------------------------------------------------------ iterative Tarjan


def tarjan_sccs(
    nodes: Sequence[str],
    successors: Mapping[str, Sequence[str]],
    counter: OpCounter | None = None,
) -> list[tuple[str, ...]]:
    """Strongly connected components via an iterative (non-recursive) Tarjan pass.

    Components are returned in reverse topological order of the edge direction: a
    component appears only after every component reachable from it. Each member tuple is
    sorted. *successors* must only reference IDs present in *nodes*.
    """
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    result: list[tuple[str, ...]] = []

    for root in nodes:
        if root in index:
            continue
        index[root] = low[root] = len(index)
        stack.append(root)
        on_stack.add(root)
        work: list[tuple[str, Any]] = [(root, iter(successors.get(root, ())))]
        while work:
            node, it = work[-1]
            descended = False
            for nxt in it:
                if counter is not None:
                    counter.tick()
                if nxt not in index:
                    index[nxt] = low[nxt] = len(index)
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, iter(successors.get(nxt, ()))))
                    descended = True
                    break
                if nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
            if descended:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                members: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    members.append(member)
                    if member == node:
                        break
                result.append(tuple(sorted(members)))
    return result


# ------------------------------------------------------------------------------ graph


@dataclass(frozen=True)
class IssueGraph:
    """Dependency structure over unique issue IDs plus fail-closed prerequisite evidence.

    ``node_status`` holds the resolved lifecycle status of every **unique** node;
    ``ambiguous`` lists IDs with more than one source (their edges are the union of every
    conflicting source and are never trusted as satisfied). ``unresolved[id]`` is present
    only for nodes with at least one unresolved prerequisite.
    """

    node_status: Mapping[str, str]
    node_types: Mapping[str, str | None]
    ambiguous: frozenset[str]
    node_paths: Mapping[str, tuple[str, ...]]
    blocked_by: Mapping[str, tuple[str, ...]]
    blocks: Mapping[str, tuple[str, ...]]
    depends_on: Mapping[str, tuple[str, ...]]
    unresolved: Mapping[str, tuple[Prerequisite, ...]]
    cycles: tuple[tuple[str, ...], ...]
    cyclic_ids: frozenset[str]
    anonymous_blockers: Mapping[str, tuple[str, ...]]
    dangling_blocks: Mapping[str, tuple[str, ...]]
    diagnostics: tuple[Diagnostic, ...]
    _dependents: Mapping[str, tuple[str, ...]] = field(
        repr=False, compare=False, default_factory=dict
    )
    _leverage_cache: dict[int, LeverageIndex] = field(
        repr=False, compare=False, default_factory=dict
    )

    def prerequisites_satisfied(self, issue_id: str) -> bool:
        """True when *issue_id* has no unresolved prerequisite (unknown nodes are False)."""
        return (
            issue_id in self.node_status
            and issue_id not in self.ambiguous
            and issue_id not in self.unresolved
        )

    def unresolved_for(self, issue_id: str) -> tuple[Prerequisite, ...]:
        """Unresolved prerequisites of *issue_id* (empty when satisfied or unknown)."""
        return self.unresolved.get(issue_id, ())

    def leverage_index(
        self, cap: int = DEFAULT_LEVERAGE_CAP, counter: OpCounter | None = None
    ) -> LeverageIndex:
        """Return the (cached) :class:`LeverageIndex` for *cap*, building it on first use."""
        cached = self._leverage_cache.get(cap)
        if cached is None:
            cached = build_leverage_index(self, cap, counter=counter)
            self._leverage_cache[cap] = cached
        return cached


def build_issue_graph(
    records: Sequence[GraphRecord],
    node_ids: Mapping[str, str],
    ambiguous: Collection[str],
    *,
    counter: OpCounter | None = None,
) -> IssueGraph:
    """Build the graph from collected records.

    Args:
        records: Every collected source (all statuses).
        node_ids: ``rel_path -> node ID`` for sources that own a graph node. Sources absent
            here are anonymous (numberless or colliding inferred names).
        ambiguous: Node IDs with more than one source (identity inventory result).
        counter: Optional operation tally.
    """
    tick = counter.tick if counter is not None else (lambda n=1: None)
    ambiguous_set = frozenset(ambiguous)

    paths_by_node: dict[str, list[str]] = {}
    status_by_node: dict[str, str] = {}
    type_by_node: dict[str, str | None] = {}
    declared_by: dict[str, set[str]] = {}
    declared_blocks: dict[str, set[str]] = {}
    declared_depends: dict[str, set[str]] = {}
    anonymous: dict[str, list[str]] = {}
    anonymous_status: dict[str, str] = {}
    # Live unsupported-shape facts: (source node or None, record, fact).
    shape_facts: list[tuple[str | None, GraphRecord, UnsupportedRelationship]] = []

    for rec in records:
        tick()
        node = node_ids.get(rec.rel_path)
        # Identity-aware live predicate: an ambiguous named record is live whatever its
        # lifecycle; any other record is live only when non-terminal.
        live = node in ambiguous_set or rec.lifecycle_status not in TERMINAL_STATUSES
        if live:
            for fact in rec.unsupported_relationships:
                tick(len(fact.keys) or 1)
                shape_facts.append((node, rec, fact))
        if node is None:
            # Numberless / colliding source: prerequisite evidence on named targets only.
            if rec.lifecycle_status not in TERMINAL_STATUSES:
                for target in rec.blocks:
                    tick()
                    anonymous.setdefault(target, []).append(rec.rel_path)
                    anonymous_status[rec.rel_path] = rec.lifecycle_status
            continue
        paths_by_node.setdefault(node, []).append(rec.rel_path)
        if node not in ambiguous_set:
            status_by_node[node] = rec.lifecycle_status
            type_by_node[node] = rec.issue_type
        declared_by.setdefault(node, set()).update(rec.blocked_by)
        declared_blocks.setdefault(node, set()).update(rec.blocks)
        declared_depends.setdefault(node, set()).update(rec.depends_on)
        tick(len(rec.blocked_by) + len(rec.blocks) + len(rec.depends_on))

    known = set(paths_by_node)  # unique + ambiguous node IDs

    hard: dict[str, dict[str, str]] = {n: {} for n in known}  # target -> prereq -> kind
    for node in known:
        for prereq in declared_by.get(node, ()):
            hard[node][prereq] = "blocked_by"
    dangling: dict[str, set[str]] = {}
    for node in known:
        for target in declared_blocks.get(node, ()):
            tick()
            if target in known:
                hard[target].setdefault(node, "blocks")
            else:
                dangling.setdefault(node, set()).add(target)

    soft: dict[str, set[str]] = {n: set(declared_depends.get(n, ())) for n in known}

    blocked_by_adj = {n: set(p) for n, p in hard.items()}
    blocks_adj: dict[str, set[str]] = {n: set() for n in known}
    dependents: dict[str, set[str]] = {}
    for node in known:
        for prereq in hard[node]:
            tick()
            if prereq in known:
                blocks_adj[prereq].add(node)
            dependents.setdefault(prereq, set()).add(node)
        for prereq in soft[node]:
            tick()
            dependents.setdefault(prereq, set()).add(node)
    for node, targets in dangling.items():
        for target in targets:
            dependents.setdefault(node, set()).add(target)

    def _resolve(prereq: str, kind: str) -> Prerequisite | None:
        if prereq in ambiguous_set:
            return Prerequisite(
                kind, prereq, REASON_AMBIGUOUS, None, _sorted_tuple(paths_by_node[prereq])
            )
        status = status_by_node.get(prereq)
        if status is None:
            return Prerequisite(kind, prereq, REASON_UNKNOWN, None, ())
        if status in TERMINAL_STATUSES:
            return None
        reason = REASON_INVALID_STATUS if status == "invalid" else REASON_NOT_TERMINAL
        return Prerequisite(kind, prereq, reason, status, _sorted_tuple(paths_by_node[prereq]))

    # Unsupported mapping input never becomes an edge: own-field facts fail the declaring
    # node closed; a ``blocks`` mapping fails every existing target named by an exact key.
    unsupported_for: dict[str, dict[tuple[str, str], Prerequisite]] = {}
    shape_diagnostics: list[Diagnostic] = []
    for src_node, rec, fact in shape_facts:
        entry = Prerequisite(
            fact.field, None, REASON_UNSUPPORTED_SHAPE, rec.lifecycle_status, (rec.rel_path,)
        )
        if fact.field == "blocks":
            for key in fact.keys:
                if key in known and key != src_node:
                    unsupported_for.setdefault(key, {})[(rec.rel_path, fact.field)] = entry
        elif src_node is not None:
            unsupported_for.setdefault(src_node, {})[(rec.rel_path, fact.field)] = entry
        excerpt, truncated = raw_excerpt(fact.raw)
        shown = excerpt + (TRUNCATION_MARKER if truncated else "")
        shape_diagnostics.append(
            Diagnostic(
                UNSUPPORTED_SHAPE_CODE,
                f"{rec.rel_path}: {fact.field} is a mapping, not a list of IDs "
                f"(unsupported input, offers it affects are excluded): {shown}",
                (rec.rel_path,),
                src_node,
            )
        )

    unresolved: dict[str, list[Prerequisite]] = {}
    for node in sorted(known):
        found: list[Prerequisite] = []
        for prereq in sorted(hard[node]):
            tick()
            item = _resolve(prereq, hard[node][prereq])
            if item is not None:
                found.append(item)
        for prereq in sorted(soft[node]):
            tick()
            item = _resolve(prereq, "depends_on")
            if item is not None:
                found.append(item)
        for path in sorted(set(anonymous.get(node, ()))):
            found.append(
                Prerequisite("blocks", None, REASON_UNANCHORED, anonymous_status[path], (path,))
            )
        found.extend(
            unsupported_for.get(node, {})[k] for k in sorted(unsupported_for.get(node, {}))
        )
        if found:
            unresolved[node] = found

    # Cycle detection over the waits-on relation among non-terminal nodes (ambiguous kept).
    active = sorted(
        n for n in known if n in ambiguous_set or status_by_node.get(n) not in TERMINAL_STATUSES
    )
    active_set = set(active)
    waits_on = {n: sorted((set(hard[n]) | soft[n]) & active_set) for n in active}
    cycles: list[tuple[str, ...]] = []
    for comp in tarjan_sccs(active, waits_on, counter):
        if len(comp) > 1 or comp[0] in waits_on[comp[0]]:
            cycles.append(comp)
    cycles.sort()
    cyclic_ids = frozenset(n for comp in cycles for n in comp)

    diagnostics = tuple(
        Diagnostic(
            code="dependency_cycle",
            message="dependency cycle among " + ", ".join(comp),
            paths=_sorted_tuple(p for n in comp for p in paths_by_node[n]),
            subject=comp[0],
        )
        for comp in cycles
    ) + tuple(shape_diagnostics)

    return IssueGraph(
        node_status=MappingProxyType(dict(sorted(status_by_node.items()))),
        node_types=MappingProxyType(dict(sorted(type_by_node.items()))),
        ambiguous=ambiguous_set & known,
        node_paths=MappingProxyType(
            {n: _sorted_tuple(p) for n, p in sorted(paths_by_node.items())}
        ),
        blocked_by=_freeze_adjacency(blocked_by_adj),
        blocks=_freeze_adjacency(blocks_adj),
        depends_on=_freeze_adjacency(soft),
        unresolved=MappingProxyType({n: tuple(v) for n, v in unresolved.items()}),
        cycles=tuple(cycles),
        cyclic_ids=cyclic_ids,
        anonymous_blockers=_freeze_adjacency(anonymous),
        dangling_blocks=_freeze_adjacency(dangling),
        diagnostics=diagnostics,
        _dependents=_freeze_adjacency(dependents),
    )


# --------------------------------------------------------------------------- leverage


@dataclass(frozen=True)
class Leverage:
    """Downstream fan-out evidence for one issue.

    ``status`` is ``exact`` (``count`` is the exact distinct count, ``0`` valid),
    ``saturated`` (``count`` is ``None``; ``count_lower_bound == cap`` and ``sample`` holds
    up to ``cap`` IDs) or ``missing`` (``missing_reason`` explains; ``partial_count`` is the
    number of dependents already proven). Cycle, dangling-target and ambiguous-node
    evidence is reported separately and never folded into the count.
    """

    issue_id: str
    status: str
    cap: int
    count: int | None
    count_lower_bound: int | None
    saturated: bool
    sample: tuple[str, ...]
    missing_reason: str | None
    partial_count: int
    in_cycle: bool
    cycle_ids: tuple[str, ...]
    missing_ids: tuple[str, ...]
    ambiguous_ids: tuple[str, ...]


@dataclass(frozen=True)
class _Component:
    ids: tuple[str, ...]
    ambiguous: tuple[str, ...]
    missing: tuple[str, ...]
    cyclic_ids: tuple[str, ...]
    cyclic: bool


def _smallest(parts: Iterable[Sequence[str]], k: int, counter: OpCounter | None) -> tuple[str, ...]:
    """The *k* smallest distinct values of the union of *parts* (composable under capping)."""
    merged: set[str] = set()
    for part in parts:
        merged.update(part)
        if counter is not None:
            counter.tick(len(part) or 1)
    return tuple(heapq.nsmallest(k, merged))


@dataclass(frozen=True)
class LeverageIndex:
    """Per-SCC capped downstream summaries; queries are O(cap)."""

    cap: int
    node_status: Mapping[str, str]
    ambiguous: frozenset[str]
    comp_of: Mapping[str, int]
    components: tuple[_Component, ...]

    def query(self, issue_id: str, counter: OpCounter | None = None) -> Leverage:
        """Leverage for *issue_id* (see :class:`Leverage`)."""
        cap = self.cap
        if counter is not None:
            counter.tick()

        def _missing(reason: str) -> Leverage:
            return Leverage(
                issue_id=issue_id,
                status="missing",
                cap=cap,
                count=None,
                count_lower_bound=None,
                saturated=False,
                sample=(),
                missing_reason=reason,
                partial_count=0,
                in_cycle=False,
                cycle_ids=(),
                missing_ids=(),
                ambiguous_ids=(),
            )

        if issue_id in self.ambiguous:
            return _missing(REASON_AMBIGUOUS)
        if issue_id not in self.node_status:
            return _missing(REASON_UNKNOWN)
        comp_index = self.comp_of.get(issue_id)
        if comp_index is None:
            return _missing("terminal_source")

        comp = self.components[comp_index]
        ids = tuple(i for i in comp.ids if i != issue_id)
        in_cycle = comp.cyclic
        common: dict[str, Any] = {
            "issue_id": issue_id,
            "cap": cap,
            "in_cycle": in_cycle,
            "cycle_ids": comp.cyclic_ids,
            "missing_ids": comp.missing,
            "ambiguous_ids": comp.ambiguous,
        }
        if len(ids) >= cap:
            return Leverage(
                status="saturated",
                count=None,
                count_lower_bound=cap,
                saturated=True,
                sample=ids[:cap],
                missing_reason=None,
                partial_count=cap,
                **common,
            )
        if comp.ambiguous:
            return Leverage(
                status="missing",
                count=None,
                count_lower_bound=None,
                saturated=False,
                sample=ids,
                missing_reason="ambiguous_downstream",
                partial_count=len(ids),
                **common,
            )
        return Leverage(
            status="exact",
            count=len(ids),
            count_lower_bound=None,
            saturated=False,
            sample=ids,
            missing_reason=None,
            partial_count=len(ids),
            **common,
        )


def build_leverage_index(
    graph: IssueGraph, cap: int = DEFAULT_LEVERAGE_CAP, *, counter: OpCounter | None = None
) -> LeverageIndex:
    """Condense the downstream graph into SCCs and attach capped (``cap + 1``) summaries.

    Downstream edges run prerequisite -> dependent. Only nonterminal unique nodes are
    traversed; an ambiguous dependent is never expanded (it only flags the summary), and a
    dangling ``blocks`` target is reported as a missing ID.
    """
    if cap < 1:
        raise ValueError(f"cap must be >= 1 (got {cap})")
    k = cap + 1
    status = graph.node_status
    traversable = [n for n in status if status[n] not in TERMINAL_STATUSES]
    trav_set = set(traversable)

    succ: dict[str, list[str]] = {}
    local_amb: dict[str, list[str]] = {}
    local_missing: dict[str, list[str]] = {}
    for node in traversable:
        edges: list[str] = []
        amb: list[str] = []
        miss: list[str] = []
        for dep in graph._dependents.get(node, ()):
            if counter is not None:
                counter.tick()
            if dep in trav_set:
                edges.append(dep)
            elif dep in graph.ambiguous:
                amb.append(dep)
            elif dep not in status:
                miss.append(dep)
            # terminal dependents are not traversed
        succ[node] = edges
        local_amb[node] = amb
        local_missing[node] = miss

    sccs = tarjan_sccs(traversable, succ, counter)
    comp_of: dict[str, int] = {}
    for idx, members in enumerate(sccs):
        for member in members:
            comp_of[member] = idx

    def _counted(node: str) -> bool:
        return status[node] in LEVERAGE_COUNTED_STATUSES and graph.node_types.get(node) != "EPIC"

    counted_members: list[tuple[str, ...]] = []
    components: list[_Component] = []
    for idx, members in enumerate(sccs):
        counted_members.append(tuple(heapq.nsmallest(k, (m for m in members if _counted(m)))))
        children: set[int] = set()
        self_loop = False
        amb_parts: list[Sequence[str]] = []
        miss_parts: list[Sequence[str]] = []
        for member in members:
            for dep in succ[member]:
                if counter is not None:
                    counter.tick()
                child = comp_of[dep]
                if child == idx:
                    self_loop = self_loop or dep == member
                else:
                    children.add(child)
            amb_parts.append(local_amb[member])
            miss_parts.append(local_missing[member])
        cyclic = len(members) > 1 or self_loop
        ordered_children = sorted(children)
        id_parts: list[Sequence[str]] = []
        cyc_parts: list[Sequence[str]] = []
        if cyclic:
            id_parts.append(counted_members[idx])
            cyc_parts.append(members)
        for child in ordered_children:
            id_parts.append(counted_members[child])
            id_parts.append(components[child].ids)
            amb_parts.append(components[child].ambiguous)
            miss_parts.append(components[child].missing)
            cyc_parts.append(components[child].cyclic_ids)
        components.append(
            _Component(
                ids=_smallest(id_parts, k, counter),
                ambiguous=_smallest(amb_parts, k, counter),
                missing=_smallest(miss_parts, k, counter),
                cyclic_ids=_smallest(cyc_parts, k, counter),
                cyclic=cyclic,
            )
        )

    return LeverageIndex(
        cap=cap,
        node_status=status,
        ambiguous=graph.ambiguous,
        comp_of=MappingProxyType(comp_of),
        components=tuple(components),
    )


def downstream_leverage(
    state: ProjectState,
    issue_id: str,
    cap: int = DEFAULT_LEVERAGE_CAP,
    *,
    counter: OpCounter | None = None,
) -> Leverage:
    """Distinct downstream ``open``/``blocked`` non-EPIC issues for *issue_id*.

    Counts through ``blocked_by``, one-sided ``blocks`` and ``depends_on`` edges, traversing
    only nonterminal nodes and excluding the source itself. Exact below *cap*; at *cap* or
    more it saturates (``count_lower_bound == cap``, ``saturated``, bounded sample). Zero
    dependents is a valid exact value. Fan-out that would have to cross an ambiguous node is
    ``missing`` unless saturation is already proven by unambiguous evidence.
    """
    index = state.graph.leverage_index(cap, counter)
    return index.query(issue_id, counter)
