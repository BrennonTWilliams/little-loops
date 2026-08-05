"""Tests for little_loops.issues.cli_claims.extract_cli_flag_claims (FEAT-3048)."""

from __future__ import annotations

from little_loops.issues.cli_claims import CliFlagClaim, extract_cli_flag_claims


def test_tool_subcommand_and_flag() -> None:
    body = "but `ll-issues link --parent` doesn't work"
    assert extract_cli_flag_claims(body) == {
        CliFlagClaim(
            tool="ll-issues", subcommand="link", flags=("--parent",), raw="ll-issues link --parent"
        )
    }


def test_tool_and_subcommand_no_flags() -> None:
    body = "Run `ll-issues format-check` first."
    assert extract_cli_flag_claims(body) == {
        CliFlagClaim(
            tool="ll-issues", subcommand="format-check", flags=(), raw="ll-issues format-check"
        )
    }


def test_multiple_flags() -> None:
    body = "`ll-issues format-check --all --fix` sweeps everything."
    (claim,) = extract_cli_flag_claims(body)
    assert claim.tool == "ll-issues"
    assert claim.subcommand == "format-check"
    assert claim.flags == ("--all", "--fix")


def test_bare_tool_with_no_subcommand_is_not_a_claim() -> None:
    assert extract_cli_flag_claims("Use `ll-issues` for issue management.") == set()


def test_short_flags_ignored() -> None:
    body = "`ll-issues format-check -a` is the short form."
    (claim,) = extract_cli_flag_claims(body)
    assert claim.flags == ()


def test_non_ll_backtick_text_is_not_a_claim() -> None:
    assert extract_cli_flag_claims("Reuse `frontmatter.update_frontmatter` for writes") == set()


def test_no_claim_inside_fenced_code_block() -> None:
    body = "```\n`ll-issues link --parent`\n```"
    assert extract_cli_flag_claims(body) == set()


def test_suppressed_claim_via_ll_prose_ok_marker() -> None:
    body = "<!-- ll-prose-ok: aspirational -->\n`ll-issues link --parent` will exist someday."
    assert extract_cli_flag_claims(body) == set()


def test_empty_body() -> None:
    assert extract_cli_flag_claims("") == set()


def test_feat_2942_regression_fixture_original_text() -> None:
    """Pins FEAT-2942's original claim text from commit 2225b414 — the
    motivating defect for FEAT-3048. Do not read the live FEAT-2942 file: it
    has since been hand-corrected and no longer contains this claim.
    """
    body = "Reuse `ll-issues link` / `frontmatter.update_frontmatter` for writes"
    claims = extract_cli_flag_claims(body)
    assert claims == {
        CliFlagClaim(tool="ll-issues", subcommand="link", flags=(), raw="ll-issues link")
    }
