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

    def test_mr11_fires_for_context_epic_after_widening(self) -> None:
        """ENH-3342: MR-11 flags ${context.epic} now that the fixed seven-key
        allowlist is dropped — ``epic`` has no runner-owned trust verdict in
        ``classify_site()``, so it is untrusted like any other author-authored
        context key. Supersedes the old regex-bounded exemption this test used
        to assert; the real corpus site (rn-implement.yaml) was converted to
        ``:shell`` as part of this issue's corpus triage (step 7)."""
        fsm = self._simple_fsm('EPIC="${context.epic}"; echo "$EPIC"')
        errors = _validate_unsafe_context_interpolation(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING
        assert "${context.epic}" in errors[0].message

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


def _mr11_warnings(fsm: FSMLoop) -> list:
    return [e for e in _validate_unsafe_context_interpolation(fsm) if "(MR-11)" in e.message]


class TestUnsafeContextInterpolationWidening:
    """ENH-3342: MR-11 widened past the fixed 7-key allowlist — namespace-generic
    classify_site() lookup, Python-literal-position awareness, and the
    column-0 heredoc terminator."""

    def _simple_fsm(self, action: str) -> FSMLoop:
        return FSMLoop(
            name="test-loop",
            initial="work",
            states={
                "work": make_state(action=action, action_type="shell", on_yes="done", on_no="work"),
                "done": make_state(terminal=True),
            },
        )

    def test_ac1_non_allowlisted_context_key_flagged_inside_python_literal(self) -> None:
        """A ${context.<key>} outside the old 7-key allowlist is flagged once it
        reaches a Python string literal inside an embedded python3 heredoc."""
        fsm = self._simple_fsm("python3 << 'PYEOF'\nx = '${context.max_depth}'\nPYEOF\n")
        errors = _mr11_warnings(fsm)
        assert len(errors) == 1
        assert "${context.max_depth}" in errors[0].message

    def test_ac2_captured_namespace_flagged_inside_python_literal(self) -> None:
        """${captured.*} — entirely invisible to the old regex — is flagged
        inside a Python literal (class B is no longer outside MR-11's reach)."""
        fsm = self._simple_fsm("python3 << 'PYEOF'\nx = '${captured.review.output}'\nPYEOF\n")
        errors = _mr11_warnings(fsm)
        assert len(errors) == 1
        assert "${captured.review.output}" in errors[0].message

    def test_ac2b_prev_output_and_stderr_flagged_at_bash_token_position(self) -> None:
        """${prev.output} / ${prev.stderr} are flagged at a bash-token position —
        the live rlhf-svg-evaluate.yaml:517 shape (PREV_OUTPUT="${prev.output}"),
        a bash position no baseline (ENH-3338) covers."""
        for key in ("output", "stderr"):
            fsm = self._simple_fsm(f'PREV_OUTPUT="${{prev.{key}}}"')
            errors = _mr11_warnings(fsm)
            assert len(errors) == 1, f"expected a finding for prev.{key}"
            assert f"${{prev.{key}}}" in errors[0].message

    def test_ac2b_prev_exit_code_not_flagged_at_bash_token_position(self) -> None:
        """${prev.exit_code} is runner-constructed metadata, not LLM/command
        output text — classify_site() trusts it (class C)."""
        fsm = self._simple_fsm('RC="${prev.exit_code}"')
        assert _mr11_warnings(fsm) == []

    def test_ac3_quoted_heredoc_that_is_a_python_body_is_flagged(self) -> None:
        """The Python-body side of AC 3: a python3 <<'EOF' heredoc IS flagged —
        distinct from test_mr11_does_not_fire_inside_quoted_heredoc's `cat`
        heredoc (a data sink, not a Python body), which correctly stays clean."""
        fsm = self._simple_fsm("python3 << 'PYEOF'\ngoal = '${context.goal}'\nPYEOF\n")
        errors = _mr11_warnings(fsm)
        assert len(errors) == 1
        assert "${context.goal}" in errors[0].message

    def test_ac4_indented_marker_equal_line_does_not_close_heredoc(self) -> None:
        """A heredoc terminator must sit at column 0; an indented line equal to
        the marker text does not end the tracked block, so a raw context value
        after it is still inside the (still-open) heredoc and stays clean —
        matching bash's own column-0 terminator semantics."""
        action = (
            "cat > \"${context.run_dir}/in.txt\" <<'LL_EOF'\n  LL_EOF\n${context.input}\nLL_EOF\n"
        )
        fsm = self._simple_fsm(action)
        # The bash-token-position scan treats the whole block as heredoc
        # interior (still open past the indented false terminator), so no
        # bash-token finding fires here — the heredoc is a `cat` sink, not a
        # Python body, so the delegated scan doesn't fire either.
        assert _mr11_warnings(fsm) == []

    def test_ac5b_shell_suffix_flagged_inside_python_body(self) -> None:
        """:shell is shell-token quoting; inside a Python literal it produces a
        shell-quoted string that breaks the Python parser instead of
        protecting it — MR-11 must flag it there, naming the LL_ARG_ hoist."""
        fsm = self._simple_fsm("python3 << 'PYEOF'\ngoal = '${context.goal:shell}'\nPYEOF\n")
        errors = _mr11_warnings(fsm)
        assert len(errors) == 1
        assert "LL_ARG_" in errors[0].message

    def test_ac5b_shell_suffix_not_flagged_at_bash_token_position(self) -> None:
        """:shell at a genuine bash-token position is the correct, safe remedy
        and must not be flagged (unchanged from pre-widening behavior)."""
        fsm = self._simple_fsm("GOAL=${context.goal:shell}")
        assert _mr11_warnings(fsm) == []


class TestMr11Marker:
    """ENH-3342: the `# ll-lint: mr11-ok(<namespace>.<key>) <reason>` per-site
    suppression marker — grammar, both placements, malformed-marker ERROR, and
    the stale-marker WARNING (constraints 1-7)."""

    def _simple_fsm(self, action: str) -> FSMLoop:
        return FSMLoop(
            name="test-loop",
            initial="work",
            states={
                "work": make_state(action=action, action_type="shell", on_yes="done", on_no="work"),
                "done": make_state(terminal=True),
            },
        )

    def test_well_formed_marker_suppresses_its_finding(self) -> None:
        fsm = self._simple_fsm(
            'echo "${context.goal}"  # ll-lint: mr11-ok(context.goal) ENH-1234 - reviewed'
        )
        errors = _mr11_warnings(fsm)
        assert errors == []

    def test_marker_exempts_only_the_named_variable(self) -> None:
        """A sibling untrusted site on the same line still fires — constraint 1
        (a bare line-level marker would hide the mechanize-skills.yaml:283-286
        failure shape: one converted binding, one raw sibling)."""
        fsm = self._simple_fsm(
            'echo "${context.goal}" "${context.topic}"'
            "  # ll-lint: mr11-ok(context.goal) ENH-1234 - reviewed"
        )
        errors = _mr11_warnings(fsm)
        assert len(errors) == 1
        assert "${context.topic}" in errors[0].message

    def test_marker_preceding_line_form_works(self) -> None:
        """A marker alone on the line immediately above the site also suppresses
        it (constraint 3's two-line form)."""
        action = '# ll-lint: mr11-ok(context.goal) ENH-1234 - reviewed\necho "${context.goal}"\n'
        fsm = self._simple_fsm(action)
        assert _mr11_warnings(fsm) == []

    def test_ordinary_comment_is_not_mistaken_for_a_marker(self) -> None:
        fsm = self._simple_fsm(
            'echo "${context.goal}"  # just a note about this line, nothing more'
        )
        errors = _mr11_warnings(fsm)
        assert len(errors) == 1
        marker_errors = [e for e in errors if "malformed" in e.message]
        assert marker_errors == []

    def test_malformed_marker_missing_parens_is_an_error(self) -> None:
        fsm = self._simple_fsm('echo "${context.goal}"  # ll-lint: mr11-ok reviewed, see ENH-1234')
        errors = _validate_unsafe_context_interpolation(fsm)
        malformed = [
            e for e in errors if e.severity == ValidationSeverity.ERROR and "malformed" in e.message
        ]
        assert len(malformed) == 1

    def test_malformed_marker_missing_reason_is_an_error(self) -> None:
        fsm = self._simple_fsm('echo "${context.goal}"  # ll-lint: mr11-ok(context.goal)')
        errors = _validate_unsafe_context_interpolation(fsm)
        malformed = [
            e for e in errors if e.severity == ValidationSeverity.ERROR and "malformed" in e.message
        ]
        assert len(malformed) == 1

    def test_malformed_marker_reason_without_issue_id_is_an_error(self) -> None:
        fsm = self._simple_fsm(
            'echo "${context.goal}"  # ll-lint: mr11-ok(context.goal) looks fine to me'
        )
        errors = _validate_unsafe_context_interpolation(fsm)
        malformed = [
            e for e in errors if e.severity == ValidationSeverity.ERROR and "malformed" in e.message
        ]
        assert len(malformed) == 1

    def test_malformed_marker_containing_dollar_brace_is_an_error(self) -> None:
        """The marker must not quote the token it exempts — the FSM interpolates
        the whole action string, comments included, so a `${` inside the marker
        becomes its own live interpolation site (constraint 4)."""
        fsm = self._simple_fsm(
            'echo "${context.goal}"  # ll-lint: mr11-ok(context.goal) '
            "see ${context.goal} in ENH-1234"
        )
        errors = _validate_unsafe_context_interpolation(fsm)
        malformed = [
            e for e in errors if e.severity == ValidationSeverity.ERROR and "malformed" in e.message
        ]
        assert len(malformed) == 1

    def test_stale_marker_matching_no_finding_is_a_warning(self) -> None:
        """A well-formed marker whose named variable produces no MR-11 finding
        (the site was converted/removed) is itself a stale-marker WARNING
        (constraint 7)."""
        fsm = self._simple_fsm(
            "echo ${context.goal:shell}  # ll-lint: mr11-ok(context.goal) ENH-1234 - reviewed"
        )
        errors = _validate_unsafe_context_interpolation(fsm)
        assert len(errors) == 1
        assert errors[0].severity == ValidationSeverity.WARNING
        assert "stale" in errors[0].message
