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


@dataclass
class _Component:
    known: int = 0
    missing: int = 0
    total: float = 0
    by_provenance: dict[str, dict[str, float]] = field(default_factory=dict)

    def add(self, value: Any, provenance: str) -> None:
        slot = self.by_provenance.setdefault(provenance, {"count": 0, "subtotal": 0})
        if value is None:
            self.missing += 1
            return
        self.known += 1
        self.total += value
        slot["count"] += 1
        slot["subtotal"] += value


class ObservationGroup:
    """Accumulates ``usage_events`` rows for one aggregate and reports metadata."""

    def __init__(self) -> None:
        self.rows = 0
        self.components: dict[str, _Component] = {c: _Component() for c in AGGREGATE_COLUMNS}
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
        for col in AGGREGATE_COLUMNS:
            value = _row_get(row, col)
            self.components[col].add(value, provenance)
            if value is not None and col in TOKEN_COLUMNS:
                sub[col] += value
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
        """Canonical total; unavailable for missing data or unresolved coverage."""
        comp = self.components[column]
        return (
            None
            if self.coverage() != "non_overlapping" or comp.missing or not comp.known
            else comp.total
        )

    def subtotal(self, column: str) -> Any:
        """Known canonical subtotal; raw audit sums remain in channel subtotals."""
        comp = self.components[column]
        return comp.total if comp.known and self.coverage() == "non_overlapping" else None

    def missing(self, column: str) -> int:
        return self.components[column].missing

    def channel_subtotals(self) -> dict[str, dict[str, Any]]:
        return {ch: dict(sub) for ch, sub in sorted(self.channels.items())}

    def entry(self, column: str, *, extra_reason: str | None = None) -> dict[str, Any]:
        """Build the ``token_provenance`` metadata entry for *column*."""
        comp = self.components[column]
        if self.coverage() != "non_overlapping" or not comp.known:
            availability = "unavailable"
        elif comp.missing:
            availability = "partial"
        else:
            availability = "available"
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
            "composition": {
                kind: {"count": int(v["count"]), "subtotal": v["subtotal"]}
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
