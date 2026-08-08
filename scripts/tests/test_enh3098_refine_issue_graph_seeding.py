"""Wiring tests for ENH-3098: graph-accelerated seeding in /ll:refine-issue.

Verifies that refine-issue (and its Codex/kimi bridge) declares Bash(ll-code:*),
that Step 3.05 exists and delegates to the shared contract doc, that the locator
and analyzer agent prompts carry a CONFIRMED SEEDS slot, and that the shared doc
states the three safety rules the seeding phase depends on.

The design constraint under test: `ll-code` is queried by the *orchestrator*, not
by ll:codebase-* agents. Those agents must stay Bash-free — agent frontmatter takes
bare tool names and cannot scope Bash to a single binary.
"""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent

REFINE_CMD = PROJECT_ROOT / "commands" / "refine-issue.md"
REFINE_BRIDGE = PROJECT_ROOT / "skills" / "ll-refine-issue" / "SKILL.md"
SHARED_DOC = PROJECT_ROOT / "docs" / "guides" / "GRAPH_DISCOVERY_GUIDE.md"
WIRE_ISSUE_LAYER = PROJECT_ROOT / "skills" / "wire-issue" / "graph-discovery-layer.md"

RESEARCH_AGENTS = (
    PROJECT_ROOT / "agents" / "codebase-locator.md",
    PROJECT_ROOT / "agents" / "codebase-analyzer.md",
    PROJECT_ROOT / "agents" / "codebase-pattern-finder.md",
)


def _frontmatter(path: Path) -> str:
    content = path.read_text()
    end = content.index("---", 3)
    return content[: end + 3]


def _body(path: Path) -> str:
    content = path.read_text()
    end = content.index("---", 3)
    return content[end + 3 :]


class TestRefineIssueFrontmatter:
    """refine-issue and its bridge must be allowed to run ll-code."""

    @pytest.mark.parametrize("path", [REFINE_CMD, REFINE_BRIDGE], ids=["command", "bridge"])
    def test_declares_ll_code_tool(self, path: Path) -> None:
        assert "Bash(ll-code:*)" in _frontmatter(path), (
            f"{path.relative_to(PROJECT_ROOT)} must include Bash(ll-code:*) in "
            "allowed-tools (ENH-3098) — Step 3.05 cannot probe the provider without it"
        )


class TestStep305Seeding:
    """Step 3.05 must exist, delegate the contract, and seed the right agents."""

    def test_step_305_present(self) -> None:
        assert "#### 3.05 Seed the agents from the code graph" in _body(REFINE_CMD), (
            "commands/refine-issue.md must define Step 3.05 (ENH-3098)"
        )

    def test_step_305_precedes_agent_dispatch(self) -> None:
        body = _body(REFINE_CMD)
        assert body.index("#### 3.05 Seed the agents") < body.index("#### Agent 1:"), (
            "Step 3.05 must run before the agent wave — seeds it cannot deliver in "
            "time are not seeds"
        )

    def test_delegates_to_shared_contract_doc(self) -> None:
        assert "GRAPH_DISCOVERY_GUIDE.md" in _body(REFINE_CMD), (
            "Step 3.05 must link the shared contract doc rather than restating the "
            "ll-code contract inline (drift risk with wire-issue Phase 3.6)"
        )

    def test_locator_and_analyzer_prompts_have_seed_slot(self) -> None:
        body = _body(REFINE_CMD)
        assert body.count("CONFIRMED SEEDS") >= 2, (
            "both the codebase-locator and codebase-analyzer prompts must carry a "
            "CONFIRMED SEEDS slot (ENH-3098)"
        )

    def test_seeds_are_marked_non_exhaustive(self) -> None:
        body = _body(REFINE_CMD)
        assert body.count("Absence from it is not evidence of absence") >= 2, (
            "every seed block must disclaim exhaustiveness — safety rule 3 "
            "(never trust negatives) is what stops the agents from stopping early"
        )

    def test_pattern_finder_is_left_unseeded(self) -> None:
        body = _body(REFINE_CMD)
        marker = "| `pattern_finder` (Agent 3) | *nothing* |"
        assert marker in body, (
            "the axis table must state that pattern_finder gets no seeds — graph "
            "edges do not express the semantic similarity it looks for"
        )

    def test_provenance_recorded_outside_session_log(self) -> None:
        body = _body(REFINE_CMD)
        assert "Graph seeds:" in body, (
            "the Step 8 output report must carry a `Graph seeds:` line recording "
            "provider/freshness (ENH-3098)"
        )
        flat = " ".join(body.split())
        assert "Do **not** put this in the Step 6.5 Session Log" in flat, (
            "Step 3.05 must warn against writing provenance into the Session Log — "
            "issue_design_timestamp() parses that line and extra text disarms the "
            "Program Design gate"
        )


class TestSharedContractDoc:
    """The canonical doc must carry the contract both consumers rely on."""

    def test_exists(self) -> None:
        assert SHARED_DOC.exists(), "docs/guides/GRAPH_DISCOVERY_GUIDE.md must exist (ENH-3098)"

    @pytest.mark.parametrize(
        "rule",
        ["Silent fallback", "Confirm-before-use", "Never trust negatives"],
        ids=["fallback", "confirm", "negatives"],
    )
    def test_states_safety_rule(self, rule: str) -> None:
        assert rule in SHARED_DOC.read_text(), (
            f"GRAPH_DISCOVERY_GUIDE.md must state the '{rule}' safety rule"
        )

    def test_documents_exit_codes(self) -> None:
        text = SHARED_DOC.read_text()
        assert "`0` = hits, `1` = no hits, `2` = provider error" in text, (
            "the doc must pin ll-code's exit-code contract — the fallback and "
            "never-trust-negatives rules both branch on it"
        )

    def test_wire_issue_layer_delegates_rather_than_duplicates(self) -> None:
        text = WIRE_ISSUE_LAYER.read_text()
        assert "GRAPH_DISCOVERY_GUIDE.md" in text, (
            "skills/wire-issue/graph-discovery-layer.md must link the shared doc"
        )
        assert "Exit codes" not in text, (
            "the wire-issue layer must not restate the ll-code contract — that "
            "duplication is exactly what ENH-3098 removed"
        )


class TestResearchAgentsStayBashFree:
    """The ll:codebase-* agents must not be granted shell to reach ll-code."""

    @pytest.mark.parametrize("path", RESEARCH_AGENTS, ids=lambda p: p.stem)
    def test_agent_has_no_bash_tool(self, path: Path) -> None:
        fm = _frontmatter(path)
        assert "Bash" not in fm, (
            f"agents/{path.name} must not declare Bash (ENH-3098). Agent frontmatter "
            "cannot scope Bash to a single binary, so this grants unrestricted shell "
            "to a read-only agent. ll-code is queried by the orchestrator instead — "
            "see docs/guides/GRAPH_DISCOVERY_GUIDE.md."
        )
