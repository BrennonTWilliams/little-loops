"""Property-based tests for FSM compilers using Hypothesis.

These tests verify structural invariants of compiled FSMs hold across
randomly generated input specifications, catching edge cases that
example-based tests may miss.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from little_loops.fsm.compilers import (
    compile_convergence,
    compile_goal,
    compile_imperative,
    compile_invariants,
)
from little_loops.fsm.schema import FSMLoop

# =============================================================================
# Custom Hypothesis Strategies
# =============================================================================


@st.composite
def goal_spec(draw: st.DrawFn) -> dict:
    """Generate valid goal paradigm specs."""
    # Goal text must be non-empty
    goal = draw(
        st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
        )
    )

    # At least 1 tool, up to 3
    num_tools = draw(st.integers(min_value=1, max_value=3))
    tools = [draw(st.text(min_size=1, max_size=50)) for _ in range(num_tools)]

    # Max iterations must be positive
    max_iter = draw(st.integers(min_value=1, max_value=100))

    spec: dict = {
        "paradigm": "goal",
        "goal": goal,
        "tools": tools,
        "max_iterations": max_iter,
    }

    # Optionally add name
    if draw(st.booleans()):
        spec["name"] = draw(
            st.text(
                min_size=1,
                max_size=30,
                alphabet=st.characters(whitelist_categories=("L", "N")),
            )
        )

    return spec


@st.composite
def convergence_spec(draw: st.DrawFn) -> dict:
    """Generate valid convergence paradigm specs."""
    name = draw(
        st.text(
            min_size=1,
            max_size=30,
            alphabet=st.characters(whitelist_categories=("L", "N")),
        )
    )
    check = draw(st.text(min_size=1, max_size=100))
    toward = draw(st.integers(min_value=0, max_value=1000))
    using = draw(st.text(min_size=1, max_size=50))

    return {
        "paradigm": "convergence",
        "name": name,
        "check": check,
        "toward": toward,
        "using": using,
        "tolerance": draw(st.integers(min_value=0, max_value=10)),
    }


@st.composite
def constraint(draw: st.DrawFn) -> dict:
    """Generate a valid constraint for invariants paradigm."""
    # Constraint names must match pattern expected by compiler
    name = draw(st.from_regex(r"[a-z][a-z0-9_]{0,19}", fullmatch=True))
    return {
        "name": name,
        "check": draw(st.text(min_size=1, max_size=50)),
        "fix": draw(st.text(min_size=1, max_size=50)),
    }


@st.composite
def invariants_spec(draw: st.DrawFn) -> dict:
    """Generate valid invariants paradigm specs."""
    name = draw(
        st.text(
            min_size=1,
            max_size=30,
            alphabet=st.characters(whitelist_categories=("L", "N")),
        )
    )

    # Generate 1-5 constraints with unique names
    num_constraints = draw(st.integers(min_value=1, max_value=5))
    constraints = []
    used_names: set[str] = set()

    for _ in range(num_constraints):
        # Keep generating until we get a unique name
        c = draw(constraint())
        attempts = 0
        while c["name"] in used_names and attempts < 100:
            c = draw(constraint())
            attempts += 1
        if c["name"] not in used_names:
            used_names.add(c["name"])
            constraints.append(c)

    # Must have at least one constraint
    if not constraints:
        c = {"name": "default", "check": "echo ok", "fix": "echo fix"}
        constraints.append(c)

    return {
        "paradigm": "invariants",
        "name": name,
        "constraints": constraints,
        "maintain": draw(st.booleans()),
    }


@st.composite
def imperative_spec(draw: st.DrawFn) -> dict:
    """Generate valid imperative paradigm specs."""
    name = draw(
        st.text(
            min_size=1,
            max_size=30,
            alphabet=st.characters(whitelist_categories=("L", "N")),
        )
    )

    # 1-5 steps
    num_steps = draw(st.integers(min_value=1, max_value=5))
    steps = [draw(st.text(min_size=1, max_size=50)) for _ in range(num_steps)]

    return {
        "paradigm": "imperative",
        "name": name,
        "steps": steps,
        "until": {
            "check": draw(st.text(min_size=1, max_size=50)),
        },
    }


# =============================================================================
# Goal Compiler Properties
# =============================================================================


class TestGoalCompilerProperties:
    """Property tests for compile_goal."""

    @given(spec=goal_spec())
    @settings(max_examples=100)
    def test_always_three_states(self, spec: dict) -> None:
        """Goal paradigm always produces exactly 3 states."""
        fsm = compile_goal(spec)
        assert len(fsm.states) == 3
        assert set(fsm.states.keys()) == {"evaluate", "fix", "done"}

    @given(spec=goal_spec())
    @settings(max_examples=100)
    def test_initial_state_exists(self, spec: dict) -> None:
        """Initial state exists in states dict."""
        fsm = compile_goal(spec)
        assert fsm.initial in fsm.states

    @given(spec=goal_spec())
    @settings(max_examples=100)
    def test_initial_is_evaluate(self, spec: dict) -> None:
        """Initial state is always 'evaluate'."""
        fsm = compile_goal(spec)
        assert fsm.initial == "evaluate"

    @given(spec=goal_spec())
    @settings(max_examples=100)
    def test_has_terminal_state(self, spec: dict) -> None:
        """Has at least one terminal state."""
        fsm = compile_goal(spec)
        terminal_states = fsm.get_terminal_states()
        assert len(terminal_states) >= 1
        assert "done" in terminal_states

    @given(spec=goal_spec())
    @settings(max_examples=100)
    def test_all_transitions_valid(self, spec: dict) -> None:
        """All transition targets are defined states."""
        fsm = compile_goal(spec)
        defined = fsm.get_all_state_names()
        referenced = fsm.get_all_referenced_states()
        assert referenced <= defined

    @given(spec=goal_spec())
    @settings(max_examples=100)
    def test_paradigm_preserved(self, spec: dict) -> None:
        """Output paradigm matches input."""
        fsm = compile_goal(spec)
        assert fsm.paradigm == "goal"

    @given(spec=goal_spec())
    @settings(max_examples=100)
    def test_max_iterations_preserved(self, spec: dict) -> None:
        """Max iterations is preserved from spec."""
        fsm = compile_goal(spec)
        assert fsm.max_iterations == spec["max_iterations"]


# =============================================================================
# Convergence Compiler Properties
# =============================================================================


class TestConvergenceCompilerProperties:
    """Property tests for compile_convergence."""

    @given(spec=convergence_spec())
    @settings(max_examples=100)
    def test_always_three_states(self, spec: dict) -> None:
        """Convergence paradigm always produces exactly 3 states."""
        fsm = compile_convergence(spec)
        assert len(fsm.states) == 3
        assert set(fsm.states.keys()) == {"measure", "apply", "done"}

    @given(spec=convergence_spec())
    @settings(max_examples=100)
    def test_initial_is_measure(self, spec: dict) -> None:
        """Initial state is always 'measure'."""
        fsm = compile_convergence(spec)
        assert fsm.initial == "measure"

    @given(spec=convergence_spec())
    @settings(max_examples=100)
    def test_all_transitions_valid(self, spec: dict) -> None:
        """All transition targets are defined states."""
        fsm = compile_convergence(spec)
        defined = fsm.get_all_state_names()
        referenced = fsm.get_all_referenced_states()
        assert referenced <= defined

    @given(spec=convergence_spec())
    @settings(max_examples=100)
    def test_paradigm_preserved(self, spec: dict) -> None:
        """Output paradigm matches input."""
        fsm = compile_convergence(spec)
        assert fsm.paradigm == "convergence"

    @given(spec=convergence_spec())
    @settings(max_examples=100)
    def test_context_contains_target(self, spec: dict) -> None:
        """Context contains the target value."""
        fsm = compile_convergence(spec)
        assert "target" in fsm.context
        assert fsm.context["target"] == spec["toward"]


# =============================================================================
# Invariants Compiler Properties
# =============================================================================


class TestInvariantsCompilerProperties:
    """Property tests for compile_invariants."""

    @given(spec=invariants_spec())
    @settings(max_examples=100)
    def test_state_count_formula(self, spec: dict) -> None:
        """State count is 2*N+1 where N is number of constraints."""
        fsm = compile_invariants(spec)
        n = len(spec["constraints"])
        expected = 2 * n + 1
        assert len(fsm.states) == expected

    @given(spec=invariants_spec())
    @settings(max_examples=100)
    def test_all_transitions_valid(self, spec: dict) -> None:
        """All transition targets are defined states."""
        fsm = compile_invariants(spec)
        defined = fsm.get_all_state_names()
        referenced = fsm.get_all_referenced_states()
        assert referenced <= defined

    @given(spec=invariants_spec())
    @settings(max_examples=100)
    def test_has_all_valid_terminal(self, spec: dict) -> None:
        """Has all_valid terminal state."""
        fsm = compile_invariants(spec)
        assert "all_valid" in fsm.states
        assert fsm.states["all_valid"].terminal is True

    @given(spec=invariants_spec())
    @settings(max_examples=100)
    def test_check_fix_pairs_exist(self, spec: dict) -> None:
        """Each constraint has both check and fix states."""
        fsm = compile_invariants(spec)
        for constraint in spec["constraints"]:
            check_name = f"check_{constraint['name']}"
            fix_name = f"fix_{constraint['name']}"
            assert check_name in fsm.states
            assert fix_name in fsm.states

    @given(spec=invariants_spec())
    @settings(max_examples=100)
    def test_paradigm_preserved(self, spec: dict) -> None:
        """Output paradigm matches input."""
        fsm = compile_invariants(spec)
        assert fsm.paradigm == "invariants"


# =============================================================================
# Imperative Compiler Properties
# =============================================================================


class TestImperativeCompilerProperties:
    """Property tests for compile_imperative."""

    @given(spec=imperative_spec())
    @settings(max_examples=100)
    def test_state_count_formula(self, spec: dict) -> None:
        """State count is N+2 where N is number of steps."""
        fsm = compile_imperative(spec)
        n = len(spec["steps"])
        expected = n + 2  # step_0..step_n-1 + check_done + done
        assert len(fsm.states) == expected

    @given(spec=imperative_spec())
    @settings(max_examples=100)
    def test_all_transitions_valid(self, spec: dict) -> None:
        """All transition targets are defined states."""
        fsm = compile_imperative(spec)
        defined = fsm.get_all_state_names()
        referenced = fsm.get_all_referenced_states()
        assert referenced <= defined

    @given(spec=imperative_spec())
    @settings(max_examples=100)
    def test_initial_is_step_0(self, spec: dict) -> None:
        """Initial state is always 'step_0'."""
        fsm = compile_imperative(spec)
        assert fsm.initial == "step_0"

    @given(spec=imperative_spec())
    @settings(max_examples=100)
    def test_has_check_done_and_done(self, spec: dict) -> None:
        """Has check_done and done states."""
        fsm = compile_imperative(spec)
        assert "check_done" in fsm.states
        assert "done" in fsm.states
        assert fsm.states["done"].terminal is True

    @given(spec=imperative_spec())
    @settings(max_examples=100)
    def test_steps_chain_correctly(self, spec: dict) -> None:
        """Step states chain: step_i -> step_i+1 or check_done."""
        fsm = compile_imperative(spec)
        n = len(spec["steps"])
        for i in range(n):
            state = fsm.states[f"step_{i}"]
            if i < n - 1:
                assert state.next == f"step_{i + 1}"
            else:
                assert state.next == "check_done"

    @given(spec=imperative_spec())
    @settings(max_examples=100)
    def test_paradigm_preserved(self, spec: dict) -> None:
        """Output paradigm matches input."""
        fsm = compile_imperative(spec)
        assert fsm.paradigm == "imperative"


# =============================================================================
# FSMLoop Serialization Properties
# =============================================================================


class TestFSMLoopProperties:
    """Property tests for FSMLoop serialization."""

    @given(spec=goal_spec())
    @settings(max_examples=50)
    def test_goal_roundtrip(self, spec: dict) -> None:
        """Goal FSM survives roundtrip serialization."""
        original = compile_goal(spec)
        restored = FSMLoop.from_dict(original.to_dict())

        assert restored.name == original.name
        assert restored.initial == original.initial
        assert restored.paradigm == original.paradigm
        assert set(restored.states.keys()) == set(original.states.keys())
        assert restored.max_iterations == original.max_iterations

    @given(spec=convergence_spec())
    @settings(max_examples=50)
    def test_convergence_roundtrip(self, spec: dict) -> None:
        """Convergence FSM survives roundtrip serialization."""
        original = compile_convergence(spec)
        restored = FSMLoop.from_dict(original.to_dict())

        assert restored.name == original.name
        assert restored.initial == original.initial
        assert set(restored.states.keys()) == set(original.states.keys())
        assert restored.context == original.context

    @given(spec=invariants_spec())
    @settings(max_examples=50)
    def test_invariants_roundtrip(self, spec: dict) -> None:
        """Invariants FSM survives roundtrip serialization."""
        original = compile_invariants(spec)
        restored = FSMLoop.from_dict(original.to_dict())

        assert restored.name == original.name
        assert restored.initial == original.initial
        assert set(restored.states.keys()) == set(original.states.keys())
        assert restored.maintain == original.maintain

    @given(spec=imperative_spec())
    @settings(max_examples=50)
    def test_imperative_roundtrip(self, spec: dict) -> None:
        """Imperative FSM survives roundtrip serialization."""
        original = compile_imperative(spec)
        restored = FSMLoop.from_dict(original.to_dict())

        assert restored.name == original.name
        assert restored.initial == original.initial
        assert set(restored.states.keys()) == set(original.states.keys())
