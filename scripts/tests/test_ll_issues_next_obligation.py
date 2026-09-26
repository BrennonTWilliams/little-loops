"""Tests for ll-issues next-obligation (FEAT-3598)."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

import little_loops.cli.issues.next_obligation as no
from little_loops.cli.issues.check_verify_verdict import classify_verify_verdict
from little_loops.cli.issues.next_obligation import (
    Obligation,
    ObligationProbeError,
    cmd_next_obligation,
    select_next_obligation,
)
from little_loops.config import BRConfig

LOOP = Path(__file__).parent.parent / "little_loops" / "loops" / "refine-to-ready-issue.yaml"
ID = "ENH-9100"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    for kind in ("bugs", "features", "enhancements", "epics"):
        (tmp_path / ".issues" / kind).mkdir(parents=True, exist_ok=True)
    (tmp_path / ".ll").mkdir(exist_ok=True)
    return tmp_path


def _write(project: Path, frontmatter: str = "", body: str = "## Summary\n\nPlain.\n") -> Path:
    path = project / ".issues" / "enhancements" / f"P3-{ID}-test.md"
    path.write_text(
        f"---\nid: {ID}\ntitle: T\ntype: enhancement\nstatus: open\npriority: P3\n"
        f"{frontmatter}---\n\n# {ID}: T\n\n{body}"
    )
    return path


def _clean(monkeypatch: pytest.MonkeyPatch, forced: dict[Obligation, Any] | None = None) -> None:
    """Make every tier-1 probe except the forced ones pass."""
    forced = forced or {}
    monkeypatch.setattr(no, "_tier1_probe", lambda ob, path, content: forced.get(ob))


SCORES_OK = "verify_verdict: VALID\nconfidence_score: 90\noutcome_confidence: 80\n"
OUTCOME_LOW = "verify_verdict: VALID\nconfidence_score: 90\noutcome_confidence: 40\n"


def _sel(project: Path, **kw: Any) -> no.ObligationResult:
    res = select_next_obligation(BRConfig(project), ID, **kw)
    assert res is not None
    return res


class TestVerify:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (None, "absent"),
            ("VALID", "VALID"),
            ("valid", "VALID"),
            ("EVIDENCE_UNVERIFIED", "EVIDENCE_UNVERIFIED"),
            ("PROPOSAL_UNSOUND", "PROPOSAL_UNSOUND"),
            ("DIRECTIVE_DRIFT", "DIRECTIVE_DRIFT"),
            ("NON_VALID", "other"),
        ],
    )
    def test_classifier(self, value: object, expected: str) -> None:
        assert classify_verify_verdict(value) == expected

    def test_absent(self, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _clean(monkeypatch)
        _write(project)
        res = _sel(project)
        assert (res.obligation, res.sub_reason) == (Obligation.VERIFY, "absent")

    @pytest.mark.parametrize(
        "verdict", ["EVIDENCE_UNVERIFIED", "PROPOSAL_UNSOUND", "DIRECTIVE_DRIFT", "NON_VALID"]
    )
    def test_sub_reasons(
        self, project: Path, monkeypatch: pytest.MonkeyPatch, verdict: str
    ) -> None:
        _clean(monkeypatch)
        _write(project, f"verify_verdict: {verdict}\n")
        res = _sel(project)
        expected = "other" if verdict == "NON_VALID" else verdict
        assert res.token() == f"VERIFY:{expected}"

    def test_valid_moves_on_to_hedges(self, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _clean(monkeypatch, {Obligation.HEDGES: ("open questions", ["open_questions=1"])})
        _write(project, "verify_verdict: VALID\n")
        assert _sel(project).obligation is Obligation.HEDGES


class TestTier1:
    def test_order_earlier_wins(self, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _clean(
            monkeypatch,
            {
                Obligation.PLACEHOLDERS: ("p", []),
                Obligation.ACCEPTANCE_CRITERIA: ("a", []),
                Obligation.DESIGN: ("d", []),
            },
        )
        _write(project, "verify_verdict: VALID\n")
        assert _sel(project).obligation is Obligation.PLACEHOLDERS

    @pytest.mark.parametrize(
        "ob", [Obligation.FORMAT, Obligation.ACCEPTANCE_CRITERIA, Obligation.DESIGN]
    )
    def test_each_forced(
        self, project: Path, monkeypatch: pytest.MonkeyPatch, ob: Obligation
    ) -> None:
        _clean(monkeypatch, {ob: ("why", ["e"])})
        _write(project, "verify_verdict: VALID\n")
        res = _sel(project)
        assert res.obligation is ob
        assert res.evidence == ["e"]

    def test_real_hedges(self, project: Path) -> None:
        _write(project, "verify_verdict: VALID\n", "## Open Questions\n\n- Should we do X?\n")
        res = _sel(project, skip=[Obligation.FORMAT, Obligation.PLACEHOLDERS])
        assert res.obligation is Obligation.HEDGES

    def test_real_acceptance_criteria(self, project: Path) -> None:
        _write(
            project,
            "verify_verdict: VALID\n",
            "## Acceptance Criteria\n\n- [ ] Check this manually in the UI\n",
        )
        res = _sel(project, skip=[Obligation.FORMAT, Obligation.PLACEHOLDERS])
        assert res.obligation is Obligation.ACCEPTANCE_CRITERIA
        assert "manually" in res.evidence[0]


class TestScoresTiers:
    def test_passing_scores_none_even_with_decision(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clean(monkeypatch)
        _write(project, SCORES_OK + "decision_needed: true\n")
        assert _sel(project).obligation is Obligation.NONE

    def test_scores_absent(self, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _clean(monkeypatch)
        _write(project, "verify_verdict: VALID\n")
        assert _sel(project).token() == "SCORES:absent"

    def test_readiness_below_beats_decision(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clean(monkeypatch)
        _write(
            project,
            "verify_verdict: VALID\nconfidence_score: 50\noutcome_confidence: 40\n"
            "decision_needed: true\n",
        )
        assert _sel(project).token() == "SCORES:readiness_below"

    def test_outcome_below_decision(self, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _clean(monkeypatch)
        _write(project, OUTCOME_LOW + "decision_needed: true\n")
        assert _sel(project).obligation is Obligation.DECISION

    def test_outcome_below_artifacts(self, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _clean(monkeypatch)
        _write(project, OUTCOME_LOW + "missing_artifacts: true\n")
        assert _sel(project).obligation is Obligation.ARTIFACTS

    def test_outcome_below_unexplained(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clean(monkeypatch)
        _write(project, OUTCOME_LOW)
        assert _sel(project).token() == "SCORES:outcome_below"

    def test_proof_absent_and_departures(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clean(monkeypatch)
        # spike_attempted without spike_completed -> assess_proof reports absent
        _write(project, OUTCOME_LOW + "spike_needed: true\nspike_attempted: true\n")
        assert _sel(project).token() == "PROOF:absent"

    def test_structured_proof_gate(self, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _clean(monkeypatch)
        _write(project, OUTCOME_LOW + "gate:\n  - kind: proof\n    satisfied: false\n")
        assert _sel(project).obligation is Obligation.PROOF

    def test_thresholds_override(self, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _clean(monkeypatch)
        _write(project, OUTCOME_LOW)
        assert _sel(project, outcome_override=30).obligation is Obligation.NONE
        assert _sel(project, readiness_override=95).token() == "SCORES:readiness_below"

    def test_honor_waiver(self, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _clean(monkeypatch)
        _write(project, OUTCOME_LOW + "outcome_gate_waived: true\n")
        assert _sel(project).token() == "SCORES:outcome_below"
        assert _sel(project, honor_waiver=True).obligation is Obligation.NONE


class TestSkip:
    def test_skip_moves_on(self, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _clean(
            monkeypatch,
            {Obligation.HEDGES: ("h", []), Obligation.PLACEHOLDERS: ("p", [])},
        )
        _write(project, "verify_verdict: VALID\n")
        res = _sel(project, skip=[Obligation.HEDGES])
        assert res.obligation is Obligation.PLACEHOLDERS
        assert res.skipped == ["HEDGES"]

    def test_skip_proof_falls_to_outcome_below(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clean(monkeypatch)
        _write(project, OUTCOME_LOW + "spike_needed: true\n")
        assert _sel(project).obligation is Obligation.PROOF
        assert _sel(project, skip=[Obligation.PROOF]).token() == "SCORES:outcome_below"

    def test_skip_scores_is_none(self, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _clean(monkeypatch)
        _write(project, "verify_verdict: VALID\n")
        assert _sel(project, skip=[Obligation.SCORES]).obligation is Obligation.NONE


class TestProbeErrors:
    def test_unresolvable_id(self, project: Path) -> None:
        assert select_next_obligation(BRConfig(project), "ENH-1") is None

    def test_fail_open_recorded(self, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(ob: Obligation, path: Any, content: str) -> None:
            if ob is Obligation.HEDGES:
                raise RuntimeError("boom")
            return None

        monkeypatch.setattr(no, "_tier1_probe", boom)
        _write(project, SCORES_OK)
        res = _sel(project)
        assert res.obligation is Obligation.NONE
        assert any("HEDGES" in e for e in res.probe_errors)

    def test_fail_closed_verify(self, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _clean(monkeypatch)
        _write(project, SCORES_OK)

        def boom(fm: Any) -> str:
            raise RuntimeError("boom")

        monkeypatch.setattr(no, "_verify_class", boom)
        with pytest.raises(ObligationProbeError):
            _sel(project)
        args = argparse.Namespace(issue_id=ID, format="token")
        monkeypatch.setattr(
            "little_loops.cli.issues.next_obligation.select_next_obligation",
            lambda *a, **k: (_ for _ in ()).throw(ObligationProbeError("x")),
        )
        assert cmd_next_obligation(BRConfig(project), args) == 2

    def test_fail_closed_scores(self, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _clean(monkeypatch)
        _write(project, "verify_verdict: VALID\n")

        def boom(*a: Any, **k: Any) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr("little_loops.cli.issues.check_readiness.readiness_status", boom)
        with pytest.raises(ObligationProbeError):
            _sel(project)


class TestOutput:
    def _args(self, fmt: str, **kw: Any) -> argparse.Namespace:
        return argparse.Namespace(issue_id=ID, format=fmt, skip=[], **kw)

    def test_formats(
        self, project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _clean(monkeypatch)
        _write(project, "verify_verdict: PROPOSAL_UNSOUND\n")
        cfg = BRConfig(project)
        assert cmd_next_obligation(cfg, self._args("token")) == 0
        assert capsys.readouterr().out.strip() == "VERIFY:PROPOSAL_UNSOUND"
        assert cmd_next_obligation(cfg, self._args("json")) == 0
        data = json.loads(capsys.readouterr().out)
        assert set(data) == {
            "issue_id",
            "obligation",
            "sub_reason",
            "reason",
            "evidence",
            "skipped",
            "probe_errors",
        }
        assert data["obligation"] == "VERIFY"
        assert cmd_next_obligation(cfg, self._args("text")) == 0
        assert "VERIFY:PROPOSAL_UNSOUND" in capsys.readouterr().out

    def test_unresolvable_exits_two(self, project: Path) -> None:
        args = argparse.Namespace(issue_id="ENH-1", format="json", skip=[])
        assert cmd_next_obligation(BRConfig(project), args) == 2


class TestCli:
    def _cli(self) -> list[str]:
        if shutil.which("ll-issues") is not None:
            return ["ll-issues"]
        return [sys.executable, "-m", "little_loops.cli"]

    def test_help_registration(self, project: Path) -> None:
        r = subprocess.run(
            [*self._cli(), "--help"], cwd=str(project), capture_output=True, text=True, timeout=30
        )
        assert r.returncode == 0 and "next-obligation" in r.stdout

    def test_subprocess_token_and_missing(self, project: Path) -> None:
        _write(project)
        r = subprocess.run(
            [*self._cli(), "next-obligation", ID, "--format", "token"],
            cwd=str(project),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode == 0
        assert r.stdout.strip() in {"FORMAT", "VERIFY:absent"}
        r = subprocess.run(
            [*self._cli(), "next-obligation", "ENH-1"],
            cwd=str(project),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode == 2


def _walk(states: dict[str, Any], start: str, edge: str, stop: set[str]) -> list[str]:
    seq, cur = [], start
    while cur and cur not in stop and cur in states and cur not in seq:
        seq.append(cur)
        cur = states[cur].get(edge)
    return seq


class TestYamlParity:
    """The child YAML is the source of truth for obligation order."""

    def test_tier1_order_matches_child(self) -> None:
        states = yaml.safe_load(LOOP.read_text())["states"]
        chain = _walk(states, "check_verify_verdict", "on_yes", {"confidence_check"})
        mapping = {
            "check_verify_verdict": Obligation.VERIFY,
            "check_hedges": Obligation.HEDGES,
            "check_placeholders": Obligation.PLACEHOLDERS,
            "check_ac_automatable": Obligation.ACCEPTANCE_CRITERIA,
            "check_design": Obligation.DESIGN,
        }
        assert [mapping[s] for s in chain] == list(no._TIER1[1:])
        assert no._TIER1[0] is Obligation.FORMAT

    def test_tier3_order_matches_child(self) -> None:
        states = yaml.safe_load(LOOP.read_text())["states"]
        # ENH-3610: the done edge passes through the child's decision gate.
        assert states["check_outcome"]["on_yes"] == "check_decision_before_done"
        chain = _walk(states, states["check_outcome"]["on_no"], "on_no", {"breakdown_issue"})
        mapping = {
            "check_decision_needed": Obligation.DECISION,
            "check_spike_needed": Obligation.PROOF,
            "check_missing_artifacts": Obligation.ARTIFACTS,
        }
        assert [mapping[s] for s in chain] == [
            Obligation.DECISION,
            Obligation.PROOF,
            Obligation.ARTIFACTS,
        ]
        order = list(Obligation)
        assert order.index(Obligation.DECISION) < order.index(Obligation.PROOF)
        assert order.index(Obligation.PROOF) < order.index(Obligation.ARTIFACTS)
