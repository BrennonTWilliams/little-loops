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
    action: str, tmp_path: Path, env: dict[str, str], input_ref: str
) -> subprocess.CompletedProcess:
    script = action.replace("${context.run_dir}", str(tmp_path))
    if input_ref:
        script = script.replace(input_ref, "BUG-9800")
    script = script.replace(":shell}", "}")
    script = script.replace("${captured.issue_id.output}", "BUG-9800")
    script = script.replace("${captured.input.output}", "BUG-9800")
    return subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)


CASES = [
    ('{"spike_attempted": "true", "spike_refuted": "true", "spike_completed": "true"}', "REFUTED"),
    ('{"spike_attempted": "true", "spike_completed": "true"}', "PROVEN"),
    ('{"spike_attempted": "true"}', "INCONCLUSIVE"),
    ('{"spike_needed": "true"}', "NO_VERDICT"),
]


@pytest.mark.parametrize(
    "loop,ref",
    [
        ("refine-to-ready-issue.yaml", "${captured.issue_id.output}"),
        ("autodev.yaml", "${captured.input.output}"),
    ],
)
@pytest.mark.parametrize("show_json,expected", CASES)
def test_route_spike_verdict_classification(
    tmp_path: Path, loop: str, ref: str, show_json: str, expected: str
) -> None:
    state = _load(loop)["states"]["route_spike_verdict"]
    result = _run(state["action"], tmp_path, _stub_path(tmp_path, show_json), ref)
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
    assert st["resolve_decision_pre_breakdown"]["on_success"] == "confidence_check"
    assert st["mark_spike_no_verdict_infra"]["next"] == "failed"
    assert "infra" in st["mark_spike_no_verdict_infra"]["action"]
    assert "spike_inconclusive" in st["record_spike_inconclusive"]["action"]
    assert st["record_spike_inconclusive"]["next"] == "failed"


def test_autodev_routing_table() -> None:
    st = _load("autodev.yaml")["states"]
    assert st["count_repair_cycle_spike"]["next"] == "route_spike_verdict"
    route = st["route_spike_verdict"]["route"]
    assert route["REFUTED"] == "check_spike_budget"
    assert route["PROVEN"] == "clear_scores_before_spike"  # BUG-3588 chain unchanged
    assert route["INCONCLUSIVE"] == "record_spike_inconclusive"
    assert route["NO_VERDICT"] == "mark_spike_no_verdict_infra"
    assert st["check_spike_budget"]["on_yes"] == "resolve_decision"
    assert st["check_spike_budget"]["on_no"] == "record_decision_unresolved"
    assert st["check_scores_present_spike"]["on_yes"] == "enqueue_or_skip"
    assert st["record_spike_inconclusive"]["next"] == "dequeue_next"
    assert st["mark_spike_no_verdict_infra"]["next"] == "dequeue_next"
    assert "set-status" not in st["mark_spike_no_verdict_infra"]["action"]  # no deferral
    # Re-armed spike runs before size review.
    assert st["recheck_after_decide"]["on_no"] == "check_rearmed_spike_after_decide"
    assert st["check_rearmed_spike_after_decide"]["on_yes"] == "run_spike"
    assert st["check_rearmed_spike_after_decide"]["on_no"] == "snap_and_size_review"
    assert "autodev-spike-inconclusive.txt" in st["skip_inflight"]["action"]
    assert "autodev-spike-inconclusive.txt" in st["init"]["action"]


@pytest.mark.parametrize(
    "state_name",
    [
        "check_spike_needed",
        "check_spike_needed_before_skip",
        "check_rearmed_spike_after_decide",
    ],
)
def test_autodev_spike_gate_budget(tmp_path: Path, state_name: str) -> None:
    action = _load("autodev.yaml")["states"][state_name]["action"]
    env = _stub_path(tmp_path, '{"spike_needed": "true", "confidence": 70}')
    counter = tmp_path / "spike-runs-BUG-9800"
    assert _run(action, tmp_path, env, "").returncode == 0
    assert counter.read_text() == "1"
    assert _run(action, tmp_path, env, "").returncode == 0
    assert counter.read_text() == "2"
    assert _run(action, tmp_path, env, "").returncode == 1  # budget spent


def test_crashed_spike_still_counts_and_budget_check(tmp_path: Path) -> None:
    for loop, ref in (("autodev.yaml", ""), ("refine-to-ready-issue.yaml", "")):
        action = _load(loop)["states"]["check_spike_budget"]["action"]
        env = _stub_path(tmp_path, "{}")
        counter = tmp_path / "spike-runs-BUG-9800"
        counter.write_text("1")
        assert _run(action, tmp_path, env, ref).returncode == 0  # decide
        counter.write_text("2")
        assert _run(action, tmp_path, env, ref).returncode != 0  # second refutation defers


def test_dispatch_pre_deferral_remedy_spike_budget(tmp_path: Path) -> None:
    action = _load("autodev.yaml")["states"]["dispatch_pre_deferral_remedy"]["action"]
    env = _stub_path(tmp_path, '{"confidence": 60}')
    (tmp_path / "autodev-pre-deferral-remedy.txt").write_text("spike")
    (tmp_path / "spike-runs-BUG-9800").write_text("2")
    assert _run(action, tmp_path, env, "").returncode == 1  # -> reconcile_current
    (tmp_path / "autodev-pre-deferral-remedy.txt").write_text("spike")
    (tmp_path / "spike-runs-BUG-9800").write_text("1")
    assert _run(action, tmp_path, env, "").returncode == 0
    assert (tmp_path / "spike-runs-BUG-9800").read_text() == "2"


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
