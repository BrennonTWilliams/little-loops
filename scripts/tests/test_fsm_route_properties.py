"""Property-based tests for FSM route-table round-trip using Hypothesis.

Verifies that RouteTableRenderer.to_markdown() → RouteTableParser.parse_markdown()
preserves the state×verdict matrix exactly.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from little_loops.fsm.route_table import RouteTableParser, RouteTableRenderer

# Safe identifiers: start with a letter, contain only lowercase alphanumeric and hyphens/underscores.
# Excluding pipe characters avoids breaking the markdown table delimiters.
_safe_name = st.from_regex(r"[a-z][a-z0-9_-]{0,14}", fullmatch=True)

# Only the standard shorthand verdicts (no "default" — RouteTableExtractor writes it
# from route.default, not directly; our matrix generator stays in the renderer's domain).
_verdict_label = st.sampled_from(["yes", "no", "error", "partial", "blocked", "next"])


@st.composite
def route_matrix(draw: st.DrawFn) -> dict[str, dict[str, str]]:
    """Generate a valid state×verdict matrix for round-trip testing."""
    state_names = draw(st.lists(_safe_name, min_size=1, max_size=6, unique=True))
    matrix: dict[str, dict[str, str]] = {}
    for name in state_names:
        verdicts = draw(st.lists(_verdict_label, max_size=4, unique=True))
        row: dict[str, str] = {}
        for v in verdicts:
            # Target must be a non-empty safe name (not EMPTY_CELL "—" or "-")
            row[v] = draw(_safe_name)
        matrix[name] = row
    return matrix


class TestRouteTableRoundTrip:
    """Property tests for route-table render/parse round-trip."""

    @pytest.mark.slow
    @given(matrix=route_matrix())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=list(HealthCheck),
    )
    def test_render_parse_roundtrip(self, matrix: dict[str, dict[str, str]]) -> None:
        """render→parse preserves the state×verdict matrix exactly.

        RouteTableRenderer.to_markdown() and RouteTableParser.parse_markdown()
        form a lossless pair for any matrix whose state names and target values
        contain no pipe characters or EMPTY_CELL markers.
        """
        known_states = set(matrix.keys())
        md = RouteTableRenderer.to_markdown(matrix)
        parsed = RouteTableParser.parse_markdown(md, known_states)

        assert parsed.matrix == matrix, (
            f"Matrix not preserved after render→parse.\n"
            f"Original: {matrix}\n"
            f"Parsed:   {parsed.matrix}"
        )
        assert parsed.new_stubs == [], "Unexpected new stubs in parsed result"
        assert set(parsed.deleted_states) == set(), "Unexpected deleted states in parsed result"
