"""Structural and end-to-end tests for autodev.yaml's outer-loop states.

ENH-3623 moved the second-pass preparation ladder (guard-2 classification,
reconcile/plateau/contradiction gates, recheck/regate design gates, pre-deferral
remedies, repair-cycle counters) out of autodev into ``prepare-issue.yaml``,
whose decisions live in ``little_loops.preparation_policy.decide`` (table-tested
in ``test_preparation_policy.py``). What remains here pins the autodev states
that survived: the ``dequeue_next`` snapshots the policy reads, the
``refine_current`` -> ``copy_broke_down`` hand-off, the ``check_passed``
design-aware first gate, the dequeue-time gate check, and the transitive
base-SHA stamp.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import yaml

AUTODEV_LOOP_PATH = Path(__file__).parent.parent / "little_loops" / "loops" / "autodev.yaml"


def _load_autodev_yaml() -> dict[str, Any]:
    assert AUTODEV_LOOP_PATH.exists(), f"Loop file not found: {AUTODEV_LOOP_PATH}"
    return yaml.safe_load(AUTODEV_LOOP_PATH.read_text())


class TestDequeueNextPreReadinessSnapshot:
    """FEAT-2751: dequeue_next must snapshot pre-refine confidence per-issue and
    reset the repair-cycle counter. ENH-3611: the separate pre-spike snapshot is gone."""

    def test_action_writes_pre_readiness_snapshot(self) -> None:
        action = _load_autodev_yaml()["states"]["dequeue_next"]["action"]
        assert "autodev-pre-readiness.txt" in action

    def test_action_resets_repair_cycle_counter(self) -> None:
        action = _load_autodev_yaml()["states"]["dequeue_next"]["action"]
        assert "autodev-repair-cycle-count.txt" in action

    def test_action_no_longer_touches_spike_snapshot_or_decide_marker(self) -> None:
        """ENH-3611 stays-deleted: autodev-pre-spike-readiness.txt and the
        autodev-decide-ran clear left dequeue_next with the spike/decide states."""
        action = _load_autodev_yaml()["states"]["dequeue_next"]["action"]
        assert "autodev-pre-spike-readiness.txt" not in action
        assert "autodev-decide-ran" not in action


class TestRepairCycleCounterMovedToPolicy:
    """ENH-3623: the repair-cycle counter is derived from the preparation fact
    log (``Facts.repair_cycles``); autodev keeps no ``count_repair_cycle_*``
    states and ``refine_current`` hands straight to ``copy_broke_down``."""

    def test_no_count_repair_cycle_states_remain(self) -> None:
        """Supersedes ENH-3611's spike-only stays-deleted pin: every counter
        state (spike, refine, wire, size_review, reconcile, refine_for_design)
        is gone."""
        states = _load_autodev_yaml()["states"]
        leftover = sorted(n for n in states if n.startswith("count_repair_cycle_"))
        assert leftover == []

    def test_refine_current_routes_on_success_to_copy_broke_down(self) -> None:
        states = _load_autodev_yaml()["states"]
        assert states["refine_current"].get("on_success") == "copy_broke_down"
        assert states["copy_broke_down"].get("next") == "route_refine_success"


class TestCheckPassedDesignGate:
    """ENH-2870/ENH-2967/ENH-3625: the surviving autodev gate hard-ANDs the
    Program Design verdict via the single ``ll-issues check-design`` owner."""

    def test_check_passed_composes_check_design_after_check_readiness(self) -> None:
        """ENH-3625: the first gate hard-ANDs check-design like the later gates."""
        action = _load_autodev_yaml()["states"]["check_passed"]["action"]
        assert "ll-issues check-readiness" in action
        assert "&& ll-issues check-design" in action
        assert action.index("check-readiness") < action.index("check-design")
        assert action.index("check-design") < action.index("autodev-staged.txt")


class TestCheckGateAtDequeueMarkerLiterals:
    """ENH-3148: check_gate_at_dequeue reuses GATE_MARKER's phrase list
    verbatim (BUG-3147's inline-matcher precedent), not a shared helper."""

    def test_marker_literals_present_in_action(self) -> None:
        action = _load_autodev_yaml()["states"]["check_gate_at_dequeue"]["action"]
        # ENH-3575: the phrase regex lives once, in the shared helper.
        assert "ll-issues check-gate" in action
        assert "grep -qiE" not in action
        from little_loops.cli.issues.check_gate import _PROSE_GATE_RE

        for literal in (
            "do not start otherwise",
            "measurement \\(gate\\)",
            "pre-implementation measurement",
            "⚠ Gated",
            "do not implement before",
            "evidence gate",
            "gate opens",
            "is explicitly gated",
        ):
            assert literal in _PROSE_GATE_RE.pattern


class TestAutodevHasNoOwnBaseShaStamp:
    """ENH-2866 decision 3: autodev is stamped transitively, not per-state.

    ``dequeue_next`` fires once per issue but ``loop_runs`` is one row per run
    with no issue dimension, so a run-dir SHA file could only ever hold the last
    issue's value — and ``implement_current``'s ``ll-auto --only`` shell-out
    already produces a per-issue ``orchestration_runs`` row at a strictly better
    moment (after refine/wire churn is committed, immediately pre-patch).
    """

    def test_no_dequeue_sha_run_dir_artifact(self) -> None:
        """The removed design's specific artifact must not appear anywhere."""
        raw = AUTODEV_LOOP_PATH.read_text()
        assert "autodev-dequeue-sha" not in raw, (
            "autodev must not capture its own base SHA — the ll-auto --only "
            "shell-out in implement_current stamps each issue transitively"
        )

    def test_implement_current_still_shells_out_to_ll_auto(self) -> None:
        """The transitive stamp depends on this shell-out; guard it explicitly."""
        action = _load_autodev_yaml()["states"]["implement_current"].get("action", "")
        assert "ll-auto" in action
        assert "--only" in action


def _bug_body(*, program_design: str | None, confidence: int, outcome: int) -> str:
    """A structurally complete BUG issue body with configurable scores and an
    optional Program Design section (ENH-2967 loop-level fixture)."""
    sections = [
        "---",
        "id: BUG-9700",
        "status: open",
        "discovered_date: 2026-07-20",
        f"confidence_score: {confidence}",
        f"outcome_confidence: {outcome}",
        "---",
        "",
        "# BUG-9700: Something broke",
        "",
        "## Summary",
        "The widget explodes when the input is empty.",
        "",
        "## Steps to Reproduce",
        "1. Open the widget\n2. Submit an empty form",
        "",
        "## Current Behavior",
        "It explodes.",
        "",
        "## Expected Behavior",
        "It should not break.",
        "",
        "## Actual Behavior",
        "It breaks loudly.",
        "",
        "## Impact",
        "- **Priority**: P3 - Minor annoyance for a rare input.",
        "",
        "## Status",
        "**Open** | Created: 2026-07-20 | Priority: P3",
    ]
    if program_design is not None:
        sections.insert(-3, "## Program Design")
        sections.insert(-3, program_design.strip())
        sections.insert(-3, "")
    return "\n".join(sections) + "\n"


def _run_check_passed(project_root: Path, issue_id: str) -> None:
    """Run the real `check_passed` shell action end-to-end (real `ll-issues`
    subprocess calls), the way the FSM would substitute
    ${captured.input.output}/${context.run_dir}/thresholds."""
    action = _load_autodev_yaml()["states"]["check_passed"]["action"]
    script = (
        action.replace('ID="${captured.input.output}"', f'ID="{issue_id}"')
        .replace("${context.run_dir}", str(project_root))
        .replace("${context.readiness_threshold:shell}", "85")
        .replace("${context.outcome_threshold:shell}", "65")
    )
    subprocess.run(["bash", "-c", script], cwd=str(project_root), check=False)


class TestCheckPassedDesignGateEndToEnd:
    """ENH-2967/ENH-3625: a design-less issue is not staged even with passing
    scores. Retargeted from the deleted ``recheck_scores`` state (ENH-3623) to
    ``check_passed``, the only autodev gate left that writes
    ``autodev-staged.txt``."""

    def _make_project(self, tmp_path: Path, *, program_design: str | None) -> Path:
        issues_dir = tmp_path / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        issue_file = issues_dir / "P3-BUG-9700-test-bug.md"
        issue_file.write_text(
            _bug_body(program_design=program_design, confidence=95, outcome=90),
            encoding="utf-8",
        )
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        (ll_dir / "program-design-cutover.json").write_text(
            json.dumps({"sha": "0" * 40, "date": "2026-07-01"}), encoding="utf-8"
        )
        return issue_file

    def test_design_less_issue_is_not_staged(self, tmp_path: Path) -> None:
        """High readiness/outcome scores alone must not stage an issue missing
        `## Program Design` once the gate is armed."""
        self._make_project(tmp_path, program_design=None)

        _run_check_passed(tmp_path, "BUG-9700")

        staged = tmp_path / "autodev-staged.txt"
        assert not staged.exists() or "BUG-9700" not in staged.read_text()

    def test_issue_with_program_design_is_staged(self, tmp_path: Path) -> None:
        """The same high scores WITH a present, non-boilerplate Program Design
        section must stage normally — the gate change must not over-block."""
        valid_section = (
            "### Types\n\n- `sha: str`\n\n"
            "### Signatures\n\n- `design_gate_failed(gaps: FormatGaps) -> bool`\n\n"
            "### Call Path\n\n`design_gate_failed` -> `check_format_gaps`\n"
        )
        self._make_project(tmp_path, program_design=valid_section)
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
        (tmp_path / "mod.py").write_text(
            "def design_gate_failed(gaps):\n    return False\n", encoding="utf-8"
        )
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=tmp_path, check=True)

        _run_check_passed(tmp_path, "BUG-9700")

        staged = tmp_path / "autodev-staged.txt"
        assert staged.exists() and "BUG-9700" in staged.read_text()
