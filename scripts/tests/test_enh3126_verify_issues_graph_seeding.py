"""Wiring tests for ENH-3126: graph-accelerated checks in /ll:verify-issues.

Verifies that verify-issues declares Bash(ll-code:*), that §2B.0 exists and
delegates to the shared contract doc, that it states the verdict-origination
prohibition rule (stricter than the other two consumers), and that the shared
doc lists verify-issues as a consumer.

Unlike refine-issue and wire-issue, verify-issues spawns no sub-agents and may
write frontmatter (`verify_verdict`) and close issues — so a graph result may
only corroborate or correct a verdict, never originate one.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

VERIFY_CMD = PROJECT_ROOT / "commands" / "verify-issues.md"
VERIFY_BRIDGE = PROJECT_ROOT / "skills" / "ll-verify-issues" / "SKILL.md"
SHARED_DOC = PROJECT_ROOT / "docs" / "guides" / "GRAPH_DISCOVERY_GUIDE.md"
CLI_DOC = PROJECT_ROOT / "docs" / "reference" / "CLI.md"


def _frontmatter(path: Path) -> str:
    content = path.read_text()
    end = content.index("---", 3)
    return content[: end + 3]


def _body(path: Path) -> str:
    content = path.read_text()
    end = content.index("---", 3)
    return content[end + 3 :]


class TestVerifyIssuesFrontmatter:
    """verify-issues and its bridge must be allowed to run ll-code."""

    def test_declares_ll_code_tool(self) -> None:
        assert "Bash(ll-code:*)" in _frontmatter(VERIFY_CMD), (
            "commands/verify-issues.md must include Bash(ll-code:*) in "
            "allowed-tools (ENH-3126) — §2B.0 cannot probe the provider without it"
        )

    def test_bridge_mirrors_allowed_tools(self) -> None:
        fm = VERIFY_BRIDGE.read_text()
        assert "Bash(ll-code:*)" in fm, (
            "skills/ll-verify-issues/SKILL.md must mirror the command's "
            "Bash(ll-code:*) grant (ENH-3126), matching the "
            "skills/ll-refine-issue/SKILL.md precedent"
        )


class TestSection2B0GraphAssistedChecks:
    """§2B.0 must exist, precede the manual sweep, and delegate the contract."""

    def test_section_present(self) -> None:
        assert "Graph-assisted checks" in _body(VERIFY_CMD), (
            "commands/verify-issues.md must define §2B.0 Graph-assisted checks (ENH-3126)"
        )

    def test_section_precedes_manual_sweep(self) -> None:
        body = _body(VERIFY_CMD)
        assert body.index("Graph-assisted checks") < body.index(
            "#### B. Verify Against Codebase"
        ), "§2B.0 must run before the manual verification sweep (2B.1-2B.5)"

    def test_delegates_to_shared_contract_doc(self) -> None:
        assert "GRAPH_DISCOVERY_GUIDE.md" in _body(VERIFY_CMD), (
            "§2B.0 must link the shared contract doc rather than restating the "
            "ll-code contract inline (drift risk with refine-issue/wire-issue)"
        )

    def test_restricts_query_surface(self) -> None:
        body = _body(VERIFY_CMD)
        assert "impact-of" in body and "NOT permitted" in body, (
            "§2B.0 must explicitly exclude impact-of from the permitted query "
            "surface — the git-history regression path already provides "
            "deterministic evidence"
        )

    def test_states_verdict_origination_prohibition(self) -> None:
        flat = " ".join(_body(VERIFY_CMD).split())
        assert "may corroborate or correct a verdict" in flat, (
            "§2B.0 must state the verdict-origination prohibition — a graph "
            "result may never originate a verdict, only confirm or correct one"
        )
        assert "never by itself produce" in flat, (
            "the prohibition must call out that a callers-of 'no callers' exit "
            "must never by itself produce RESOLVED or INVALID"
        )

    def test_wires_defines_into_anchor_check(self) -> None:
        body = _body(VERIFY_CMD)
        assert "ll-code" in body and "defines" in body, (
            "§2B.0 must wire `defines` into the line-number/anchor drift check"
        )

    def test_records_provider_freshness_outside_session_log(self) -> None:
        body = _body(VERIFY_CMD)
        assert "provider" in body.lower() and "freshness" in body.lower(), (
            "the verification report must record provider/freshness (ENH-3126)"
        )
        flat = " ".join(body.split())
        assert "Do **not** put this in the Session Log" in flat or (
            "issue_design_timestamp" in flat
        ), (
            "§2B.0 must warn against writing provenance into the Session Log — "
            "issue_design_timestamp() parses that line and extra text disarms "
            "the Program Design gate"
        )


class TestSharedContractDocListsVerifyIssues:
    """The canonical doc's Consumers table must include verify-issues."""

    def test_consumers_table_has_verify_issues_row(self) -> None:
        text = SHARED_DOC.read_text()
        assert "/ll:verify-issues" in text, (
            "GRAPH_DISCOVERY_GUIDE.md § Consumers must list /ll:verify-issues (ENH-3126)"
        )
        assert "commands/verify-issues.md" in text

    def test_cli_doc_names_verify_issues_consumer(self) -> None:
        text = CLI_DOC.read_text()
        assert "/ll:verify-issues" in text, (
            "docs/reference/CLI.md's 'Skill consumers' sentence under ll-code "
            "must append /ll:verify-issues (§2B.0) (ENH-3126)"
        )
