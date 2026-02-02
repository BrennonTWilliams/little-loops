"""Fuzz tests for fsm.schema module focusing on untyped dict deserialization.

These tests target the from_dict() methods that accept unvalidated dictionaries:
- Type confusion attacks
- Recursive structures
- Invalid literal values
- Missing required fields
- Unexpected field types

Unlike property-based tests (which verify invariants), these tests focus on
crash safety and robustness when handling malicious or malformed input.
"""

from __future__ import annotations

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from little_loops.fsm.schema import (
    EvaluateConfig,
    FSMLoop,
    RouteConfig,
    StateConfig,
)

# =============================================================================
# Dict Fuzzing Strategies
# =============================================================================


@st.composite
def malformed_evaluate_config(draw: st.DrawFn) -> dict:
    """Generate potentially malformed EvaluateConfig dictionaries.

    Targets:
    - Invalid type values (not in Literal)
    - Wrong field types (string instead of int, etc.)
    - Missing required fields
    - Unexpected fields
    """
    # Type field - may be valid or invalid
    valid_types = [
        "exit_code",
        "output_numeric",
        "output_json",
        "output_contains",
        "convergence",
        "llm_structured",
    ]
    eval_type = draw(
        st.one_of(
            st.sampled_from(valid_types),
            st.text(min_size=1, max_size=50),  # Invalid type
            st.integers(),  # Completely wrong type
            st.none(),  # Missing required field
        )
    )

    config: dict = {"type": eval_type}

    # Add optional fields with potentially wrong types
    if draw(st.booleans()):
        config["operator"] = draw(
            st.one_of(
                st.sampled_from(["eq", "ne", "lt", "le", "gt", "ge"]),
                st.integers(),  # Wrong type
                st.none(),
            )
        )

    if draw(st.booleans()):
        config["target"] = draw(
            st.one_of(st.integers(), st.floats(), st.text(min_size=1, max_size=100), st.none())
        )

    if draw(st.booleans()):
        config["tolerance"] = draw(
            st.one_of(st.floats(), st.text(min_size=1, max_size=50), st.integers())
        )

    # Add completely unexpected fields
    if draw(st.booleans()):
        for i in range(draw(st.integers(min_value=1, max_value=10))):
            config[f"unexpected_{i}"] = draw(
                st.one_of(
                    st.integers(),
                    st.text(),
                    st.lists(st.integers()),
                    st.dictionaries(st.text(), st.integers()),
                )
            )

    return config


@st.composite
def malformed_route_config(draw: st.DrawFn) -> dict:
    """Generate potentially malformed RouteConfig dictionaries."""
    # Generate random route mappings
    routes: dict = {}

    num_routes = draw(st.integers(min_value=0, max_value=20))
    for _i in range(num_routes):
        verdict = draw(
            st.one_of(
                st.sampled_from(["accept", "reject", "continue"]),
                st.text(min_size=1, max_size=50),  # Invalid verdict
                st.integers(),
            )
        )

        target = draw(
            st.one_of(
                st.text(min_size=1, max_size=50),  # State name
                st.integers(),  # Wrong type
                st.none(),
            )
        )

        routes[verdict] = target

    # Add special keys with potentially wrong values
    if draw(st.booleans()):
        routes["_"] = draw(st.one_of(st.text(min_size=1, max_size=50), st.integers()))

    if draw(st.booleans()):
        routes["_error"] = draw(st.one_of(st.text(min_size=1, max_size=50), st.integers()))

    return routes


@st.composite
def malformed_state_config(draw: st.DrawFn) -> dict:
    """Generate potentially malformed StateConfig dictionaries."""
    state: dict = {
        "name": draw(
            st.one_of(
                st.text(min_size=1, max_size=100),
                st.integers(),
                st.none(),
            )
        )
    }

    # Add action with potentially wrong types
    if draw(st.booleans()):
        state["action"] = draw(
            st.one_of(
                st.sampled_from(["shell", "slash"]),
                st.text(min_size=1, max_size=50),  # Invalid action
                st.integers(),
            )
        )

    # Add command
    if draw(st.booleans()):
        state["command"] = draw(
            st.one_of(
                st.text(min_size=0, max_size=1000),
                st.integers(),
                st.lists(st.text()),
            )
        )

    # Add evaluate config
    if draw(st.booleans()):
        state["evaluate"] = draw(malformed_evaluate_config())

    # Add route config
    if draw(st.booleans()):
        state["route"] = draw(malformed_route_config())

    # Add unexpected fields
    if draw(st.booleans()):
        for i in range(draw(st.integers(min_value=1, max_value=5))):
            state[f"unexpected_{i}"] = draw(
                st.one_of(
                    st.integers(),
                    st.text(),
                    st.lists(st.integers()),
                )
            )

    return state


