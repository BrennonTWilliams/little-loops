"""Doc-wiring tests for ENH-1362: --issues filter argument for align-issues.

Asserts that commands/align-issues.md has the correct frontmatter,
conditional Step 4 branch, and example invocations for the new filter argument.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
COMMAND_FILE = PROJECT_ROOT / "commands" / "align-issues.md"
HELP_FILE = PROJECT_ROOT / "commands" / "help.md"
COMMANDS_REF = PROJECT_ROOT / "docs" / "reference" / "COMMANDS.md"


class TestAlignIssuesFrontmatter:
    """commands/align-issues.md must have complete ENH-1362 frontmatter."""

    def test_command_file_exists(self) -> None:
        assert COMMAND_FILE.exists(), "commands/align-issues.md not found"

    def test_argument_hint_updated(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "--issues" in content and "argument-hint" in content, (
            'commands/align-issues.md must have "--issues" in argument-hint frontmatter'
        )

    def test_arguments_block_present(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "arguments:" in content, (
            "commands/align-issues.md must have an arguments: block in frontmatter"
        )

    def test_issues_argument_named(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "name: issues" in content, (
            "commands/align-issues.md must declare a named argument 'issues'"
        )

    def test_issues_argument_description_mentions_comma_separated(self) -> None:
        content = COMMAND_FILE.read_text()
        args_start = content.index("arguments:")
        args_section = content[args_start : args_start + 400]
        assert "Comma-separated" in args_section or "comma-separated" in args_section, (
            "The 'issues' argument description must mention comma-separated IDs"
        )

    def test_ll_issues_in_allowed_tools(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "Bash(ll-issues:*)" in content, (
            "commands/align-issues.md must include Bash(ll-issues:*) in allowed-tools "
            "to permit ll-issues path calls in the conditional branch"
        )


class TestAlignIssuesConditionalStep4:
    """commands/align-issues.md must have the conditional Step 4 filter branch."""

    def test_issues_arg_variable_present(self) -> None:
        content = COMMAND_FILE.read_text()
        assert 'ISSUES_ARG="${issues:-}"' in content, (
            'commands/align-issues.md must contain ISSUES_ARG="${issues:-}" in Step 1'
        )

    def test_ll_issues_path_call_present(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "ll-issues path" in content, (
            "commands/align-issues.md must call `ll-issues path` to resolve IDs in the conditional branch"
        )

    def test_skip_on_miss_warning_present(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "not found (skipping)" in content or "Warning: Issue" in content, (
            "commands/align-issues.md must include skip-on-miss warning for unresolvable IDs"
        )

    def test_zero_ids_error_present(self) -> None:
        content = COMMAND_FILE.read_text()
        assert "None of the specified issue IDs" in content or "ISSUE_FILES[@]} -eq 0" in content, (
            "commands/align-issues.md must abort when no IDs resolve to active issues"
        )


class TestAlignIssuesExamples:
    """commands/align-issues.md must show filtered invocation examples."""

    def test_single_id_example_present(self) -> None:
        content = COMMAND_FILE.read_text()
        examples_start = content.index("## Examples")
        examples_section = content[examples_start:]
        assert "--issues" in examples_section, (
            "commands/align-issues.md Examples section must show a --issues invocation"
        )

    def test_comma_separated_example_present(self) -> None:
        content = COMMAND_FILE.read_text()
        examples_start = content.index("## Examples")
        examples_section = content[examples_start:]
        assert "," in examples_section and "--issues" in examples_section, (
            "commands/align-issues.md Examples section must show a comma-separated IDs invocation"
        )


class TestHelpFileUpdated:
    """`commands/help.md` must show the --issues flag for align-issues."""

    def test_help_file_shows_issues_flag(self) -> None:
        content = HELP_FILE.read_text()
        align_start = content.index("/ll:align-issues")
        align_block = content[align_start : align_start + 300]
        assert "--issues" in align_block, (
            "commands/help.md must show the --issues flag for /ll:align-issues"
        )


class TestCommandsRefUpdated:
    """`docs/reference/COMMANDS.md` must document the issues argument for align-issues."""

    def test_commands_ref_has_arguments_section(self) -> None:
        content = COMMANDS_REF.read_text()
        align_start = content.index("### `/ll:align-issues`")
        next_heading = content.find("\n###", align_start + 1)
        align_block = content[
            align_start : next_heading if next_heading != -1 else align_start + 500
        ]
        assert "**Arguments:**" in align_block, (
            "docs/reference/COMMANDS.md must have an **Arguments:** subsection under /ll:align-issues"
        )

    def test_commands_ref_documents_issues_argument(self) -> None:
        content = COMMANDS_REF.read_text()
        align_start = content.index("### `/ll:align-issues`")
        next_heading = content.find("\n###", align_start + 1)
        align_block = content[
            align_start : next_heading if next_heading != -1 else align_start + 500
        ]
        assert "`issues`" in align_block or "issues" in align_block, (
            "docs/reference/COMMANDS.md Arguments section must document the 'issues' argument"
        )
