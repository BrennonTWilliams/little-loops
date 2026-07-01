"""Conformance corpus tests for FEAT-2301 (self-contained HTML policy builder).

The corpus at ``fixtures/policy_builder/conformance_corpus.json`` is the
cross-language contract: a JS validator embedded in the HTML builder must
reproduce the same ``evaluate_rules`` / ``_detect_shadows`` verdicts as the
canonical Python implementation. These tests pin the corpus against the
canonical functions so the contract cannot silently drift.
"""

import json
import re
from pathlib import Path

CORPUS = Path(__file__).parent / "fixtures" / "policy_builder" / "conformance_corpus.json"


def _load() -> dict:
    return json.loads(CORPUS.read_text())


def test_evaluate_cases_match_canonical() -> None:
    from little_loops.fsm.policy_rules import evaluate_rules, parse_rules

    data = _load()
    for case in data["evaluate_cases"]:
        rules = parse_rules(case["rules"])
        got = evaluate_rules(rules, case["scores"])
        assert got == case["expected_target"], f"{case['name']}: got {got!r}"


def test_shadow_cases_match_canonical() -> None:
    from little_loops.fsm.policy_rules import parse_rules
    from little_loops.fsm.route_table import _detect_shadows

    data = _load()
    for case in data["shadow_cases"]:
        rules = parse_rules(case["rules"])
        warnings = _detect_shadows(rules)
        # extract the 1-based rule number each warning refers to ("Rule N ...")
        got_numbers = sorted(int(re.match(r"Rule (\d+)", w).group(1)) for w in warnings)
        assert got_numbers == sorted(case["expected_shadowed_rule_numbers"]), (
            f"{case['name']}: got {got_numbers}, warnings={warnings}"
        )


def test_corpus_is_non_trivial() -> None:
    data = _load()
    evaluate_cases = data["evaluate_cases"]
    shadow_cases = data["shadow_cases"]

    assert len(evaluate_cases) >= 12
    assert len(shadow_cases) >= 6

    # At least one evaluate case must exercise the no-match -> null path.
    assert any(c["expected_target"] is None for c in evaluate_cases)

    # At least one shadow case must be a clean table with no shadows.
    assert any(not c["expected_shadowed_rule_numbers"] for c in shadow_cases)
