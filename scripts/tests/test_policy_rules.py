"""Unit tests for fsm/policy_rules.py — parse / serialize / evaluate.

Covers:
- parse_rules: single predicate, conjunctive &, catch-all *, all operators,
  blank/comment skipping, parse-time validation errors
- serialize_rules: lossless inverse, parse→serialize→parse round-trip stability
- evaluate_rules: first-match-wins, numeric coercion ("9" < "10" is True),
  conjunctive AND semantics, missing dimension handling, string fallback
"""

from __future__ import annotations

import pytest

from little_loops.fsm.policy_rules import (
    Predicate,
    evaluate_rules,
    parse_rules,
    serialize_rules,
)

# ---------------------------------------------------------------------------
# parse_rules
# ---------------------------------------------------------------------------


class TestParseRules:
    def test_single_predicate_ge(self) -> None:
        rules = parse_rules("confidence:>=85 -> implement")
        assert len(rules) == 1
        r = rules[0]
        assert not r.is_catchall
        assert len(r.predicates) == 1
        assert r.predicates[0] == Predicate(dim="confidence", op=">=", value="85")
        assert r.target == "implement"

    def test_single_predicate_lt(self) -> None:
        rules = parse_rules("security:<65 -> escalate")
        assert len(rules) == 1
        assert rules[0].predicates[0] == Predicate(dim="security", op="<", value="65")
        assert rules[0].target == "escalate"

    def test_catchall(self) -> None:
        rules = parse_rules("* -> fallback")
        assert len(rules) == 1
        assert rules[0].is_catchall
        assert rules[0].target == "fallback"
        assert rules[0].predicates == []

    def test_conjunctive_two_predicates(self) -> None:
        rules = parse_rules("confidence:>=85 & outcome:>=75 -> implement")
        assert len(rules) == 1
        r = rules[0]
        assert not r.is_catchall
        assert len(r.predicates) == 2
        assert r.predicates[0] == Predicate(dim="confidence", op=">=", value="85")
        assert r.predicates[1] == Predicate(dim="outcome", op=">=", value="75")
        assert r.target == "implement"

    def test_conjunctive_three_predicates(self) -> None:
        rules = parse_rules("a:>=85 & b:>=85 & c:>=85 -> all_high")
        assert len(rules[0].predicates) == 3

    def test_all_operators_parsed(self) -> None:
        text = "\n".join(
            [
                "a:>=10 -> s1",
                "b:<=10 -> s2",
                "c:==10 -> s3",
                "d:!=10 -> s4",
                "e:<10  -> s5",
                "f:>10  -> s6",
            ]
        )
        rules = parse_rules(text)
        assert len(rules) == 6
        ops = [r.predicates[0].op for r in rules]
        assert ops == [">=", "<=", "==", "!=", "<", ">"]

    def test_blank_lines_skipped(self) -> None:
        text = "\nconfidence:>=85 -> implement\n\n"
        rules = parse_rules(text)
        assert len(rules) == 1

    def test_comment_lines_skipped(self) -> None:
        text = "# header\nconfidence:>=85 -> implement\n# tail"
        rules = parse_rules(text)
        assert len(rules) == 1

    def test_source_order_preserved(self) -> None:
        text = "a:>=90 -> high\na:>=70 -> medium\n* -> low"
        rules = parse_rules(text)
        assert [r.target for r in rules] == ["high", "medium", "low"]

    def test_multi_rule_table(self) -> None:
        text = (
            "security:<65 -> escalate\n"
            "completeness:<60 -> deep_repair\n"
            "feasibility:<60 -> rethink\n"
            "aggregate:>=85 -> done\n"
            "aggregate:>=60 -> light_repair\n"
            "* -> deep_repair"
        )
        rules = parse_rules(text)
        assert len(rules) == 6
        assert rules[-1].is_catchall

    def test_equals_string_value_allowed(self) -> None:
        rules = parse_rules("flag:==true -> match")
        assert rules[0].predicates[0].value == "true"

    def test_not_equals_string_value_allowed(self) -> None:
        rules = parse_rules("flag:!=false -> match")
        assert rules[0].predicates[0].value == "false"

    def test_ordered_op_non_numeric_raises(self) -> None:
        with pytest.raises(ValueError, match="numeric"):
            parse_rules("dim:>=abc -> state")

    def test_ordered_op_non_numeric_lt_raises(self) -> None:
        with pytest.raises(ValueError, match="numeric"):
            parse_rules("dim:<notanumber -> state")

    def test_missing_arrow_raises(self) -> None:
        with pytest.raises(ValueError, match="missing"):
            parse_rules("dim:>=85 state")

    def test_empty_target_raises(self) -> None:
        with pytest.raises(ValueError, match="empty target"):
            parse_rules("dim:>=85 ->")

    def test_invalid_target_name_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid target"):
            parse_rules("dim:>=85 -> has space")

    def test_empty_text_returns_empty_list(self) -> None:
        assert parse_rules("") == []

    def test_comments_only_returns_empty_list(self) -> None:
        assert parse_rules("# just a comment\n# another") == []

    def test_dim_with_hyphen(self) -> None:
        rules = parse_rules("change-surface:==0 -> wire")
        assert rules[0].predicates[0].dim == "change-surface"


