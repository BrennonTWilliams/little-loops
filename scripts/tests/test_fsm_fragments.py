"""Tests for FSM fragment library resolution (FEAT-937).

Tests cover:
- _deep_merge: recursive merge semantics
- resolve_fragments: import loading, namespace merging, state expansion
- Integration with load_and_validate (KNOWN_TOP_LEVEL_KEYS, no spurious warnings)
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from little_loops.fsm.fragments import _deep_merge, resolve_fragments

# ---------------------------------------------------------------------------
# _deep_merge tests
# ---------------------------------------------------------------------------


class TestDeepMerge:
    def test_override_wins_at_top_level(self) -> None:
        base = {"action_type": "shell", "evaluate": {"type": "exit_code"}}
        override = {"action_type": "prompt"}
        result = _deep_merge(base, override)
        assert result["action_type"] == "prompt"
        assert result["evaluate"] == {"type": "exit_code"}

    def test_base_keys_not_in_override_are_kept(self) -> None:
        base = {"action_type": "shell", "on_yes": "done"}
        override = {"action": "echo hi"}
        result = _deep_merge(base, override)
        assert result["action_type"] == "shell"
        assert result["on_yes"] == "done"
        assert result["action"] == "echo hi"

    def test_nested_dict_deep_merges(self) -> None:
        base = {"evaluate": {"type": "output_numeric", "operator": "lt", "target": 3}}
        override = {"evaluate": {"target": 5}}
        result = _deep_merge(base, override)
        assert result["evaluate"]["type"] == "output_numeric"
        assert result["evaluate"]["operator"] == "lt"
        assert result["evaluate"]["target"] == 5

    def test_nested_override_wins_scalar(self) -> None:
        base = {"evaluate": {"type": "exit_code"}}
        override = {"evaluate": {"type": "output_numeric", "operator": "lt", "target": 3}}
        result = _deep_merge(base, override)
        assert result["evaluate"]["type"] == "output_numeric"
        assert result["evaluate"]["operator"] == "lt"

    def test_non_mutating(self) -> None:
        base = {"evaluate": {"type": "exit_code"}}
        override = {"action": "echo hi"}
        original_base = {"evaluate": {"type": "exit_code"}}
        _deep_merge(base, override)
        assert base == original_base

    def test_override_scalar_replaces_nested_dict(self) -> None:
        """When override has a non-dict where base has a dict, override wins."""
        base = {"evaluate": {"type": "exit_code"}}
        override = {"evaluate": "disabled"}
        result = _deep_merge(base, override)
        assert result["evaluate"] == "disabled"

    def test_empty_base(self) -> None:
        result = _deep_merge({}, {"action": "echo hi"})
        assert result == {"action": "echo hi"}

    def test_empty_override(self) -> None:
        result = _deep_merge({"action": "echo hi"}, {})
        assert result == {"action": "echo hi"}


# ---------------------------------------------------------------------------
# resolve_fragments tests — no imports, inline fragments: block only
# ---------------------------------------------------------------------------


class TestResolveFragmentsInlineOnly:
    def test_no_fragments_is_noop(self, tmp_path: Path) -> None:
        raw = {
            "name": "test",
            "initial": "start",
            "states": {
                "start": {"action": "echo hi", "terminal": True},
            },
        }
        result = resolve_fragments(raw, tmp_path)
        assert result == raw

    def test_fragment_absent_in_state_is_noop(self, tmp_path: Path) -> None:
        raw = {
            "name": "test",
            "initial": "start",
            "fragments": {
                "shell_exit": {"action_type": "shell", "evaluate": {"type": "exit_code"}},
            },
            "states": {
                "start": {"action": "echo hi", "terminal": True},
            },
        }
        result = resolve_fragments(raw, tmp_path)
        assert result["states"]["start"] == {"action": "echo hi", "terminal": True}

    def test_inline_fragment_expands_into_state(self, tmp_path: Path) -> None:
        raw = {
            "name": "test",
            "initial": "run",
            "fragments": {
                "shell_exit": {"action_type": "shell", "evaluate": {"type": "exit_code"}},
            },
            "states": {
                "run": {
                    "fragment": "shell_exit",
                    "action": "echo hi",
                    "on_yes": "done",
                    "on_no": "fail",
                },
                "done": {"terminal": True},
                "fail": {"terminal": True},
            },
        }
        result = resolve_fragments(raw, tmp_path)
        state = result["states"]["run"]
        assert state["action_type"] == "shell"
        assert state["evaluate"] == {"type": "exit_code"}
        assert state["action"] == "echo hi"
        assert state["on_yes"] == "done"
        assert "fragment" not in state

    def test_state_keys_override_fragment_keys(self, tmp_path: Path) -> None:
        raw = {
            "name": "test",
            "initial": "run",
            "fragments": {
                "numeric": {
                    "action_type": "shell",
                    "evaluate": {"type": "output_numeric", "operator": "lt", "target": 3},
                },
            },
            "states": {
                "run": {
                    "fragment": "numeric",
                    "action": "wc -l file.txt",
                    "evaluate": {"target": 10},
                    "on_yes": "done",
                    "on_no": "fail",
                },
                "done": {"terminal": True},
                "fail": {"terminal": True},
            },
        }
        result = resolve_fragments(raw, tmp_path)
        state = result["states"]["run"]
        # State-level evaluate.target overrides fragment's target
        assert state["evaluate"]["type"] == "output_numeric"
        assert state["evaluate"]["operator"] == "lt"
        assert state["evaluate"]["target"] == 10

    def test_unknown_fragment_raises_valueerror(self, tmp_path: Path) -> None:
        raw = {
            "name": "test",
            "initial": "run",
            "states": {
                "run": {"fragment": "nonexistent", "action": "echo hi", "on_yes": "done"},
                "done": {"terminal": True},
            },
        }
        with pytest.raises(ValueError, match="nonexistent"):
            resolve_fragments(raw, tmp_path)

    def test_fragment_key_consumed_not_in_result(self, tmp_path: Path) -> None:
        raw = {
            "name": "test",
            "initial": "run",
            "fragments": {"shell_exit": {"action_type": "shell"}},
            "states": {
                "run": {"fragment": "shell_exit", "action": "echo hi", "terminal": True},
            },
        }
        result = resolve_fragments(raw, tmp_path)
        assert "fragment" not in result["states"]["run"]


# ---------------------------------------------------------------------------
# resolve_fragments tests — with import: file loading
# ---------------------------------------------------------------------------


class TestResolveFragmentsImport:
    def _write_lib(self, lib_dir: Path, content: str) -> Path:
        lib_dir.mkdir(parents=True, exist_ok=True)
        lib_file = lib_dir / "common.yaml"
        lib_file.write_text(textwrap.dedent(content))
        return lib_file

    def test_import_and_use_fragment(self, tmp_path: Path) -> None:
        self._write_lib(
            tmp_path / "lib",
            """\
            fragments:
              shell_exit:
                action_type: shell
                evaluate:
                  type: exit_code
            """,
        )
        raw = {
            "name": "test",
            "initial": "run",
            "import": ["lib/common.yaml"],
            "states": {
                "run": {
                    "fragment": "shell_exit",
                    "action": "ruff check .",
                    "on_yes": "done",
                    "on_no": "fail",
                },
                "done": {"terminal": True},
                "fail": {"terminal": True},
            },
        }
        result = resolve_fragments(raw, tmp_path)
        state = result["states"]["run"]
        assert state["action_type"] == "shell"
        assert state["evaluate"]["type"] == "exit_code"
        assert state["action"] == "ruff check ."
        assert "fragment" not in state

    def test_missing_import_file_raises_filenotfounderror(self, tmp_path: Path) -> None:
        raw = {
            "name": "test",
            "initial": "run",
            "import": ["lib/missing.yaml"],
            "states": {"run": {"action": "echo hi", "terminal": True}},
        }
        with pytest.raises(FileNotFoundError, match="missing.yaml"):
            resolve_fragments(raw, tmp_path)

    def test_local_fragments_override_imported(self, tmp_path: Path) -> None:
        """Local fragments: block takes precedence over same-name imported fragment."""
        self._write_lib(
            tmp_path / "lib",
            """\
            fragments:
              shell_exit:
                action_type: shell
                evaluate:
                  type: exit_code
            """,
        )
        raw = {
            "name": "test",
            "initial": "run",
            "import": ["lib/common.yaml"],
            "fragments": {
                # Override shell_exit with a different action_type
                "shell_exit": {"action_type": "prompt"},
            },
            "states": {
                "run": {
                    "fragment": "shell_exit",
                    "action": "echo hi",
                    "terminal": True,
                },
            },
        }
        result = resolve_fragments(raw, tmp_path)
        assert result["states"]["run"]["action_type"] == "prompt"

    def test_multiple_imports_merged_in_order(self, tmp_path: Path) -> None:
        """Later imports override earlier imports for the same fragment name."""
        lib1 = tmp_path / "lib" / "lib1.yaml"
        lib2 = tmp_path / "lib" / "lib2.yaml"
        (tmp_path / "lib").mkdir()
        lib1.write_text("fragments:\n  shared:\n    action_type: shell\n")
        lib2.write_text("fragments:\n  shared:\n    action_type: prompt\n")
        raw = {
            "name": "test",
            "initial": "run",
            "import": ["lib/lib1.yaml", "lib/lib2.yaml"],
            "states": {
                "run": {"fragment": "shared", "action": "echo hi", "terminal": True},
            },
        }
        result = resolve_fragments(raw, tmp_path)
        # lib2 loaded second, so its version wins
        assert result["states"]["run"]["action_type"] == "prompt"

    def test_import_path_relative_to_loop_dir(self, tmp_path: Path) -> None:
        """Import paths are relative to loop_dir, not cwd."""
        subdir = tmp_path / "nested"
        subdir.mkdir()
        self._write_lib(
            subdir / "lib",
            """\
            fragments:
              ping:
                action_type: shell
            """,
        )
        raw = {
            "name": "test",
            "initial": "run",
            "import": ["lib/common.yaml"],
            "states": {
                "run": {"fragment": "ping", "action": "ping", "terminal": True},
            },
        }
        result = resolve_fragments(raw, subdir)
        assert result["states"]["run"]["action_type"] == "shell"


# ---------------------------------------------------------------------------
# Integration: load_and_validate with import: no spurious warnings
# ---------------------------------------------------------------------------


class TestLoadAndValidateIntegration:
    def test_import_and_fragments_keys_no_warning(self, tmp_path: Path) -> None:
        """KNOWN_TOP_LEVEL_KEYS includes import and fragments — no unknown-key warning."""
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()
        (lib_dir / "common.yaml").write_text(
            "fragments:\n  shell_exit:\n    action_type: shell\n    evaluate:\n      type: exit_code\n"
        )
        loop_yaml = tmp_path / "test-loop.yaml"
        loop_yaml.write_text(
            textwrap.dedent(
                """\
                name: test-loop
                initial: run
                import:
                  - lib/common.yaml
                states:
                  run:
                    fragment: shell_exit
                    action: "echo hi"
                    on_yes: done
                    on_no: fail
                  done:
                    terminal: true
                  fail:
                    terminal: true
                """
            )
        )
        from little_loops.fsm.validation import load_and_validate

        fsm, warnings = load_and_validate(loop_yaml)
        # No unknown-key warnings for import/fragments
        unknown_warnings = [w for w in warnings if "Unknown top-level keys" in str(w)]
        assert unknown_warnings == []
        # Fragment was resolved: state has action_type from fragment
        assert fsm.states["run"].action_type == "shell"
        assert fsm.states["run"].evaluate is not None
        assert fsm.states["run"].evaluate.type == "exit_code"

    def test_fragments_key_no_warning(self, tmp_path: Path) -> None:
        """Inline fragments: block also produces no unknown-key warning."""
        loop_yaml = tmp_path / "test-loop.yaml"
        loop_yaml.write_text(
            textwrap.dedent(
                """\
                name: test-loop
                initial: run
                fragments:
                  shell_exit:
                    action_type: shell
                    evaluate:
                      type: exit_code
                states:
                  run:
                    fragment: shell_exit
                    action: "echo hi"
                    on_yes: done
                    on_no: fail
                  done:
                    terminal: true
                  fail:
                    terminal: true
                """
            )
        )
        from little_loops.fsm.validation import load_and_validate

        fsm, warnings = load_and_validate(loop_yaml)
        unknown_warnings = [w for w in warnings if "Unknown top-level keys" in str(w)]
        assert unknown_warnings == []


# ---------------------------------------------------------------------------
# Built-in loop migration: shell_exit fragment resolves correctly
# ---------------------------------------------------------------------------


class TestBuiltinLoopMigration:
    def test_builtin_loops_load_after_migration(self) -> None:
        """All 10 built-in loops that use fragment: shell_exit must still validate."""
        from little_loops.fsm.validation import load_and_validate

        loops_dir = Path(__file__).parent.parent / "little_loops" / "loops"
        # The 10 migration targets
        migration_targets = [
            "dead-code-cleanup.yaml",
            "docs-sync.yaml",
            "fix-quality-and-tests.yaml",
            "harness-multi-item.yaml",
            "harness-single-shot.yaml",
            "issue-refinement.yaml",
            "prompt-across-issues.yaml",
            "refine-to-ready-issue.yaml",
            "sprint-build-and-validate.yaml",
            "test-coverage-improvement.yaml",
        ]
        for loop_name in migration_targets:
            path = loops_dir / loop_name
            assert path.exists(), f"Missing built-in loop: {path}"
            # Should not raise
            fsm, warnings = load_and_validate(path)
            assert fsm is not None, f"Failed to load {loop_name}"
