"""Route table extraction, rendering, parsing, and application for FSM loops."""

from __future__ import annotations

import csv
import io
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from little_loops.fsm.schema import FSMLoop

# Ordered standard verdict labels for column display
_STANDARD_VERDICTS = ["yes", "no", "error", "partial", "blocked", "next", "default"]

# Mapping from verdict label → YAML field name (shorthand mode)
_VERDICT_TO_FIELD: dict[str, str] = {
    "yes": "on_yes",
    "no": "on_no",
    "error": "on_error",
    "partial": "on_partial",
    "blocked": "on_blocked",
    "next": "next",
}

EMPTY_CELL = "—"


@dataclass
class ParsedTable:
    """Result of parsing an edited route table."""

    matrix: dict[str, dict[str, str]]
    new_stubs: list[str]
    deleted_states: list[str]


class RouteTableExtractor:
    """Extract FSM routing into a state×verdict matrix."""

    @staticmethod
    def extract(fsm: FSMLoop) -> dict[str, dict[str, str]]:
        """Return {state: {verdict: target}} for all states in fsm."""
        matrix: dict[str, dict[str, str]] = {}
        for name, state in fsm.states.items():
            row: dict[str, str] = {}
            # Shorthand fields
            for verdict, target in [
                ("yes", state.on_yes),
                ("no", state.on_no),
                ("error", state.on_error),
                ("partial", state.on_partial),
                ("blocked", state.on_blocked),
                ("next", state.next),
            ]:
                if target:
                    row[verdict] = target
            # route: block fields (may overlap shorthands; route takes precedence at runtime)
            if state.route:
                for verdict, target in state.route.routes.items():
                    row[verdict] = target
                if state.route.default:
                    row["default"] = state.route.default
            # extra_routes: on_<custom> → stored with prefix stripped
            for verdict, target in state.extra_routes.items():
                row[verdict] = target
            matrix[name] = row
        return matrix


def _all_verdicts(matrix: dict[str, dict[str, str]]) -> list[str]:
    """Return ordered verdict columns: standard first, then custom alpha-sorted."""
    seen: set[str] = set()
    for row in matrix.values():
        seen.update(row.keys())
    standard = [v for v in _STANDARD_VERDICTS if v in seen]
    extra = sorted(seen - set(_STANDARD_VERDICTS))
    return standard + extra


class RouteTableRenderer:
    """Render a state×verdict matrix as markdown or CSV."""

    @staticmethod
    def to_markdown(matrix: dict[str, dict[str, str]]) -> str:
        verdicts = _all_verdicts(matrix)
        headers = ["state"] + verdicts
        rows = [
            [state] + [row.get(v, EMPTY_CELL) for v in verdicts] for state, row in matrix.items()
        ]

        # Column widths
        widths = [max(len(str(r[i])) for r in ([headers] + rows)) for i in range(len(headers))]

        def fmt(cells: list[str]) -> str:
            return "| " + " | ".join(str(c).ljust(widths[i]) for i, c in enumerate(cells)) + " |"

        lines = [
            fmt(headers),
            "|" + "|".join("-" * (w + 2) for w in widths) + "|",
        ]
        lines.extend(fmt(row) for row in rows)
        return "\n".join(lines) + "\n"

    @staticmethod
    def to_csv(matrix: dict[str, dict[str, str]]) -> str:
        verdicts = _all_verdicts(matrix)
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["state"] + verdicts)
        writer.writeheader()
        for state_name, row in matrix.items():
            writer.writerow({"state": state_name, **{v: row.get(v, "") for v in verdicts}})
        return buf.getvalue()


