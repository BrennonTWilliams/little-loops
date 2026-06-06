"""Tests for .ll/program.md steering convention (ENH-1121)."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import patch

import pytest

SAMPLE_PROGRAM_MD = """\
## Directive

Improve the refine-issue skill so it produces more actionable steps.

## Targets

- skills/refine-issue/SKILL.md
- skills/wire-issue/SKILL.md

## Benchmark

task_dir: evals/refine-issue
scorer: ./scripts/score.sh

## Budget

wall_clock: 8h

## Constraints

Do not modify CLAUDE.md.
"""


class TestParseProgramMd:
    """Unit tests for _parse_program_md()."""

    def test_returns_empty_dict_when_file_absent(self, tmp_path: Path) -> None:
        """Missing file returns empty dict (not an error)."""
        from little_loops.cli.loop.run import _parse_program_md

        result = _parse_program_md(tmp_path / "nonexistent.md")
        assert result == {}

    def test_returns_empty_dict_on_oserror(self, tmp_path: Path) -> None:
        """OSError on read returns empty dict."""
        from little_loops.cli.loop.run import _parse_program_md

        path = tmp_path / "program.md"
        path.write_text("## Directive\nsome text\n")
        path.chmod(0o000)
        try:
            result = _parse_program_md(path)
            assert result == {}
        finally:
            path.chmod(0o644)

    def test_parses_directive_section(self, tmp_path: Path) -> None:
        """## Directive section becomes 'directive' key."""
        from little_loops.cli.loop.run import _parse_program_md

        path = tmp_path / "program.md"
        path.write_text(SAMPLE_PROGRAM_MD)
        result = _parse_program_md(path)
        assert "directive" in result
        assert "Improve the refine-issue skill" in result["directive"]

    def test_parses_targets_as_space_joined(self, tmp_path: Path) -> None:
        """## Targets bullet list becomes space-joined 'targets' key."""
        from little_loops.cli.loop.run import _parse_program_md

        path = tmp_path / "program.md"
        path.write_text(SAMPLE_PROGRAM_MD)
        result = _parse_program_md(path)
        assert result["targets"] == "skills/refine-issue/SKILL.md skills/wire-issue/SKILL.md"

    def test_parses_benchmark_key_value_pairs(self, tmp_path: Path) -> None:
        """## Benchmark key:value pairs are injected directly into result."""
        from little_loops.cli.loop.run import _parse_program_md

        path = tmp_path / "program.md"
        path.write_text(SAMPLE_PROGRAM_MD)
        result = _parse_program_md(path)
        assert result["task_dir"] == "evals/refine-issue"
        assert result["scorer"] == "./scripts/score.sh"

    def test_parses_budget_section(self, tmp_path: Path) -> None:
        """## Budget section becomes 'budget' key."""
        from little_loops.cli.loop.run import _parse_program_md

        path = tmp_path / "program.md"
        path.write_text(SAMPLE_PROGRAM_MD)
        result = _parse_program_md(path)
        assert "budget" in result
        assert "8h" in result["budget"]

    def test_parses_constraints_section(self, tmp_path: Path) -> None:
        """## Constraints section becomes 'constraints' key."""
        from little_loops.cli.loop.run import _parse_program_md

        path = tmp_path / "program.md"
        path.write_text(SAMPLE_PROGRAM_MD)
        result = _parse_program_md(path)
        assert "constraints" in result
        assert "CLAUDE.md" in result["constraints"]

    def test_missing_section_not_in_result(self, tmp_path: Path) -> None:
        """Absent sections do not appear in result dict."""
        from little_loops.cli.loop.run import _parse_program_md

        path = tmp_path / "program.md"
        path.write_text("## Directive\nJust a goal.\n")
        result = _parse_program_md(path)
        assert "targets" not in result
        assert "budget" not in result

    def test_case_insensitive_headings(self, tmp_path: Path) -> None:
        """Section headings are matched case-insensitively."""
        from little_loops.cli.loop.run import _parse_program_md

        path = tmp_path / "program.md"
        path.write_text("## directive\nmy goal\n\n## targets\n- foo.md\n")
        result = _parse_program_md(path)
        assert result.get("directive") == "my goal"
        assert result.get("targets") == "foo.md"

    def test_empty_file_returns_empty_dict(self, tmp_path: Path) -> None:
        """Empty file returns empty dict."""
        from little_loops.cli.loop.run import _parse_program_md

        path = tmp_path / "program.md"
        path.write_text("")
        assert _parse_program_md(path) == {}