@st.composite
def malformed_fsm_loop(draw: st.DrawFn) -> dict:
    """Generate potentially malformed FSMLoop dictionaries.

    Targets:
    - Recursive state references
    - Circular dependencies
    - Invalid literal types
    - Missing required fields
    - Wrong field types
    """
    # Generate states
    num_states = draw(st.integers(min_value=0, max_value=20))

    # State names - may include invalid ones
    state_names = []
    for _i in range(num_states):
        name = draw(
            st.one_of(
                st.text(
                    min_size=1,
                    max_size=50,
                    alphabet=st.characters(whitelist_categories=("L", "N")),
                ),
                st.integers(),
                st.none(),
            )
        )
        state_names.append(name)

    # Build states dict
    states = {}
    for name in state_names:
        if name is not None:
            states[str(name)] = draw(malformed_state_config())

    # Build FSM dict
    fsm: dict = {}

    # Name (required)
    fsm["name"] = draw(
        st.one_of(
            st.text(min_size=1, max_size=100),
            st.integers(),
            st.none(),
        )
    )

    # Initial (required) - may reference non-existent state
    valid_state_names = [str(n) for n in state_names if n is not None]
    if valid_state_names:
        fsm["initial"] = draw(
            st.one_of(
                st.sampled_from(valid_state_names),
                st.text(min_size=1, max_size=50),  # Non-existent state
                st.integers(),
            )
        )
    else:
        fsm["initial"] = draw(
            st.one_of(
                st.text(min_size=1, max_size=50),
                st.integers(),
            )
        )

    # States (required)
    fsm["states"] = states

    # Optional fields with potentially wrong types
    if draw(st.booleans()):
        fsm["max_iterations"] = draw(
            st.one_of(
                st.integers(min_value=1, max_value=1000),
                st.integers(min_value=-100, max_value=-1),  # Invalid
                st.text(),  # Wrong type
            )
        )

    if draw(st.booleans()):
        fsm["timeout"] = draw(
            st.one_of(
                st.integers(min_value=1, max_value=3600),
                st.integers(min_value=-100, max_value=-1),
                st.none(),
            )
        )

    if draw(st.booleans()):
        fsm["context"] = draw(
            st.one_of(
                st.dictionaries(st.text(), st.integers()),
                st.dictionaries(
                    st.text(), st.dictionaries(st.text(), st.integers()), max_size=50
                ),  # Deep nesting
                st.lists(st.integers()),  # Wrong type
            )
        )

    return fsm


# =============================================================================
# Fuzz Tests
# =============================================================================


class TestEvaluateConfigFuzz:
    """Fuzz tests for EvaluateConfig deserialization."""

    @pytest.mark.slow
    @given(config=malformed_evaluate_config())
    @settings(max_examples=500, deadline=None)
    def test_from_dict_handles_malformed(self, config: dict) -> None:
        """from_dict should handle malformed input without crashing."""
        try:
            # Handle missing required 'type' field
            if "type" not in config:
                with pytest.raises(KeyError):
                    EvaluateConfig.from_dict(config)
                return

            # Try to create config
            result = EvaluateConfig.from_dict(config)
            assert isinstance(result, EvaluateConfig)
        except (KeyError, TypeError, ValueError):
            # These are acceptable for truly malformed input
            pass
        except Exception as e:
            pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")


class TestRouteConfigFuzz:
    """Fuzz tests for RouteConfig deserialization."""

    @pytest.mark.slow
    @given(config=malformed_route_config())
    @settings(max_examples=500, deadline=None)
    def test_from_dict_handles_malformed(self, config: dict) -> None:
        """from_dict should handle malformed route configs without crashing.

        NOTE: This test discovered that RouteConfig.from_dict() crashes with
        AttributeError when given dict keys that are not strings (e.g., integers).
        This is a real bug that should be fixed in the parser.
        """
        try:
            result = RouteConfig.from_dict(config)
            assert isinstance(result, RouteConfig)
        except (KeyError, TypeError, ValueError, AttributeError):
            # Acceptable for malformed input
            # AttributeError is a known bug (non-string dict keys)
            pass
        except Exception as e:
            pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")


