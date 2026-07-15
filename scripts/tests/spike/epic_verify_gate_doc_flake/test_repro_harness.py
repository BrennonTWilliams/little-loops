"""AC tests for the BUG-2650 spike (Option A harness-shape proof)."""

from __future__ import annotations

import ast
from pathlib import Path

from tests.spike.epic_verify_gate_doc_flake.repro_harness import (
    MAX_ITERATIONS,
    MAX_WORKERS,
    build_repo_with_needle,
    run_gate_n_times,
)


class TestHarnessReproducesGateCheckoutPath:
    """Risk (b): unproven that a fixed-repeat loop through the real gate can
    observe checkout state at all."""

    def test_harness_reproduces_gate_checkout_path(self, tmp_path: Path) -> None:
        repo = build_repo_with_needle(tmp_path, needle="spike")

        results = run_gate_n_times(repo, iterations=3)

        assert len(results) == 3
        for ok, message, returncode in results:
            assert ok is True, f"gate unexpectedly failed: {message} (exit {returncode})"


class TestBoundedLoopStaysWithinCaps:
    """Regression guard: the harness itself must not trip the suite's
    documented CPU-starvation/beachball constraint."""

    def test_bounded_loop_stays_within_worker_and_iteration_caps(self, tmp_path: Path) -> None:
        repo = build_repo_with_needle(tmp_path)

        try:
            run_gate_n_times(repo, iterations=MAX_ITERATIONS + 1)
        except ValueError as e:
            assert "exceeds spike cap" in str(e)
        else:
            raise AssertionError("expected ValueError for iterations over the spike cap")

        try:
            run_gate_n_times(repo, iterations=1, max_workers=MAX_WORKERS + 1)
        except ValueError as e:
            assert "exceeds spike cap" in str(e)
        else:
            raise AssertionError("expected ValueError for max_workers over the spike cap")

    def test_spike_does_not_import_production_worktree_module_source(self) -> None:
        """AST sniff: the spike may call verify_epic_branch_before_merge() (a
        read-only dependency) but must not import internals meant to stay
        production-only (e.g. cleanup_worktree, setup_worktree) that would let
        it reach into worktree lifecycle management beyond the gate's public
        surface."""
        harness_path = Path(__file__).parent / "repro_harness.py"
        tree = ast.parse(harness_path.read_text())
        imported_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "little_loops.worktree_utils":
                imported_names.update(alias.name for alias in node.names)

        forbidden = {"setup_worktree", "cleanup_worktree", "merge_epic_branch_to_base"}
        assert not (imported_names & forbidden), (
            f"spike imports production worktree-lifecycle internals: {imported_names & forbidden}"
        )


class TestNeedlePresentEveryIteration:
    """Baseline: with the needle genuinely present on the branch, the gate
    returns ok=True on every iteration in this bounded run — the "cannot
    recur" evidence path if the harness stays dry."""

    def test_needle_present_on_every_iteration_absent_the_flake(self, tmp_path: Path) -> None:
        repo = build_repo_with_needle(tmp_path, needle="spike")

        results = run_gate_n_times(repo, iterations=5)

        failures = [r for r in results if not r[0]]
        assert not failures, f"gate false-negatived on a present needle: {failures}"
