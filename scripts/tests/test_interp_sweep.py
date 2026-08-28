"""Unit tests for the ENH-3338 interpolation sweep (`little_loops.fsm.interp_sweep`)."""

from __future__ import annotations

from pathlib import Path

from little_loops.fsm.interp_sweep import InterpSite, classify_site, scan_action, scan_corpus


class TestClassifySite:
    def test_captured_is_always_class_b(self) -> None:
        assert classify_site("captured", "anything") == "B"
        assert classify_site("captured", "output") == "B"

    def test_prev_output_and_stderr_are_class_b(self) -> None:
        assert classify_site("prev", "output") == "B"
        assert classify_site("prev", "stderr") == "B"

    def test_prev_other_keys_are_class_c(self) -> None:
        assert classify_site("prev", "exit_code") == "C"
        assert classify_site("prev", "state") == "C"
        assert classify_site("prev", "timeout_kind") == "C"

    def test_context_untrusted_key_is_class_a(self) -> None:
        assert classify_site("context", "goal") == "A"
        assert classify_site("context", "description") == "A"

    def test_context_trusted_keys_are_class_c(self) -> None:
        assert classify_site("context", "run_dir") == "C"
        assert classify_site("context", "promoted_artifact") == "C"
        assert classify_site("context", "_tamper_guard") == "C"

    def test_other_namespaces_are_class_b(self) -> None:
        """No namespace besides context/captured/prev has an explicit trust
        verdict, so the safe-direction default applies (decided 2026-08-28)."""
        assert classify_site("result", "output") == "B"
        assert classify_site("state", "name") == "B"
        assert classify_site("env", "HOME") == "B"
        assert classify_site("messages", "last") == "B"
        assert classify_site("param", "x") == "B"


class TestScanActionHeredoc:
    def test_heredoc_opener_mid_line_after_env_binding(self) -> None:
        action = "LL_X=1 python3 << 'PYEOF'\ngoal = '${context.goal}'\nPYEOF\n"
        sites = scan_action(action, state="s1", file="loops/x.yaml")
        assert len(sites) == 1
        assert sites[0].var == "context.goal"
        assert sites[0].cls == "A"
        assert sites[0].host_shape == "heredoc"

    def test_heredoc_terminator_must_be_column_zero(self) -> None:
        action = (
            "python3 << 'PYEOF'\n"
            "  PYEOF\n"  # indented line equal to marker text; must NOT close the heredoc
            "goal = '${context.goal}'\n"
            "PYEOF\n"
        )
        sites = scan_action(action, state="s1", file="loops/x.yaml")
        assert len(sites) == 1
        assert sites[0].var == "context.goal"

    def test_misapplied_shell_suffix_inside_heredoc_is_reported(self) -> None:
        action = "python3 << 'PYEOF'\ngoal = '${context.goal:shell}'\nPYEOF\n"
        sites = scan_action(action, state="s1", file="loops/x.yaml")
        assert len(sites) == 1
        assert sites[0].cls == "A"
        assert sites[0].misapplied_remedy is True

    def test_shell_suffix_at_bash_position_outside_body_not_reported(self) -> None:
        action = "LL_ARG_X=${context.x:shell} python3 << 'PYEOF'\nprint(1)\nPYEOF\n"
        sites = scan_action(action, state="s1", file="loops/x.yaml")
        assert sites == []

    def test_data_sink_heredoc_is_not_reported(self) -> None:
        """AC 11: a `cat > file << 'MARKER'` heredoc writes to disk, never to
        the Python parser -- a captured value inside its body is not a site.
        The following `python3` heredoc reading the file back IS scanned."""
        action = (
            "cat > \"${captured.run_dir.output}/round_ideas.txt\" << 'RAWEOF'\n"
            "${captured.round_ideas.output}\n"
            "RAWEOF\n"
            "python3 << 'PYEOF'\n"
            "x = '${captured.run_dir.output}'\n"
            "PYEOF\n"
        )
        sites = scan_action(action, state="s1", file="loops/x.yaml")
        assert len(sites) == 1
        assert sites[0].var == "captured.run_dir.output"

    def test_here_string_not_mistaken_for_heredoc(self) -> None:
        """`<<<` here-strings (and fence.py's `<<<BRIEF` prose markers) must
        not be parsed as a heredoc opener."""
        action = 'done <<< "${captured.commands_json.output}"\n'
        sites = scan_action(action, state="s1", file="loops/x.yaml")
        assert sites == []

    def test_prev_output_and_exit_code(self) -> None:
        action = "python3 << 'PYEOF'\na = '${prev.output}'\nb = '${prev.exit_code}'\nPYEOF\n"
        sites = scan_action(action, state="s1", file="loops/x.yaml")
        by_var = {s.var: s for s in sites}
        assert by_var["prev.output"].cls == "B"
        assert by_var["prev.exit_code"].cls == "C"


class TestScanActionCString:
    def test_double_quoted_c_string(self) -> None:
        action = "python3 -c \"x = '${captured.thing.output}'\"\n"
        sites = scan_action(action, state="s1", file="loops/x.yaml")
        assert len(sites) == 1
        assert sites[0].cls == "B"
        assert sites[0].host_shape == "c-string"

    def test_single_quoted_c_string(self) -> None:
        action = "python3 -c 'x = \"${context.goal}\"'\n"
        sites = scan_action(action, state="s1", file="loops/x.yaml")
        assert len(sites) == 1
        assert sites[0].cls == "A"
        assert sites[0].host_shape == "c-string"


class TestScanCorpus:
    def test_walks_fragments_key(self, tmp_path: Path) -> None:
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()
        (lib_dir / "frag.yaml").write_text(
            "fragments:\n"
            "  do_thing:\n"
            "    action_type: shell\n"
            "    action: |\n"
            "      python3 << 'PYEOF'\n"
            "      x = '${captured.run_dir.output}'\n"
            "      PYEOF\n"
        )
        sites = scan_corpus(tmp_path)
        assert len(sites) == 1
        assert sites[0].state == "do_thing"
        assert sites[0].cls == "B"

    def test_skips_prompt_action_type(self, tmp_path: Path) -> None:
        (tmp_path / "loop.yaml").write_text(
            "states:\n"
            "  apply:\n"
            "    action_type: prompt\n"
            "    action: |\n"
            "      python3 -c \"x = '${context.goal}'\"\n"
        )
        sites = scan_corpus(tmp_path)
        assert sites == []

    def test_skips_slash_command_action(self, tmp_path: Path) -> None:
        (tmp_path / "loop.yaml").write_text(
            "states:\n  dispatch:\n    action: /ll:some-command ${context.goal}\n"
        )
        sites = scan_corpus(tmp_path)
        assert sites == []


class TestInterpSiteEquality:
    def test_equality_ignores_informational_fields(self) -> None:
        a = InterpSite(
            file="loops/x.yaml",
            state="s",
            var="context.goal",
            cls="A",
            host_shape="heredoc",
            misapplied_remedy=False,
            line=1,
            count=1,
        )
        b = InterpSite(
            file="loops/x.yaml",
            state="s",
            var="context.goal",
            cls="A",
            host_shape="c-string",
            misapplied_remedy=True,
            line=99,
            count=5,
        )
        assert a == b
        assert hash(a) == hash(b)