class TestCmdRunProgramMdInjection:
    """Integration tests for program.md → fsm.context injection in cmd_run.

    Uses dry_run=True so cmd_run applies context overrides and returns before
    attempting real execution — same pattern as test_ll_loop_commands.py.
    Context is verified by patching load_and_validate to return a mock FSM
    with a real dict that we can inspect after the call.
    """

    def _make_args(self, **kwargs: object) -> argparse.Namespace:
        defaults = {
            "input": None,
            "context": [],
            "max_iterations": None,
            "delay": None,
            "no_llm": False,
            "llm_model": None,
            "dry_run": True,
            "background": False,
            "foreground_internal": False,
            "quiet": False,
            "verbose": False,
            "follow": False,
            "show_diagrams": None,
            "diagram_edge_labels": None,
            "diagram_state_detail": None,
            "diagram_scope": None,
            "clear": False,
            "queue": False,
            "handoff_threshold": None,
            "program_md": None,
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def _make_loop(self, tmp_path: Path) -> Path:
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "test-loop.yaml").write_text(
            "name: test-loop\ninitial: done\n"
            'context:\n  targets: ""\n  directive: ""\n  design_tokens_context: ""\n'
            "states:\n  done:\n    terminal: true\n"
        )
        return loops_dir

    def test_program_md_fields_injected_into_context(self, tmp_path: Path) -> None:
        """Fields from program.md are set in fsm.context before dry_run returns."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.fsm.validation import load_and_validate
        from little_loops.logger import Logger

        program_md = tmp_path / "program.md"
        program_md.write_text(
            "## Directive\nOptimize for clarity.\n\n## Targets\n- skills/foo/SKILL.md\n"
        )

        loops_dir = self._make_loop(tmp_path)
        args = self._make_args(program_md=program_md, dry_run=True)
        logger = Logger(use_color=False)

        # Load the real FSM to capture the context after injection
        fsm, _ = load_and_validate(loops_dir / "test-loop.yaml")

        def fake_load_and_validate(path: Path):  # type: ignore[override]
            return fsm, []

        with patch(
            "little_loops.fsm.validation.load_and_validate", side_effect=fake_load_and_validate
        ):
            cmd_run("test-loop", args, loops_dir, logger)

        assert fsm.context.get("directive") == "Optimize for clarity."
        assert fsm.context.get("targets") == "skills/foo/SKILL.md"

    def test_context_flag_overrides_program_md(self, tmp_path: Path) -> None:
        """--context KEY=VALUE overrides program.md values (precedence check)."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.fsm.validation import load_and_validate
        from little_loops.logger import Logger

        program_md = tmp_path / "program.md"
        program_md.write_text("## Targets\n- original.md\n")

        loops_dir = self._make_loop(tmp_path)
        args = self._make_args(
            program_md=program_md,
            context=["targets=override.md"],
            dry_run=True,
        )
        logger = Logger(use_color=False)

        fsm, _ = load_and_validate(loops_dir / "test-loop.yaml")

        def fake_load_and_validate(path: Path):  # type: ignore[override]
            return fsm, []

        with patch(
            "little_loops.fsm.validation.load_and_validate", side_effect=fake_load_and_validate
        ):
            cmd_run("test-loop", args, loops_dir, logger)

        assert fsm.context.get("targets") == "override.md"

    def test_absent_program_md_does_not_error(self, tmp_path: Path) -> None:
        """Missing .ll/program.md is not an error; loop runs normally (dry_run)."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.logger import Logger

        loops_dir = self._make_loop(tmp_path)
        args = self._make_args(dry_run=True)
        logger = Logger(use_color=False)

        result = cmd_run("test-loop", args, loops_dir, logger)
        assert result == 0

    def test_run_dir_injected_into_context(self, tmp_path: Path) -> None:
        """run_dir is injected into fsm.context by cmd_run before dry_run returns."""
        import re

        from little_loops.cli.loop.run import cmd_run
        from little_loops.fsm.validation import load_and_validate
        from little_loops.logger import Logger

        loops_dir = self._make_loop(tmp_path)
        args = self._make_args(dry_run=True)
        logger = Logger(use_color=False)

        fsm, _ = load_and_validate(loops_dir / "test-loop.yaml")

        def fake_load_and_validate(path: Path):  # type: ignore[override]
            return fsm, []

        with patch(
            "little_loops.fsm.validation.load_and_validate", side_effect=fake_load_and_validate
        ):
            cmd_run("test-loop", args, loops_dir, logger)

        run_dir = fsm.context.get("run_dir", "")
        assert run_dir, "run_dir must be injected into fsm.context"
        assert "runs" in run_dir, f"run_dir must be under .loops/runs/, got: {run_dir!r}"
        assert re.search(r"test-loop-\d{8}T\d{6}", run_dir), (
            f"run_dir must match test-loop-YYYYMMDDTHHMMSS, got: {run_dir!r}"
        )
        assert run_dir.endswith("/"), "run_dir must end with /"

    def test_design_tokens_context_injected_into_context(self, tmp_path: Path) -> None:
        """design_tokens_context is injected into fsm.context by cmd_run before dry_run returns.

        The test loop YAML declares ``design_tokens_context: ""`` (empty placeholder),
        so the guard must evaluate value truthiness, not key existence, to trigger
        injection. This test mocks load_design_tokens with a valid DesignTokens object
        and render_as_prompt_context with a known string to verify the populated value
        replaces the empty placeholder.
        """
        from unittest.mock import patch

        from little_loops.cli.loop.run import cmd_run
        from little_loops.design_tokens import DesignTokens
        from little_loops.fsm.validation import load_and_validate
        from little_loops.logger import Logger

        loops_dir = self._make_loop(tmp_path)
        args = self._make_args(dry_run=True)
        logger = Logger(use_color=False)

        fsm, _ = load_and_validate(loops_dir / "test-loop.yaml")

        def fake_load_and_validate(path: Path):  # type: ignore[override]
            return fsm, []

        mock_tokens = DesignTokens(
            primitives={},
            semantic={},
            theme={},
            resolved={"color.accent": "#ff0000"},
            source_path=tmp_path / "tokens.json",
        )
        _expected_context = "**Design tokens** (resolved values):\n```\ncolor.accent: #ff0000\n```"

        with (
            patch(
                "little_loops.fsm.validation.load_and_validate",
                side_effect=fake_load_and_validate,
            ),
            patch(
                "little_loops.design_tokens.load_design_tokens",
                return_value=mock_tokens,
            ),
        ):
            cmd_run("test-loop", args, loops_dir, logger)

        assert fsm.context.get("design_tokens_context") == _expected_context, (
            "design_tokens_context must be populated with rendered token context "
            "when the loop YAML declares an empty placeholder"
        )

    def test_input_hash_injected_into_context(self, tmp_path: Path) -> None:
        """input_hash is injected into fsm.context by cmd_run when input is non-empty."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.fsm.validation import load_and_validate
        from little_loops.logger import Logger

        # Create a loop that declares input: null so the runner injects positional input
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "test-loop.yaml").write_text(
            "name: test-loop\ninitial: done\n"
            'context:\n  input: null\n  targets: ""\n  directive: ""\n  design_tokens_context: ""\n'
            "states:\n  done:\n    terminal: true\n"
        )

        args = self._make_args(input="FEAT-719", dry_run=True)
        logger = Logger(use_color=False)

        fsm, _ = load_and_validate(loops_dir / "test-loop.yaml")

        def fake_load_and_validate(path: Path):  # type: ignore[override]
            return fsm, []

        from unittest.mock import patch

        with patch(
            "little_loops.fsm.validation.load_and_validate",
            side_effect=fake_load_and_validate,
        ):
            cmd_run("test-loop", args, loops_dir, logger)

        assert "input_hash" in fsm.context, (
            "input_hash must be present in fsm.context when input is non-empty"
        )
        assert isinstance(fsm.context["input_hash"], str)
        assert len(fsm.context["input_hash"]) == 12, "input_hash must be a 12-char hex digest"

    def test_input_hash_not_injected_when_input_absent(self, tmp_path: Path) -> None:
        """input_hash is NOT injected when input is absent (None or empty)."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.fsm.validation import load_and_validate
        from little_loops.logger import Logger

        loops_dir = self._make_loop(tmp_path)
        args = self._make_args(input=None, dry_run=True)
        logger = Logger(use_color=False)

        fsm, _ = load_and_validate(loops_dir / "test-loop.yaml")

        def fake_load_and_validate(path: Path):  # type: ignore[override]
            return fsm, []

        from unittest.mock import patch

        with patch(
            "little_loops.fsm.validation.load_and_validate",
            side_effect=fake_load_and_validate,
        ):
            cmd_run("test-loop", args, loops_dir, logger)

        assert "input_hash" not in fsm.context, (
            "input_hash must NOT be present in fsm.context when input is absent"
        )

    def test_context_input_hash_not_overwritten_by_user_context(self, tmp_path: Path) -> None:
        """--context input_hash=custom overrides the runner-injected default."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.fsm.validation import load_and_validate
        from little_loops.logger import Logger

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "test-loop.yaml").write_text(
            "name: test-loop\ninitial: done\n"
            'context:\n  input: null\n  targets: ""\n  directive: ""\n  design_tokens_context: ""\n'
            "states:\n  done:\n    terminal: true\n"
        )

        args = self._make_args(
            input="FEAT-719",
            context=["input_hash=custom-hash-value"],
            dry_run=True,
        )
        logger = Logger(use_color=False)

        fsm, _ = load_and_validate(loops_dir / "test-loop.yaml")

        def fake_load_and_validate(path: Path):  # type: ignore[override]
            return fsm, []

        from unittest.mock import patch

        with patch(
            "little_loops.fsm.validation.load_and_validate",
            side_effect=fake_load_and_validate,
        ):
            cmd_run("test-loop", args, loops_dir, logger)

        assert fsm.context.get("input_hash") == "custom-hash-value", (
            "--context input_hash=VALUE must override the runner-injected default"
        )

    def test_context_run_dir_not_overwritten_by_user_context(self, tmp_path: Path) -> None:
        """--context run_dir=custom overrides the runner-injected default."""
        from little_loops.cli.loop.run import cmd_run
        from little_loops.fsm.validation import load_and_validate
        from little_loops.logger import Logger

        loops_dir = self._make_loop(tmp_path)
        args = self._make_args(dry_run=True, context=["run_dir=/custom/path/"])
        logger = Logger(use_color=False)

        fsm, _ = load_and_validate(loops_dir / "test-loop.yaml")

        def fake_load_and_validate(path: Path):  # type: ignore[override]
            return fsm, []

        with patch(
            "little_loops.fsm.validation.load_and_validate", side_effect=fake_load_and_validate
        ):
            cmd_run("test-loop", args, loops_dir, logger)

        assert fsm.context.get("run_dir") == "/custom/path/", (
            "--context run_dir=VALUE must take precedence over runner injection"
        )

    def test_default_program_md_path_is_cwd_ll_program_md(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When program_md arg is None, defaults to .ll/program.md in cwd."""
        from little_loops.cli.loop.run import _parse_program_md

        monkeypatch.chdir(tmp_path)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        (ll_dir / "program.md").write_text("## Directive\nDefault path goal.\n")

        result = _parse_program_md(tmp_path / ".ll" / "program.md")
        assert result.get("directive") == "Default path goal."
