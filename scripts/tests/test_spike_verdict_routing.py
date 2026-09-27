"""BUG-3593: refuted/inconclusive/no-verdict spike routing, shared budget, re-arm."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

LOOPS = Path(__file__).parent.parent / "little_loops" / "loops"


def _load(name: str) -> dict[str, Any]:
    return yaml.safe_load((LOOPS / name).read_text())


def _stub_path(tmp_path: Path, show_json: str) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "ll-issues"
    fake.write_text(f"#!/bin/sh\necho '{show_json}'\n")
    fake.chmod(0o755)
    return {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}


def _run(
    action: str, tmp_path: Path, env: dict[str, str], input_ref: str, cwd: Path | None = None
) -> subprocess.CompletedProcess:
    script = action.replace("${context.run_dir}", str(tmp_path))
    if input_ref:
        script = script.replace(input_ref, "BUG-9800")
    script = script.replace(":shell}", "}")
    script = script.replace("${captured.issue_id.output}", "BUG-9800")
    script = script.replace("${captured.input.output}", "BUG-9800")
    return subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, cwd=cwd)


CASES = [
    ('{"spike_attempted": "true", "spike_refuted": "true", "spike_completed": "true"}', "REFUTED"),
    ('{"spike_attempted": "true", "spike_completed": "true"}', "PROVEN"),
    ('{"spike_attempted": "true"}', "INCONCLUSIVE"),
    ('{"spike_needed": "true"}', "NO_VERDICT"),
]


@pytest.mark.parametrize("show_json,expected", CASES)
def test_route_spike_verdict_classification(tmp_path: Path, show_json: str, expected: str) -> None:
    # ENH-3611: autodev's copy was removed; the child's route_spike_verdict is the
    # only verdict router.
    state = _load("refine-to-ready-issue.yaml")["states"]["route_spike_verdict"]
    result = _run(
        state["action"],
        tmp_path,
        _stub_path(tmp_path, show_json),
        "${captured.issue_id.output}",
    )
    assert result.stdout.strip() == expected, result.stderr


def test_refine_to_ready_routing_table() -> None:
    st = _load("refine-to-ready-issue.yaml")["states"]
    assert st["route_spike_verdict"]["route"] == {
        "REFUTED": "check_spike_budget",
        "PROVEN": "confidence_check",
        "INCONCLUSIVE": "record_spike_inconclusive",
        "NO_VERDICT": "mark_spike_no_verdict_infra",
        "_": "mark_spike_no_verdict_infra",
        "_error": "mark_spike_no_verdict_infra",
    }
    # Refuted edge bypasses check_decide_attempts and runs before any rescoring.
    assert st["check_spike_budget"]["on_yes"] == "resolve_decision_pre_breakdown"
    assert st["check_spike_budget"]["on_no"] == "record_decision_unresolved"
    assert (
        st["resolve_decision_pre_breakdown"]["on_success"] == "check_proposal_revision"
    )  # BUG-3574
    assert st["check_proposal_revision"]["on_no"] == "confidence_check"
    assert st["mark_spike_no_verdict_infra"]["next"] == "failed"
    assert "infra" in st["mark_spike_no_verdict_infra"]["action"]
    assert "spike_inconclusive" in st["record_spike_inconclusive"]["action"]
    assert st["record_spike_inconclusive"]["next"] == "failed"


#: ENH-3611: the 22 autodev spike/decision states removed in commit 2 (stays-deleted).
REMOVED_AUTODEV_STATES = (
    "check_spike_needed",
    "run_spike",
    "count_repair_cycle_spike",
    "route_spike_verdict",
    "check_spike_budget",
    "record_spike_inconclusive",
    "mark_spike_no_verdict_infra",
    "rerun_confidence_after_spike",
    "clear_scores_before_spike",
    "check_scores_present_spike",
    "check_spike_needed_before_skip",
    "resolve_decision",
    "mark_decide_ran",
    "rerun_confidence_after_decide",
    "clear_scores_before_decide",
    "check_scores_present_decide",
    "recheck_after_decide",
    "check_rearmed_spike_after_decide",
    "check_decide_rate_limited",
    "record_decision_unresolved",
    "snap_and_size_review",
    "check_proof_gate_before_implement",
)


def test_autodev_spike_and_decision_states_stay_deleted() -> None:
    """ENH-3611: the child owns spike/decision routing; autodev has none of it."""
    st = _load("autodev.yaml")["states"]
    assert len(REMOVED_AUTODEV_STATES) == 22
    assert [n for n in REMOVED_AUTODEV_STATES if n in st] == []
    # No surviving state routes to a removed state.
    removed = set(REMOVED_AUTODEV_STATES)
    for name, state in st.items():
        for key in ("next", "on_yes", "on_no", "on_error", "on_success", "on_failure"):
            assert state.get(key) not in removed, (name, key)
        assert not (set((state.get("route") or {}).values()) & removed), name


def test_autodev_ledger_discipline_after_spike_removal() -> None:
    st = _load("autodev.yaml")["states"]
    # skip_inflight still suppresses the child's spike_inconclusive stop.
    assert "autodev-spike-inconclusive.txt" in st["skip_inflight"]["action"]
    assert "autodev-spike-inconclusive.txt" in st["init"]["action"]
    # ENH-3611: nothing in autodev writes or reads the no-verdict / pre-spike markers.
    for name, state in st.items():
        action = state.get("action") or ""
        assert "autodev-spike-no-verdict.txt" not in action, name
        assert "autodev-pre-spike-readiness.txt" not in action, name
    # BUG-3603: the pre-implement proof-gate infra deferral gets the same
    # per-reason ledger discipline — written by mark_proof_gate_infra, truncated
    # by init so a stale prior-run ledger cannot inflate the count.
    assert "autodev-proof-gate-infra.txt" in st["mark_proof_gate_infra"]["action"]
    assert "autodev-proof-gate-infra.txt" in st["init"]["action"]


def test_autodev_never_writes_spike_runs_counter() -> None:
    """ENH-3611: autodev only READS spike-runs-<ID> (the child spends the budget)."""
    for name, state in _load("autodev.yaml")["states"].items():
        for line in (state.get("action") or "").splitlines():
            if "spike-runs-" in line:
                assert ">" not in line.replace("2>/dev/null", "").replace(">/dev/null", ""), (
                    name,
                    line,
                )


def test_child_crashed_spike_still_counts_and_budget_check(tmp_path: Path) -> None:
    action = _load("refine-to-ready-issue.yaml")["states"]["check_spike_budget"]["action"]
    env = _stub_path(tmp_path, "{}")
    counter = tmp_path / "spike-runs-BUG-9800"
    counter.write_text("1")
    assert _run(action, tmp_path, env, "").returncode == 0  # decide
    counter.write_text("2")
    assert _run(action, tmp_path, env, "").returncode != 0  # second refutation defers


def test_resolve_issue_does_not_reset_spike_counter() -> None:
    action = _load("refine-to-ready-issue.yaml")["states"]["resolve_issue"]["action"]
    assert "spike" not in action


def test_oracle_rearm_on_cleared_edge_only() -> None:
    st = _load("oracles/resolve-decision.yaml")["states"]
    assert st["assert_decision_cleared"]["on_no"] == "rearm_refuted_spike"
    assert st["assert_decision_cleared"]["on_yes"] == "check_residual_decision"
    assert st["rearm_refuted_spike"]["next"] == "done"
    assert "on_error" not in st["rearm_refuted_spike"]
    assert st["rearm_refuted_spike"]["action"].endswith("|| true")
    assert st["check_residual_decision"].get("on_yes") != "rearm_refuted_spike"
    assert st["check_residual_decision"].get("on_no") != "rearm_refuted_spike"


def _issue(tmp_path: Path, extra: str) -> Any:
    from little_loops.config import BRConfig

    d = tmp_path / ".issues" / "bugs"
    d.mkdir(parents=True)
    (d / "P2-BUG-9801-x.md").write_text(
        f"---\nid: BUG-9801\ntype: BUG\nstatus: open\n{extra}---\n\n# BUG-9801: x\n"
    )
    (tmp_path / ".ll").mkdir()
    return BRConfig(tmp_path), d / "P2-BUG-9801-x.md"


def test_rearm_spike_removes_keys_when_refuted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from little_loops.cli.issues.rearm_spike import cmd_rearm_spike

    cfg, path = _issue(
        tmp_path,
        "spike_attempted: 'true'\nspike_refuted: 'true'\nspike_needed: 'true'\n"
        "unproven_mechanism: 'true'\n",
    )
    assert cmd_rearm_spike(cfg, argparse.Namespace(issue_id="BUG-9801")) == 0
    text = path.read_text()
    assert "spike_attempted" not in text and "spike_refuted" not in text
    assert "spike_needed" in text and "unproven_mechanism" in text
    assert "[SPIKE_REARMED] BUG-9801" in capsys.readouterr().out


def test_rearm_spike_noop_when_not_refuted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from little_loops.cli.issues.rearm_spike import cmd_rearm_spike

    cfg, path = _issue(tmp_path, "spike_attempted: 'true'\nspike_completed: 'true'\n")
    before = path.read_text()
    assert cmd_rearm_spike(cfg, argparse.Namespace(issue_id="BUG-9801")) == 0
    assert path.read_text() == before
    assert capsys.readouterr().out == ""


def test_rearm_spike_unknown_id(tmp_path: Path) -> None:
    from little_loops.cli.issues.rearm_spike import cmd_rearm_spike

    cfg, _ = _issue(tmp_path, "")
    assert cmd_rearm_spike(cfg, argparse.Namespace(issue_id="BUG-1")) == 2


def test_defer_reason_and_triage_rank() -> None:
    from little_loops.cli.issues.deferred_triage import _REASON_RANK
    from little_loops.issue_lifecycle import DeferReason

    assert DeferReason.SPIKE_INCONCLUSIVE.value == "spike_inconclusive"
    assert "spike_inconclusive" in _REASON_RANK


def test_autodev_ledgers_proposal_unsound_stop_not_as_refine_failed() -> None:
    """BUG-3574: a nested proposal_unsound stop is not also ledgered as refine_failed."""
    st = _load("autodev.yaml")["states"]
    skip = st["skip_inflight"]["action"]
    assert 'grep -qxF "$ID" ${context.run_dir}/autodev-proposal-unsound.txt' in skip
    assert skip.index("autodev-proposal-unsound.txt") < skip.index('refine_failed" >>')
    assert "autodev-proposal-unsound.txt" in st["init"]["action"]
