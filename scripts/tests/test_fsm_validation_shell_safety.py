"""Tests for FSM validation shell-escaping rule family (MR-7, MR-9, MR-11):
bash-default interpolation, over-escaped shell $$, and unsafe context
interpolation.
"""

from __future__ import annotations

from pathlib import Path

from little_loops.fsm.schema import (
    FSMLoop,
    StateConfig,
)
from little_loops.fsm.validation import (
    ValidationSeverity,
    _validate_bash_default_interpolation,
    _validate_overescaped_shell,
    _validate_unsafe_context_interpolation,
    load_and_validate,
    validate_fsm,
)


def make_state(**kwargs) -> StateConfig:
    """Convenience constructor for StateConfig in tests."""
    return StateConfig(**kwargs)


class TestBashDefaultInterpolation:
    """MR-7 (ENH-2348): unescaped ${ns.path:-default} bash-default interpolation lint."""

    def _simple_fsm(self, action: str, *, bash_default_ok: bool = False) -> FSMLoop:
        return FSMLoop(
            name="test-loop",
            initial="work",
            states={
                "work": make_state(action=action, on_yes="done", on_no="work"),
                "done": make_state(terminal=True),
            },
            bash_default_ok=bash_default_ok,
        )

    def test_mr7_fires_for_unescaped_bash_default(self) -> None:
        """MR-7 ERROR fires when an action contains ${ns.path:-default}."""
        fsm = self._simple_fsm("echo ${context.order:-queue}")
        errors = _validate_bash_default_interpolation(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.ERROR
        assert "${context.order:-queue}" in errors[0].message
        assert errors[0].path == "states.work.action"

    def test_mr7_does_not_fire_for_engine_default(self) -> None:
        """MR-7 does not fire for ${ns.path:default=value} (engine-native form)."""
        fsm = self._simple_fsm("echo ${context.order:default=queue}")
        errors = _validate_bash_default_interpolation(fsm)
        assert errors == []

    def test_mr7_does_not_fire_for_escaped_bash_default(self) -> None:
        """MR-7 does not fire for $${VAR:-value} (escaped, handled by shell)."""
        fsm = self._simple_fsm("echo $${DEPTH:-0}")
        errors = _validate_bash_default_interpolation(fsm)
        assert errors == []

    def test_mr7_suppressed_by_bash_default_ok(self) -> None:
        """bash_default_ok: true suppresses MR-7."""
        fsm = self._simple_fsm("echo ${context.order:-queue}", bash_default_ok=True)
        errors = _validate_bash_default_interpolation(fsm)
        assert errors == []

    def test_mr7_wired_into_validate_fsm(self) -> None:
        """validate_fsm() includes MR-7 errors for bash-default interpolation."""
        fsm = self._simple_fsm("echo ${context.order:-queue}")
        errors = validate_fsm(fsm)
        mr7 = [
            e for e in errors if e.severity == ValidationSeverity.ERROR and "ENH-2348" in e.message
        ]
        assert len(mr7) == 1

    def test_bash_default_ok_recognized_as_top_level_key(self, tmp_path: Path) -> None:
        """A YAML with top-level bash_default_ok produces no Unknown-top-level warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: A loop that intentionally uses bash default syntax\n"
            "initial: work\n"
            "bash_default_ok: true\n"
            "states:\n"
            "  work:\n"
            "    action: run.sh\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        _, warnings = load_and_validate(loop_yaml)
        unknown_warnings = [w for w in warnings if "Unknown top-level" in w.message]
        assert unknown_warnings == []


class TestOverescapedShell:
    """MR-9: over-escaped shell `$$` that expands to the PID at `bash -c` time."""

    def _simple_fsm(
        self,
        action: str,
        *,
        action_type: str | None = "shell",
        shell_pid_ok: bool = False,
    ) -> FSMLoop:
        return FSMLoop(
            name="test-loop",
            initial="work",
            states={
                "work": make_state(
                    action=action, action_type=action_type, on_yes="done", on_no="work"
                ),
                "done": make_state(terminal=True),
            },
            shell_pid_ok=shell_pid_ok,
        )

    def test_mr9_fires_for_overescaped_command_substitution(self) -> None:
        """MR-9 ERROR fires for $$( command substitution."""
        fsm = self._simple_fsm('echo "$$(pwd)"')
        errors = _validate_overescaped_shell(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.ERROR
        assert errors[0].path == "states.work.action"
        assert "$$(" in errors[0].message

    def test_mr9_fires_for_overescaped_variable(self) -> None:
        """MR-9 ERROR fires for a bare $$VAR reference."""
        fsm = self._simple_fsm('echo "$$DIR"')
        errors = _validate_overescaped_shell(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.ERROR

    def test_mr9_counts_each_occurrence(self) -> None:
        """The real init bug ($$(pwd)/$$DIR) yields two findings."""
        fsm = self._simple_fsm('echo "$$(pwd)/$$DIR"')
        errors = _validate_overescaped_shell(fsm)
        assert len(errors) == 2

    def test_mr9_does_not_fire_for_correct_single_dollar(self) -> None:
        """MR-9 does not fire for the correct $(pwd)/$DIR form."""
        fsm = self._simple_fsm('echo "$(pwd)/$DIR"')
        errors = _validate_overescaped_shell(fsm)
        assert errors == []

    def test_mr9_does_not_fire_for_legit_brace_escape(self) -> None:
        """MR-9 does not fire for the legit $${VAR} / $${VAR:-x} brace escape."""
        fsm = self._simple_fsm('[ -z "$${VISION_API_KEY:-}" ] && echo "$${HOME}"')
        errors = _validate_overescaped_shell(fsm)
        assert errors == []

    def test_mr9_does_not_fire_for_standalone_pid(self) -> None:
        """MR-9 does not fire for a standalone PID `$$` (tmp.$$ / "$$ ")."""
        fsm = self._simple_fsm('echo "tmp.$$"; echo "pid=$$ "')
        errors = _validate_overescaped_shell(fsm)
        assert errors == []

    def test_mr9_ignores_prompt_actions(self) -> None:
        """A $$VAR in a prompt action is inert text and is not flagged."""
        fsm = self._simple_fsm("Summarize $$DIR for the user", action_type="prompt")
        errors = _validate_overescaped_shell(fsm)
        assert errors == []

    def test_mr9_suppressed_by_shell_pid_ok(self) -> None:
        """shell_pid_ok: true suppresses MR-9."""
        fsm = self._simple_fsm('echo "$$(pwd)"', shell_pid_ok=True)
        errors = _validate_overescaped_shell(fsm)
        assert errors == []

    def test_mr9_wired_into_validate_fsm(self) -> None:
        """validate_fsm() includes MR-9 errors for over-escaped shell $$."""
        fsm = self._simple_fsm('echo "$$(pwd)"')
        errors = validate_fsm(fsm)
        mr9 = [
            e for e in errors if e.severity == ValidationSeverity.ERROR and "(MR-9)" in e.message
        ]
        assert len(mr9) == 1

    def test_shell_pid_ok_recognized_as_top_level_key(self, tmp_path: Path) -> None:
        """A YAML with top-level shell_pid_ok produces no Unknown-top-level warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: A loop that intentionally embeds a literal PID via $$\n"
            "initial: work\n"
            "shell_pid_ok: true\n"
            "states:\n"
            "  work:\n"
            "    action: run.sh\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        _, warnings = load_and_validate(loop_yaml)
        unknown_warnings = [w for w in warnings if "Unknown top-level" in w.message]
        assert unknown_warnings == []


class TestUnsafeContextInterpolation:
    """MR-11 (BUG-2622): user-controlled ${context.*} pasted raw into a shell body."""

    def _simple_fsm(
        self,
        action: str,
        *,
        action_type: str | None = "shell",
        unsafe_context_interpolation_ok: bool = False,
    ) -> FSMLoop:
        return FSMLoop(
            name="test-loop",
            initial="work",
            states={
                "work": make_state(
                    action=action, action_type=action_type, on_yes="done", on_no="work"
                ),
                "done": make_state(terminal=True),
            },
            unsafe_context_interpolation_ok=unsafe_context_interpolation_ok,
        )

    def test_mr11_fires_for_double_quoted_token_position(self) -> None:
        """MR-11 WARNING fires for [ -z "${context.input}" ] (the BUG-2622 repro)."""
        fsm = self._simple_fsm('if [ -z "${context.input}" ]; then exit 1; fi')
        errors = _validate_unsafe_context_interpolation(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING
        assert errors[0].path == "states.work.action"
        assert "${context.input}" in errors[0].message

    def test_mr11_fires_for_bare_unquoted_token(self) -> None:
        """MR-11 fires for a bare unquoted ${context.goal} token position."""
        fsm = self._simple_fsm("echo ${context.goal}")
        errors = _validate_unsafe_context_interpolation(fsm)
        assert len(errors) == 1

    def test_mr11_fires_for_each_user_controlled_var_name(self) -> None:
        """MR-11 recognizes input/goal/description/task/prompt/query/topic."""
        for var in ("input", "goal", "description", "task", "prompt", "query", "topic"):
            fsm = self._simple_fsm(f'echo "${{context.{var}}}"')
            errors = _validate_unsafe_context_interpolation(fsm)
            assert len(errors) == 1, f"expected a finding for context.{var}"

    def test_mr11_does_not_fire_for_other_context_vars(self) -> None:
        """MR-11 does not flag non-user-controlled context vars like run_dir."""
        fsm = self._simple_fsm('echo "${context.run_dir}"')
        errors = _validate_unsafe_context_interpolation(fsm)
        assert errors == []

    def test_mr11_does_not_fire_for_epic_context_var(self) -> None:
        """MR-11 does not flag context.epic (ENH-2660): ``epic`` is outside the
        user-controlled regex set, so rn-implement's --epic branch can interpolate
        ``${context.epic}`` bare without needing unsafe_context_interpolation_ok.
        Locks the regex-bounded scope against a future "tighten MR-11" change."""
        fsm = self._simple_fsm('EPIC="${context.epic}"; echo "$EPIC"')
        errors = _validate_unsafe_context_interpolation(fsm)
        assert errors == []

    def test_mr11_does_not_fire_for_single_quoted_position(self) -> None:
        """MR-11 does not fire when the placeholder sits inside single quotes."""
        fsm = self._simple_fsm("printf '%s' '${context.input}'")
        errors = _validate_unsafe_context_interpolation(fsm)
        assert errors == []

    def test_mr11_does_not_fire_inside_quoted_heredoc(self) -> None:
        """MR-11 does not fire for a value written through a quoted heredoc."""
        fsm = self._simple_fsm(
            "cat > \"${context.run_dir}/in.txt\" <<'LL_EOF'\n${context.input}\nLL_EOF\n"
        )
        errors = _validate_unsafe_context_interpolation(fsm)
        assert errors == []

    def test_mr11_does_not_fire_for_shell_suffix(self) -> None:
        """MR-11 does not fire when the placeholder already uses :shell."""
        fsm = self._simple_fsm("INPUT=${context.input:shell}")
        errors = _validate_unsafe_context_interpolation(fsm)
        assert errors == []

    def test_mr11_does_not_fire_for_shell_default_composed(self) -> None:
        """ENH-3337: MR-11 recognizes :shell wherever it appears in the suffix
        chain, not only a trailing `:shell}` — a composed
        `${context.goal:shell:default=}` must not be flagged as unsafe."""
        fsm = self._simple_fsm("GOAL=${context.goal:shell:default=}")
        errors = _validate_unsafe_context_interpolation(fsm)
        assert errors == []

    def test_mr11_does_not_fire_for_default_shell_composed(self) -> None:
        """The reverse ordering (:default= before :shell) is also recognized."""
        fsm = self._simple_fsm("GOAL=${context.goal:default=:shell}")
        errors = _validate_unsafe_context_interpolation(fsm)
        assert errors == []

    def test_mr11_does_not_fire_in_comment(self) -> None:
        """MR-11 does not fire for a placeholder mentioned only in a comment."""
        fsm = self._simple_fsm("# Never test ${context.input} as a bare token.\necho ok")
        errors = _validate_unsafe_context_interpolation(fsm)
        assert errors == []

    def test_mr11_ignores_prompt_actions(self) -> None:
        """A raw ${context.input} in a prompt action is safe (LLM payload, not bash)."""
        fsm = self._simple_fsm('Describe: "${context.input}"', action_type="prompt")
        errors = _validate_unsafe_context_interpolation(fsm)
        assert errors == []

    def test_mr11_ignores_slash_command_actions(self) -> None:
        """A raw ${context.input} in a slash-command body is not shell-parsed."""
        fsm = self._simple_fsm('/ll:refine-issue "${context.input}"')
        errors = _validate_unsafe_context_interpolation(fsm)
        assert errors == []

    def test_mr11_suppressed_by_flag(self) -> None:
        """unsafe_context_interpolation_ok: true suppresses MR-11."""
        fsm = self._simple_fsm('echo "${context.input}"', unsafe_context_interpolation_ok=True)
        errors = _validate_unsafe_context_interpolation(fsm)
        assert errors == []

    def test_mr11_wired_into_validate_fsm(self) -> None:
        """validate_fsm() includes MR-11 warnings for unsafe raw context interpolation."""
        fsm = self._simple_fsm('echo "${context.input}"')
        errors = validate_fsm(fsm)
        mr11 = [
            e for e in errors if e.severity == ValidationSeverity.WARNING and "(MR-11)" in e.message
        ]
        assert len(mr11) == 1

    def test_unsafe_context_interpolation_ok_recognized_as_top_level_key(
        self, tmp_path: Path
    ) -> None:
        """A YAML with top-level unsafe_context_interpolation_ok produces no
        Unknown-top-level warning."""
        loop_yaml = tmp_path / "loop.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: A loop that intentionally embeds raw context in shell\n"
            "initial: work\n"
            "unsafe_context_interpolation_ok: true\n"
            "states:\n"
            "  work:\n"
            "    action: run.sh\n"
            "    on_yes: done\n"
            "  done:\n"
            "    terminal: true\n"
        )
        _, warnings = load_and_validate(loop_yaml)
        unknown_warnings = [w for w in warnings if "Unknown top-level" in w.message]
        assert unknown_warnings == []
