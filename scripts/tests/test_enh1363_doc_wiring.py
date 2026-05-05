"""Doc-wiring tests for ENH-1363: --issues filter argument for tradeoff-review-issues.

Asserts that commands/tradeoff-review-issues.md has the correct frontmatter,
conditional Phase 1 branch, and example invocations for the new filter argument.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
COMMAND_FILE = PROJECT_ROOT / "commands" / "tradeoff-review-issues.md"
HELP_FILE = PROJECT_ROOT / "commands" / "help.md"
COMMANDS_REF = PROJECT_ROOT / "docs" / "reference" / "COMMANDS.md"


class TestTradeoffReviewFrontmatter:
    """commands/tradeoff-review-issues.md must have complete ENH-1363 frontmatter."""

    def test_command_file_exists(self) -> None:
        assert COMMAND_FILE.exists(), "commands/tradeoff-review-issues.md not found"

    def test_argument_hint_present(self) -> None:
        content = COMMAND_FILE.read_text()
        assert 'argument-hint: "[issue-ids]"' in content, (
            'commands/tradeoff-review-issues.md must have argument-hint: "[issue-ids]" in frontmatter'
        )

    def test_arguments_block_present(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "arguments:" in content, (
            "commands/tradeoff-review-issues.md must have an arguments: block in frontmatter"
        )

    def test_issues_argument_named(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "name: issues" in content, (
            "commands/tradeoff-review-issues.md must declare a named argument 'issues'"
        )

    def test_issues_argument_description_mentions_comma_separated(self) -> None:
        content = COMMAND_FILE.read_text()
        args_start = content.index("arguments:")
        # Look within the arguments block (up to next top-level --- or end of frontmatter)
        args_section = content[args_start : args_start + 300]
        assert "Comma-separated" in args_section or "comma-separated" in args_section, (
            "The 'issues' argument description must mention comma-separated IDs"
        )

    def test_ll_issues_in_allowed_tools(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "Bash(ll-issues:*)" in content, (
            "commands/tradeoff-review-issues.md must include Bash(ll-issues:*) in allowed-tools "
            "to permit ll-issues path calls in the conditional branch"
        )


class TestTradeoffReviewConditionalPhase1:
    """commands/tradeoff-review-issues.md must have the conditional Phase 1 filter branch."""

    def test_conditional_branch_present(self) -> None:
        content = COMMAND_FILE.read_text()
        assert (
            'ISSUES_ARG="${issues:-}"' in content
            or "issues argument is provided" in content.lower()
            or "If the `issues` argument is provided" in content
        ), (
            "commands/tradeoff-review-issues.md must contain the conditional Phase 1 branch for the issues argument"
        )

    def test_ll_issues_path_call_present(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "ll-issues path" in content, (
            "commands/tradeoff-review-issues.md must call `ll-issues path` to resolve IDs in the conditional branch"
        )

    def test_skip_on_miss_warning_present(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "not found (skipping)" in content or "Warning: Issue" in content, (
            "commands/tradeoff-review-issues.md must include skip-on-miss warning for unresolvable IDs"
        )

    def test_zero_ids_error_present(self) -> None:
        content = COMMAND_FILE.read_text()
        assert (
            "None of the specified issue IDs" in content
            or "zero IDs" in content.lower()
            or "ISSUE_FILES[@]} -eq 0" in content
        ), "commands/tradeoff-review-issues.md must abort when no IDs resolve to active issues"


class TestTradeoffReviewExamples:
    """commands/tradeoff-review-issues.md must show filtered invocation examples."""

    def test_single_id_example_present(self) -> None:
        content = COMMAND_FILE.read_text()
        examples_start = content.index("## Examples")
        examples_section = content[examples_start:]
        assert "BUG-123" in examples_section or "FEAT-" in examples_section, (
            "commands/tradeoff-review-issues.md Examples section must show a single-ID invocation"
        )

    def test_comma_separated_example_present(self) -> None:
        content = COMMAND_FILE.read_text()
        examples_start = content.index("## Examples")
        examples_section = content[examples_start:]
        assert "," in examples_section and "tradeoff-review-issues" in examples_section, (
            "commands/tradeoff-review-issues.md Examples section must show a comma-separated IDs invocation"
        )


class TestHelpFileUpdated:
    """`commands/help.md` must show the [issue-ids] argument for tradeoff-review-issues."""

    def test_help_file_shows_issue_ids_arg(self) -> None:
        content = HELP_FILE.read_text()
        tradeoff_start = content.index("/ll:tradeoff-review-issues")
        tradeoff_block = content[tradeoff_start : tradeoff_start + 300]
        assert (
            "issue-ids" in tradeoff_block
            or "issue_ids" in tradeoff_block
            or "issues" in tradeoff_block
        ), "commands/help.md must show the [issue-ids] argument for /ll:tradeoff-review-issues"


class TestCommandsRefUpdated:
    """`docs/reference/COMMANDS.md` must have an Arguments section for tradeoff-review-issues."""

    def test_commands_ref_has_arguments_section(self) -> None:
        content = COMMANDS_REF.read_text()
        tradeoff_start = content.index("### `/ll:tradeoff-review-issues`")
        next_heading = content.find("\n###", tradeoff_start + 1)
        tradeoff_block = content[
            tradeoff_start : next_heading if next_heading != -1 else tradeoff_start + 500
        ]
        assert "**Arguments:**" in tradeoff_block, (
            "docs/reference/COMMANDS.md must have an **Arguments:** subsection under /ll:tradeoff-review-issues"
        )

    def test_commands_ref_documents_issues_argument(self) -> None:
        content = COMMANDS_REF.read_text()
        tradeoff_start = content.index("### `/ll:tradeoff-review-issues`")
        next_heading = content.find("\n###", tradeoff_start + 1)
        tradeoff_block = content[
            tradeoff_start : next_heading if next_heading != -1 else tradeoff_start + 500
        ]
        assert "`issues`" in tradeoff_block or "issues" in tradeoff_block, (
            "docs/reference/COMMANDS.md Arguments section must document the 'issues' argument"
        )
