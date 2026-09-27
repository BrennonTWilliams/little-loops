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


def _run_state_proc(
    project: Path, state: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    """Run a real autodev state action; return the full CompletedProcess.

    BUG-3603: failure-path tests need returncode/stderr alongside stdout (the
    proof-gate states discriminate on the check-gate exit code, not just the
    stdout token). Pass ``env`` to shadow ``ll-issues`` with a stub on PATH.
    """
    run_dir = project / "run"
    run_dir.mkdir(exist_ok=True)
    script = (
        _state_action(state)
        .replace("${captured.input.output:shell}", ID)
        .replace("${captured.input.output}", ID)
        .replace("${context.run_dir}", str(run_dir))
    )
    run_env = dict(env) if env is not None else {**os.environ}
    ll = shutil.which("ll-issues")
    if ll and env is None:
        run_env["PATH"] = f"{Path(ll).parent}:{run_env['PATH']}"
    return subprocess.run(
        ["bash", "-c", script], cwd=str(project), env=run_env, capture_output=True, text=True
    )


def _run_state(project: Path, state: str) -> str:
    """Run a real autodev state action against the real ll-issues; return stdout."""
    return _run_state_proc(project, state).stdout


def _stub_env(project: Path, stub_body: str) -> dict[str, str]:
    """Env with a stub ll-issues first on PATH (delegates nothing; every call
    runs the stub body)."""
    bin_dir = project / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "ll-issues"
    fake.write_text(f"#!/bin/sh\n{stub_body}\n")
    fake.chmod(0o755)
    return {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}


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

    def test_unsatisfied_proof_gate_defers_at_pre_implement_gate(self, project: Path) -> None:
        """ENH-3611: autodev no longer spikes (PROOF_SPIKE is gone); the child's
        check_proof_before_done / the selectors' PROOF re-entry own the spike, and an
        open gate that reaches the fail-closed stage defers as blocked_by_gate."""
        _write(project, "gate:\n  kind: proof\n  satisfied: false\n")
        out = _run_state(project, "check_proof_defer_or_implement")
        assert "PROOF_DEFER" in out
        assert "PROOF_SPIKE" not in out

    def test_proven_spike_clears_proof_gate(self, project: Path) -> None:
        _write(
            project,
            "gate:\n  kind: proof\n  satisfied: false\nspike_attempted: true\n"
            "spike_completed: true\n",
        )
        out = _run_state(project, "check_proof_defer_or_implement")
        assert "PROOF_CLEAR" in out
        assert out.count("PROOF_DEFER") == 0

    def test_spent_spike_budget_defers(self, project: Path) -> None:
        _write(project, "gate:\n  kind: proof\n  satisfied: false\n")
        run_dir = project / "run"
        run_dir.mkdir()
        (run_dir / f"spike-runs-{ID}").write_text("2")
        assert "PROOF_DEFER" in _run_state(project, "check_proof_defer_or_implement")

    def test_no_gate_reaches_implement(self, project: Path) -> None:
        _write(project, "")
        # Exit-1-with-recognized-token (`none`) is a real verdict, not infra:
        # the state must clear it (BUG-3603 keeps this path clear).
        assert "PROOF_CLEAR" in _run_state(project, "check_proof_defer_or_implement")

    def test_prose_gate_defers_at_both_proof_states(self, project: Path) -> None:
        """BUG-3603: a real `prose` verdict is a gate in force — dequeue and
        recheck_after_size_review already treat it as gated, so the pre-implement
        states must route it to PROOF_DEFER, never PROOF_CLEAR."""
        _write(project, "", GATE_PROSE)
        for state in ("check_proof_defer_or_implement",):
            out = _run_state(project, state)
            assert "PROOF_DEFER" in out, f"{state} must defer a prose gate, got: {out!r}"
            assert "PROOF_CLEAR" not in out

    def test_helper_exit_two_emits_proof_infra(self, project: Path) -> None:
        """BUG-3603: check-gate exiting 2 (unresolvable ID) with empty stdout is a
        helper failure — both proof states must emit PROOF_INFRA, not PROOF_CLEAR."""
        _write(project, "")
        env = _stub_env(project, 'if [ "$1" = "check-gate" ]; then exit 2; fi\nexit 0')
        for state in ("check_proof_defer_or_implement",):
            result = _run_state_proc(project, state, env)
            assert "PROOF_INFRA" in result.stdout, (
                f"{state} must emit PROOF_INFRA on helper exit 2, "
                f"got {result.stdout!r} (stderr: {result.stderr!r})"
            )
            assert "PROOF_CLEAR" not in result.stdout

    def test_unknown_token_emits_proof_infra(self, project: Path) -> None:
        """BUG-3603: unrecognised stdout (helper printed garbage, exit 0) is a
        helper failure, not a clear verdict."""
        _write(project, "")
        env = _stub_env(
            project, 'if [ "$1" = "check-gate" ]; then echo "TRACE: something"; exit 0; fi\nexit 0'
        )
        for state in ("check_proof_defer_or_implement",):
            out = _run_state_proc(project, state, env).stdout
            assert "PROOF_INFRA" in out, (
                f"{state} must emit PROOF_INFRA on unknown token, got {out!r}"
            )

    def test_implement_edges_route_through_guard(self) -> None:
        states = yaml.safe_load(LOOP.read_text())["states"]
        # ENH-3623: the pre-implement obligation selector moved into the
        # prepare-issue policy; check_passed.on_yes reaches the fail-closed proof
        # gate directly. ENH-3611: check_proof_defer_or_implement is the only proof
        # stage, and the only edge into implement_current.
        assert states["check_passed"]["on_yes"] == "check_proof_defer_or_implement"
        assert "select_obligation_pre_implement" not in states
        assert "check_proof_gate_before_implement" not in states
        route = states["check_proof_defer_or_implement"].get("route", {})
        assert route.get("PROOF_DEFER") == "defer_gated"
        assert route.get("PROOF_CLEAR") == "implement_current"
        assert route.get("PROOF_INFRA") == "mark_proof_gate_infra"
        assert route.get("_") == "mark_proof_gate_infra"
        assert route.get("_error") == "mark_proof_gate_infra"


class TestProofGateFailClosed:
    """BUG-3603: the pre-implement proof gate is the LAST gate before
    implement_current — it must fail closed, not open."""

    @pytest.fixture(scope="class")
    def states(self) -> dict[str, Any]:
        return yaml.safe_load(LOOP.read_text())["states"]

    def test_no_error_edge_targets_implement_current(self, states: dict[str, Any]) -> None:
        offenders = []
        for name, state in states.items():
            for edge in ("on_error", "on_cannot_judge"):
                if state.get(edge) == "implement_current":
                    offenders.append(f"{name}.{edge}")
        assert not offenders, (
            f"failure edges must not target implement_current (BUG-3603 fail-closed): {offenders}"
        )

    def test_implement_current_reachable_only_from_proof_defer_state(
        self, states: dict[str, Any]
    ) -> None:
        predecessors: set[str] = set()
        for name, state in states.items():
            targets = {
                state.get(edge)
                for edge in ("on_yes", "on_no", "on_error", "on_cannot_judge", "next")
            }
            targets |= set((state.get("route") or {}).values())
            if "implement_current" in targets:
                predecessors.add(name)
        assert predecessors == {"check_proof_defer_or_implement"}, (
            "implement_current must be reachable only from the proof gate's "
            f"PROOF_CLEAR route, got predecessors: {sorted(predecessors)}"
        )

    def test_first_proof_state_stays_deleted(self, states: dict[str, Any]) -> None:
        """ENH-3611: check_proof_gate_before_implement (the spiking first stage) is
        gone; check_proof_defer_or_implement is the only proof stage and no state
        routes to a removed proof-spike target."""
        assert "check_proof_gate_before_implement" not in states
        for name, state in states.items():
            targets = {state.get(e) for e in ("on_yes", "on_no", "on_error", "next")}
            targets |= set((state.get("route") or {}).values())
            assert "check_proof_gate_before_implement" not in targets, name

    def test_defer_state_classifies_all_outcomes(self, states: dict[str, Any]) -> None:
        state = states["check_proof_defer_or_implement"]
        assert state.get("evaluate", {}).get("type") == "classify"
        route = state.get("route", {})
        assert route.get("PROOF_CLEAR") == "implement_current"
        assert route.get("PROOF_DEFER") == "defer_gated"
        for key in ("PROOF_INFRA", "_", "_error"):
            assert route.get(key) == "mark_proof_gate_infra", (
                f"route.{key} must fail closed to the infra deferral"
            )

    def test_mark_proof_gate_infra_state_convention(self, states: dict[str, Any]) -> None:
        state = states.get("mark_proof_gate_infra", {})
        action = state.get("action", "")
        assert "autodev-proof-gate-infra.txt" in action
        assert "autodev-inflight" in action
        assert "[PROOF_GATE_INFRA]" in action
        assert "ll-issues set-status" not in action, "infra deferral must not set status"
        assert state.get("action_type") == "shell"
        assert state.get("next") == "dequeue_next"
        assert state.get("on_error") == "dequeue_next"

    def test_init_truncates_proof_gate_infra_ledger(self, states: dict[str, Any]) -> None:
        assert "autodev-proof-gate-infra.txt" in states["init"]["action"], (
            "init must truncate autodev-proof-gate-infra.txt so a stale ledger from a "
            "prior run cannot inflate the summary count (BUG-3603)"
        )
