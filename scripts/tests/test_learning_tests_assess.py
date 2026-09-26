"""Single budget owner for learning-proof evidence (ENH-3602).

``assess_proof`` is the one classifier for learning-test targets + spike
proof; this suite pins its classification table, the attempt-budget policy,
the ``assess_proof`` pre-check inside ``run_learning_gate_for_issue``, the
``ll-learning-tests assess`` CLI contract, and the shared-fixture parity
requirement (same fixture → same verdict from every in-scope consumer),
modeled on the dual-parametrize idiom of ``test_spike_verdict_routing.py``.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from little_loops.learning_tests import Assertion, LearnTestRecord, write_record
from little_loops.learning_tests.assess import ProofVerdict, assess_proof
from little_loops.learning_tests.gate import run_learning_gate_for_issue

ISSUE_ID = "ENH-42"
TARGET = "parity-target"


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _record(
    *,
    target: str = TARGET,
    status: str = "proven",
    age_days: int = 0,
) -> LearnTestRecord:
    date = (datetime.date.today() - datetime.timedelta(days=age_days)).isoformat()
    return LearnTestRecord(
        target=target,
        date=date,
        status=status,  # type: ignore[arg-type]
        assertions=[Assertion(claim="c", result="pass")],
        raw_output_path=None,
    )


def _write_issue(
    tmp_path: Path,
    *,
    extra_fm: str = "",
    learning_tests: list[str] | None = None,
) -> Path:
    fm = [f"id: {ISSUE_ID}", "status: open"]
    if learning_tests is not None:
        fm.append("learning_tests_required: [" + ", ".join(learning_tests) + "]")
    if extra_fm:
        fm.append(extra_fm.rstrip())
    path = tmp_path / f"{ISSUE_ID}.md"
    path.write_text("---\n" + "\n".join(fm) + "\n---\n\n# body\n")
    return path


def _project(
    tmp_path: Path,
    *,
    enabled: bool = True,
    stale_after_days: int = 30,
) -> Path:
    """Write a minimal .ll/ll-config.json arming learning_tests staleness."""
    ll_dir = tmp_path / ".ll"
    ll_dir.mkdir(exist_ok=True)
    (ll_dir / "ll-config.json").write_text(
        json.dumps({"learning_tests": {"enabled": enabled, "stale_after_days": stale_after_days}})
    )
    return tmp_path


def _registry_dir(tmp_path: Path) -> Path:
    base = tmp_path / ".ll" / "learning-tests"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _ok_result() -> MagicMock:
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = ""
    mock.stderr = ""
    return mock


# ---------------------------------------------------------------------------
# Classification table
# ---------------------------------------------------------------------------


class TestAssessProofClassification:
    def test_fresh_proven_record_is_proven(self, tmp_path: Path) -> None:
        _project(tmp_path)
        write_record(_record(age_days=0), base_dir=_registry_dir(tmp_path))
        path = _write_issue(tmp_path, learning_tests=[TARGET])
        verdict = assess_proof(path, cwd=tmp_path)
        assert verdict.status == "proven"
        assert verdict.targets == {TARGET: "proven"}
        assert verdict.issue_id == ISSUE_ID

    def test_aged_record_is_stale(self, tmp_path: Path) -> None:
        _project(tmp_path, stale_after_days=30)
        write_record(_record(age_days=400), base_dir=_registry_dir(tmp_path))
        path = _write_issue(tmp_path, learning_tests=[TARGET])
        verdict = assess_proof(path, cwd=tmp_path)
        assert verdict.status == "stale"
        assert verdict.targets == {TARGET: "stale"}

    def test_refuted_record_is_refuted(self, tmp_path: Path) -> None:
        _project(tmp_path)
        write_record(_record(status="refuted"), base_dir=_registry_dir(tmp_path))
        path = _write_issue(tmp_path, learning_tests=[TARGET])
        verdict = assess_proof(path, cwd=tmp_path)
        assert verdict.status == "refuted"
        assert verdict.targets == {TARGET: "refuted"}

    def test_missing_record_is_absent(self, tmp_path: Path) -> None:
        _project(tmp_path)
        path = _write_issue(tmp_path, learning_tests=[TARGET])
        verdict = assess_proof(path, cwd=tmp_path)
        assert verdict.status == "absent"
        assert verdict.targets == {TARGET: "absent"}

    def test_no_requirements_is_not_required(self, tmp_path: Path) -> None:
        _project(tmp_path)
        path = _write_issue(tmp_path)
        verdict = assess_proof(path, cwd=tmp_path)
        assert verdict.status == "not_required"
        assert verdict.targets == {}

    def test_empty_requirements_list_is_not_required(self, tmp_path: Path) -> None:
        _project(tmp_path)
        path = _write_issue(tmp_path, learning_tests=[])
        verdict = assess_proof(path, cwd=tmp_path)
        assert verdict.status == "not_required"
        assert verdict.targets == {}

    def test_worst_status_wins_absent_over_stale(self, tmp_path: Path) -> None:
        _project(tmp_path, stale_after_days=30)
        write_record(_record(age_days=400), base_dir=_registry_dir(tmp_path))
        path = _write_issue(tmp_path, learning_tests=[TARGET, "other-target"])
        verdict = assess_proof(path, cwd=tmp_path)
        assert verdict.status == "absent"
        assert verdict.targets == {TARGET: "stale", "other-target": "absent"}

    def test_worst_status_wins_refuted_over_absent(self, tmp_path: Path) -> None:
        _project(tmp_path)
        write_record(_record(status="refuted"), base_dir=_registry_dir(tmp_path))
        path = _write_issue(tmp_path, learning_tests=[TARGET, "other-target"])
        verdict = assess_proof(path, cwd=tmp_path)
        assert verdict.status == "refuted"

    def test_disabled_config_counts_aged_proven_fresh(self, tmp_path: Path) -> None:
        """learning_tests.enabled=false turns staleness off entirely (executor parity)."""
        _project(tmp_path, enabled=False, stale_after_days=30)
        write_record(_record(age_days=400), base_dir=_registry_dir(tmp_path))
        path = _write_issue(tmp_path, learning_tests=[TARGET])
        verdict = assess_proof(path, cwd=tmp_path)
        assert verdict.status == "proven"

    def test_no_config_defaults_to_staleness_off(self, tmp_path: Path) -> None:
        """A project without learning_tests config defaults to disabled staleness."""
        write_record(_record(age_days=400), base_dir=_registry_dir(tmp_path))
        path = _write_issue(tmp_path, learning_tests=[TARGET])
        verdict = assess_proof(path, cwd=tmp_path)
        assert verdict.status == "proven"

    def test_stale_after_days_override(self, tmp_path: Path) -> None:
        _project(tmp_path, stale_after_days=30)
        write_record(_record(age_days=400), base_dir=_registry_dir(tmp_path))
        path = _write_issue(tmp_path, learning_tests=[TARGET])
        # Explicit override with an unreachable threshold counts the record fresh.
        assert assess_proof(path, cwd=tmp_path, stale_after_days=10_000).status == "proven"


class TestAssessProofTargetsOverride:
    """Caller-resolved targets take precedence over frontmatter declarations."""

    def test_override_targets_when_frontmatter_declares_none(self, tmp_path: Path) -> None:
        _project(tmp_path)
        write_record(_record(age_days=0), base_dir=_registry_dir(tmp_path))
        path = _write_issue(tmp_path)  # no learning_tests_required
        verdict = assess_proof(path, cwd=tmp_path, targets=[TARGET])
        assert verdict.status == "proven"
        assert verdict.targets == {TARGET: "proven"}

    def test_empty_override_is_not_required(self, tmp_path: Path) -> None:
        _project(tmp_path)
        write_record(_record(), base_dir=_registry_dir(tmp_path))
        path = _write_issue(tmp_path, learning_tests=[TARGET])
        verdict = assess_proof(path, cwd=tmp_path, targets=[])
        assert verdict.status == "not_required"


# ---------------------------------------------------------------------------
# Spike leg
# ---------------------------------------------------------------------------


class TestAssessProofSpikeLeg:
    def test_spike_refuted_flag(self, tmp_path: Path) -> None:
        _project(tmp_path)
        path = _write_issue(
            tmp_path, extra_fm="spike_attempted: true\nspike_refuted: true\nspike_completed: true"
        )
        verdict = assess_proof(path, cwd=tmp_path)
        assert verdict.status == "refuted"
        assert verdict.targets == {"spike": "refuted"}

    def test_spike_completed_is_proven(self, tmp_path: Path) -> None:
        _project(tmp_path)
        path = _write_issue(tmp_path, extra_fm="spike_attempted: true\nspike_completed: true")
        verdict = assess_proof(path, cwd=tmp_path)
        assert verdict.status == "proven"
        assert verdict.targets == {"spike": "proven"}

    def test_spike_attempted_without_completion_is_absent(self, tmp_path: Path) -> None:
        _project(tmp_path)
        path = _write_issue(tmp_path, extra_fm="spike_attempted: true")
        verdict = assess_proof(path, cwd=tmp_path)
        assert verdict.status == "absent"
        assert verdict.targets == {"spike": "absent"}

    def test_unsatisfied_proof_gate_declares_spike_requirement(self, tmp_path: Path) -> None:
        _project(tmp_path)
        path = _write_issue(
            tmp_path,
            extra_fm="gate:\n  kind: proof\n  satisfied: false",
        )
        verdict = assess_proof(path, cwd=tmp_path)
        assert verdict.status == "absent"
        assert verdict.targets == {"spike": "absent"}

    def test_spike_proven_satisfies_proof_gate(self, tmp_path: Path) -> None:
        _project(tmp_path)
        path = _write_issue(
            tmp_path,
            extra_fm="spike_attempted: true\nspike_completed: true\ngate:\n  kind: proof\n  satisfied: false",
        )
        verdict = assess_proof(path, cwd=tmp_path)
        assert verdict.status == "proven"
        assert verdict.targets == {"spike": "proven"}

    def test_no_spike_requirement_omits_spike_key(self, tmp_path: Path) -> None:
        _project(tmp_path)
        write_record(_record(), base_dir=_registry_dir(tmp_path))
        path = _write_issue(tmp_path, learning_tests=[TARGET])
        verdict = assess_proof(path, cwd=tmp_path)
        assert "spike" not in verdict.targets


# ---------------------------------------------------------------------------
# Budget policy and reason
# ---------------------------------------------------------------------------


class TestAssessProofBudget:
    @pytest.mark.parametrize(
        "attempts_used,expected",
        [(0, 2), (1, 1), (2, 0), (5, 0)],
    )
    def test_budget_remaining_arithmetic(
        self, tmp_path: Path, attempts_used: int, expected: int
    ) -> None:
        _project(tmp_path)
        write_record(_record(), base_dir=_registry_dir(tmp_path))
        path = _write_issue(tmp_path, learning_tests=[TARGET])
        verdict = assess_proof(path, cwd=tmp_path, attempts_used=attempts_used)
        assert verdict.budget_remaining == expected

    def test_standalone_call_has_no_run_scoped_budget(self, tmp_path: Path) -> None:
        _project(tmp_path)
        write_record(_record(), base_dir=_registry_dir(tmp_path))
        path = _write_issue(tmp_path, learning_tests=[TARGET])
        assert assess_proof(path, cwd=tmp_path).budget_remaining is None


class TestAssessProofReason:
    def test_reason_names_unproven_target_and_status(self, tmp_path: Path) -> None:
        _project(tmp_path)
        path = _write_issue(tmp_path, learning_tests=[TARGET])
        verdict = assess_proof(path, cwd=tmp_path)
        assert TARGET in verdict.reason
        assert "absent" in verdict.reason

    def test_reason_carries_staleness_detail(self, tmp_path: Path) -> None:
        _project(tmp_path, stale_after_days=30)
        write_record(_record(age_days=400), base_dir=_registry_dir(tmp_path))
        path = _write_issue(tmp_path, learning_tests=[TARGET])
        verdict = assess_proof(path, cwd=tmp_path)
        assert "stale" in verdict.reason
        assert "days old" in verdict.reason

    def test_all_proven_reason(self, tmp_path: Path) -> None:
        _project(tmp_path)
        write_record(_record(), base_dir=_registry_dir(tmp_path))
        path = _write_issue(tmp_path, learning_tests=[TARGET])
        assert assess_proof(path, cwd=tmp_path).reason == "all proof targets proven"

    def test_not_required_reason(self, tmp_path: Path) -> None:
        _project(tmp_path)
        path = _write_issue(tmp_path)
        assert assess_proof(path, cwd=tmp_path).reason == "no proof requirements declared"


def test_proof_verdict_to_dict_shape(tmp_path: Path) -> None:
    _project(tmp_path)
    write_record(_record(), base_dir=_registry_dir(tmp_path))
    path = _write_issue(tmp_path, learning_tests=[TARGET])
    data = assess_proof(path, cwd=tmp_path).to_dict()
    assert set(data) == {"issue_id", "status", "targets", "budget_remaining", "reason"}
    assert isinstance(data["targets"], dict)


# ---------------------------------------------------------------------------
# run_learning_gate_for_issue pre-check
# ---------------------------------------------------------------------------


class TestRunLearningGatePreCheck:
    def test_proven_short_circuits_without_subprocess(self, tmp_path: Path) -> None:
        _project(tmp_path)
        write_record(_record(), base_dir=_registry_dir(tmp_path))
        path = _write_issue(tmp_path, learning_tests=[TARGET])
        with patch(
            "little_loops.learning_tests.gate.subprocess.run", return_value=_ok_result()
        ) as mock_sub:
            verdict = run_learning_gate_for_issue(path, cwd=tmp_path, targets=[TARGET])
        assert verdict == "passed"
        mock_sub.assert_not_called()

    def test_not_required_short_circuits_without_subprocess(self, tmp_path: Path) -> None:
        _project(tmp_path)
        path = _write_issue(tmp_path)  # bare issue, JIT-caller shape
        with patch(
            "little_loops.learning_tests.gate.subprocess.run", return_value=_ok_result()
        ) as mock_sub:
            verdict = run_learning_gate_for_issue(path, cwd=tmp_path)
        assert verdict == "passed"
        mock_sub.assert_not_called()

    def test_stale_takes_subprocess_path(self, tmp_path: Path) -> None:
        """Stale classifies short of proven, so remediation falls to the child gate."""
        _project(tmp_path, stale_after_days=30)
        write_record(_record(age_days=400), base_dir=_registry_dir(tmp_path))
        path = _write_issue(tmp_path, learning_tests=[TARGET])
        with patch(
            "little_loops.learning_tests.gate.subprocess.run", return_value=_ok_result()
        ) as mock_sub:
            verdict = run_learning_gate_for_issue(path, cwd=tmp_path, targets=[TARGET])
        assert verdict == "passed"  # child re-proved (classification vs remediation)
        mock_sub.assert_called_once()

    def test_absent_takes_subprocess_path(self, tmp_path: Path) -> None:
        _project(tmp_path)
        path = _write_issue(tmp_path, learning_tests=[TARGET])
        with patch(
            "little_loops.learning_tests.gate.subprocess.run", return_value=_ok_result()
        ) as mock_sub:
            verdict = run_learning_gate_for_issue(path, cwd=tmp_path, targets=[TARGET])
        assert verdict == "passed"
        mock_sub.assert_called_once()

    def test_explicit_targets_with_bare_frontmatter_reach_subprocess(self, tmp_path: Path) -> None:
        """ENH-2834 shape: caller-resolved targets must be assessed, not the (empty) field."""
        _project(tmp_path)
        path = _write_issue(tmp_path)  # no learning_tests_required
        with patch(
            "little_loops.learning_tests.gate.subprocess.run", return_value=_ok_result()
        ) as mock_sub:
            verdict = run_learning_gate_for_issue(path, cwd=tmp_path, targets=[TARGET])
        assert verdict == "passed"  # record absent → subprocess; child proved it
        mock_sub.assert_called_once()

    def test_skip_still_short_circuits_first(self, tmp_path: Path) -> None:
        _project(tmp_path)
        path = _write_issue(tmp_path)
        with patch("little_loops.learning_tests.gate.subprocess.run") as mock_sub:
            verdict = run_learning_gate_for_issue(path, cwd=tmp_path, skip=True)
        assert verdict == "skipped"
        mock_sub.assert_not_called()

    def test_assess_failure_falls_through_to_subprocess(self, tmp_path: Path) -> None:
        """A pre-check failure must fail open to the existing subprocess gate."""
        _project(tmp_path)
        path = tmp_path / "does-not-exist.md"
        with patch(
            "little_loops.learning_tests.gate.subprocess.run", return_value=_ok_result()
        ) as mock_sub:
            verdict = run_learning_gate_for_issue(path, cwd=tmp_path)
        assert verdict == "passed"
        mock_sub.assert_called_once()


# ---------------------------------------------------------------------------
# ll-learning-tests assess CLI
# ---------------------------------------------------------------------------


class TestAssessCLI:
    def _issue_project(self, tmp_path: Path, *, learning_tests: list[str] | None) -> Path:
        """Lay out a real .issues/ tree so --issue resolves like production."""
        issues_dir = tmp_path / ".issues" / "enhancements"
        issues_dir.mkdir(parents=True)
        path = issues_dir / "P3-ENH-42-parity-fixture.md"
        lines = ["---", f"id: {ISSUE_ID}", "status: open"]
        if learning_tests is not None:
            lines.append("learning_tests_required: [" + ", ".join(learning_tests) + "]")
        lines.extend(["---", ""])
        path.write_text("\n".join(lines))
        return path

    def _run_cli(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *extra: str) -> int:
        from little_loops.cli.learning_tests import main_learning_tests

        argv = ["ll-learning-tests", "assess", "--issue", ISSUE_ID, *extra]
        with patch("sys.argv", argv):
            return main_learning_tests()

    def test_proven_exits_0_with_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _project(tmp_path)
        write_record(_record(), base_dir=_registry_dir(tmp_path))
        self._issue_project(tmp_path, learning_tests=[TARGET])
        monkeypatch.chdir(tmp_path)
        result = self._run_cli(monkeypatch, tmp_path, "--json")
        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert data["status"] == "proven"
        assert data["issue_id"] == ISSUE_ID
        assert data["targets"] == {TARGET: "proven"}
        assert data["budget_remaining"] is None

    def test_stale_exits_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _project(tmp_path, stale_after_days=30)
        write_record(_record(age_days=400), base_dir=_registry_dir(tmp_path))
        self._issue_project(tmp_path, learning_tests=[TARGET])
        monkeypatch.chdir(tmp_path)
        result = self._run_cli(monkeypatch, tmp_path, "--json")
        assert result == 1
        data = json.loads(capsys.readouterr().out)
        assert data["status"] == "stale"

    def test_absent_exits_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _project(tmp_path)
        self._issue_project(tmp_path, learning_tests=[TARGET])
        monkeypatch.chdir(tmp_path)
        result = self._run_cli(monkeypatch, tmp_path, "--json")
        assert result == 1
        data = json.loads(capsys.readouterr().out)
        assert data["status"] == "absent"

    def test_not_required_exits_0(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _project(tmp_path)
        self._issue_project(tmp_path, learning_tests=None)
        monkeypatch.chdir(tmp_path)
        result = self._run_cli(monkeypatch, tmp_path, "--json")
        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert data["status"] == "not_required"
        assert data["targets"] == {}

    def test_unknown_issue_exits_2(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _project(tmp_path)
        monkeypatch.chdir(tmp_path)
        from little_loops.cli.learning_tests import main_learning_tests

        with patch("sys.argv", ["ll-learning-tests", "assess", "--issue", "ENH-999999"]):
            result = main_learning_tests()
        assert result == 2

    def test_default_output_is_status_token(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _project(tmp_path)
        write_record(_record(), base_dir=_registry_dir(tmp_path))
        self._issue_project(tmp_path, learning_tests=[TARGET])
        monkeypatch.chdir(tmp_path)
        result = self._run_cli(monkeypatch, tmp_path)
        assert result == 0
        assert capsys.readouterr().out.strip() == "proven"


# ---------------------------------------------------------------------------
# Shared-fixture parity: same fixture → same verdict from every consumer
# (dual-parametrize idiom per test_spike_verdict_routing.py:42-63)
# ---------------------------------------------------------------------------

PARITY_CASES = [
    ({"status": "proven", "age_days": 0}, "proven"),
    ({"status": "proven", "age_days": 400}, "stale"),
    ({"status": "refuted", "age_days": 0}, "refuted"),
    (None, "absent"),
]

PARITY_CONSUMERS = ["assess_proof", "assess_cli", "ll_auto_precheck"]


@pytest.mark.parametrize("record_kwargs,expected_status", PARITY_CASES)
@pytest.mark.parametrize("consumer", PARITY_CONSUMERS)
def test_proof_parity_across_consumers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    consumer: str,
    record_kwargs: dict | None,
    expected_status: str,
) -> None:
    _project(tmp_path, stale_after_days=30)
    if record_kwargs is not None:
        write_record(_record(**record_kwargs), base_dir=_registry_dir(tmp_path))
    # One shared issue file, laid out for the CLI's ID resolver; assess_proof
    # and the pre-check take the same path directly.
    issues_dir = tmp_path / ".issues" / "enhancements"
    issues_dir.mkdir(parents=True, exist_ok=True)
    path = _write_issue(tmp_path, learning_tests=[TARGET])
    path = path.rename(issues_dir / "P3-ENH-42-parity-fixture.md")

    if consumer == "assess_proof":
        assert assess_proof(path, cwd=tmp_path).status == expected_status
    elif consumer == "assess_cli":
        monkeypatch.chdir(tmp_path)
        from little_loops.cli.learning_tests import main_learning_tests

        with patch("sys.argv", ["ll-learning-tests", "assess", "--issue", ISSUE_ID, "--json"]):
            result = main_learning_tests()
        data = json.loads(capsys.readouterr().out)
        assert data["status"] == expected_status
        assert result == (0 if expected_status in ("proven", "not_required") else 1)
    else:  # ll_auto_precheck — classification observable via short-circuit behavior
        with patch(
            "little_loops.learning_tests.gate.subprocess.run", return_value=_ok_result()
        ) as mock_sub:
            verdict = run_learning_gate_for_issue(path, cwd=tmp_path, targets=[TARGET])
        if expected_status in ("proven", "not_required"):
            assert verdict == "passed"
            mock_sub.assert_not_called()
        else:
            mock_sub.assert_called_once()


def test_not_required_parity_across_consumers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _project(tmp_path)
    path = _write_issue(tmp_path)  # declares nothing

    assert assess_proof(path, cwd=tmp_path).status == "not_required"

    monkeypatch.chdir(tmp_path)
    issues_dir = tmp_path / ".issues" / "enhancements"
    issues_dir.mkdir(parents=True)
    (issues_dir / "P3-ENH-42-parity-fixture.md").write_text(
        f"---\nid: {ISSUE_ID}\nstatus: open\n---\n"
    )
    from little_loops.cli.learning_tests import main_learning_tests

    with patch("sys.argv", ["ll-learning-tests", "assess", "--issue", ISSUE_ID, "--json"]):
        result = main_learning_tests()
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "not_required"
    assert result == 0

    with patch(
        "little_loops.learning_tests.gate.subprocess.run", return_value=_ok_result()
    ) as mock_sub:
        verdict = run_learning_gate_for_issue(path, cwd=tmp_path)
    assert verdict == "passed"
    mock_sub.assert_not_called()


# Imported to keep the reference honest: ProofVerdict is the transport every
# consumer maps (asserted structurally above via to_dict()).
_ = ProofVerdict
