"""Tests for pure layout functions in cli/loop/layout.py and _helpers.py.

Focuses on functions with zero direct test coverage — currently only exercised
indirectly through snapshot/integration tests in test_ll_loop_display.py.
Direct unit tests provide better failure localization and make refactoring safer.
"""

from __future__ import annotations

import pytest

from tests.helpers import make_test_fsm, make_test_state

# ---------------------------------------------------------------------------
# _colorize_label
# ---------------------------------------------------------------------------


class TestColorizeLabel:
    """Direct unit tests for _colorize_label() — currently zero coverage."""

    @pytest.fixture(autouse=True)
    def _force_color(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Force ANSI color output in test environment (non-TTY)."""
        monkeypatch.setattr("little_loops.cli.loop.layout._USE_COLOR", True, raising=False)
        monkeypatch.setattr("little_loops.cli.output._USE_COLOR", True, raising=False)

    def test_no_slash_returns_unchanged(self) -> None:
        """A simple label without '/' is returned as-is if no color code matched."""
        from little_loops.cli.loop.layout import _colorize_label

        result = _colorize_label("yes")
        # 'yes' alone gets colorized (it matches the yes branch)
        assert "\033[32" in result

    def test_compound_no_error_gets_no_color(self) -> None:
        """'no/error' gets 'no' color (priority: no/error > partial > yes > next)."""
        from little_loops.cli.loop.layout import _colorize_label

        result = _colorize_label("no/error")
        assert "\033[38;5;208" in result  # orange for no

    def test_compound_partial_yes_gets_partial_color(self) -> None:
        """'partial/yes' gets partial color (partial has higher priority than yes)."""
        from little_loops.cli.loop.layout import _colorize_label

        result = _colorize_label("partial/yes")
        assert "\033[33" in result  # yellow for partial

    def test_compound_yes_next_gets_yes_color(self) -> None:
        """'yes/next' gets yes color (yes > next in priority)."""
        from little_loops.cli.loop.layout import _colorize_label

        result = _colorize_label("yes/next")
        assert "\033[32" in result  # green for yes

    def test_next_underscore_gets_next_color(self) -> None:
        """'next' or '_' gets next color (dim)."""
        from little_loops.cli.loop.layout import _colorize_label

        result = _colorize_label("next")
        assert "\033[2" in result  # dim for next

    def test_unknown_label_returns_uncolorized(self) -> None:
        """A label with no matched color codes is returned unchanged."""
        from little_loops.cli.loop.layout import _colorize_label

        result = _colorize_label("unknown")
        assert "\033" not in result
        assert result == "unknown"

    def test_empty_string_returns_empty(self) -> None:
        """Empty label returns empty string."""
        from little_loops.cli.loop.layout import _colorize_label

        result = _colorize_label("")
        assert result == ""

    def test_no_overrides_partial(self) -> None:
        """'no' in any position overrides partial coloring."""
        from little_loops.cli.loop.layout import _colorize_label

        result = _colorize_label("partial/no")
        assert "\033[38;5;208" in result  # orange from no, not yellow from partial


# ---------------------------------------------------------------------------
# _box_kind_color
# ---------------------------------------------------------------------------


class TestBoxKindColor:
    """Direct unit tests for _box_kind_color()."""

    @pytest.fixture(autouse=True)
    def _force_color(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("little_loops.cli.loop.layout._USE_COLOR", True, raising=False)
        monkeypatch.setattr("little_loops.cli.output._USE_COLOR", True, raising=False)

    @staticmethod
    def _state(**kwargs):
        """Build a StateConfig with the given overrides (test helper)."""
        from little_loops.fsm.schema import StateConfig

        defaults = {
            "action": None,
            "action_type": None,
            "params": {},
            "evaluate": None,
            "route": None,
            "on_yes": None,
            "on_no": None,
            "on_error": None,
            "on_partial": None,
            "on_blocked": None,
            "next": None,
            "terminal": False,
            "capture": None,
            "append_to_messages": None,
            "timeout": None,
            "on_maintain": None,
            "max_retries": None,
            "on_retry_exhausted": None,
            "retryable_exit_codes": None,
            "max_rate_limit_retries": None,
            "on_rate_limit_exhausted": None,
            "rate_limit_backoff_base_seconds": None,
            "rate_limit_max_wait_seconds": None,
            "rate_limit_long_wait_ladder": None,
            "loop": None,
            "context_passthrough": False,
            "with_": {},
            "fragment_name": None,
            "fragment_bindings": {},
            "fragment_parameters": {},
            "agent": None,
            "tools": None,
            "model": None,
            "extra_routes": {},
            "type": None,
            "throttle": None,
            "on_throttle_hard": None,
            "learning": None,
            "cost_ceiling": None,
        }
        defaults.update(kwargs)
        return StateConfig(**defaults)

    def test_none_returns_none(self) -> None:
        from little_loops.cli.loop.layout import _box_kind_color

        assert _box_kind_color(None) is None

    def test_sub_loop_maps_to_magenta(self) -> None:
        from little_loops.cli.loop.layout import _box_kind_color, _SUB_LOOP_KIND_COLOR

        st = self._state(loop="inner-fsm", terminal=False)
        assert _box_kind_color(st) == _SUB_LOOP_KIND_COLOR == "35"

    def test_slash_command_maps_to_blue(self) -> None:
        from little_loops.cli.loop.layout import _box_kind_color

        st = self._state(action="/x", action_type="slash_command")
        assert _box_kind_color(st) == "34"

    def test_prompt_maps_to_magenta(self) -> None:
        from little_loops.cli.loop.layout import _box_kind_color

        st = self._state(action="do x", action_type="prompt")
        assert _box_kind_color(st) == "35"

    def test_shell_explicit_maps_to_bright_black(self) -> None:
        # Per UX request: shell states render as bright black (gray) to recede
        # on the warm-paper dark theme palette (cyan 36 was rendering greenish).
        from little_loops.cli.loop.layout import _box_kind_color

        st = self._state(action="echo hi", action_type="shell")
        assert _box_kind_color(st) == "90"

    def test_bare_action_defaults_to_shell(self) -> None:
        from little_loops.cli.loop.layout import _box_kind_color

        st = self._state(action="echo hi", action_type=None)
        assert _box_kind_color(st) == "90"

    def test_mcp_tool_maps_to_yellow(self) -> None:
        from little_loops.cli.loop.layout import _box_kind_color

        st = self._state(action="mcp://x", action_type="mcp_tool")
        assert _box_kind_color(st) == "33"

    def test_unknown_action_type_returns_none(self) -> None:
        from little_loops.cli.loop.layout import _box_kind_color

        st = self._state(action="do x", action_type="weird")
        assert _box_kind_color(st) is None

    def test_terminal_without_action_returns_dim(self) -> None:
        from little_loops.cli.loop.layout import _box_kind_color, _TERMINAL_KIND_COLOR

        st = self._state(terminal=True, action=None, action_type=None)
        assert _box_kind_color(st) == _TERMINAL_KIND_COLOR == "2"

    def test_loop_wins_over_action_type(self) -> None:
        from little_loops.cli.loop.layout import _box_kind_color, _SUB_LOOP_KIND_COLOR

        st = self._state(loop="child", action="/x", action_type="slash_command")
        assert _box_kind_color(st) == _SUB_LOOP_KIND_COLOR


class TestWithDiagramColor:
    """Verify the context manager temporarily flips ``_USE_COLOR`` for diagram
    rendering sites (dry-run, info, streaming, pinned)."""

    def test_flips_to_true_when_enabled(self, monkeypatch):
        from little_loops.cli import output as _output
        from little_loops.cli.loop._helpers import with_diagram_color

        monkeypatch.setattr(_output, "_USE_COLOR", False, raising=False)
        with with_diagram_color(True):
            assert _output._USE_COLOR is True
        assert _output._USE_COLOR is False

    def test_no_op_when_disabled(self, monkeypatch):
        from little_loops.cli import output as _output
        from little_loops.cli.loop._helpers import with_diagram_color

        monkeypatch.setattr(_output, "_USE_COLOR", False, raising=False)
        with with_diagram_color(False):
            assert _output._USE_COLOR is False

    def test_no_color_env_overrides(self, monkeypatch):
        from little_loops.cli import output as _output
        from little_loops.cli.loop._helpers import with_diagram_color

        monkeypatch.setattr(_output, "_USE_COLOR", False, raising=False)
        monkeypatch.setenv("NO_COLOR", "1")
        try:
            with with_diagram_color(True):
                assert _output._USE_COLOR is False, "NO_COLOR=1 must be honored"
        finally:
            monkeypatch.delenv("NO_COLOR", raising=False)

    def test_restores_previous_value_even_on_exception(self, monkeypatch):
        from little_loops.cli import output as _output
        from little_loops.cli.loop._helpers import with_diagram_color

        monkeypatch.setattr(_output, "_USE_COLOR", False, raising=False)
        try:
            with with_diagram_color(True):
                raise RuntimeError("simulated")
        except RuntimeError:
            pass
        assert _output._USE_COLOR is False


# ---------------------------------------------------------------------------
# End-to-end diagram rendering with kind colors
# ---------------------------------------------------------------------------


class TestDiagramKindColors:
    """Confirm non-active state boxes get distinguishing colors in the
    rendered diagram when no highlight is set (dry-run / ``ll-loop info`` /
    initial render paths that were colorless before this fix)."""

    @pytest.fixture(autouse=True)
    def _force_color(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("little_loops.cli.output._USE_COLOR", True, raising=False)
        monkeypatch.setattr("little_loops.cli.loop.layout._USE_COLOR", True, raising=False)

    def _make_fsm(self):
        from little_loops.fsm.schema import FSMLoop

        states = {
            "shell_state": TestBoxKindColor._state(action="echo a", action_type="shell"),
            "sub_loop_state": TestBoxKindColor._state(loop="inner"),
            "done": TestBoxKindColor._state(terminal=True),
        }
        states["shell_state"].next = "sub_loop_state"
        states["sub_loop_state"].next = "done"
        return FSMLoop(
            name="t",
            initial="shell_state",
            states=states,
            context={},
            required_inputs=[],
            max_steps=50,
        )

    def test_kind_colors_appear_without_highlight(self) -> None:
        """Each kind's color must appear in the rendered diagram, even
        though no state is highlighted (the dry-run / info path)."""
        from little_loops.cli.loop.layout import _render_fsm_diagram

        diagram = _render_fsm_diagram(
            self._make_fsm(),
            highlight_state=None,
            highlight_color="32",
            suppress_labels=True,
            title_only=True,
        )

        assert "\033[90" in diagram, "shell action_type should color the box bright black (gray)"
        assert "\033[35" in diagram, "sub-loop state should be magenta"
        assert "\033[2m" in diagram, "terminal state should be dim"

    def test_active_box_still_uses_highlight_color(self) -> None:
        """Active state uses highlight_color (with bg fill); kind hues
        apply to *non-active* states only — they shouldn't replace the
        highlight for the active row."""
        from little_loops.cli.loop.layout import _render_fsm_diagram

        diagram = _render_fsm_diagram(
            self._make_fsm(),
            highlight_state="sub_loop_state",
            highlight_color="32",
            suppress_labels=True,
            title_only=True,
        )

        # highlight_color=32 → expect a green fg/bg pair on the active row.
        assert "\033[32" in diagram or "\033[42" in diagram


# ---------------------------------------------------------------------------
# _badge_display_width
# ---------------------------------------------------------------------------


class TestBadgeDisplayWidth:
    """Direct unit tests for _badge_display_width()."""

    def test_ascii_badge_width(self) -> None:
        """ASCII badge width equals string length."""
        from little_loops.cli.loop.layout import _badge_display_width

        assert _badge_display_width("OK") == 2
        assert _badge_display_width("/->") == 3

    def test_empty_string(self) -> None:
        """Empty badge has zero width."""
        from little_loops.cli.loop.layout import _badge_display_width

        assert _badge_display_width("") == 0

    def test_unicode_badge_positive_width(self) -> None:
        """Unicode badge returns positive display width."""
        from little_loops.cli.loop.layout import _badge_display_width

        # ✦ (U+2726) should have width 1 or 2
        width = _badge_display_width("✦")
        assert width > 0

    def test_sub_loop_badge(self) -> None:
        """The sub-loop badge has display width."""
        from little_loops.cli.loop.layout import _SUB_LOOP_BADGE, _badge_display_width

        width = _badge_display_width(_SUB_LOOP_BADGE)
        assert width > 0


# ---------------------------------------------------------------------------
# _box_inner_lines
# ---------------------------------------------------------------------------


class TestBoxInnerLines:
    """Direct unit tests for _box_inner_lines() edge cases.

    Snapshot tests cover the common rendering paths; these tests cover
    specific edge cases like title_only, verbose wrapping, and truncation.
    """

    def test_title_only_excludes_action(self) -> None:
        """title_only=True returns just the name line, no action content."""
        from little_loops.cli.loop.layout import _box_inner_lines

        state = make_test_state(action="echo hello")
        lines = _box_inner_lines(state, "mystate", verbose=True, inner_width=40, title_only=True)
        assert lines == ["mystate"]

    def test_non_verbose_truncates_long_action(self) -> None:
        """Non-verbose mode truncates long action with ellipsis."""
        from little_loops.cli.loop.layout import _box_inner_lines

        state = make_test_state(action="this is a very long action that exceeds the inner width")
        lines = _box_inner_lines(state, "mystate", verbose=False, inner_width=20, title_only=False)
        assert len(lines) == 2  # name line + truncated action
        assert lines[1].endswith("…")  # ends with ellipsis

    def test_verbose_wraps_long_lines(self) -> None:
        """Verbose mode wraps long lines at inner_width."""
        from little_loops.cli.loop.layout import _box_inner_lines

        action = "123456789012345" * 3  # 45 chars
        state = make_test_state(action=action)
        lines = _box_inner_lines(state, "mystate", verbose=True, inner_width=15, title_only=False)
        # Each wrapped line should be ≤ inner_width
        for line in lines[1:]:  # skip name line
            assert len(line) <= 15
        # Should have at least 3 wrapped lines (45/15 = 3)
        assert len(lines) >= 4  # name + 3+ action lines

    def test_none_state_no_action_lines(self) -> None:
        """None state produces only the name line."""
        from little_loops.cli.loop.layout import _box_inner_lines

        lines = _box_inner_lines(None, "mystate", verbose=True, inner_width=40)
        assert lines == ["mystate"]

    def test_state_without_action_no_action_lines(self) -> None:
        """State without action produces only the name line."""
        from little_loops.cli.loop.layout import _box_inner_lines

        state = make_test_state()  # no action
        lines = _box_inner_lines(state, "mystate", verbose=True, inner_width=40)
        assert lines == ["mystate"]

    def test_empty_action_no_action_lines(self) -> None:
        """Empty string action produces only the name line."""
        from little_loops.cli.loop.layout import _box_inner_lines

        state = make_test_state(action="")
        lines = _box_inner_lines(state, "mystate", verbose=True, inner_width=40)
        assert lines == ["mystate"]

    def test_exact_width_action_not_truncated(self) -> None:
        """Action exactly at inner_width is not truncated."""
        from little_loops.cli.loop.layout import _box_inner_lines

        action = "1234567890"  # 10 chars
        state = make_test_state(action=action)
        lines = _box_inner_lines(state, "mystate", verbose=False, inner_width=10, title_only=False)
        assert len(lines) == 2
        assert lines[1] == action

    def test_multiline_action_non_verbose_shows_first_line(self) -> None:
        """Non-verbose mode shows only the first non-empty line of a multiline action."""
        from little_loops.cli.loop.layout import _box_inner_lines

        state = make_test_state(action="line1\nline2\nline3")
        lines = _box_inner_lines(state, "mystate", verbose=False, inner_width=40, title_only=False)
        assert len(lines) == 2
        assert lines[1] == "line1"


# ---------------------------------------------------------------------------
# _bfs_order
# ---------------------------------------------------------------------------


class TestBfsOrder:
    """Direct unit tests for _bfs_order() BFS traversal."""

    def test_single_node(self) -> None:
        """Single node with no edges returns just that node at depth 0."""
        from little_loops.cli.loop.layout import _bfs_order

        order, depth = _bfs_order("start", [])
        assert order == ["start"]
        assert depth == {"start": 0}

    def test_linear_chain(self) -> None:
        """Linear chain assigns increasing depths."""
        from little_loops.cli.loop.layout import _bfs_order

        edges = [("a", "b", ""), ("b", "c", ""), ("c", "d", "")]
        order, depth = _bfs_order("a", edges)
        assert order == ["a", "b", "c", "d"]
        assert depth == {"a": 0, "b": 1, "c": 2, "d": 3}

    def test_branching(self) -> None:
        """Branching from a single node assigns correct depths."""
        from little_loops.cli.loop.layout import _bfs_order

        edges = [("a", "b", ""), ("a", "c", ""), ("b", "d", ""), ("c", "d", "")]
        order, depth = _bfs_order("a", edges)
        assert order[:3] == ["a", "b", "c"]  # BFS order within level can vary
        assert depth["a"] == 0
        assert depth["b"] == 1
        assert depth["c"] == 1
        assert depth["d"] == 2

    def test_cycle_handled(self) -> None:
        """Cycle edges don't cause infinite loops (already-visited nodes skipped)."""
        from little_loops.cli.loop.layout import _bfs_order

        edges = [("a", "b", ""), ("b", "a", "")]  # cycle
        order, depth = _bfs_order("a", edges)
        assert order == ["a", "b"]
        assert depth == {"a": 0, "b": 1}

    def test_disconnected_nodes_not_visited(self) -> None:
        """Nodes unreachable from initial are not included."""
        from little_loops.cli.loop.layout import _bfs_order

        edges = [("a", "b", "")]
        order, depth = _bfs_order("a", edges)
        assert "c" not in order
        assert "c" not in depth


# ---------------------------------------------------------------------------
# _trace_main_path
# ---------------------------------------------------------------------------


class TestTraceMainPath:
    """Direct unit tests for _trace_main_path() happy-path tracing."""

    def test_linear_path(self) -> None:
        """Linear path follows on_yes chain."""
        from little_loops.cli.loop.layout import _trace_main_path

        fsm = make_test_fsm(
            states={
                "start": make_test_state(action="a", on_yes="mid"),
                "mid": make_test_state(action="b", on_yes="done"),
                "done": make_test_state(terminal=True),
            }
        )
        edges = [("start", "mid", "yes"), ("mid", "done", "yes")]
        path, edge_set = _trace_main_path(fsm, edges)
        assert path == ["start", "mid", "done"]
        assert ("start", "mid") in edge_set
        assert ("mid", "done") in edge_set

    def test_stops_at_terminal(self) -> None:
        """Path stops at terminal state."""
        from little_loops.cli.loop.layout import _trace_main_path

        fsm = make_test_fsm(
            states={
                "start": make_test_state(terminal=True),
            }
        )
        path, _ = _trace_main_path(fsm, [])
        assert path == ["start"]

    def test_follows_next_when_no_on_yes(self) -> None:
        """Follows 'next' when 'on_yes' is not set."""
        from little_loops.cli.loop.layout import _trace_main_path

        fsm = make_test_fsm(
            states={
                "start": make_test_state(action="a", next="done"),
                "done": make_test_state(terminal=True),
            }
        )
        edges = [("start", "done", "_")]
        path, _ = _trace_main_path(fsm, edges)
        assert path == ["start", "done"]

    def test_follows_route_first_value(self) -> None:
        """When route is set, follows the first route value."""
        from little_loops.cli.loop.layout import _trace_main_path
        from little_loops.fsm.schema import RouteConfig

        fsm = make_test_fsm(
            states={
                "start": make_test_state(
                    action="a", route=RouteConfig(routes={"yes": "done", "no": "fail"})
                ),
                "done": make_test_state(terminal=True),
            }
        )
        edges = [("start", "done", "yes"), ("start", "fail", "no")]
        path, _ = _trace_main_path(fsm, edges)
        # First route value is "done"
        assert "done" in path

    def test_cycle_detection(self) -> None:
        """Cycle in main path is detected and stopped."""
        from little_loops.cli.loop.layout import _trace_main_path

        fsm = make_test_fsm(
            states={
                "start": make_test_state(action="a", on_yes="start"),  # self-loop on_yes
            }
        )
        path, _ = _trace_main_path(fsm, [])
        assert path == ["start"]  # stops immediately, self-loop detected


# ---------------------------------------------------------------------------
# _classify_edges
# ---------------------------------------------------------------------------


class TestClassifyEdges:
    """Direct unit tests for _classify_edges() branch/back-edge classification."""

    def test_all_main_edges_no_branches(self) -> None:
        """When all edges are main-path, branches and back_edges are empty."""
        from little_loops.cli.loop.layout import _classify_edges

        edges = [("a", "b", "yes"), ("b", "c", "yes")]
        main_set = {("a", "b"), ("b", "c")}
        bfs_order = ["a", "b", "c"]
        branches, back_edges = _classify_edges(edges, main_set, bfs_order)
        assert branches == []
        assert back_edges == []

    def test_forward_branch_classified(self) -> None:
        """Forward edge not on main path is a branch."""
        from little_loops.cli.loop.layout import _classify_edges

        edges = [("a", "b", "yes"), ("a", "c", "no")]  # a→c is a branch
        main_set = {("a", "b")}
        bfs_order = ["a", "b", "c"]
        branches, back_edges = _classify_edges(edges, main_set, bfs_order)
        assert len(branches) == 1
        assert branches[0][:2] == ("a", "c")
        assert back_edges == []

    def test_backward_edge_classified(self) -> None:
        """Edge going to earlier BFS position is a back-edge."""
        from little_loops.cli.loop.layout import _classify_edges

        edges = [("a", "b", "yes"), ("b", "a", "back")]  # b→a is a back-edge
        main_set = {("a", "b")}
        bfs_order = ["a", "b"]
        branches, back_edges = _classify_edges(edges, main_set, bfs_order)
        assert branches == []
        assert len(back_edges) == 1
        assert back_edges[0][:2] == ("b", "a")

    def test_self_loop_is_back_edge(self) -> None:
        """Self-loop (src == dst) is classified as a back-edge."""
        from little_loops.cli.loop.layout import _classify_edges

        edges = [("a", "b", "yes"), ("b", "b", "retry")]  # self-loop
        main_set = {("a", "b")}
        bfs_order = ["a", "b"]
        branches, back_edges = _classify_edges(edges, main_set, bfs_order)
        assert len(back_edges) == 1
        assert back_edges[0][:2] == ("b", "b")


# ---------------------------------------------------------------------------
# TopologyDetector
# ---------------------------------------------------------------------------


class TestTopologyDetector:
    """Direct unit tests for TopologyDetector.classify()."""

    def test_linear_topology(self) -> None:
        """A simple linear path classifies as 'linear'."""
        from little_loops.cli.loop.layout import TopologyDetector

        edges = [("a", "b", ""), ("b", "c", "")]
        detector = TopologyDetector(
            edges=edges,
            main_path=["a", "b", "c"],
            branches=[],
            back_edges=[],
        )
        assert detector.classify() == "linear"

    def test_linear_with_self_loops(self) -> None:
        """Linear topology with only self-loop back-edges still classifies as 'linear'."""
        from little_loops.cli.loop.layout import TopologyDetector

        edges = [("a", "b", ""), ("b", "b", "retry")]
        detector = TopologyDetector(
            edges=edges,
            main_path=["a", "b"],
            branches=[],
            back_edges=[("b", "b", "retry")],
        )
        assert detector.classify() == "linear"

    def test_tree_topology(self) -> None:
        """A tree (branches but no fan-in) classifies as 'tree'."""
        from little_loops.cli.loop.layout import TopologyDetector

        edges = [("a", "b", ""), ("a", "c", "")]
        detector = TopologyDetector(
            edges=edges,
            main_path=["a", "b"],
            branches=[("a", "c", "")],
            back_edges=[],
        )
        assert detector.classify() == "tree"

    def test_general_topology_with_fan_in(self) -> None:
        """Fan-in (multiple edges to same node) classifies as 'general'."""
        from little_loops.cli.loop.layout import TopologyDetector

        edges = [("a", "c", ""), ("b", "c", "")]  # both point to c
        detector = TopologyDetector(
            edges=edges,
            main_path=["a", "c"],
            branches=[("b", "c", "")],
            back_edges=[],
        )
        assert detector.classify() == "general"

    def test_general_topology_with_non_self_back_edges(self) -> None:
        """Non-self back-edges force 'general' classification."""
        from little_loops.cli.loop.layout import TopologyDetector

        edges = [("a", "b", ""), ("b", "a", "back")]
        detector = TopologyDetector(
            edges=edges,
            main_path=["a", "b"],
            branches=[],
            back_edges=[("b", "a", "back")],
        )
        assert detector.classify() == "general"


# ---------------------------------------------------------------------------
# _count_display_lines (from _helpers.py)
# ---------------------------------------------------------------------------


class TestCountDisplayLines:
    """Direct unit tests for _count_display_lines()."""

    def test_empty_string(self) -> None:
        """Empty string has zero lines."""
        from little_loops.cli.loop._helpers import _count_display_lines

        assert _count_display_lines("") == 0

    def test_single_line_no_trailing_newline(self) -> None:
        """Single line without trailing newline counts as 1."""
        from little_loops.cli.loop._helpers import _count_display_lines

        assert _count_display_lines("hello") == 1

    def test_single_line_with_trailing_newline(self) -> None:
        """Trailing newline is not counted as an extra row."""
        from little_loops.cli.loop._helpers import _count_display_lines

        assert _count_display_lines("hello\n") == 1

    def test_multiline(self) -> None:
        """Multiple newlines produce correct count."""
        from little_loops.cli.loop._helpers import _count_display_lines

        assert _count_display_lines("line1\nline2\nline3") == 3

    def test_multiline_with_trailing_newline(self) -> None:
        """Multiple lines with trailing newline — trailing not counted."""
        from little_loops.cli.loop._helpers import _count_display_lines

        assert _count_display_lines("line1\nline2\nline3\n") == 3

    def test_only_newlines(self) -> None:
        """String of only newlines counts each line."""
        from little_loops.cli.loop._helpers import _count_display_lines

        assert _count_display_lines("\n\n") == 2  # trailing \n not counted as extra
        assert _count_display_lines("\n") == 1


# ---------------------------------------------------------------------------
# _render_single_line_status (from _helpers.py)
# ---------------------------------------------------------------------------


class TestRenderSingleLineStatus:
    """Direct unit tests for _render_single_line_status()."""

    def test_valid_active_state(self) -> None:
        """Active state with preds and succs renders correctly."""
        from little_loops.cli.loop._helpers import _render_single_line_status

        fsm = make_test_fsm(
            states={
                "start": make_test_state(action="a", on_yes="mid"),
                "mid": make_test_state(action="b", on_yes="done"),
                "done": make_test_state(terminal=True),
            }
        )
        result = _render_single_line_status(fsm, "mid")
        assert "mid" in result
        assert "start" in result  # pred
        assert "done" in result  # succ

    def test_none_active_state(self) -> None:
        """None active state shows '?' placeholder."""
        from little_loops.cli.loop._helpers import _render_single_line_status

        fsm = make_test_fsm()
        result = _render_single_line_status(fsm, None)
        assert "?" in result
        assert "·" in result

    def test_unknown_active_state(self) -> None:
        """Active state not in FSM states shows the name but with '·' preds/succs."""
        from little_loops.cli.loop._helpers import _render_single_line_status

        fsm = make_test_fsm()
        result = _render_single_line_status(fsm, "nonexistent")
        # State name is shown even though it's not in fsm.states
        assert "nonexistent" in result
        assert "·" in result  # no preds/succs found

    def test_no_preds_or_succs(self) -> None:
        """State with no predecessors or successors shows '·'."""
        from little_loops.cli.loop._helpers import _render_single_line_status

        fsm = make_test_fsm(
            states={
                "start": make_test_state(action="a", on_yes="done"),
                "done": make_test_state(terminal=True),
            }
        )
        result = _render_single_line_status(fsm, "start")
        assert "· → [start] → done" in result

    def test_format_matches_expected_pattern(self) -> None:
        """Output matches 'fsm: <preds> → [<active>] → <succs>' pattern."""
        from little_loops.cli.loop._helpers import _render_single_line_status

        fsm = make_test_fsm()
        result = _render_single_line_status(fsm, "start")
        assert result.startswith("fsm: ")
        assert "→" in result
        assert "[" in result
        assert "]" in result
