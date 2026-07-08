"""Per-state cost attribution with stable JSON shape (ENH-2477).

Mirrors the ``ab_writer`` stable-JSON dataclass pattern: a pure
serialization layer with no I/O in the core, plus thin write/read
helpers at the module boundary. The on-disk data source is
``<run_dir>/usage.jsonl`` (one row per ``action_complete`` event),
written by ``PersistentExecutor._handle_event()`` at
``fsm/persistence.py:637-655``.

The ``from_history(db_path)`` constructor is the future API gated by
sibling ENH-2461 (P3) — until that lands, it returns ``[]`` gracefully
on a missing ``usage_event`` table so the implementation is shippable
without ENH-2461.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from little_loops.pricing import estimate_cost_usd

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
        cost_usd: Sum of ``estimate_cost_usd`` across invocations;
            falls back to ``0.0`` if any row used an unknown model
            (see ``has_unknown_model``).
        wallclock_ms: Sum of wallclock_ms across invocations.
        has_unknown_model: True if any contributing row had a model
            that ``estimate_cost_usd`` could not price — in that case
            ``cost_usd`` is left at 0 and the table renderer prints
            ``"n/a"`` for the row.
    """

    state: str
    iterations: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float = 0.0
    wallclock_ms: int = 0
    has_unknown_model: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return the locked stable-JSON shape for this state."""
        return {
            "state": self.state,
            "iterations": self.iterations,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "cost_usd": self.cost_usd,
            "wallclock_ms": self.wallclock_ms,
        }

    def table_row(self) -> str:
        """Render one row in the existing CLI table column layout.

        Preserves the byte-identical column order/width of the legacy
        ``_print_usage_summary`` printer at
        ``cli/loop/_helpers.py:1717-1724`` so the 8 existing
        ``TestPrintUsageSummary`` scenarios remain green.

        Columns: state (24w left), invoc (5w right), input (8w right),
        output (8w right), cache (8w right = cache_read + cache_creation),
        est_cost (10w right = ``$X.XXXX`` or ``n/a``).
        """
        cache = self.cache_read_tokens + self.cache_creation_tokens
        cost_str = f"${self.cost_usd:.4f}" if not self.has_unknown_model else "n/a"
        return (
            f"{self.state:<24} {self.iterations:>5} "
            f"{self.input_tokens:>8} {self.output_tokens:>8} "
            f"{cache:>8} {cost_str:>10}"
        )


@dataclass
class CostReport:
    """Top-level cost report: per-state aggregates plus run-wide totals.

    Attributes:
        states: Per-state aggregates (one PerStateCost per state).
        totals: Run-wide aggregate keyed by the same metric names.
    """

    states: list[PerStateCost] = field(default_factory=list)
    totals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return the locked stable-JSON shape for the report."""
        return {
            "states": [s.to_dict() for s in self.states],
            "totals": dict(self.totals),
        }

    def table(self) -> str:
        """Render the existing CLI cost table (byte-identical to legacy output).

        Header and separator line widths match the original
        ``_print_usage_summary`` at ``cli/loop/_helpers.py:1717-1718``:
        the separator is ``"-" * 68``. Rows are sorted by state name.
        """
        lines: list[str] = []
        lines.append(
            f"{'state':<24} {'invoc':>5} {'input':>8} {'output':>8} {'cache':>8} {'est_cost':>10}"
        )
        lines.append("-" * 68)
        for state in sorted(self.states, key=lambda s: s.state):
            lines.append(state.table_row())
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
            states.append(
                PerStateCost(
                    state=str(entry.get("state", "unknown")),
                    iterations=int(entry.get("iterations", 0) or 0),
                    input_tokens=int(entry.get("input_tokens", 0) or 0),
                    output_tokens=int(entry.get("output_tokens", 0) or 0),
                    cache_read_tokens=int(entry.get("cache_read_tokens", 0) or 0),
                    cache_creation_tokens=int(entry.get("cache_creation_tokens", 0) or 0),
                    cost_usd=float(entry.get("cost_usd", 0.0) or 0.0),
                    wallclock_ms=int(entry.get("wallclock_ms", 0) or 0),
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
            inp = int(row.get("input_tokens", 0) or 0)
            out = int(row.get("output_tokens", 0) or 0)
            cr = int(row.get("cache_read_tokens", 0) or 0)
            cc = int(row.get("cache_creation_tokens", 0) or 0)
            wallclock = int(row.get("wallclock_ms", 0) or 0)
            bucket = buckets[state]
            bucket["iterations"] += 1
            bucket["input_tokens"] += inp
            bucket["output_tokens"] += out
            bucket["cache_read_tokens"] += cr
            bucket["cache_creation_tokens"] += cc
            bucket["wallclock_ms"] += wallclock
            cost = estimate_cost_usd(model, inp, out, cr, cc)
            if cost is None:
                bucket["has_unknown_model"] = True
            else:
                bucket["cost_usd"] += cost

        states = [
            PerStateCost(
                state=state_name,
                iterations=b["iterations"],
                input_tokens=b["input_tokens"],
                output_tokens=b["output_tokens"],
                cache_read_tokens=b["cache_read_tokens"],
                cache_creation_tokens=b["cache_creation_tokens"],
                cost_usd=b["cost_usd"],
                wallclock_ms=b["wallclock_ms"],
                has_unknown_model=b["has_unknown_model"],
            )
            for state_name, b in buckets.items()
        ]

        return cls(states=states, totals=_compute_totals(states))


def _compute_totals(states: list[PerStateCost]) -> dict[str, Any]:
    """Aggregate per-state metrics into run-wide totals."""
    totals: dict[str, Any] = {
        "iterations": sum(s.iterations for s in states),
        "input_tokens": sum(s.input_tokens for s in states),
        "output_tokens": sum(s.output_tokens for s in states),
        "cache_read_tokens": sum(s.cache_read_tokens for s in states),
        "cache_creation_tokens": sum(s.cache_creation_tokens for s in states),
        "wallclock_ms": sum(s.wallclock_ms for s in states),
        "cost_usd": 0.0,
        "has_unknown_model": any(s.has_unknown_model for s in states),
    }
    if not totals["has_unknown_model"]:
        totals["cost_usd"] = sum(s.cost_usd for s in states)
    return totals


# ---------------------------------------------------------------------------
# ENH-2461-gated API: read per-state cost from .ll/history.db
# ---------------------------------------------------------------------------


def _from_history(db_path: Path) -> list[PerStateCost]:
    """Read per-state cost from the ``usage_event`` table (ENH-2461, gated).

    The ``usage_event`` table is proposed in ENH-2461 (P3) and is not
    present at the time of this writing. This constructor returns
    ``[]`` when the table is missing, so callers can use the
    feature-flagged API without crashing on legacy DBs.
    """
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
    except sqlite3.Error:
        return []
    try:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT state, input_tokens, output_tokens, "
                "cache_read_tokens, cache_creation_tokens, "
                "model, wallclock_ms "
                "FROM usage_event"
            ).fetchall()
        except sqlite3.OperationalError:
            # ENH-2461 not merged yet — table absent.
            return []
    finally:
        conn.close()

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
        }
    )
    for row in rows:
        state = str(row["state"] or "unknown")
        model = str(row["model"] or "unknown")
        inp = int(row["input_tokens"] or 0)
        out = int(row["output_tokens"] or 0)
        cr = int(row["cache_read_tokens"] or 0)
        cc = int(row["cache_creation_tokens"] or 0)
        wallclock = int(row["wallclock_ms"] or 0)
        bucket = buckets[state]
        bucket["iterations"] += 1
        bucket["input_tokens"] += inp
        bucket["output_tokens"] += out
        bucket["cache_read_tokens"] += cr
        bucket["cache_creation_tokens"] += cc
        bucket["wallclock_ms"] += wallclock
        cost = estimate_cost_usd(model, inp, out, cr, cc)
        if cost is None:
            bucket["has_unknown_model"] = True
        else:
            bucket["cost_usd"] += cost

    return [
        PerStateCost(
            state=state_name,
            iterations=b["iterations"],
            input_tokens=b["input_tokens"],
            output_tokens=b["output_tokens"],
            cache_read_tokens=b["cache_read_tokens"],
            cache_creation_tokens=b["cache_creation_tokens"],
            cost_usd=b["cost_usd"],
            wallclock_ms=b["wallclock_ms"],
            has_unknown_model=b["has_unknown_model"],
        )
        for state_name, b in buckets.items()
    ]


# Attach the feature-flagged constructor to PerStateCost so callers
# can use ``PerStateCost.from_history(db_path)`` per the issue spec.
PerStateCost.from_history = classmethod(lambda cls, db_path: _from_history(db_path))  # type: ignore[attr-defined]
