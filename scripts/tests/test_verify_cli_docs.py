"""Tests for ll-verify-cli-docs (ENH-2970)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.cli.verify_cli_docs import (
    DocClaim,
    _extract_choices,
    _extract_subcommands,
    _find_paren_groups,
    _run,
    _split_top_level,
    _unwrap_bare_token,
    find_undocumented_entry_points,
    main_verify_cli_docs,
    parse_cli_section,
    probe_tool,
    verify_claims,
)

_REAL_CLAUDE_MD = Path(__file__).resolve().parents[2] / ".claude" / "CLAUDE.md"


def _write_md(tmp_path: Path, cli_tools_body: str) -> Path:
    md_path = tmp_path / "CLAUDE.md"
    md_path.write_text(
        f"# little-loops\n\n## CLI Tools\n\n{cli_tools_body}\n\n## Next Section\n\nmore text\n"
    )
    return md_path


class TestFindParenGroups:
    def test_single_top_level_group(self) -> None:
        assert _find_paren_groups("desc (a, b, c)") == ["a, b, c"]

    def test_nested_groups_only_top_level(self) -> None:
        assert _find_paren_groups("desc (a, b (aside), c)") == ["a, b (aside), c"]

    def test_multiple_top_level_groups(self) -> None:
        assert _find_paren_groups("(one) prose (two)") == ["one", "two"]

    def test_parens_inside_backticks_are_not_grouping(self) -> None:
        assert _find_paren_groups("`type(scope): description` (a, b)") == ["a, b"]

    def test_no_groups(self) -> None:
        assert _find_paren_groups("no parens here") == []


class TestSplitTopLevel:
    def test_splits_on_comma_outside_parens(self) -> None:
        assert _split_top_level("a, b, c", ",") == ["a", " b", " c"]

    def test_ignores_comma_nested_in_parens(self) -> None:
        assert _split_top_level("a, b (nested, comma), c", ",") == ["a", " b (nested, comma)", " c"]

    def test_ignores_separator_inside_backticks(self) -> None:
        assert _split_top_level("`{test,lint,format,type}_cmd`, next", ",") == [
            "`{test,lint,format,type}_cmd`",
            " next",
        ]


class TestUnwrapBareToken:
    def test_plain_bare_token(self) -> None:
        assert _unwrap_bare_token("status") == "status"

    def test_backtick_wrapped_token(self) -> None:
        assert _unwrap_bare_token("`callers-of`") == "callers-of"

    def test_rejects_flag(self) -> None:
        assert _unwrap_bare_token("--foo") is None
        assert _unwrap_bare_token("`--foo`") is None

    def test_rejects_multiword(self) -> None:
        assert _unwrap_bare_token("two words") is None


class TestExtractSubcommands:
    def test_bare_comma_list(self) -> None:
        names, skipped = _extract_subcommands("next-id, list, show")
        assert names == ["next-id", "list", "show"]
        assert skipped == []

    def test_slash_separated_backtick_list(self) -> None:
        names, skipped = _extract_subcommands("`status`/`callers-of`/`impact-of`")
        assert names == ["status", "callers-of", "impact-of"]
        assert skipped == []

    def test_nested_aside_keeps_leading_token(self) -> None:
        names, skipped = _extract_subcommands("find-similar (alias `fs`; some prose here), list")
        assert names == ["find-similar", "list"]

    def test_impure_segment_is_skipped_whole_not_cherry_picked(self) -> None:
        # Regression: an incidental bare word inside a prose sentence (e.g.
        # "tagging each with `declared`/`inferred`/`default` provenance")
        # must not surface as a lone subcommand claim.
        names, skipped = _extract_subcommands(
            "tagging each with `declared`/`inferred`/`default` provenance, apply"
        )
        assert "inferred" not in names
        assert "declared" not in names
        assert "default" not in names
        assert names == ["apply"]

    def test_flag_paired_with_subcommand_extracts_only_subcommand(self) -> None:
        names, skipped = _extract_subcommands("`--plan`/`apply`")
        assert names == ["apply"]

    def test_brace_expansion_in_backticks_not_split_as_subcommands(self) -> None:
        # Regression: `{test,lint,format,type}_cmd` must not yield "lint"/"format".
        names, skipped = _extract_subcommands(
            "derives `{test,lint,format,type}_cmd` from manifests"
        )
        assert "lint" not in names
        assert "format" not in names


class TestParseCliSection:
    def test_missing_section_returns_empty(self, tmp_path: Path) -> None:
        md_path = tmp_path / "CLAUDE.md"
        md_path.write_text("# no cli tools section here\n")
        claims, skipped = parse_cli_section(md_path)
        assert claims == []
        assert skipped == []

    def test_tool_with_no_extractable_claims_still_documented(self, tmp_path: Path) -> None:
        md_path = _write_md(
            tmp_path, "- `ll-parallel` - Process issues concurrently using worktrees"
        )
        claims, _ = parse_cli_section(md_path)
        tool_level = [
            c for c in claims if c.tool == "ll-parallel" and c.subcommand is None and c.flag is None
        ]
        assert len(tool_level) == 1

    def test_flags_extracted(self, tmp_path: Path) -> None:
        md_path = _write_md(
            tmp_path, "- `ll-auto` - Process issues (`--skip-learning-gate` bypasses the gate)"
        )
        claims, _ = parse_cli_section(md_path)
        flags = [c.flag for c in claims if c.flag]
        assert flags == ["--skip-learning-gate"]

    def test_subcommands_extracted_with_group_index(self, tmp_path: Path) -> None:
        md_path = _write_md(tmp_path, "- `ll-issues` - Issue management (next-id, list, show)")
        claims, _ = parse_cli_section(md_path)
        subs = [(c.subcommand, c.group) for c in claims if c.subcommand]
        assert subs == [("next-id", 0), ("list", 0), ("show", 0)]

    def test_stops_at_next_header(self, tmp_path: Path) -> None:
        md_path = tmp_path / "CLAUDE.md"
        md_path.write_text(
            "## CLI Tools\n\n- `ll-auto` - desc\n\n## Other Section\n\n- `ll-should-not-parse` - desc\n"
        )
        claims, _ = parse_cli_section(md_path)
        assert {c.tool for c in claims} == {"ll-auto"}


class TestExtractChoices:
    def test_brace_list(self) -> None:
        help_text = "usage: ll-x [-h] {a,b,c} ...\n"
        assert _extract_choices(help_text) == frozenset({"a", "b", "c"})

    def test_positional_arguments_block(self) -> None:
        help_text = (
            "usage: ll-queue [-h] COMMAND ...\n\n"
            "positional arguments:\n"
            "  COMMAND\n"
            "    add       Enqueue a work item\n"
            "    list      List all queue entries\n\n"
            "options:\n"
            "  -h, --help  show this help message and exit\n"
        )
        assert _extract_choices(help_text) == frozenset({"add", "list"})

    def test_no_choices(self) -> None:
        assert _extract_choices("usage: ll-x [-h]\n\noptions:\n  -h, --help\n") == frozenset()


class TestProbeTool:
    def test_real_tool_resolves(self) -> None:
        probed = probe_tool("ll-issues")
        assert probed is not None
        choices, help_text = probed
        assert "list" in choices or "show" in choices
        assert "ll-issues" in help_text or "usage" in help_text

    def test_nonexistent_tool_returns_none(self) -> None:
        assert probe_tool("ll-this-tool-does-not-exist-xyz") is None

    def test_cached_across_calls(self) -> None:
        first = probe_tool("ll-verify-cli-allowlist")
        second = probe_tool("ll-verify-cli-allowlist")
        assert first is second


class TestVerifyClaims:
    def test_unknown_tool_is_error(self) -> None:
        drifts = verify_claims(
            [DocClaim(tool="ll-not-a-real-tool", subcommand=None, flag=None, line=1)]
        )
        assert len(drifts) == 1
        assert drifts[0].kind == "unknown_tool"
        assert drifts[0].severity == "error"

    def test_known_flag_produces_no_drift(self) -> None:
        drifts = verify_claims(
            [DocClaim(tool="ll-auto", subcommand=None, flag="--skip-learning-gate", line=1)]
        )
        assert drifts == []

    def test_unknown_flag_is_error(self) -> None:
        drifts = verify_claims(
            [DocClaim(tool="ll-auto", subcommand=None, flag="--totally-bogus-flag", line=1)]
        )
        assert len(drifts) == 1
        assert drifts[0].kind == "unknown_flag"
        assert drifts[0].severity == "error"

    def test_nested_subcommand_flag_found_via_combined_help(self) -> None:
        # --force belongs to `ll-loop queue remove`, two levels deep.
        drifts = verify_claims([DocClaim(tool="ll-loop", subcommand=None, flag="--force", line=1)])
        assert drifts == []

    def test_known_subcommand_produces_no_drift(self) -> None:
        drifts = verify_claims(
            [DocClaim(tool="ll-issues", subcommand="list", flag=None, line=1, group=0)]
        )
        assert drifts == []

    def test_unknown_subcommand_is_error_when_group_has_a_real_match(self) -> None:
        drifts = verify_claims(
            [
                DocClaim(tool="ll-issues", subcommand="list", flag=None, line=1, group=0),
                DocClaim(tool="ll-issues", subcommand="bogus-xyz", flag=None, line=1, group=0),
            ]
        )
        kinds = [(d.kind, d.tool) for d in drifts]
        assert ("unknown_subcommand", "ll-issues") in kinds
        assert len(drifts) == 1

    def test_group_with_no_real_matches_is_not_flagged(self) -> None:
        # Simulates a prose gloss group where nothing resolves — treated as
        # unparsed prose, not documentation drift (ll-code's plain-English
        # aside is the real-world instance of this).
        drifts = verify_claims(
            [
                DocClaim(tool="ll-code", subcommand="callers", flag=None, line=1, group=0),
                DocClaim(tool="ll-code", subcommand="callees", flag=None, line=1, group=0),
            ]
        )
        assert drifts == []


class TestFindUndocumentedEntryPoints:
    def test_flags_entry_point_with_no_claim(self) -> None:
        drifts = find_undocumented_entry_points(
            [DocClaim(tool="ll-auto", subcommand=None, flag=None, line=1)]
        )
        tools = {d.tool for d in drifts}
        assert (
            "ll-issues" in tools
        )  # definitely a real entry point, not documented in this fake claim set
        assert "ll-auto" not in tools
        assert all(d.severity == "warn" for d in drifts)


class TestRunOnRealClaudeMd:
    def test_no_error_severity_drift(self) -> None:
        assert _REAL_CLAUDE_MD.is_file(), "expected .claude/CLAUDE.md to exist in the source repo"
        exit_code, drifts, _skipped = _run(_REAL_CLAUDE_MD)
        errors = [d for d in drifts if d.severity == "error"]
        assert errors == [], f"unexpected CLAUDE.md CLI drift: {errors}"
        assert exit_code == 0


class TestMainVerifyCliDocs:
    def test_clean_tree_returns_zero(self) -> None:
        with patch("sys.argv", ["ll-verify-cli-docs"]):
            assert main_verify_cli_docs() == 0

    def test_missing_path_is_skip_not_failure(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        missing = tmp_path / "does-not-exist.md"
        with patch("sys.argv", ["ll-verify-cli-docs", "--path", str(missing)]):
            ret = main_verify_cli_docs()
        assert ret == 0
        assert "SKIP" in capsys.readouterr().err

    def test_injected_bogus_flag_fails(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        md_path = _write_md(
            tmp_path, "- `ll-auto` - Process issues (`--totally-bogus-flag` does nothing)"
        )
        with patch("sys.argv", ["ll-verify-cli-docs", "--path", str(md_path)]):
            ret = main_verify_cli_docs()
        assert ret == 1
        assert "--totally-bogus-flag" in capsys.readouterr().err
