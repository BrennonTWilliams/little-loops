"""Tests for FSM loop template inheritance via `from:` (FEAT-1308).

Tests cover:
- resolve_inheritance: simple/deep override, multi-level chains, cycle detection,
  missing parent, route dict merging, fragment+from interaction.
- Integration with load_and_validate (KNOWN_TOP_LEVEL_KEYS, no spurious warnings).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from little_loops.fsm.fragments import resolve_inheritance
from little_loops.fsm.validation import load_and_validate


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip())
    return path


# ---------------------------------------------------------------------------
# resolve_inheritance unit tests
# ---------------------------------------------------------------------------


class TestResolveInheritance:
    def test_no_from_field_returns_unchanged(self, tmp_path: Path) -> None:
        data = {"name": "foo", "initial": "a", "states": {"a": {"action": "x"}}}
        result = resolve_inheritance(data, tmp_path)
        assert result == data

    def test_simple_inheritance_overrides_state_field(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "parent.yaml",
            """
            name: parent
            initial: a
            states:
              a:
                action_type: shell
                action: "echo hi"
                evaluate:
                  type: exit_code
                on_yes: done
              done:
                terminal: true
            """,
        )
        child = {
            "name": "child",
            "from": "parent",
            "states": {"a": {"action": "echo bye"}},
        }
        result = resolve_inheritance(child, tmp_path)
        assert result["name"] == "child"
        assert "from" not in result
        assert result["initial"] == "a"
        assert result["states"]["a"]["action"] == "echo bye"
        # Parent fields preserved
        assert result["states"]["a"]["action_type"] == "shell"
        assert result["states"]["a"]["on_yes"] == "done"
        assert result["states"]["a"]["evaluate"] == {"type": "exit_code"}

    def test_deep_override_preserves_unmodified_parent_keys(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "parent.yaml",
            """
            name: parent
            initial: a
            states:
              a:
                action_type: shell
                action: "ls"
                evaluate:
                  type: output_numeric
                  operator: gt
                  target: 10
            """,
        )
        child = {
            "name": "child",
            "from": "parent",
            "states": {"a": {"evaluate": {"target": 100}}},
        }
        result = resolve_inheritance(child, tmp_path)
        ev = result["states"]["a"]["evaluate"]
        assert ev["target"] == 100  # child override
        assert ev["type"] == "output_numeric"  # parent preserved
        assert ev["operator"] == "gt"  # parent preserved

    def test_top_level_field_override(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "parent.yaml",
            """
            name: parent
            description: Parent description
            category: parent-cat
            labels: [a, b]
            initial: s
            states:
              s:
                action: "x"
            """,
        )
        child = {
            "name": "child",
            "from": "parent",
            "description": "Child description",
            "category": "child-cat",
            "labels": ["c"],
        }
        result = resolve_inheritance(child, tmp_path)
        assert result["description"] == "Child description"
        assert result["category"] == "child-cat"
        assert result["labels"] == ["c"]  # lists are replaced, not merged

    def test_route_dict_deep_merges_by_verdict(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "parent.yaml",
            """
            name: parent
            initial: s
            states:
              s:
                action: "x"
                route:
                  "yes": done
                  "no": retry
                  error: fail
            """,
        )
        child = {
            "name": "child",
            "from": "parent",
            "states": {"s": {"route": {"no": "alternate"}}},
        }
        result = resolve_inheritance(child, tmp_path)
        route = result["states"]["s"]["route"]
        assert route["no"] == "alternate"  # child override
        assert route["yes"] == "done"  # parent preserved
        assert route["error"] == "fail"  # parent preserved

    def test_multi_level_chain(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "grand.yaml",
            """
            name: grand
            initial: s
            states:
              s:
                action_type: shell
                action: "g"
                on_yes: done
            """,
        )
        _write(
            tmp_path,
            "parent.yaml",
            """
            name: parent
            from: grand
            states:
              s:
                action: "p"
            """,
        )
        child = {
            "name": "child",
            "from": "parent",
            "states": {"s": {"on_yes": "alt_done"}},
        }
        result = resolve_inheritance(child, tmp_path)
        assert result["initial"] == "s"  # from grand
        assert result["states"]["s"]["action_type"] == "shell"  # from grand
        assert result["states"]["s"]["action"] == "p"  # parent override of grand
        assert result["states"]["s"]["on_yes"] == "alt_done"  # child override of grand

    def test_circular_chain_raises(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "a.yaml",
            """
            name: a
            from: b
            initial: s
            states:
              s:
                action: "x"
            """,
        )
        _write(
            tmp_path,
            "b.yaml",
            """
            name: b
            from: a
            initial: s
            states:
              s:
                action: "y"
            """,
        )
        child = {"name": "c", "from": "a"}
        with pytest.raises(ValueError, match="Circular .* chain"):
            resolve_inheritance(child, tmp_path)

    def test_self_reference_raises(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "loop.yaml",
            """
            name: loop
            from: loop
            initial: s
            states:
              s:
                action: "x"
            """,
        )
        child = {"name": "c", "from": "loop"}
        # First load: parent loop has from: loop, recursing on it should detect cycle
        with pytest.raises(ValueError, match="Circular .* chain"):
            resolve_inheritance(child, tmp_path)

    def test_missing_parent_raises(self, tmp_path: Path) -> None:
        child = {"name": "c", "from": "does-not-exist"}
        with pytest.raises(FileNotFoundError):
            resolve_inheritance(child, tmp_path)

    def test_from_key_stripped_from_result(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "parent.yaml",
            """
            name: parent
            initial: s
            states:
              s:
                action: "x"
            """,
        )
        child = {"name": "c", "from": "parent"}
        result = resolve_inheritance(child, tmp_path)
        assert "from" not in result

    def test_from_must_be_string(self, tmp_path: Path) -> None:
        child = {"name": "c", "from": 42}
        with pytest.raises(ValueError, match="must be a string"):
            resolve_inheritance(child, tmp_path)

    def test_parent_must_be_mapping(self, tmp_path: Path) -> None:
        _write(tmp_path, "bad.yaml", "- just\n- a list\n")
        child = {"name": "c", "from": "bad"}
        with pytest.raises(ValueError, match="not a YAML mapping"):
            resolve_inheritance(child, tmp_path)


# ---------------------------------------------------------------------------
# Integration with fragments
# ---------------------------------------------------------------------------


class TestFromCombinedWithFragments:
    def test_parent_fragments_visible_to_child(self, tmp_path: Path) -> None:
        """Parent uses import:/fragments:; child inherits and resolves fragments after merge."""
        _write(
            tmp_path,
            "lib/common.yaml",
            """
            fragments:
              shell_exit:
                action_type: shell
                evaluate:
                  type: exit_code
            """,
        )
        _write(
            tmp_path,
            "parent.yaml",
            """
            name: parent
            initial: lint
            import:
              - lib/common.yaml
            states:
              lint:
                fragment: shell_exit
                action: "ruff check"
                on_yes: done
              done:
                terminal: true
            """,
        )
        child_yaml = _write(
            tmp_path,
            "child.yaml",
            """
            name: child
            from: parent
            states:
              lint:
                action: "ruff format --check"
            """,
        )
        fsm, warnings = load_and_validate(child_yaml)
        assert fsm.name == "child"
        assert fsm.initial == "lint"
        assert fsm.states["lint"].action_type == "shell"  # from fragment
        assert fsm.states["lint"].action == "ruff format --check"  # child override
        assert fsm.states["lint"].evaluate is not None
        assert fsm.states["lint"].evaluate.type == "exit_code"  # from fragment


# ---------------------------------------------------------------------------
# End-to-end load_and_validate
# ---------------------------------------------------------------------------


class TestLoadAndValidateEndToEnd:
    def test_inherited_loop_loads_and_validates(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "parent.yaml",
            """
            name: parent
            description: A parent loop
            initial: a
            states:
              a:
                action_type: shell
                action: "echo hi"
                evaluate:
                  type: exit_code
                on_yes: done
              done:
                terminal: true
            """,
        )
        child_path = _write(
            tmp_path,
            "child.yaml",
            """
            name: child
            from: parent
            description: A child loop
            states:
              a:
                action: "echo bye"
            """,
        )
        fsm, warnings = load_and_validate(child_path)
        assert fsm.name == "child"
        assert fsm.description == "A child loop"
        assert fsm.initial == "a"
        assert fsm.states["a"].action == "echo bye"
        assert fsm.states["a"].action_type == "shell"

    def test_no_unknown_key_warning_for_from(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "parent.yaml",
            """
            name: parent
            initial: s
            states:
              s:
                action: "x"
                action_type: shell
                evaluate:
                  type: exit_code
                on_yes: done
              done:
                terminal: true
            """,
        )
        child_path = _write(
            tmp_path,
            "child.yaml",
            """
            name: child
            from: parent
            """,
        )
        fsm, warnings = load_and_validate(child_path)
        # No warning about `from` being unknown
        for w in warnings:
            assert "from" not in w.message.lower() or "unknown" not in w.message.lower()

    def test_child_can_omit_initial_and_states(self, tmp_path: Path) -> None:
        """A child that only overrides description should still validate (parent provides initial/states)."""
        _write(
            tmp_path,
            "parent.yaml",
            """
            name: parent
            initial: s
            states:
              s:
                action_type: shell
                action: "x"
                evaluate:
                  type: exit_code
                on_yes: done
              done:
                terminal: true
            """,
        )
        child_path = _write(
            tmp_path,
            "child.yaml",
            """
            name: child
            from: parent
            description: Just a different description
            """,
        )
        fsm, _ = load_and_validate(child_path)
        assert fsm.name == "child"
        assert fsm.description == "Just a different description"
        assert fsm.initial == "s"

    def test_missing_parent_in_load_and_validate(self, tmp_path: Path) -> None:
        child_path = _write(
            tmp_path,
            "child.yaml",
            """
            name: child
            from: nonexistent-parent
            """,
        )
        with pytest.raises(FileNotFoundError):
            load_and_validate(child_path)
