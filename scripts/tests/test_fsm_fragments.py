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

    def test_llm_gate_inline_expands_action_type_and_evaluate_type(self, tmp_path: Path) -> None:
        raw = {
            "name": "test",
            "initial": "check",
            "fragments": {
                "llm_gate": {"action_type": "prompt", "evaluate": {"type": "llm_structured"}},
            },
            "states": {
                "check": {
                    "fragment": "llm_gate",
                    "action": "Is the task complete? Answer YES or NO.",
                    "evaluate": {"prompt": "Is the task complete?"},
                    "on_yes": "done",
                    "on_no": "retry",
                },
                "done": {"terminal": True},
                "retry": {"terminal": True},
            },
        }
        result = resolve_fragments(raw, tmp_path)
        state = result["states"]["check"]
        assert state["action_type"] == "prompt"
        assert state["evaluate"]["type"] == "llm_structured"
        assert state["evaluate"]["prompt"] == "Is the task complete?"
        assert "fragment" not in state

    def test_llm_gate_inline_evaluate_deep_merges(self, tmp_path: Path) -> None:
        """Caller's evaluate.prompt merges with fragment's evaluate.type (not replaced)."""
        raw = {
            "name": "test",
            "initial": "check",
            "fragments": {
                "llm_gate": {"action_type": "prompt", "evaluate": {"type": "llm_structured"}},
            },
            "states": {
                "check": {
                    "fragment": "llm_gate",
                    "action": "Done?",
                    "evaluate": {"prompt": "Done?"},
                    "on_yes": "done",
                    "on_no": "retry",
                },
                "done": {"terminal": True},
                "retry": {"terminal": True},
            },
        }
        result = resolve_fragments(raw, tmp_path)
        state = result["states"]["check"]
        # Fragment provides type; caller provides prompt; both survive deep merge
        assert state["evaluate"]["type"] == "llm_structured"
        assert state["evaluate"]["prompt"] == "Done?"

    def test_numeric_gate_inline_expands_action_type_and_evaluate_type(
        self, tmp_path: Path
    ) -> None:
        raw = {
            "name": "test",
            "initial": "count",
            "fragments": {
                "numeric_gate": {"action_type": "shell", "evaluate": {"type": "output_numeric"}},
            },
            "states": {
                "count": {
                    "fragment": "numeric_gate",
                    "action": "echo 5",
                    "evaluate": {"operator": "gt", "target": 0},
                    "on_yes": "review",
                    "on_no": "done",
                },
                "review": {"terminal": True},
                "done": {"terminal": True},
            },
        }
        result = resolve_fragments(raw, tmp_path)
        state = result["states"]["count"]
        assert state["action_type"] == "shell"
        assert state["evaluate"]["type"] == "output_numeric"
        assert state["evaluate"]["operator"] == "gt"
        assert state["evaluate"]["target"] == 0
        assert "fragment" not in state

    def test_numeric_gate_inline_evaluate_deep_merges(self, tmp_path: Path) -> None:
        """Caller's evaluate.operator+target merge with fragment's evaluate.type."""
        raw = {
            "name": "test",
            "initial": "count",
            "fragments": {
                "numeric_gate": {"action_type": "shell", "evaluate": {"type": "output_numeric"}},
            },
            "states": {
                "count": {
                    "fragment": "numeric_gate",
                    "action": "wc -l file.txt",
                    "evaluate": {"operator": "lt", "target": 10},
                    "on_yes": "ok",
                    "on_no": "fail",
                },
                "ok": {"terminal": True},
                "fail": {"terminal": True},
            },
        }
        result = resolve_fragments(raw, tmp_path)
        state = result["states"]["count"]
        assert state["evaluate"]["type"] == "output_numeric"
        assert state["evaluate"]["operator"] == "lt"
        assert state["evaluate"]["target"] == 10


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
        with pytest.raises(FileNotFoundError, match=r"missing\.yaml"):
            resolve_fragments(raw, tmp_path)

    def test_builtin_lib_resolves_when_local_absent(self, tmp_path: Path) -> None:
        """When lib/ doesn't exist locally, resolve_fragments falls back to built-in loops dir."""
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
        assert "fragment" not in state

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

    def test_import_llm_gate_from_lib(self, tmp_path: Path) -> None:
        """llm_gate loaded via import expands action_type and evaluate.type correctly."""
        self._write_lib(
            tmp_path / "lib",
            """\
            fragments:
              llm_gate:
                action_type: prompt
                evaluate:
                  type: llm_structured
            """,
        )
        raw = {
            "name": "test",
            "initial": "check",
            "import": ["lib/common.yaml"],
            "states": {
                "check": {
                    "fragment": "llm_gate",
                    "action": "Is the task complete?",
                    "evaluate": {"prompt": "Is it done?"},
                    "on_yes": "done",
                    "on_no": "retry",
                },
                "done": {"terminal": True},
                "retry": {"terminal": True},
            },
        }
        result = resolve_fragments(raw, tmp_path)
        state = result["states"]["check"]
        assert state["action_type"] == "prompt"
        assert state["evaluate"]["type"] == "llm_structured"
        assert state["evaluate"]["prompt"] == "Is it done?"
        assert "fragment" not in state

    def test_import_numeric_gate_from_lib(self, tmp_path: Path) -> None:
        """numeric_gate loaded via import expands action_type and evaluate.type correctly."""
        self._write_lib(
            tmp_path / "lib",
            """\
            fragments:
              numeric_gate:
                action_type: shell
                evaluate:
                  type: output_numeric
            """,
        )
        raw = {
            "name": "test",
            "initial": "count",
            "import": ["lib/common.yaml"],
            "states": {
                "count": {
                    "fragment": "numeric_gate",
                    "action": "echo 5",
                    "evaluate": {"operator": "gt", "target": 0},
                    "on_yes": "review",
                    "on_no": "done",
                },
                "review": {"terminal": True},
                "done": {"terminal": True},
            },
        }
        result = resolve_fragments(raw, tmp_path)
        state = result["states"]["count"]
        assert state["action_type"] == "shell"
        assert state["evaluate"]["type"] == "output_numeric"
        assert state["evaluate"]["operator"] == "gt"
        assert state["evaluate"]["target"] == 0
        assert "fragment" not in state