class RouteTableParser:
    """Parse an edited markdown or CSV table back to a state×verdict matrix."""

    @staticmethod
    def parse_markdown(text: str, known_states: set[str]) -> ParsedTable:
        """Parse a markdown table into ParsedTable.

        Unknown state names with all-empty verdict cells are classified as new_stubs.
        Unknown state names with non-empty cells raise ValueError.
        """
        lines = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("|")]
        if len(lines) < 2:
            raise ValueError("No valid markdown table found in input")

        header_cells = [c.strip() for c in lines[0].strip("|").split("|")]
        verdicts = header_cells[1:]  # skip "state" column

        result: dict[str, dict[str, str]] = {}
        new_stubs: list[str] = []
        for line in lines[2:]:  # skip header + separator
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not cells or not cells[0].strip():
                continue
            state_name = cells[0].strip()
            row: dict[str, str] = {}
            for i, verdict in enumerate(verdicts):
                if i + 1 < len(cells):
                    val = cells[i + 1].strip()
                    if val and val not in (EMPTY_CELL, "-", ""):
                        row[verdict] = val
            if state_name not in known_states:
                if not row:
                    new_stubs.append(state_name)
                else:
                    raise ValueError(
                        f"Unknown state in edited table: '{state_name}' "
                        f"(known: {sorted(known_states)})"
                    )
            else:
                result[state_name] = row
        deleted_states = [s for s in known_states if s not in result]
        return ParsedTable(matrix=result, new_stubs=new_stubs, deleted_states=deleted_states)

    @staticmethod
    def parse_csv(text: str, known_states: set[str]) -> ParsedTable:
        """Parse a CSV table into ParsedTable.

        Unknown state names with all-empty verdict cells are classified as new_stubs.
        Unknown state names with non-empty cells raise ValueError.
        """
        reader = csv.DictReader(io.StringIO(text))
        result: dict[str, dict[str, str]] = {}
        new_stubs: list[str] = []
        for csv_row in reader:
            state_name = csv_row.pop("state", "").strip()
            if not state_name:
                continue
            row = {k.strip(): v for k, v in csv_row.items() if v and v not in (EMPTY_CELL, "-")}
            if state_name not in known_states:
                if not row:
                    new_stubs.append(state_name)
                else:
                    raise ValueError(
                        f"Unknown state in edited table: '{state_name}' "
                        f"(known: {sorted(known_states)})"
                    )
            else:
                result[state_name] = row
        deleted_states = [s for s in known_states if s not in result]
        return ParsedTable(matrix=result, new_stubs=new_stubs, deleted_states=deleted_states)


class RouteTableApplier:
    """Apply a matrix diff back to a loop YAML file, preserving non-route content."""

    @staticmethod
    def apply(
        path: Path,
        old_matrix: dict[str, dict[str, str]],
        new_matrix: dict[str, dict[str, str]],
        new_stubs: list[str] | None = None,
        allow_delete: bool = False,
    ) -> None:
        """Write changed routes from new_matrix back to the YAML loop file.

        Args:
            path: Path to the loop YAML file.
            old_matrix: Original state×verdict matrix before editing.
            new_matrix: Edited state×verdict matrix (excludes deleted states and new stubs).
            new_stubs: State names to insert as terminal: true stubs.
            allow_delete: When True, removes states absent from new_matrix from the YAML.
                          When False, emits a warning but leaves absent states unchanged.
        """
        from io import StringIO

        from ruamel.yaml import YAML
        from ruamel.yaml.comments import CommentedMap

        from little_loops.file_utils import atomic_write

        yaml = YAML(typ="rt")
        data = yaml.load(path)
        states_data = data.get("states", {})
        changed = False

        # Detect deleted states (known states absent from the edited table)
        deleted = set(old_matrix.keys()) - set(new_matrix.keys())

        if deleted:
            if allow_delete:
                # Warn about dangling routes to deleted states
                for remaining_state, remaining_routes in new_matrix.items():
                    for verdict, target in remaining_routes.items():
                        if target in deleted:
                            print(
                                f"⚠  Dangling route: '{remaining_state}' routes to "
                                f"deleted state '{target}' via '{verdict}'"
                            )
                # Remove deleted states from YAML
                for state_name in deleted:
                    states_data.pop(state_name, None)
                    changed = True
            else:
                for state_name in sorted(deleted):
                    print(
                        f"⚠  State '{state_name}' removed from table but "
                        f"--allow-delete not set; skipping deletion"
                    )

        for state_name, new_row in new_matrix.items():
            old_row = old_matrix.get(state_name, {})
            if new_row == old_row:
                continue

            state_data = states_data.get(state_name)
            if state_data is None:
                continue

            uses_route_block = "route" in state_data

            # Apply added/changed verdicts
            for verdict, new_target in new_row.items():
                if old_row.get(verdict) == new_target:
                    continue
                _write_route_field(state_data, verdict, new_target, uses_route_block)
                changed = True

            # Remove deleted verdicts
            for verdict in old_row:
                if verdict not in new_row:
                    _clear_route_field(state_data, verdict, uses_route_block)
                    changed = True

        # Insert new terminal stubs
        if new_stubs:
            for stub_name in new_stubs:
                states_data[stub_name] = CommentedMap({"terminal": True})
                changed = True

        if changed:
            buf = StringIO()
            yaml.dump(data, buf)
            atomic_write(path, buf.getvalue())


