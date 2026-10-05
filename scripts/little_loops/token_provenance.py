"""Token provenance aggregation and rendering (ENH-3528).

Pure helpers that turn streamed ``usage_events`` rows (see
:func:`little_loops.history_reader.usage.select_usage_observations`) into the
``token_provenance`` metadata contract: per-component known/missing counts,
provenance composition, verified source hosts, channel subtotals and the
live/transcript coverage policy. Provenance is read only from stored
observations -- never from the currently configured host or runtime
capabilities.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

TOKEN_COLUMNS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)
COST_COLUMN = "cost_usd"
AGGREGATE_COLUMNS = (*TOKEN_COLUMNS, COST_COLUMN)

#: Version of the qualification policy carried on every :class:`UsageQualification`
#: (ENH-3731). Bump together with the shared behavioral matrix whenever row
#: admission, provenance, figure prerequisites or reason precedence change;
#: coverage-policy and export-allowlist versions are separate.
USAGE_QUALIFICATION_POLICY_VERSION = 1

#: Bounded handoff vocabulary for figure qualification reasons (ENH-3731). Coverage
#: diagnostic prose never enters these codes; unknown reasons become ``unclassified``.
USAGE_QUALIFICATION_REASONS = frozenset(
    {
        "empty_selection",
        "coverage_overlap_unresolved",
        "coverage_unknown",
        "unclassified",
        "missing_token_component",
        "invalid_token_component",
        "unknown_provenance",
        "not_measured",
        "invalid_cost",
        "unpriced_contributor",
        "zero_denominator",
    }
)

#: Reserved model bucket for rows with a NULL model; no model ID can produce it.
UNKNOWN_MODEL_BUCKET = "(unknown model)"

_OVERLAP_REASON = (
    "live and transcript observations may cover the same work; unreconciled "
    "observation sum, may count the same work twice"
)


def escape_pointer_token(token: str) -> str:
    """Escape one RFC 6901 JSON Pointer reference token (``~`` then ``/``)."""
    return token.replace("~", "~0").replace("/", "~1")


def json_pointer(*tokens: str) -> str:
    """Build an RFC 6901 JSON Pointer from *tokens* (each escaped verbatim)."""
    return "".join("/" + escape_pointer_token(t) for t in tokens)


def resolve_pointer(document: Any, pointer: str) -> Any:
    """Resolve *pointer* against *document*; raises ``KeyError`` if it dangles."""
    node = document
    if pointer == "":
        return node
    for raw in pointer.split("/")[1:]:
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict):
            node = node[token]
        elif isinstance(node, list):
            node = node[int(token)]
        else:
            raise KeyError(pointer)
    return node


def _row_get(row: Mapping[str, Any] | Any, key: str) -> Any:
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def row_channel(row: Any) -> str:
    """Acquisition channel of *row*; legacy NULL is classified by ``session_id``."""
    channel = _row_get(row, "channel")
    if channel:
        return str(channel)
    return "transcript" if _row_get(row, "session_id") else "live"


def row_provenance(row: Any) -> str:
    """Row-level numeric provenance; NULL/unrecognised reads as ``unknown``."""
    value = _row_get(row, "provenance")
    return value if value in ("measured", "estimated") else "unknown"


def row_host_verified(row: Any) -> bool:
    """Whether *row*'s ``host`` is a verified source-host fact.

    Replay-derived rows (any non-``live`` channel) are verified only when
    ``host_basis='handle'`` (BUG-3542); live rows take the invocation host.
    """
    if not _row_get(row, "host"):
        return False
    if row_channel(row) == "live":
        return True
    return _row_get(row, "host_basis") == "handle"


def valid_token_value(value: Any) -> bool:
    """Whether *value* is an admissible stored token count (a non-negative ``int``)."""
    return type(value) is int and value >= 0


def valid_cost_value(value: Any) -> bool:
    """Whether *value* is an admissible stored cost (finite non-bool ``int``/``float`` >= 0)."""
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def _stable_sum(values: list[Any]) -> float | None:
    """Order-independent finite sum of *values*; ``None`` when it overflows."""
    try:
        total = math.fsum(values)
    except OverflowError:
        return None
    return total if math.isfinite(total) else None


@dataclass
class _Slot:
    count: int = 0
    int_total: int = 0
    values: list[Any] = field(default_factory=list)


@dataclass
class _Component:
    cost: bool = False
    known: int = 0
    missing: int = 0
    invalid: int = 0
    slots: dict[str, _Slot] = field(default_factory=dict)
    _final: tuple[Any, ...] | None = None

    @property
    def by_provenance(self) -> dict[str, dict[str, Any]]:
        return {
            k: {"count": v.count, "subtotal": self._slot_total(v)} for k, v in self.slots.items()
        }

    def add(self, value: Any, provenance: str) -> str:
        """Record *value*; returns ``missing`` | ``invalid`` | ``valid``."""
        slot = self.slots.setdefault(provenance, _Slot())
        if value is None:
            self.missing += 1
            return "missing"
        if not (valid_cost_value(value) if self.cost else valid_token_value(value)):
            self.invalid += 1
            return "invalid"
        self.known += 1
        slot.count += 1
        if self.cost:
            slot.values.append(value)
        else:
            slot.int_total += value
        self._final = None
        return "valid"

    def _slot_total(self, slot: _Slot) -> Any:
        if not self.cost:
            return slot.int_total
        return _stable_sum(slot.values) if slot.values else 0

    def total(self) -> Any:
        """Finalized sum of valid values; ``None`` without valid values or on overflow."""
        if not self.known:
            return None
        if self._final is None:
            if self.cost:
                self._final = (_stable_sum([v for s in self.slots.values() for v in s.values]),)
            else:
                self._final = (sum(s.int_total for s in self.slots.values()),)
        return self._final[0]

    def overflowed(self) -> bool:
        return bool(self.cost and self.known and self.total() is None)

    def counts(self, column: str) -> UsageComponentCounts:
        return UsageComponentCounts(column, self.known, self.missing, self.invalid)


@dataclass(frozen=True)
class UsageComponentCounts:
    """Valid/NULL/present-invalid observation counts of one column (ENH-3731)."""

    column: str
    known_count: int
    missing_count: int
    invalid_count: int


@dataclass(frozen=True)
class UsageQualification:
    """Result of :func:`qualify_usage`; ``eligible`` iff ``reason is None`` (ENH-3731)."""

    eligible: bool
    provenance: str
    reason: str | None
    contributors: int
    rejected_contributors: int
    component_counts: tuple[UsageComponentCounts, ...]
    policy_version: int

    def counts(self, column: str) -> UsageComponentCounts:
        for item in self.component_counts:
            if item.column == column:
                return item
        raise KeyError(column)


class ObservationGroup:
    """Accumulates ``usage_events`` rows for one aggregate and reports metadata."""

    def __init__(self) -> None:
        self.rows = 0
        self.components: dict[str, _Component] = {
            c: _Component(cost=(c == COST_COLUMN)) for c in AGGREGATE_COLUMNS
        }
        self.hosts: set[str] = set()
        self.unverified_host_rows = 0
        self.channels: dict[str, dict[str, Any]] = {}
        self.provenances: set[str] = set()
        self.scope_kinds: set[str] = set()
        self.session_ids: set[str] = set()
        self.invocation_ids: set[str] = set()
        self.observed: list[str] = []
        self.time_bases: set[str] = set()
        self._live_sessions: set[str] = set()
        self._transcript_sessions: set[str] = set()
        self._live_without_session = False
        self._coverage_labels: set[str] = set()
        self._coverage_reasons: set[str] = set()
        self._unannotated_rows = False
        # Per-row qualification counters (ENH-3731); a row is counted once per counter.
        self._rows_missing_token = 0
        self._rows_invalid_token = 0
        self._rows_unknown_provenance = 0
        self._rows_not_measured = 0
        self._rows_invalid_cost = 0
        self._rows_missing_cost = 0
        # Rejected rows keyed by (measured_only, require_cost).
        self._rejected = {(m, c): 0 for m in (False, True) for c in (False, True)}

    def add(self, row: Any) -> None:
        self.rows += 1
        provenance = row_provenance(row)
        channel = row_channel(row)
        coverage = _row_get(row, "_coverage")
        if coverage in ("non_overlapping", "overlap_unresolved", "unknown"):
            self._coverage_labels.add(coverage)
            reason = _row_get(row, "_coverage_reason")
            if reason:
                self._coverage_reasons.add(str(reason))
        else:
            self._unannotated_rows = True
        self.provenances.add(provenance)
        sub = self.channels.setdefault(channel, {"events": 0, **dict.fromkeys(TOKEN_COLUMNS, 0)})
        sub["events"] += 1
        states: dict[str, str] = {}
        for col in AGGREGATE_COLUMNS:
            value = _row_get(row, col)
            states[col] = self.components[col].add(value, provenance)
            if states[col] == "valid" and col in TOKEN_COLUMNS:
                sub[col] += value
        token_states = {states[c] for c in TOKEN_COLUMNS}
        missing_token = "missing" in token_states
        invalid_token = "invalid" in token_states
        admitted = not (missing_token or invalid_token)
        self._rows_missing_token += missing_token
        self._rows_invalid_token += invalid_token
        self._rows_unknown_provenance += provenance == "unknown"
        self._rows_not_measured += provenance != "measured"
        self._rows_invalid_cost += states[COST_COLUMN] == "invalid"
        self._rows_missing_cost += states[COST_COLUMN] == "missing"
        base_ok = admitted and provenance != "unknown"
        for measured_only, require_cost in self._rejected:
            ok = (
                base_ok
                and (not measured_only or provenance == "measured")
                and (not require_cost or states[COST_COLUMN] == "valid")
            )
            if not ok:
                self._rejected[(measured_only, require_cost)] += 1
        host = _row_get(row, "host")
        if host:
            if row_host_verified(row):
                self.hosts.add(str(host))
            else:
                self.unverified_host_rows += 1
        if _row_get(row, "scope_kind"):
            self.scope_kinds.add(str(_row_get(row, "scope_kind")))
        session_id = _row_get(row, "session_id")
        if session_id:
            self.session_ids.add(str(session_id))
        if _row_get(row, "invocation_id"):
            self.invocation_ids.add(str(_row_get(row, "invocation_id")))
        if _row_get(row, "observed_at"):
            self.observed.append(str(_row_get(row, "observed_at")))
        if _row_get(row, "observed_at_basis"):
            self.time_bases.add(str(_row_get(row, "observed_at_basis")))
        if channel == "live":
            if session_id:
                self._live_sessions.add(str(session_id))
            else:
                self._live_without_session = True
        elif session_id:
            self._transcript_sessions.add(str(session_id))

    def coverage(self) -> str:
        """``non_overlapping`` | ``overlap_unresolved`` | ``unknown`` (identity-based only)."""
        if not self.rows:
            return "unknown"
        if "overlap_unresolved" in self._coverage_labels:
            return "overlap_unresolved"
        if "unknown" in self._coverage_labels or (self._coverage_labels and self._unannotated_rows):
            return "unknown"
        if self._coverage_labels:
            return "non_overlapping"
        live = "live" in self.channels
        replay = any(ch != "live" for ch in self.channels)
        if not (live and replay):
            return "non_overlapping"
        # Both channels: demonstrably disjoint only when every live row carries
        # a session identity that no replay row shares. Equal values, timestamps
        # or run IDs are never proof of identity.
        if not self._live_without_session and not (self._live_sessions & self._transcript_sessions):
            return "non_overlapping"
        return "overlap_unresolved"

    def coverage_reason(self) -> str | None:
        """Return stable selector reasons, retaining the legacy overlap explanation."""
        if self._coverage_reasons:
            return "; ".join(sorted(self._coverage_reasons))
        if self.coverage() == "overlap_unresolved":
            return _OVERLAP_REASON
        return None

    def aggregate_provenance(self, column: str) -> str:
        if not self.rows or self.coverage() != "non_overlapping":
            return "unknown"
        kinds = set(self.components[column].by_provenance)
        if "unknown" in kinds or not kinds:
            return "unknown"
        if kinds == {"measured"}:
            return "measured"
        if kinds == {"estimated"}:
            return "estimated"
        return "mixed"

    def total(self, column: str) -> Any:
        """Canonical total; ``None`` unless :func:`qualify_usage` finds the column eligible."""
        if not qualify_usage(self, require_cost=(column == COST_COLUMN)).eligible:
            return None
        return self.components[column].total()

    def audit_subtotal(self, column: str) -> Any:
        """Sum of valid values (``None`` without one); no coverage/provenance gate."""
        return self.components[column].total()

    def missing(self, column: str) -> int:
        return self.components[column].missing

    def channel_subtotals(self) -> dict[str, dict[str, Any]]:
        return {ch: dict(sub) for ch, sub in sorted(self.channels.items())}

    def entry(self, column: str, *, extra_reason: str | None = None) -> dict[str, Any]:
        """Build the ``token_provenance`` metadata entry for *column*."""
        comp = self.components[column]
        qualification = qualify_usage(self, require_cost=(column == COST_COLUMN))
        availability = "available" if qualification.eligible else "unavailable"
        coverage = self.coverage()
        reasons: list[str] = []
        if extra_reason:
            reasons.append(extra_reason)
        coverage_reason = self.coverage_reason()
        if coverage_reason:
            reasons.append(coverage_reason)
        if self.unverified_host_rows:
            reasons.append(
                f"host attribution unverified on {self.unverified_host_rows} replay-derived "
                "row(s) (host_basis is not 'handle')"
            )
        if not comp.known:
            reasons.append(f"no observation supplied {column}")
        entry: dict[str, Any] = {
            "provenance": self.aggregate_provenance(column),
            "metric": column,
            "scope_kind": _single(self.scope_kinds),
            "observation_time_basis": _single(self.time_bases),
            "availability": availability,
            "known_count": comp.known,
            "missing_count": comp.missing,
            "invalid_count": comp.invalid,
            "rejected_contributors": qualification.rejected_contributors,
            "qualification_reason": qualification.reason,
            "composition": {
                kind: {"count": v["count"], "subtotal": v["subtotal"]}
                for kind, v in sorted(comp.by_provenance.items())
                if v["count"]
            },
            "coverage": coverage,
        }
        if self.hosts:
            entry["hosts"] = sorted(self.hosts)
        if self.channels:
            entry["channels"] = sorted(self.channels)
        if len(self.session_ids) == 1:
            entry["session_id"] = next(iter(self.session_ids))
        if len(self.invocation_ids) == 1:
            entry["invocation_id"] = next(iter(self.invocation_ids))
        if self.observed:
            entry["observed_from"] = min(self.observed)
            entry["observed_to"] = max(self.observed)
        if reasons:
            entry["reason"] = "; ".join(reasons)
        return entry


def qualify_usage(
    group: ObservationGroup, *, require_cost: bool = False, measured_only: bool = False
) -> UsageQualification:
    """Decide whether *group* may publish a canonical stored-usage figure (ENH-3731).

    Pure over *group* state. Row admission (all four token columns valid) and the
    provenance gate always apply; ``require_cost`` and ``measured_only`` can only
    tighten the result. The first applicable group-wide failure wins, independent
    of insertion order: empty selection, coverage, missing/invalid token component,
    unknown provenance, not measured, invalid cost, unpriced contributor.
    """
    provenances = group.provenances
    if not provenances or "unknown" in provenances:
        label = "unknown"
    elif len(provenances) > 1:
        label = "mixed"
    else:
        label = next(iter(provenances))
    reason: str | None = None
    if not group.rows:
        reason = "empty_selection"
    else:
        coverage = group.coverage()
        if coverage == "overlap_unresolved":
            reason = "coverage_overlap_unresolved"
        elif coverage == "unknown":
            reason = "coverage_unknown"
        elif coverage != "non_overlapping":
            reason = "unclassified"
        elif group._rows_missing_token:
            reason = "missing_token_component"
        elif group._rows_invalid_token:
            reason = "invalid_token_component"
        elif group._rows_unknown_provenance:
            reason = "unknown_provenance"
        elif measured_only and group._rows_not_measured:
            reason = "not_measured"
        elif require_cost and (
            group._rows_invalid_cost or group.components[COST_COLUMN].overflowed()
        ):
            reason = "invalid_cost"
        elif require_cost and group._rows_missing_cost:
            reason = "unpriced_contributor"
    return UsageQualification(
        eligible=reason is None,
        provenance=label,
        reason=reason,
        contributors=group.rows,
        rejected_contributors=group._rejected[(measured_only, require_cost)],
        component_counts=tuple(group.components[c].counts(c) for c in AGGREGATE_COLUMNS),
        policy_version=USAGE_QUALIFICATION_POLICY_VERSION,
    )


def _single(values: set[str]) -> str:
    if not values:
        return "unknown"
    return next(iter(values)) if len(values) == 1 else "mixed"


def group_rows(rows: Iterable[Any], key: Any) -> dict[Any, ObservationGroup]:
    """Group *rows* by ``key(row)`` (insertion-ordered) into observation groups."""
    groups: dict[Any, ObservationGroup] = {}
    for row in rows:
        groups.setdefault(key(row), ObservationGroup()).add(row)
    return groups


def estimated_entry(
    metric: str,
    *,
    scope_kind: str = "session",
    available: bool = True,
    reason: str | None = None,
) -> dict[str, Any]:
    """Entry for a figure derived from a context-state estimate (always ``estimated``)."""
    entry: dict[str, Any] = {
        "provenance": "estimated",
        "metric": metric,
        "scope_kind": scope_kind,
        "observation_time_basis": "unknown",
        "availability": "available" if available else "unavailable",
        "known_count": 1 if available else 0,
        "missing_count": 0 if available else 1,
        "composition": {},
        "coverage": "non_overlapping",
    }
    if reason:
        entry["reason"] = reason
    return entry


def context_occupancy_entry(state: Mapping[str, Any]) -> dict[str, Any]:
    """Describe the hook's context estimate without treating it as consumption.

    Legacy state files contain no observation evidence. Their numeric estimate
    remains available, but baseline freshness is unknown rather than inferred
    from the time this file was read.
    """
    available = state.get("estimated_tokens") is not None
    entry = estimated_entry("context_occupancy_tokens", scope_kind="context", available=available)
    if not available:
        entry["provenance"] = "unknown"
    entry["session_id"] = state.get("session_id") or None
    entry["estimate_reason"] = state.get("estimate_reason") or "legacy_state_unknown_estimator"
    entry["baseline_observed_at"] = state.get("baseline_observed_at") or None
    entry["estimate_updated_at"] = state.get("estimate_updated_at") or None
    entry["baseline_observation_boundary"] = state.get("baseline_observation_boundary") or None
    entry["baseline_context_boundary"] = state.get("baseline_context_boundary") or None
    entry["context_boundary"] = state.get("context_boundary") or None
    entry["observation_time_basis"] = (
        "hook_wall_clock"
        if entry["baseline_observed_at"] or entry["estimate_updated_at"]
        else "unknown"
    )
    entry["stale"] = state.get("stale") if isinstance(state.get("stale"), bool) else None
    entry["stale_reason"] = state.get("stale_reason") or "unknown_baseline_freshness"
    entry["reason"] = f"{entry['estimate_reason']}; {entry['stale_reason']}"
    return entry


def counted_entry(
    metric: str,
    *,
    provenance: str,
    known: int,
    missing: int,
    coverage: str = "non_overlapping",
    scope_kind: str = "unknown",
    hosts: list[str] | None = None,
    channels: list[str] | None = None,
    session_id: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Entry built from pre-aggregated known/missing counts (rollups without raw rows)."""
    if not known:
        availability = "unavailable"
    elif missing:
        availability = "partial"
    else:
        availability = "available"
    entry: dict[str, Any] = {
        "provenance": provenance,
        "metric": metric,
        "scope_kind": scope_kind,
        "observation_time_basis": "unknown",
        "availability": availability,
        "known_count": known,
        "missing_count": missing,
        "composition": {provenance: {"count": known}} if known else {},
        "coverage": coverage,
    }
    if hosts:
        entry["hosts"] = hosts
    if channels:
        entry["channels"] = channels
    if session_id:
        entry["session_id"] = session_id
    if reason:
        entry["reason"] = reason
    return entry


