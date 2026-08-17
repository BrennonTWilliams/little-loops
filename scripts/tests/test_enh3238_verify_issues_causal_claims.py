"""Wiring tests for ENH-3238: causal/identity-claim rule in /ll:verify-issues.

verify-issues' §B "Test claims" check had no method distinguishing a directly
observable *consequence* claim from an *identity/causal* claim (e.g. "the live
view IS the vN definition") — a consequence merely consistent with a stated
cause was accepted as sufficient to confirm it. This asserts the new rule's
presence, its placement outside the ll-code-availability-gated §2B.0 block,
and its necessary-vs-sufficient / NEEDS_UPDATE consequence.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

VERIFY_CMD = PROJECT_ROOT / "commands" / "verify-issues.md"


def _body(path: Path) -> str:
    content = path.read_text()
    end = content.index("---", 3)
    return content[end + 3 :]


class TestCausalIdentityClaimRule:
    """§B must gain a causal/identity-claim rule, unconditional and outside §2B.0."""

    def test_rule_present(self) -> None:
        flat = " ".join(_body(VERIFY_CMD).split())
        assert "Causal / identity claims" in flat, (
            "commands/verify-issues.md must define a causal/identity-claim rule "
            "for check 4 (ENH-3238)"
        )

    def test_rule_sits_outside_graph_assisted_block(self) -> None:
        body = _body(VERIFY_CMD)
        graph_block_start = body.index("Graph-assisted checks")
        section_b_start = body.index("#### B. Verify Against Codebase")
        rule_start = body.index("Causal / identity claims")
        assert rule_start > section_b_start > graph_block_start, (
            "the causal/identity-claim rule must sit in §B, after §2B.0's "
            "Graph-assisted checks block — it must run unconditionally, not "
            "only when ll-code is available and fresh"
        )

    def test_states_necessary_not_sufficient(self) -> None:
        flat = " ".join(_body(VERIFY_CMD).split())
        assert "necessary but not sufficient" in flat, (
            "the rule must state that a consequence consistent with the "
            "stated cause is necessary but not sufficient to confirm it"
        )

    def test_states_needs_update_consequence(self) -> None:
        flat = " ".join(_body(VERIFY_CMD).split())
        assert "assign `NEEDS_UPDATE` rather than `VALID`" in flat, (
            "an unverifiable causal/identity claim must route to NEEDS_UPDATE, "
            "not VALID"
        )

    def test_states_load_bearing_firing_constraint(self) -> None:
        flat = " ".join(_body(VERIFY_CMD).split())
        assert "load-bearing for the fix" in flat, (
            "the rule must scope its trigger to load-bearing attributions "
            "(root cause / artifact identity / version attribution), not "
            "incidental causal prose — otherwise it over-fires on nearly "
            "every issue"
        )

    def test_names_direct_probe_over_inference(self) -> None:
        flat = " ".join(_body(VERIFY_CMD).split())
        assert "sqlite_master" in flat and "PRAGMA table_info" in flat, (
            "the rule must contrast a direct probe (stored DDL) against an "
            "inferred consequence-only signal, per the BUG-3236 case study"
        )