# ---------------------------------------------------------------------------
# serialize_rules
# ---------------------------------------------------------------------------


class TestSerializeRules:
    def test_single_rule_roundtrip(self) -> None:
        rules = parse_rules("confidence:>=85 -> implement")
        assert serialize_rules(rules) == "confidence:>=85 -> implement"

    def test_catchall_roundtrip(self) -> None:
        rules = parse_rules("* -> fallback")
        assert serialize_rules(rules) == "* -> fallback"

    def test_conjunctive_rule_roundtrip(self) -> None:
        text = "confidence:>=85 & outcome:>=75 -> implement"
        assert serialize_rules(parse_rules(text)) == text

    def test_multi_rule_table_roundtrip(self) -> None:
        text = "security:<65 -> escalate\ncompleteness:<60 -> deep_repair\n* -> light_repair"
        assert serialize_rules(parse_rules(text)) == text

    def test_parse_serialize_parse_stability(self) -> None:
        """parse → serialize → parse produces structurally identical output."""
        text = (
            "security:<65 -> escalate\n"
            "confidence:>=85 & outcome:>=75 -> implement\n"
            "ambiguity:>=15 & change-surface:==0 -> wire\n"
            "* -> repair"
        )
        rules1 = parse_rules(text)
        text2 = serialize_rules(rules1)
        rules2 = parse_rules(text2)
        assert len(rules1) == len(rules2)
        for r1, r2 in zip(rules1, rules2, strict=True):
            assert r1.is_catchall == r2.is_catchall
            assert r1.target == r2.target
            assert r1.predicates == r2.predicates

    def test_empty_list_serializes_to_empty_string(self) -> None:
        assert serialize_rules([]) == ""

    def test_three_predicate_conjunctive_roundtrip(self) -> None:
        text = "a:>=85 & b:>=85 & c:>=85 -> all_high"
        assert serialize_rules(parse_rules(text)) == text


# ---------------------------------------------------------------------------
# evaluate_rules
# ---------------------------------------------------------------------------


