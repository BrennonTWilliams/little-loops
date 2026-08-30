"""AC tests for the FEAT-3335 rolling-baseline spike.

Each test retires one risk factor from the issue's Decision Rationale
(the rolling-baseline pattern has no in-repo precedent). See
.ll/spikes/spike-FEAT-3335.md for the mapping.
"""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

from scripts.tests.spike.rolling_scope_gate.rolling_gate import (
    changed_set,
    run_gate,
    write_baseline,
)


def _init_repo(root: Path) -> str:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "spike@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "spike"], cwd=root, check=True)
    (root / "README.md").write_text("seed\n")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=root, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()


class TestRollingBaselineGate:
    def test_gate_passes_and_advances_baseline(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        ref = _init_repo(root)
        run_dir = root / "run"
        run_dir.mkdir()
        baseline_path = tmp_path / "baseline.json"
        write_baseline(str(baseline_path), changed_set(str(root), ref))

        (run_dir / "output.txt").write_text("in scope\n")

        result = run_gate(str(root), ref, str(run_dir), str(baseline_path))

        assert result.passed
        assert result.violations == []
        on_disk = json.loads(baseline_path.read_text())
        assert on_disk == result.snapshot
        assert any(p.startswith("run/") for p in on_disk)

    def test_gate_fails_and_leaves_baseline_untouched(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        ref = _init_repo(root)
        run_dir = root / "run"
        run_dir.mkdir()
        baseline_path = tmp_path / "baseline.json"
        baseline_snapshot = changed_set(str(root), ref)
        write_baseline(str(baseline_path), baseline_snapshot)
        before = baseline_path.read_text()

        (root / "stray.txt").write_text("out of scope\n")

        result = run_gate(str(root), ref, str(run_dir), str(baseline_path))

        assert not result.passed
        assert result.violations == ["stray.txt"]
        assert baseline_path.read_text() == before

    def test_sequential_windows_attribute_violation_to_correct_gate(self, tmp_path):
        """The core Option B claim: a 3-gate chain (init -> gate1 -> gate2)
        attributes a violation to the window it actually occurred in, not to
        an earlier or later window."""
        root = tmp_path / "repo"
        root.mkdir()
        ref = _init_repo(root)
        run_dir = root / "run"
        run_dir.mkdir()
        baseline_path = tmp_path / "baseline.json"
        write_baseline(str(baseline_path), changed_set(str(root), ref))

        # Window 1 (init -> gate1): a legitimate in-scope write only.
        (run_dir / "sketch.yaml").write_text("state graph\n")
        gate1 = run_gate(str(root), ref, str(run_dir), str(baseline_path))
        assert gate1.passed, "window 1 has no violation and must pass"

        # Window 2 (gate1 -> gate2): an out-of-scope write.
        (root / "leaked.md").write_text("should not exist here\n")
        gate2 = run_gate(str(root), ref, str(run_dir), str(baseline_path))

        assert not gate2.passed
        # Attribution must name exactly the window-2 offender, not the
        # window-1 file (which gate1 already rolled into the baseline).
        assert gate2.violations == ["leaked.md"]
        assert "sketch.yaml" not in " ".join(gate2.violations)

    def test_advance_does_not_mask_a_violation_in_the_same_pass(self, tmp_path):
        """A gate that both advances the baseline and reports a violation in
        the same call would let a later window silently absorb an
        unresolved violation. Baseline must only ever advance on a clean
        pass."""
        root = tmp_path / "repo"
        root.mkdir()
        ref = _init_repo(root)
        run_dir = root / "run"
        run_dir.mkdir()
        baseline_path = tmp_path / "baseline.json"
        write_baseline(str(baseline_path), changed_set(str(root), ref))
        before = baseline_path.read_text()

        (run_dir / "ok.txt").write_text("fine\n")
        (root / "bad.txt").write_text("not fine\n")

        result = run_gate(str(root), ref, str(run_dir), str(baseline_path), advance=True)

        assert not result.passed
        assert "bad.txt" in result.violations
        assert baseline_path.read_text() == before, (
            "baseline advanced despite a violation -- would mask 'ok.txt' "
            "into the next window's accepted state without the violation "
            "ever having been cleared"
        )


class TestIsolationGuard:
    def test_rolling_gate_module_has_no_production_imports(self):
        """Regression guard: the spike must stay a standalone reimplementation,
        not a wrapper around little_loops production code -- otherwise it
        would prove nothing about the mechanism's viability in isolation."""
        module_path = Path(__file__).parent / "rolling_gate.py"
        tree = ast.parse(module_path.read_text())
        forbidden_prefixes = ("little_loops", "scripts.little_loops")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(forbidden_prefixes), (
                        f"forbidden import of {alias.name!r} in rolling_gate.py"
                    )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert not module.startswith(forbidden_prefixes), (
                    f"forbidden import from {module!r} in rolling_gate.py"
                )
