"""Per-state cost attribution with stable JSON shape (ENH-2477).

Mirrors the ``ab_writer`` stable-JSON dataclass pattern: a pure
serialization layer with no I/O in the core, plus thin write/read
helpers at the module boundary. The on-disk data source is
``<run_dir>/usage.jsonl`` (one row per ``action_complete`` event),
written by ``PersistentExecutor._handle_event()`` at
``fsm/persistence.py:1008-1036``.

This module is the *live* per-state cost path and stays sourced from
``usage.jsonl`` (which carries FSM ``state``). A history-DB-backed per-state
reader was considered under ENH-2461 but retired: that issue's ``usage_events``
table is per-call grain with no ``state`` column, so per-state cost is not
derivable from it. History-DB usage rollups live on
``history_reader.aggregate_usage()`` instead (grouped by model/session).
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from little_loops.pricing import MODEL_PRICING, _event_date, estimate_cost_usd

# Locked JSON keys (do not reorder / rename without a schema version bump).
_STATE_KEYS = (
    "state",
    "iterations",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_creation_tokens",
    "cost_usd",
    "wallclock_ms",
)

# ENH-3719: pinned sentinel set for "the row's model identifier is missing
# rather than unknown-by-name". When a row carries one of these as its model,
# the diagnostic listing renders a separate "missing identifier" footer line
# (so the user can see *why* the cost is n/a: not a missing price, but no
# identifier to look up). Everything else (concrete IDs, dated/prefixed/
# suffixed variants, or any other unrecognized name) lands in the concrete
# footer line.
_MISSING_MODEL_SENTINELS = frozenset(
    {
        "unknown",  # default str(None) after the row dict lookup
        "none",  # str(None) — persisted rows with JSON-null model
        "",  # explicit empty string
        " ",  # whitespace-only after strip
    }
)


def _is_missing_model_sentinel(model: str) -> bool:
    """Return True if the model's effective identifier is a missing-ID sentinel.

    The sentinel set (``unknown``, ``None``, ``""``, whitespace-only) is
    distinct from concrete IDs (which may be unrecognized but still name a
    specific model — e.g. ``claude-sonnet-5-5-20261001``, ``anthropic.fable-5``,
    ``claude-opus-5[1m]``). The footer splits these two cases so the user
    can tell *why* the cost is n/a: no identifier vs. identifier not priced.
    """
    return model.strip().lower() in {s.lower() for s in _MISSING_MODEL_SENTINELS}


# ENH-3538: token components tracked for completeness. A ``None`` component is
# unknown (no contributor reported it); ``<component>_missing > 0`` marks a
# numeric value as a partial subtotal.
_TOKEN_COMPONENTS = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_creation_tokens",
)


def _missing_key(component: str) -> str:
    return f"{component}_missing"


# BUG-3724: an action may report usage from several models / batch modes /
# pricing dates. ``action_complete`` and ``usage.jsonl`` rows therefore carry
# ``usage_contributions`` — one bucket per (model, is_batch, pricing date) — and
# ``CostReport`` prices each bucket individually. The row's flat token fields
# remain an audit/compatibility summary and are never priced a second time.
# A row *without* the key is a legacy aggregate (priced at its single
# model/flag, as before); a row *with* an empty or malformed value is invalid
# and its cost stays unavailable rather than falling back to the last model.
USAGE_CONTRIBUTIONS_KEY = "usage_contributions"
INVALID_ATTRIBUTION_REASON = "invalid usage attribution"
UNPRICEABLE_MODEL_REASON = "unpriceable model"


def build_usage_contributions(events: Iterable[Any]) -> list[dict[str, Any]]:
    """Bucket ``TokenUsage`` events by (model, is_batch, effective pricing date).

    The pricing date is the UTC date of the event's ``observed_at``; it is
    ``None`` (resolved to the action-completion date at read time) when the
    event carries no parseable observation time. Components keep the ENH-3538
    nullable contract: the sum of known values (``None`` if no event supplied
    it) plus a ``<component>_missing`` count.
    """
    grouped: dict[tuple[str, bool, str | None], list[Any]] = {}
    for event in events:
        day = _event_date(getattr(event, "observed_at", None))
        key = (event.model, bool(event.is_batch), day.isoformat() if day else None)
        grouped.setdefault(key, []).append(event)
    contributions: list[dict[str, Any]] = []
    for (model, is_batch, pricing_date), members in grouped.items():
        bucket: dict[str, Any] = {
            "model": model,
            "is_batch": is_batch,
            "pricing_date": pricing_date,
            "usage_event_count": len(members),
        }
        for component in _TOKEN_COMPONENTS:
            known = [v for m in members if (v := getattr(m, component)) is not None]
            bucket[component] = sum(known) if known else None
            bucket[_missing_key(component)] = len(members) - len(known)
        contributions.append(bucket)
    return contributions


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _contribution_cost(contribution: Any, fallback_date: date | None) -> float | None:
    """Price one contribution; ``None`` when invalid, incomplete, or unpriced."""
    if not isinstance(contribution, dict):
        return None
    model = contribution.get("model")
    if not isinstance(model, str) or not model:
        return None
    is_batch = contribution.get("is_batch", False)
    if not isinstance(is_batch, bool):
        return None
    pricing_date = contribution.get("pricing_date")
    as_of = fallback_date
    if pricing_date is not None:
        if not isinstance(pricing_date, str):
            return None
        try:
            as_of = date.fromisoformat(pricing_date)
        except ValueError:
            return None
    values: dict[str, int] = {}
    for component in _TOKEN_COMPONENTS:
        value = contribution.get(component)
        missing = contribution.get(_missing_key(component), 0)
        if value is None or not _is_count(value) or not _is_count(missing) or missing:
            return None  # unknown / partial / malformed component: unpriceable
        values[component] = value
    return estimate_cost_usd(
        model,
        values["input_tokens"],
        values["output_tokens"],
        values["cache_read_tokens"],
        values["cache_creation_tokens"],
        is_batch=is_batch,
        as_of=as_of,
    )


def _fmt_tokens(value: int | None, missing: int) -> str:
    """Render a token figure: ``n/a`` when unknown, ``N+`` for a partial subtotal."""
    if value is None:
        return "n/a"
    return f"{value}+" if missing else str(value)


@dataclass
class PerStateCost:
    """Aggregated cost / usage for a single FSM state.

    Attributes:
        state: FSM state name (or ``"unknown"`` for unkeyed rows).
        iterations: Number of action_complete events for this state.
        input_tokens: Sum of input tokens across invocations.
        output_tokens: Sum of output tokens across invocations.
        cache_read_tokens: Sum of cache-read tokens.
        cache_creation_tokens: Sum of cache-creation tokens.
        cost_usd: Sum of ``estimate_cost_usd`` across invocations, or
            ``None`` when any contribution was unpriced (unknown model or
            an incomplete token observation) — a known-cost subtotal is
            never exposed as the total (ENH-3538).
        wallclock_ms: Sum of wallclock_ms across invocations.
        has_unknown_model: True if any contributing row could not be
            priced (unknown model, a ``None`` token component, or a
            partial-subtotal row). ``cost_usd`` is then ``None`` and the
            table renderer prints ``"n/a"`` for the row. Serialized as
            ``cost_usd: null``.
        input_tokens_missing / output_tokens_missing /
        cache_read_tokens_missing / cache_creation_tokens_missing: number of
            contributing observations that lacked that component. Token
            fields are ``None`` when no contributor reported the component
            and a partial subtotal when the matching count is non-zero.
    """

    state: str
    iterations: int = 0
    input_tokens: int | None = 0
    output_tokens: int | None = 0
    cache_read_tokens: int | None = 0
    cache_creation_tokens: int | None = 0
    cost_usd: float | None = 0.0
    wallclock_ms: int = 0
    has_unknown_model: bool = False
    input_tokens_missing: int = 0
    output_tokens_missing: int = 0
    cache_read_tokens_missing: int = 0
    cache_creation_tokens_missing: int = 0
    unavailable_reason: str | None = None
    """Why ``cost_usd`` is unavailable (BUG-3724). Diagnostic only — never serialized,
    so the stable report JSON is unchanged."""

    def to_dict(self) -> dict[str, Any]:
        """Return the locked stable-JSON shape for this state.

        ``cost_usd`` is ``None`` for an unpriced state. ``<component>_missing``
        keys are emitted only when non-zero, so complete-data output is
        byte-identical to the pre-ENH-3538 shape.
        """
        data: dict[str, Any] = {
            "state": self.state,
            "iterations": self.iterations,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "cost_usd": None if self.has_unknown_model else self.cost_usd,
            "wallclock_ms": self.wallclock_ms,
        }
        for component in _TOKEN_COMPONENTS:
            missing = getattr(self, _missing_key(component))
            if missing:
                data[_missing_key(component)] = missing
        return data

    def table_row(self) -> str:
        """Render one row in the existing CLI table column layout.

        Preserves the byte-identical column order/width of the legacy
        ``_print_usage_summary`` printer at
        ``cli/loop/runner.py`` so the 8 existing
        ``TestPrintUsageSummary`` scenarios remain green.

        Columns: state (24w left), invoc (5w right), input (8w right),
        output (8w right), cache (8w right = cache_read + cache_creation),
        est_cost (10w right = ``$X.XXXX`` or ``n/a``).
        """
        if self.cache_read_tokens is None and self.cache_creation_tokens is None:
            cache_str = "n/a"
        else:
            cache = (self.cache_read_tokens or 0) + (self.cache_creation_tokens or 0)
            partial = (
                self.cache_read_tokens is None
                or self.cache_creation_tokens is None
                or self.cache_read_tokens_missing
                or self.cache_creation_tokens_missing
            )
            cache_str = f"{cache}+" if partial else str(cache)
        input_str = _fmt_tokens(self.input_tokens, self.input_tokens_missing)
        output_str = _fmt_tokens(self.output_tokens, self.output_tokens_missing)
        cost_str = (
            "n/a" if self.has_unknown_model or self.cost_usd is None else f"${self.cost_usd:.4f}"
        )
        return (
            f"{self.state:<24} {self.iterations:>5} "
            f"{input_str:>8} {output_str:>8} "
            f"{cache_str:>8} {cost_str:>10}"
        )


@dataclass
class CostReport:
    """Top-level cost report: per-state aggregates plus run-wide totals.

    Attributes:
        states: Per-state aggregates (one PerStateCost per state).
        totals: Run-wide aggregate keyed by the same metric names.
        unpriced_models: Sorted, de-duplicated effective pricing IDs absent
            from ``pricing.MODEL_PRICING`` (concrete IDs only; sentinel
            missing-IDs land in ``unpriced_missing_sentinels``). Diagnostic
            only — intentionally absent from the stable JSON shape so an
    unknown-model report round-trips without diagnostic metadata
            (ENH-3719). Once BUG-3724 lands and the per-contribution
            identity is available, ``unpriced_models`` collects every
            contributor's pricing ID, not just the legacy aggregate one.
        unpriced_missing_sentinels: True when at least one row's model is
            a sentinel from ``_MISSING_MODEL_SENTINELS`` (no price
            identifier to look up). Diagnostic only — absent from JSON.
    """

    states: list[PerStateCost] = field(default_factory=list)
    totals: dict[str, Any] = field(default_factory=dict)
    unpriced_models: list[str] = field(default_factory=list)
    unpriced_missing_sentinels: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return the locked stable-JSON shape for the report.

        ``unpriced_models`` and ``unpriced_missing_sentinels`` are diagnostic
        only — they are intentionally absent from the stable JSON shape so
        the JSON consumer (cli/loop/summary.py writes this for downstream
        tools) never reads a diagnostic field it didn't have before
        ENH-3719.
        """
        return {
            "states": [s.to_dict() for s in self.states],
            "totals": dict(self.totals),
        }

    def table(self) -> str:
        """Render the existing CLI cost table with optional ENH-3719 footer.

        When ``unpriced_models`` is non-empty OR
        ``unpriced_missing_sentinels`` is true, one or two footer lines
        appear after the state rows. The footer is end-user-phrased and
        never instructs the user to edit ``little_loops.pricing`` —
        it only names the IDs and sentinel rows that the report could not
        price.

        An empty report (no states) renders no footer (no table for the user
        to read); the calling code short-circuits in that case but the
        guard here is defensive.
        """
        lines: list[str] = []
        lines.append(
            f"{'state':<24} {'invoc':>5} {'input':>8} {'output':>8} {'cache':>8} {'est_cost':>10}"
        )
        lines.append("-" * 68)
        for state in sorted(self.states, key=lambda s: s.state):
            lines.append(state.table_row())
        if self.states:
            if self.unpriced_models:
                lines.append(
                    f"Note: {', '.join(self.unpriced_models)} not priced; cost shown is n/a."
                )
            if self.unpriced_missing_sentinels:
                lines.append(
                    "Note: usage rows with no price identifier "
                    '(unknown, None, "") contribute to n/a.'
                )
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # I/O helpers
    # ------------------------------------------------------------------

    def write_json(self, path: Path) -> None:
        """Write the stable-JSON report to ``path`` (indent=2)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def read_json(cls, path: Path) -> CostReport | None:
        """Read a stable-JSON report from ``path``; return ``None`` on error."""
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(data, dict):
            return None
        states: list[PerStateCost] = []
        for entry in data.get("states") or []:
            # ENH-3538: an explicit null token/cost is unknown, not zero. A
            # missing key (legacy report) keeps the historical 0 default; the
            # uncertainty of a legacy numeric zero was never stored.
            tokens: dict[str, Any] = {
                c: (None if entry.get(c, 0) is None else int(entry.get(c, 0) or 0))
                for c in _TOKEN_COMPONENTS
            }
            missing: dict[str, Any] = {
                _missing_key(c): int(entry.get(_missing_key(c), 0) or 0) for c in _TOKEN_COMPONENTS
            }
            cost_raw = entry.get("cost_usd", 0.0)
            states.append(
                PerStateCost(
                    state=str(entry.get("state", "unknown")),
                    iterations=int(entry.get("iterations", 0) or 0),
                    cost_usd=None if cost_raw is None else float(cost_raw or 0.0),
                    wallclock_ms=int(entry.get("wallclock_ms", 0) or 0),
                    has_unknown_model=cost_raw is None,
                    **tokens,
                    **missing,
                )
            )
        totals = data.get("totals") or {}
        if not isinstance(totals, dict):
            totals = {}
        return cls(states=states, totals=totals)

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_usage_jsonl(cls, path: Path) -> CostReport:
        """Build a CostReport from a ``<run_dir>/usage.jsonl`` file.

        Missing file or empty file returns a report with no states
        (callers short-circuit the print on empty). Malformed JSONL
        rows are skipped (same behavior as the legacy reader).
        """
        if not path.exists():
            return cls()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return cls()
        if not text.strip():
            return cls()

        # ENH-3719: diagnostic-only collections for the table() footer.
        # Sorted and de-duplicated at return; concrete-IDs are effective
        # pricing IDs absent from ``MODEL_PRICING``; the boolean captures
        # whether any row carried a missing-identifier sentinel. Set
        # membership uses effective ID string equality (no normalization —
        # dated/prefixed/suffixed variants land in their own distinct
        # entries so the footer names them verbatim).
        unpriced_concrete_ids_set: set[str] = set()
        unpriced_missing_sentinels_flag: bool = False

        buckets: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "iterations": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cache_creation_tokens": 0,
                "cost_usd": 0.0,
                "wallclock_ms": 0,
                "has_unknown_model": False,
                "unavailable_reason": None,
                # ENH-3538: contributors that reported each component, and
                # how many observations lacked it.
                **{f"{c}_known": 0 for c in _TOKEN_COMPONENTS},
                **{_missing_key(c): 0 for c in _TOKEN_COMPONENTS},
            }
        )
        for raw in text.splitlines():
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            state = str(row.get("state", "unknown"))
            model = str(row.get("model", "unknown"))
            wallclock = int(row.get("wallclock_ms", 0) or 0)
            is_batch = bool(row.get("is_batch", False))
            bucket = buckets[state]
            # ENH-3719: collect pricing diagnostics. The footer splits
            # missing-identifier sentinels (no price to look up — ``unknown``,
            # ``None``, ``""``, whitespace) from concrete IDs that are
            # unrecognized by ``pricing.MODEL_PRICING`` (dated/prefixed/
            # suffixed variants etc). Both are diagnostic-only — never
            # serialized to the stable JSON shape. We collect before the
            # contribution branch so BUG-3724's per-contribution IDs can
            # replace the legacy aggregate ``model`` field; the table()
            # call renders whatever the constructor collected.
            if _is_missing_model_sentinel(model):
                unpriced_missing_sentinels_flag = True
            elif model not in MODEL_PRICING:
                unpriced_concrete_ids_set.add(model)
            bucket["iterations"] += 1
            bucket["wallclock_ms"] += wallclock
            # ENH-3538: an explicit null component is unknown; an absent key is a
            # legacy row and keeps the historical 0. `<component>_missing > 0`
            # on the row marks its value a partial subtotal.
            values: dict[str, int | None] = {}
            row_incomplete = False
            for component in _TOKEN_COMPONENTS:
                raw_value = row.get(component, 0)
                row_missing = int(row.get(_missing_key(component), 0) or 0)
                if raw_value is None:
                    values[component] = None
                    bucket[_missing_key(component)] += max(row_missing, 1)
                    row_incomplete = True
                    continue
                value = int(raw_value or 0)
                values[component] = value
                bucket[component] += value
                bucket[f"{component}_known"] += 1
                if row_missing:
                    bucket[_missing_key(component)] += row_missing
                    row_incomplete = True
            row_date = _event_date(str(row.get("timestamp") or ""))
            cost: float | None
            reason = UNPRICEABLE_MODEL_REASON
            if USAGE_CONTRIBUTIONS_KEY in row:
                # BUG-3724: new-format row — contributions are the pricing
                # source; the flat aggregate above is audit-only.
                contributions = row[USAGE_CONTRIBUTIONS_KEY]
                if not isinstance(contributions, list) or not contributions:
                    cost = None
                    reason = INVALID_ATTRIBUTION_REASON
                else:
                    parts = [_contribution_cost(c, row_date) for c in contributions]
                    known_parts = [p for p in parts if p is not None]
                    cost = sum(known_parts) if len(known_parts) == len(parts) else None
                    if cost is None and not all(
                        isinstance(c, dict) and isinstance(c.get("model"), str) and c["model"]
                        for c in contributions
                    ):
                        reason = INVALID_ATTRIBUTION_REASON
            else:
                cost = (
                    None
                    if row_incomplete
                    else estimate_cost_usd(
                        model,
                        values["input_tokens"],
                        values["output_tokens"],
                        values["cache_read_tokens"],
                        values["cache_creation_tokens"],
                        is_batch=is_batch,
                        as_of=row_date,
                    )
                )
            if cost is None:
                bucket["has_unknown_model"] = True
                if bucket["unavailable_reason"] != INVALID_ATTRIBUTION_REASON:
                    bucket["unavailable_reason"] = reason
            else:
                bucket["cost_usd"] += cost

        states = [
            PerStateCost(
                state=state_name,
                iterations=b["iterations"],
                cost_usd=None if b["has_unknown_model"] else b["cost_usd"],
                wallclock_ms=b["wallclock_ms"],
                has_unknown_model=b["has_unknown_model"],
                input_tokens=b["input_tokens"] if b["input_tokens_known"] else None,
                output_tokens=b["output_tokens"] if b["output_tokens_known"] else None,
                cache_read_tokens=b["cache_read_tokens"] if b["cache_read_tokens_known"] else None,
                cache_creation_tokens=(
                    b["cache_creation_tokens"] if b["cache_creation_tokens_known"] else None
                ),
                input_tokens_missing=b["input_tokens_missing"],
                output_tokens_missing=b["output_tokens_missing"],
                cache_read_tokens_missing=b["cache_read_tokens_missing"],
                cache_creation_tokens_missing=b["cache_creation_tokens_missing"],
                unavailable_reason=b["unavailable_reason"],
            )
            for state_name, b in buckets.items()
        ]

        return cls(
            states=states,
            totals=_compute_totals(states),
            unpriced_models=sorted(unpriced_concrete_ids_set),
            unpriced_missing_sentinels=unpriced_missing_sentinels_flag,
        )


def _compute_totals(states: list[PerStateCost]) -> dict[str, Any]:
    """Aggregate per-state metrics into run-wide totals.

    Token components sum the known per-state values (``None`` when no state
    knows the component); ``<component>_missing`` keys are added only when
    non-zero, and a state that is itself ``None`` or partial counts as missing.
    ``cost_usd`` is ``None`` whenever any state is unpriced (ENH-3538).
    """
    totals: dict[str, Any] = {"iterations": sum(s.iterations for s in states)}
    for component in _TOKEN_COMPONENTS:
        known = [v for s in states if (v := getattr(s, component)) is not None]
        totals[component] = sum(known) if known else None
    totals["wallclock_ms"] = sum(s.wallclock_ms for s in states)
    totals["has_unknown_model"] = any(s.has_unknown_model for s in states)
    totals["cost_usd"] = (
        None if totals["has_unknown_model"] else sum(s.cost_usd or 0.0 for s in states)
    )
    for component in _TOKEN_COMPONENTS:
        missing = sum(
            getattr(s, _missing_key(component)) + (1 if getattr(s, component) is None else 0)
            for s in states
        )
        if missing:
            totals[_missing_key(component)] = missing
    return totals