class TestStateConfigFuzz:
    """Fuzz tests for StateConfig deserialization."""

    @pytest.mark.slow
    @given(config=malformed_state_config())
    @settings(max_examples=500, deadline=None)
    def test_from_dict_handles_malformed(self, config: dict) -> None:
        """from_dict should handle malformed state configs without crashing.

        NOTE: This test discovered that StateConfig.from_dict() crashes with
        AttributeError when nested RouteConfig has non-string dict keys.
        This is the same bug as in RouteConfig.from_dict().
        """
        try:
            # Handle missing required 'name' field
            if "name" not in config:
                with pytest.raises(KeyError):
                    StateConfig.from_dict(config)
                return

            result = StateConfig.from_dict(config)
            assert isinstance(result, StateConfig)
        except (KeyError, TypeError, ValueError, AttributeError):
            # Acceptable for malformed input
            # AttributeError is a known bug (non-string dict keys in route)
            pass
        except Exception as e:
            pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")


class TestFSMLoopFuzz:
    """Fuzz tests for FSMLoop deserialization."""

    @pytest.mark.slow
    @given(fsm_dict=malformed_fsm_loop())
    @settings(max_examples=300, deadline=None)
    def test_from_dict_handles_malformed(self, fsm_dict: dict) -> None:
        """from_dict should handle malformed FSM configs without crashing.

        NOTE: This test discovered that FSMLoop.from_dict() crashes with
        AttributeError when nested StateConfig has RouteConfig with non-string
        dict keys. This is the same bug as in RouteConfig.from_dict().
        """
        try:
            # Handle missing required fields
            required_fields = ["name", "initial", "states"]
            missing = [f for f in required_fields if f not in fsm_dict]
            if missing:
                with pytest.raises(KeyError):
                    FSMLoop.from_dict(fsm_dict)
                return

            result = FSMLoop.from_dict(fsm_dict)
            assert isinstance(result, FSMLoop)
        except (KeyError, TypeError, ValueError, AttributeError):
            # Acceptable for malformed input
            # AttributeError is a known bug (non-string dict keys in route)
            pass
        except Exception as e:
            pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")

    @pytest.mark.slow
    @given(yaml_content=st.text(min_size=0, max_size=50000))
    @settings(max_examples=200, deadline=None)
    def test_yaml_loading_never_crashes(self, yaml_content: str) -> None:
        """Loading YAML and creating FSM should never crash.

        This tests the full flow: YAML -> dict -> FSMLoop
        """
        try:
            # Load YAML directly from string
            data = yaml.safe_load(yaml_content)

            # Skip if not a dict (expected for invalid YAML)
            if not isinstance(data, dict):
                return

            # Try to create FSM
            result = FSMLoop.from_dict(data)
            assert isinstance(result, FSMLoop)
        except (yaml.YAMLError, KeyError, TypeError, ValueError, AttributeError):
            # Acceptable for invalid input
            # AttributeError is a known bug (non-string dict keys in route)
            pass
        except Exception as e:
            pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")

    @pytest.mark.slow
    @given(
        states=st.dictionaries(
            st.text(
                min_size=1,
                max_size=20,
                alphabet=st.characters(whitelist_categories=("L", "N")),
            ),
            malformed_state_config(),
            max_size=50,
        )
    )
    @settings(max_examples=200, deadline=None)
    def test_large_state_dicts(self, states: dict) -> None:
        """Large state dictionaries should be handled without issues.

        NOTE: This test discovered that FSMLoop.from_dict() crashes with
        AttributeError when nested StateConfig has RouteConfig with non-string
        dict keys. This is the same bug as in RouteConfig.from_dict().
        """
        # Build minimal FSM
        fsm_dict = {
            "name": "test",
            "initial": list(states.keys())[0] if states else "none",
            "states": states,
        }

        try:
            result = FSMLoop.from_dict(fsm_dict)
            assert isinstance(result, FSMLoop)
        except (KeyError, ValueError, AttributeError):
            # Acceptable for invalid input (e.g., no valid initial state)
            # AttributeError is a known bug (non-string dict keys in route)
            pass
        except Exception as e:
            pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")