class TestEvaluateRules:
    def test_first_matching_rule_wins(self) -> None:
        rules = parse_rules("confidence:>=90 -> high\nconfidence:>=70 -> medium\n* -> low")
        assert evaluate_rules(rules, {"confidence": 95}) == "high"
        assert evaluate_rules(rules, {"confidence": 80}) == "medium"
        assert evaluate_rules(rules, {"confidence": 50}) == "low"

    def test_catchall_fallback(self) -> None:
        rules = parse_rules("confidence:>=85 -> done\n* -> repair")
        assert evaluate_rules(rules, {"confidence": 70}) == "repair"

    def test_no_match_without_catchall_returns_none(self) -> None:
        rules = parse_rules("confidence:>=85 -> done")
        assert evaluate_rules(rules, {"confidence": 70}) is None

    def test_numeric_coercion_nine_less_than_ten(self) -> None:
        """Numeric comparison: "9" < "10" must evaluate True (float), not False (lexical)."""
        rules = parse_rules("dim:<10 -> match")
        # Integer value
        assert evaluate_rules(rules, {"dim": 9}) == "match"
        # String "9" coerced to float 9.0
        assert evaluate_rules(rules, {"dim": "9"}) == "match"
        # 10 should NOT match < 10
        assert evaluate_rules(rules, {"dim": 10}) is None
        # String "10" also should not match
        assert evaluate_rules(rules, {"dim": "10"}) is None

    def test_numeric_coercion_ge(self) -> None:
        scores = {"x": 85}
        assert evaluate_rules(parse_rules("x:>=85 -> ok"), scores) == "ok"
        assert evaluate_rules(parse_rules("x:>=86 -> ok"), scores) is None

    def test_numeric_coercion_le(self) -> None:
        scores = {"x": 85}
        assert evaluate_rules(parse_rules("x:<=85 -> ok"), scores) == "ok"
        assert evaluate_rules(parse_rules("x:<=84 -> ok"), scores) is None

    def test_numeric_coercion_gt(self) -> None:
        scores = {"x": 85}
        assert evaluate_rules(parse_rules("x:>84 -> ok"), scores) == "ok"
        assert evaluate_rules(parse_rules("x:>85 -> ok"), scores) is None

    def test_numeric_coercion_lt(self) -> None:
        scores = {"x": 85}
        assert evaluate_rules(parse_rules("x:<86 -> ok"), scores) == "ok"
        assert evaluate_rules(parse_rules("x:<85 -> ok"), scores) is None

    def test_equality_numeric(self) -> None:
        assert evaluate_rules(parse_rules("x:==85 -> ok"), {"x": 85}) == "ok"
        assert evaluate_rules(parse_rules("x:==85 -> ok"), {"x": 84}) is None

    def test_inequality_numeric(self) -> None:
        assert evaluate_rules(parse_rules("x:!=85 -> ok"), {"x": 80}) == "ok"
        assert evaluate_rules(parse_rules("x:!=85 -> ok"), {"x": 85}) is None

    def test_equality_string_fallback(self) -> None:
        assert evaluate_rules(parse_rules("flag:==true -> ok"), {"flag": "true"}) == "ok"
        assert evaluate_rules(parse_rules("flag:==false -> ok"), {"flag": "true"}) is None

    def test_inequality_string_fallback(self) -> None:
        assert evaluate_rules(parse_rules("flag:!=false -> ok"), {"flag": "true"}) == "ok"
        assert evaluate_rules(parse_rules("flag:!=true -> ok"), {"flag": "true"}) is None

    def test_conjunctive_all_must_hold(self) -> None:
        rules = parse_rules("confidence:>=85 & outcome:>=75 -> implement\n* -> refine")
        assert evaluate_rules(rules, {"confidence": 90, "outcome": 80}) == "implement"
        assert evaluate_rules(rules, {"confidence": 90, "outcome": 70}) == "refine"
        assert evaluate_rules(rules, {"confidence": 80, "outcome": 80}) == "refine"

    def test_conjunctive_three_predicates(self) -> None:
        rules = parse_rules("a:>=85 & b:>=85 & c:>=85 -> all_high\n* -> low")
        assert evaluate_rules(rules, {"a": 90, "b": 90, "c": 90}) == "all_high"
        assert evaluate_rules(rules, {"a": 90, "b": 90, "c": 80}) == "low"

    def test_missing_dimension_no_match_for_ordered_ops(self) -> None:
        rules = parse_rules("dim:>=50 -> match\n* -> fallback")
        assert evaluate_rules(rules, {}) == "fallback"

    def test_missing_dimension_equals_no_match(self) -> None:
        rules = parse_rules("dim:==true -> match\n* -> fallback")
        assert evaluate_rules(rules, {}) == "fallback"

    def test_missing_dimension_not_equals_matches(self) -> None:
        """absent != anything should match."""
        rules = parse_rules("flag:!=true -> match")
        assert evaluate_rules(rules, {}) == "match"

    def test_empty_rules_returns_none(self) -> None:
        assert evaluate_rules([], {"x": 1}) is None

    def test_catchall_alone_always_matches(self) -> None:
        rules = parse_rules("* -> default_state")
        assert evaluate_rules(rules, {}) == "default_state"
        assert evaluate_rules(rules, {"x": 999}) == "default_state"

    def test_rn_remediate_style_rules(self) -> None:
        """Validate that rn-remediate's diagnose logic maps to conjunctive rules."""
        text = (
            "confidence:>=85 & outcome:>=75 -> IMPLEMENT\n"
            "decision_needed:==true -> DECIDE\n"
            "missing_artifacts:==true -> WIRE\n"
            "ambiguity:>=15 & change-surface:==0 -> WIRE\n"
            "ambiguity:>=15 -> REFINE\n"
            "* -> REFINE\n"
        )
        rules = parse_rules(text)
        # IMPLEMENT: both thresholds met
        assert (
            evaluate_rules(
                rules, {"confidence": 90, "outcome": 80, "ambiguity": 5, "change-surface": 5}
            )
            == "IMPLEMENT"
        )
        # DECIDE: decision_needed flag
        assert (
            evaluate_rules(rules, {"confidence": 70, "outcome": 70, "decision_needed": "true"})
            == "DECIDE"
        )
        # WIRE via MISSING_ARTIFACTS
        assert (
            evaluate_rules(rules, {"confidence": 70, "outcome": 70, "missing_artifacts": "true"})
            == "WIRE"
        )
        # WIRE via ambiguity + no change-surface (change-surface == 0)
        assert (
            evaluate_rules(
                rules, {"confidence": 70, "outcome": 70, "ambiguity": 20, "change-surface": 0}
            )
            == "WIRE"
        )
        # REFINE via high ambiguity alone (change-surface != 0)
        assert (
            evaluate_rules(
                rules, {"confidence": 70, "outcome": 70, "ambiguity": 20, "change-surface": 5}
            )
            == "REFINE"
        )