def _write_route_field(
    state_data: Any,
    verdict: str,
    target: str,
    uses_route_block: bool,
) -> None:
    """Write a single verdict→target mapping into the ruamel state CommentedMap."""
    if verdict == "next":
        state_data["next"] = target
        return
    if uses_route_block:
        if "route" not in state_data:
            state_data["route"] = {}
        if verdict == "default":
            state_data["route"]["_"] = target
        else:
            state_data["route"][verdict] = target
    else:
        field = _VERDICT_TO_FIELD.get(verdict)
        if field:
            state_data[field] = target
        else:
            # Extra route: stored as on_<verdict> in YAML
            state_data[f"on_{verdict}"] = target


def _clear_route_field(
    state_data: Any,
    verdict: str,
    uses_route_block: bool,
) -> None:
    """Remove a verdict from the ruamel state CommentedMap."""
    if verdict == "next":
        state_data.pop("next", None)
        return
    if uses_route_block:
        route = state_data.get("route", {})
        if verdict == "default":
            route.pop("_", None)
        else:
            route.pop(verdict, None)
    else:
        field = _VERDICT_TO_FIELD.get(verdict)
        if field:
            state_data.pop(field, None)
        else:
            state_data.pop(f"on_{verdict}", None)


def detect_routing_gaps(fsm: FSMLoop) -> list[str]:
    """Detect unreachable states, dead-end states, and missing verdict arms."""
    from little_loops.fsm.validation import _find_reachable_states

    warnings: list[str] = []
    reachable = _find_reachable_states(fsm)

    for state_name, state in fsm.states.items():
        if state_name not in reachable:
            warnings.append(f"Unreachable state: '{state_name}' has no route leading to it")

        if state.terminal:
            continue

        has_any_route = (
            state.on_yes
            or state.on_no
            or state.on_error
            or state.on_partial
            or state.on_blocked
            or state.next
            or state.route is not None
            or state.extra_routes
        )
        if not has_any_route:
            warnings.append(
                f"Dead-end state: '{state_name}' has no outbound routes and is not terminal"
            )
            continue

        # Missing arm: on_yes present but no on_no and no catch-all
        has_default = (state.route and state.route.default is not None) or state.next is not None
        if state.on_yes and not state.on_no and not has_default:
            warnings.append(
                f"Missing verdict arm: '{state_name}' has on_yes but no on_no or default"
            )

    return warnings


def open_in_editor(table_text: str, fmt: str = "markdown") -> str | None:
    """Write table to a temp file, open $EDITOR, return edited text (or None on cancel)."""
    suffix = ".md" if fmt == "markdown" else ".csv"
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(table_text)
        tmp_path = tmp.name

    try:
        editor = os.environ.get("EDITOR", "vi")
        rc = subprocess.call([editor, tmp_path])
        if rc != 0:
            return None
        return Path(tmp_path).read_text(encoding="utf-8")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
