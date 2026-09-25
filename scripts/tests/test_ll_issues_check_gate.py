"""Tests for ll-issues check-gate and the autodev states that consume it (ENH-3575)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from little_loops.cli.issues.check_gate import (
    detect_prose_gate,
    parse_gate,
    resolve_gate_verdict,
)
from little_loops.frontmatter import parse_frontmatter

LOOP = Path(__file__).parent.parent / "little_loops" / "loops" / "autodev.yaml"
ID = "FEAT-9000"


def _cli() -> list[str]:
    if shutil.which("ll-issues") is not None:
        return ["ll-issues"]
    return [sys.executable, "-m", "little_loops.cli"]


@pytest.fixture
def project(tmp_path: Path) -> Path:
    for kind in ("bugs", "features", "enhancements", "epics"):
        (tmp_path / ".issues" / kind).mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write(project: Path, frontmatter: str = "", body: str = "## Summary\n\nPlain.\n") -> Path:
    path = project / ".issues" / "features" / f"P3-{ID}-test-9000.md"
    path.write_text(
        f"---\nid: {ID}\ntitle: T\ntype: feature\nstatus: open\npriority: P3\n"
        f"{frontmatter}---\n\n# {ID}: T\n\n{body}"
    )
    return path


def _run(project: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [*_cli(), *args], cwd=str(project), capture_output=True, text=True, timeout=30
    )


GATE_PROSE = "The evidence gate must open first.\n"


class TestParseGate:
    def test_absent_is_none_and_empty_list_is_distinct(self) -> None:
        assert parse_gate({}) is None
        assert parse_gate(parse_frontmatter("---\ngate: []\n---\n")) == []

    def test_lone_mapping_normalizes_and_lowercases_kind(self) -> None:
        fm = parse_frontmatter(
            "---\ngate:\n  kind: External\n  satisfied: false\n  evidence: null\n---\n"
        )
        (spec,) = parse_gate(fm) or []
        assert spec.kind == "external"
        assert spec.satisfied is False
        assert spec.evidence is None

    def test_list_of_mappings(self) -> None:
        fm = parse_frontmatter(
            "---\ngate:\n- kind: manual\n  satisfied: true\n- kind: proof\n  satisfied: 'false'\n---\n"
        )
        specs = parse_gate(fm) or []
        assert [(g.kind, g.satisfied) for g in specs] == [("manual", True), ("proof", False)]

    def test_malformed_fails_toward_parking(self) -> None:
        (spec,) = parse_gate({"gate": {"kind": "bogus", "satisfied": "true"}}) or []
        assert (spec.kind, spec.satisfied) == ("manual", False)


class TestResolveGateVerdict:
    def test_absent_uses_prose_fallback(self) -> None:
        assert resolve_gate_verdict({}, GATE_PROSE, False)[0] == "prose"
        assert resolve_gate_verdict({}, "nothing", False)[0] == "none"

    def test_present_field_ignores_prose(self) -> None:
        sat = {"gate": {"kind": "external", "satisfied": "true"}}
        assert resolve_gate_verdict(sat, GATE_PROSE, False)[0] == "structured_satisfied"
        assert resolve_gate_verdict({"gate": []}, GATE_PROSE, False)[0] == "structured_satisfied"

    def test_mixed_list_most_restrictive_wins(self) -> None:
        fm = {
            "gate": [
                {"kind": "proof", "satisfied": "false"},
                {"kind": "external", "satisfied": "false"},
            ]
        }
        assert resolve_gate_verdict(fm, "", True)[0] == "structured_open"

    def test_proven_spike_satisfies_proof_gate(self) -> None:
        fm: dict[str, Any] = {"gate": {"kind": "proof", "satisfied": "false"}}
        assert resolve_gate_verdict(fm, "", False)[0] == "structured_proof"
        assert resolve_gate_verdict(fm, "", True)[0] == "structured_satisfied"

    def test_all_eight_prose_phrases_detected(self) -> None:
        for phrase in (
            "do not start otherwise",
            "Measurement (gate)",
            "pre-implementation measurement",
            "⚠ Gated",
            "do not implement before",
            "Evidence gate",
            "gate opens",
            "is explicitly gated",
        ):
            assert detect_prose_gate(f"x {phrase} y"), phrase
        assert not detect_prose_gate("nothing to see")


class TestCli:
    @pytest.mark.parametrize(
        ("fm", "body", "token", "code"),
        [
            ("", GATE_PROSE, "prose", 0),
            ("", "plain\n", "none", 1),
            ("gate:\n  kind: manual\n  satisfied: false\n", "", "structured_open", 0),
            ("gate:\n  kind: proof\n  satisfied: false\n", "", "structured_proof", 0),
            (
                "gate:\n  kind: proof\n  satisfied: false\nspike_attempted: true\n"
                "spike_completed: true\n",
                "",
                "structured_satisfied",
                1,
            ),
            ("gate: []\n", GATE_PROSE, "structured_satisfied", 1),
        ],
    )
    def test_verdict_and_exit_code(
        self, project: Path, fm: str, body: str, token: str, code: int
    ) -> None:
        _write(project, fm, body)
        result = _run(project, "check-gate", ID)
        assert result.stdout.strip() == token, result.stderr
        assert result.returncode == code

    def test_json_output(self, project: Path) -> None:
        _write(project, "gate:\n  kind: manual\n  satisfied: false\n  owner: ops\n")
        result = _run(project, "check-gate", ID, "--json")
        assert '"verdict": "structured_open"' in result.stdout
        assert '"owner": "ops"' in result.stdout

    def test_unresolvable_exits_two(self, project: Path) -> None:
        assert _run(project, "check-gate", "FEAT-1234").returncode == 2

    def test_subcommand_in_help(self, project: Path) -> None:
        assert "check-gate" in _run(project, "--help").stdout


def _state_action(state: str) -> str:
    return yaml.safe_load(LOOP.read_text())["states"][state]["action"]


def _run_state(project: Path, state: str) -> str:
    """Run a real autodev state action against the real ll-issues; return stdout."""
    run_dir = project / "run"
    run_dir.mkdir(exist_ok=True)
    script = (
        _state_action(state)
        .replace("${captured.input.output:shell}", ID)
        .replace("${captured.input.output}", ID)
        .replace("${context.run_dir}", str(run_dir))
    )
    env = {**os.environ}
    ll = shutil.which("ll-issues")
    if ll:
        env["PATH"] = f"{Path(ll).parent}:{env['PATH']}"
    return subprocess.run(
        ["bash", "-c", script], cwd=str(project), env=env, capture_output=True, text=True
    ).stdout


class TestAutodevRouting:
    """The real state actions, driven end to end against real issue files."""

    def test_satisfied_gate_with_historical_prose_not_parked(self, project: Path) -> None:
        _write(project, "gate:\n  kind: external\n  satisfied: true\n", GATE_PROSE)
        assert "GATE_YES" not in _run_state(project, "check_gate_at_dequeue")

    def test_empty_gate_with_prose_not_parked(self, project: Path) -> None:
        _write(project, "gate: []\n", GATE_PROSE)
        assert "GATE_YES" not in _run_state(project, "check_gate_at_dequeue")

    def test_absent_gate_with_prose_still_parked(self, project: Path) -> None:
        _write(project, "", GATE_PROSE)
        assert "GATE_YES" in _run_state(project, "check_gate_at_dequeue")

    def test_open_external_gate_parked(self, project: Path) -> None:
        _write(project, "gate:\n  kind: external\n  satisfied: false\n")
        assert "GATE_YES" in _run_state(project, "check_gate_at_dequeue")

    def test_proof_gate_not_parked_at_dequeue(self, project: Path) -> None:
        _write(project, "gate:\n  kind: proof\n  satisfied: false\n")
        assert "GATE_YES" not in _run_state(project, "check_gate_at_dequeue")

    def test_placeholder_ac_skipped_when_gate_field_present(self, project: Path) -> None:
        body = "## Acceptance Criteria\n\nTo be determined.\n"
        _write(project, "gate: []\n", body)
        assert "GATE_YES" not in _run_state(project, "check_gate_at_dequeue")
        _write(project, "", body)
        assert "GATE_YES" in _run_state(project, "check_gate_at_dequeue")

    def test_unsatisfied_proof_gate_reaches_run_spike(self, project: Path) -> None:
        _write(project, "gate:\n  kind: proof\n  satisfied: false\n")
        assert "PROOF_SPIKE" in _run_state(project, "check_proof_gate_before_implement")

    def test_proven_spike_clears_proof_gate(self, project: Path) -> None:
        _write(
            project,
            "gate:\n  kind: proof\n  satisfied: false\nspike_attempted: true\n"
            "spike_completed: true\n",
        )
        out = _run_state(project, "check_proof_gate_before_implement")
        assert "PROOF_CLEAR" in out
        assert _run_state(project, "check_proof_defer_or_implement").count("PROOF_DEFER") == 0

    def test_spent_spike_budget_defers(self, project: Path) -> None:
        _write(project, "gate:\n  kind: proof\n  satisfied: false\n")
        run_dir = project / "run"
        run_dir.mkdir()
        (run_dir / f"spike-runs-{ID}").write_text("2")
        assert "PROOF_DEFER" in _run_state(project, "check_proof_gate_before_implement")
        assert "PROOF_DEFER" in _run_state(project, "check_proof_defer_or_implement")

    def test_no_gate_reaches_implement(self, project: Path) -> None:
        _write(project, "")
        assert "PROOF_CLEAR" in _run_state(project, "check_proof_gate_before_implement")

    def test_implement_edges_route_through_guard(self) -> None:
        states = yaml.safe_load(LOOP.read_text())["states"]
        assert states["check_passed"]["on_yes"] == "check_proof_gate_before_implement"
        assert states["check_proof_gate_before_implement"]["on_yes"] == "run_spike"
        assert states["check_proof_defer_or_implement"]["on_yes"] == "defer_gated"
        assert states["check_proof_defer_or_implement"]["on_no"] == "implement_current"