# ---------------------------------------------------------------------------
# Real lib/common.yaml: verify llm_gate and numeric_gate are present
# ---------------------------------------------------------------------------


class TestCommonYamlNewFragments:
    """Tests that llm_gate and numeric_gate exist in the real lib/common.yaml."""

    @staticmethod
    def _load_common_yaml() -> dict:
        import yaml

        lib_path = Path(__file__).parent.parent / "little_loops" / "loops" / "lib" / "common.yaml"
        with open(lib_path) as f:
            return yaml.safe_load(f)

    def test_llm_gate_defined_in_common_yaml(self) -> None:
        data = self._load_common_yaml()
        assert "llm_gate" in data["fragments"], "llm_gate fragment missing from lib/common.yaml"

    def test_llm_gate_has_correct_action_type(self) -> None:
        data = self._load_common_yaml()
        assert data["fragments"]["llm_gate"]["action_type"] == "prompt"

    def test_llm_gate_has_correct_evaluate_type(self) -> None:
        data = self._load_common_yaml()
        assert data["fragments"]["llm_gate"]["evaluate"]["type"] == "llm_structured"

    def test_numeric_gate_defined_in_common_yaml(self) -> None:
        data = self._load_common_yaml()
        assert "numeric_gate" in data["fragments"], (
            "numeric_gate fragment missing from lib/common.yaml"
        )

    def test_numeric_gate_has_correct_action_type(self) -> None:
        data = self._load_common_yaml()
        assert data["fragments"]["numeric_gate"]["action_type"] == "shell"

    def test_numeric_gate_has_correct_evaluate_type(self) -> None:
        data = self._load_common_yaml()
        assert data["fragments"]["numeric_gate"]["evaluate"]["type"] == "output_numeric"

    def test_llm_gate_resolves_from_real_common_yaml(self) -> None:
        """Full resolve_fragments integration against the real lib/common.yaml."""
        loops_dir = Path(__file__).parent.parent / "little_loops" / "loops"
        raw = {
            "name": "test",
            "initial": "check",
            "import": ["lib/common.yaml"],
            "states": {
                "check": {
                    "fragment": "llm_gate",
                    "action": "Is the task complete?",
                    "evaluate": {"prompt": "Is it done?"},
                    "on_yes": "done",
                    "on_no": "retry",
                },
                "done": {"terminal": True},
                "retry": {"terminal": True},
            },
        }
        result = resolve_fragments(raw, loops_dir)
        state = result["states"]["check"]
        assert state["action_type"] == "prompt"
        assert state["evaluate"]["type"] == "llm_structured"
        assert state["evaluate"]["prompt"] == "Is it done?"
        assert "fragment" not in state

    def test_numeric_gate_resolves_from_real_common_yaml(self) -> None:
        """Full resolve_fragments integration against the real lib/common.yaml."""
        loops_dir = Path(__file__).parent.parent / "little_loops" / "loops"
        raw = {
            "name": "test",
            "initial": "count",
            "import": ["lib/common.yaml"],
            "states": {
                "count": {
                    "fragment": "numeric_gate",
                    "action": "echo 5",
                    "evaluate": {"operator": "gt", "target": 0},
                    "on_yes": "review",
                    "on_no": "done",
                },
                "review": {"terminal": True},
                "done": {"terminal": True},
            },
        }
        result = resolve_fragments(raw, loops_dir)
        state = result["states"]["count"]
        assert state["action_type"] == "shell"
        assert state["evaluate"]["type"] == "output_numeric"
        assert state["evaluate"]["operator"] == "gt"
        assert state["evaluate"]["target"] == 0
        assert "fragment" not in state


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