# -- text rendering -----------------------------------------------------------

_META_KEYS = (
    "provenance",
    "metric",
    "scope_kind",
    "hosts",
    "channels",
    "observation_time_basis",
    "availability",
    "known_count",
    "missing_count",
    "coverage",
    "stale",
    "session_id",
    "invocation_id",
    "observed_from",
    "observed_to",
    "composition",
    "qualification_reason",
    "invalid_count",
    "rejected_contributors",
)


def suffix_for(entry: Mapping[str, Any]) -> str:
    """``[provenance · availability · coverage · stale]`` in the fixed qualifier order."""
    parts = [str(entry["provenance"])]
    availability = entry.get("availability", "available")
    if availability != "available":
        known = int(entry.get("known_count", 0))
        total = known + int(entry.get("missing_count", 0))
        parts.append(
            f"{availability} {known}/{total}" if availability == "partial" else availability
        )
    coverage = entry.get("coverage", "non_overlapping")
    if coverage != "non_overlapping":
        parts.append(coverage.replace("_", " "))
    if entry.get("stale"):
        parts.append("stale")
    return "[" + " · ".join(parts) + "]"


def same_metadata(entries: Iterable[Mapping[str, Any]]) -> bool:
    """True when every entry's metadata is identical excluding ``reason`` and ``metric``."""
    seen: list[dict[str, Any]] = []
    for entry in entries:
        seen.append({k: entry.get(k) for k in _META_KEYS if k != "metric"})
    return all(item == seen[0] for item in seen[1:])


def format_figure(value: Any, entry: Mapping[str, Any] | None, *, suffix: bool = True) -> str:
    """Render one token figure: ``12,345 [measured]`` or ``— [unavailable]``."""
    shown = "—" if value is None else f"{int(value):,}"
    if entry is None or not suffix:
        return shown
    if value is None:
        entry = {**entry, "availability": "unavailable"}
    return f"{shown} {suffix_for(entry)}"


def footnotes(entries: Iterable[Mapping[str, Any]]) -> list[str]:
    """Deduplicated ``* <reason>`` lines, in first-seen order."""
    seen: list[str] = []
    for entry in entries:
        reason = entry.get("reason")
        if reason and reason not in seen:
            seen.append(str(reason))
    return [f"* {r}" for r in seen]
