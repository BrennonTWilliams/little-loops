"""Meta-test: every in-scope grader in fsm/evaluators.py must carry deterministic
unit tests for each case kind (pass/fail/boundary) its inventory row requires,
tagged with `@pytest.mark.grader_case(grader, kind)`.

This is the CI-tier discipline described in ENH-3463: a grader that decides
pass/fail for a live-model probe must have its own logic verified by fixed
synthetic inputs before it is trusted to grade a real run. See that issue's
Design section for the full rationale and the rejected runtime-gate alternative.

Marker discovery is an AST scan over scripts/tests/*.py, not pytest session
collection — a subset run (`-k`, `--lf`, a single file, mutmut's per-mutant
`-n0` selection) must not make this gate fail spuriously because the tagged
tests weren't collected alongside it.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from little_loops.fsm import evaluators

TESTS_DIR = Path(__file__).parent

# {grader_name: frozenset(required case kinds)} — kinds are "pass", "fail",
# "boundary". "boundary" only applies where a numeric threshold exists.
IN_SCOPE_GRADERS: dict[str, frozenset[str]] = {
    "evaluate_output_numeric": frozenset({"pass", "fail", "boundary"}),
    "evaluate_output_json": frozenset({"pass", "fail", "boundary"}),
    "evaluate_llm_structured": frozenset({"pass", "fail", "boundary"}),
    "evaluate_exit_code": frozenset({"pass", "fail"}),
    "evaluate_output_contains": frozenset({"pass", "fail"}),
    "evaluate_classify": frozenset({"pass", "fail"}),
    "evaluate_mcp_result": frozenset({"pass", "fail"}),
    "evaluate_harbor_scorer": frozenset({"pass", "fail"}),
    "evaluate_blind_comparator": frozenset({"pass", "fail"}),
    "evaluate_contract": frozenset({"pass", "fail"}),
    "evaluate_comparator": frozenset({"pass", "fail"}),
}

# Loop-control/advisory evaluators: verdicts are stall/continue signals, not
# subject grading. Adding a new evaluate_* function without classifying it
# here or in IN_SCOPE_GRADERS fails this meta-test (see test_all_evaluate_functions_classified).
EXEMPT_GRADERS: frozenset[str] = frozenset(
    {
        "evaluate_convergence",
        "evaluate_diff_stall",
        "evaluate_score_stall",
        "evaluate_open_question_stall",
        "evaluate_action_stall",
        "evaluate_advisor_consult",
    }
)


def _mark_decorator_grader_case(node: ast.expr) -> tuple[str, str] | None:
    """If `node` is a `pytest.mark.grader_case("grader", "kind")` call, return
    the (grader, kind) string pair. Otherwise return None."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    # Match pytest.mark.grader_case(...)
    if not (
        isinstance(func, ast.Attribute)
        and func.attr == "grader_case"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "mark"
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "pytest"
    ):
        return None
    if len(node.args) < 2:
        return None
    grader_arg, kind_arg = node.args[0], node.args[1]
    if not (isinstance(grader_arg, ast.Constant) and isinstance(kind_arg, ast.Constant)):
        return None
    return str(grader_arg.value), str(kind_arg.value)


def _scan_source_for_grader_cases(source: str) -> set[tuple[str, str]]:
    """AST-scan a Python source string for grader_case marker decorators on
    any function or class definition. Returns the set of (grader, kind) pairs."""
    tree = ast.parse(source)
    found: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for decorator in node.decorator_list:
            pair = _mark_decorator_grader_case(decorator)
            if pair is not None:
                found.add(pair)
    return found


def _scan_tests_dir_for_grader_cases(tests_dir: Path) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path in sorted(tests_dir.glob("*.py")):
        found |= _scan_source_for_grader_cases(path.read_text())
    return found


def _discover_evaluate_functions() -> set[str]:
    return {
        name
        for name, _obj in inspect.getmembers(evaluators, inspect.isfunction)
        if name.startswith("evaluate_")
    }


class TestGraderCoverage:
    """The real gate: every in-scope grader has all its required case kinds
    tagged somewhere under scripts/tests/."""

    def test_all_in_scope_graders_covered(self) -> None:
        found = _scan_tests_dir_for_grader_cases(TESTS_DIR)
        covered: dict[str, set[str]] = {}
        for grader, kind in found:
            covered.setdefault(grader, set()).add(kind)

        missing: list[str] = []
        for grader, required_kinds in IN_SCOPE_GRADERS.items():
            have = covered.get(grader, set())
            for kind in sorted(required_kinds - have):
                missing.append(f"{grader}: missing '{kind}' case")

        assert not missing, "Grader coverage gaps:\n" + "\n".join(missing)

    def test_all_evaluate_functions_classified(self) -> None:
        all_functions = _discover_evaluate_functions()
        classified = set(IN_SCOPE_GRADERS) | EXEMPT_GRADERS
        unclassified = all_functions - classified
        assert not unclassified, (
            "New evaluate_* function(s) not classified in "
            f"IN_SCOPE_GRADERS or EXEMPT_GRADERS: {sorted(unclassified)}"
        )
        # Also catch drift the other way: a name in our tables that no longer
        # exists in evaluators.py (renamed/removed).
        stale = classified - all_functions
        assert not stale, (
            f"Classified grader name(s) no longer exist in evaluators.py: {sorted(stale)}"
        )


class TestGraderCoverageMetaTestItself:
    """Tests for the meta-test's own detection logic, run against synthetic
    source strings — never by mutating the real test suite."""

    def test_missing_kind_in_synthetic_source_is_detected(self) -> None:
        source = """
import pytest

@pytest.mark.grader_case("evaluate_output_contains", "pass")
def test_something():
    pass
"""
        found = _scan_source_for_grader_cases(source)
        assert found == {("evaluate_output_contains", "pass")}
        # 'fail' is required for evaluate_output_contains but absent here.
        assert ("evaluate_output_contains", "fail") not in found

    def test_unclassified_function_name_is_detected(self) -> None:
        fake_functions = {"evaluate_output_contains", "evaluate_totally_new_grader"}
        classified = set(IN_SCOPE_GRADERS) | EXEMPT_GRADERS
        unclassified = fake_functions - classified
        assert unclassified == {"evaluate_totally_new_grader"}

    def test_multiple_markers_on_one_test_are_all_found(self) -> None:
        source = """
import pytest

@pytest.mark.grader_case("evaluate_exit_code", "pass")
@pytest.mark.grader_case("evaluate_exit_code", "fail")
def test_exit_code_mapping():
    pass
"""
        found = _scan_source_for_grader_cases(source)
        assert found == {
            ("evaluate_exit_code", "pass"),
            ("evaluate_exit_code", "fail"),
        }

    def test_runs_in_isolation_without_session_state(self) -> None:
        """Sanity check that discovery reads files directly, not session.items
        — the module has no pytest_collection_modifyitems hook and no fixture
        depending on collected item state."""
        import sys

        self_module = sys.modules[__name__]
        assert not hasattr(self_module, "pytest_collection_modifyitems")
