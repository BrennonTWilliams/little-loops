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
            "show_diagrams": None,
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
            'context:\n  targets: ""\n  directive: ""\n'
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