# ---------------------------------------------------------------------------
# Real lib/cli.yaml: verify ll- CLI tool fragments are present and correct
# ---------------------------------------------------------------------------


class TestCliYamlFragments:
    """Tests that ll- CLI tool fragments exist in the real lib/cli.yaml."""

    @staticmethod
    def _load_cli_yaml() -> dict:
        import yaml

        lib_path = Path(__file__).parent.parent / "little_loops" / "loops" / "lib" / "cli.yaml"
        with open(lib_path) as f:
            return yaml.safe_load(f)

    def test_ll_auto_defined(self) -> None:
        data = self._load_cli_yaml()
        assert "ll_auto" in data["fragments"], "ll_auto fragment missing from lib/cli.yaml"

    def test_ll_auto_has_correct_action_type(self) -> None:
        data = self._load_cli_yaml()
        assert data["fragments"]["ll_auto"]["action_type"] == "shell"

    def test_ll_auto_has_correct_evaluate_type(self) -> None:
        data = self._load_cli_yaml()
        assert data["fragments"]["ll_auto"]["evaluate"]["type"] == "exit_code"

    def test_ll_check_links_defined(self) -> None:
        data = self._load_cli_yaml()
        assert "ll_check_links" in data["fragments"]

    def test_ll_check_links_has_correct_action(self) -> None:
        data = self._load_cli_yaml()
        assert data["fragments"]["ll_check_links"]["action"] == "ll-check-links 2>&1"

    def test_ll_issues_list_defined(self) -> None:
        data = self._load_cli_yaml()
        assert "ll_issues_list" in data["fragments"]

    def test_ll_issues_list_has_correct_action(self) -> None:
        data = self._load_cli_yaml()
        assert data["fragments"]["ll_issues_list"]["action"] == "ll-issues list --json"

    def test_ll_issues_next_defined(self) -> None:
        data = self._load_cli_yaml()
        assert "ll_issues_next" in data["fragments"]

    def test_ll_issues_next_has_correct_action(self) -> None:
        data = self._load_cli_yaml()
        assert data["fragments"]["ll_issues_next"]["action"] == "ll-issues next-action"

    def test_ll_loop_run_defined(self) -> None:
        data = self._load_cli_yaml()
        assert "ll_loop_run" in data["fragments"]

    def test_ll_loop_run_has_context_interpolation(self) -> None:
        data = self._load_cli_yaml()
        assert "${context.loop_name}" in data["fragments"]["ll_loop_run"]["action"]

    def test_all_fragments_are_shell_type(self) -> None:
        data = self._load_cli_yaml()
        for name, frag in data["fragments"].items():
            assert frag.get("action_type") == "shell", (
                f"Fragment {name!r} expected action_type: shell, got {frag.get('action_type')!r}"
            )

    def test_all_fragments_have_exit_code_evaluate(self) -> None:
        data = self._load_cli_yaml()
        for name, frag in data["fragments"].items():
            assert frag.get("evaluate", {}).get("type") == "exit_code", (
                f"Fragment {name!r} expected evaluate.type: exit_code"
            )

    def test_ll_auto_resolves_from_real_cli_yaml(self, tmp_path: Path) -> None:
        """Full resolve_fragments integration against the real lib/cli.yaml."""
        loops_dir = Path(__file__).parent.parent / "little_loops" / "loops"
        raw = {
            "name": "test",
            "initial": "run",
            "import": ["lib/cli.yaml"],
            "states": {
                "run": {
                    "fragment": "ll_auto",
                    "on_yes": "done",
                    "on_no": "retry",
                },
                "done": {"terminal": True},
                "retry": {"terminal": True},
            },
        }
        result = resolve_fragments(raw, loops_dir)
        state = result["states"]["run"]
        assert state["action_type"] == "shell"
        assert state["action"] == "ll-auto"
        assert state["evaluate"]["type"] == "exit_code"
        assert "fragment" not in state

    def test_ll_check_links_resolves_with_action_override(self, tmp_path: Path) -> None:
        """Caller can override action while keeping action_type/evaluate from fragment."""
        loops_dir = Path(__file__).parent.parent / "little_loops" / "loops"
        raw = {
            "name": "test",
            "initial": "check",
            "import": ["lib/cli.yaml"],
            "states": {
                "check": {
                    "fragment": "ll_check_links",
                    "capture": "link_results",
                    "on_yes": "done",
                    "on_no": "fix",
                },
                "done": {"terminal": True},
                "fix": {"terminal": True},
            },
        }
        result = resolve_fragments(raw, loops_dir)
        state = result["states"]["check"]
        assert state["action_type"] == "shell"
        assert state["action"] == "ll-check-links 2>&1"
        assert state["evaluate"]["type"] == "exit_code"
        assert state["capture"] == "link_results"
        assert "fragment" not in state


class TestBuiltinLoopMigration:
    def test_builtin_loops_load_after_migration(self) -> None:
        """All built-in loops that use fragment: shell_exit must still validate."""
        from little_loops.fsm.validation import load_and_validate

        loops_dir = Path(__file__).parent.parent / "little_loops" / "loops"
        migration_targets = [
            "dead-code-cleanup.yaml",
            "docs-sync.yaml",
            "fix-quality-and-tests.yaml",
            "harness-multi-item.yaml",
            "harness-single-shot.yaml",
            "issue-refinement.yaml",
            "prompt-across-issues.yaml",
            "recursive-refine.yaml",
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


# ---------------------------------------------------------------------------
# FEAT-1042: description field in fragment libraries
# ---------------------------------------------------------------------------


class TestFragmentDescriptionStripping:
    """Tests for description field stripping during fragment resolution."""

    def test_description_stripped_from_inline_fragment(self, tmp_path: Path) -> None:
        """description key is removed from merged state dict (inline fragment)."""
        raw = {
            "name": "test",
            "initial": "run",
            "fragments": {
                "my_frag": {
                    "description": "Does something useful.",
                    "action_type": "shell",
                    "evaluate": {"type": "exit_code"},
                },
            },
            "states": {
                "run": {
                    "fragment": "my_frag",
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
        assert "description" not in state
        assert state["action_type"] == "shell"
        assert state["action"] == "echo hi"
        assert "fragment" not in state

    def test_description_stripped_from_imported_fragment(self, tmp_path: Path) -> None:
        """description key is removed from merged state dict (imported fragment)."""
        lib = tmp_path / "lib.yaml"
        lib.write_text(
            "fragments:\n"
            "  shell_exit:\n"
            "    description: |\n"
            "      Shell command evaluated by exit code.\n"
            "      State must supply: action, on_yes, on_no.\n"
            "    action_type: shell\n"
            "    evaluate:\n"
            "      type: exit_code\n"
        )
        raw = {
            "name": "test",
            "initial": "run",
            "import": ["lib.yaml"],
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
        assert "description" not in state
        assert state["action_type"] == "shell"
        assert state["evaluate"] == {"type": "exit_code"}

    def test_description_not_in_merged_state_from_real_common_yaml(self) -> None:
        """description is stripped when resolving against the real lib/common.yaml."""
        loops_dir = Path(__file__).parent.parent / "little_loops" / "loops"
        raw = {
            "name": "test",
            "initial": "run",
            "import": ["lib/common.yaml"],
            "states": {
                "run": {
                    "fragment": "shell_exit",
                    "action": "pytest .",
                    "on_yes": "done",
                    "on_no": "fail",
                },
                "done": {"terminal": True},
                "fail": {"terminal": True},
            },
        }
        result = resolve_fragments(raw, loops_dir)
        state = result["states"]["run"]
        assert "description" not in state
        assert state["action_type"] == "shell"
        assert state["evaluate"] == {"type": "exit_code"}

    def test_all_common_yaml_fragments_have_description(self) -> None:
        """Every fragment in lib/common.yaml defines a description field."""
        import yaml

        lib_path = Path(__file__).parent.parent / "little_loops" / "loops" / "lib" / "common.yaml"
        with open(lib_path) as f:
            data = yaml.safe_load(f)
        fragments = data.get("fragments", {})
        assert fragments, "lib/common.yaml should define at least one fragment"
        for name, frag in fragments.items():
            assert isinstance(frag, dict), f"Fragment '{name}' should be a dict"
            assert "description" in frag, f"Fragment '{name}' is missing a description field"
            assert frag["description"].strip(), f"Fragment '{name}' has an empty description"

    def test_all_cli_yaml_fragments_have_description(self) -> None:
        """Every fragment in lib/cli.yaml defines a description field."""
        import yaml

        lib_path = Path(__file__).parent.parent / "little_loops" / "loops" / "lib" / "cli.yaml"
        with open(lib_path) as f:
            data = yaml.safe_load(f)
        fragments = data.get("fragments", {})
        assert fragments, "lib/cli.yaml should define at least one fragment"
        for name, frag in fragments.items():
            assert isinstance(frag, dict), f"Fragment '{name}' should be a dict"
            assert "description" in frag, f"Fragment '{name}' is missing a description field"
            assert frag["description"].strip(), f"Fragment '{name}' has an empty description"
