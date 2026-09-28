"""ENH-3597: typed per-issue run records written by refine-to-ready-issue.

Covers the record module (schema, round-trip, isolation), the mapping
``outcome_from_legacy_class``, the ``ll-issues run-record write`` CLI against a
real tmp ``.issues/`` tree, the loop's terminal-state call sites, and the
``.claude/workflows/refine-to-ready.js`` Finalize-phase mirror.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

TESTS_DIR = Path(__file__).parent
PACKAGE_DIR = TESTS_DIR.parent / "little_loops"
LOOP = PACKAGE_DIR / "loops" / "refine-to-ready-issue.yaml"
MIRROR = TESTS_DIR.parent.parent / ".claude" / "workflows" / "refine-to-ready.js"

# The 11 terminal-bearing states that must call the writer (Program Design Call
# Path): the seven record_*/mark_* failed-exits, classify_terminal,
# write_broke_down, and the three done-path gates.
LEGACY_CLASS_STATES = {
    "record_proposal_unsound": "proposal_unsound",
    "record_gate_unmet": "gate_unmet",
    "mark_rate_limit_infra": "infra",
    "mark_evidence_absent_infra": "infra",
    "mark_spike_no_verdict_infra": "infra",
    "record_spike_inconclusive": "spike_inconclusive",
    "record_decision_unresolved": "decision_unresolved",
    "record_advisor_veto": "gate_unmet",  # ENH-3633
}
# ENH-3610: the three done-path gates no longer write; the record write moved to
# write_done_record, reached only after check_decision_before_done.
# ENH-3604: check_outcome / check_scores_from_file were replaced by the
# route_score_obligation dispatch (its NONE route is asserted in test_builtin_loops.py).
DONE_PATH_GATES = ("check_missing_artifacts",)
TERMINAL_BEARING_STATES = (
    *LEGACY_CLASS_STATES,
    "classify_terminal",
    "write_broke_down",
    "write_done_record",
)

RECORD_KEYS = {
    "writer",
    "issue_id",
    "outcome",
    "child_ids",
    "evidence_refs",
    "legacy_class",
    "readiness",
    "outcome_confidence",
}


def _record_mod():
    try:
        from little_loops import run_record
    except ImportError as exc:  # red-phase: module lands in Phase 1
        pytest.fail(f"little_loops.run_record not implemented yet: {exc}")
    return run_record


def _cli() -> list[str]:
    if shutil.which("ll-issues") is not None:
        return ["ll-issues"]
    return [sys.executable, "-m", "little_loops.cli"]


def _ll_issues_dir() -> str:
    ll = shutil.which("ll-issues")
    return str(Path(ll).parent) if ll else ""


@pytest.fixture
def loop_states() -> dict:
    return yaml.safe_load(LOOP.read_text())["states"]


@pytest.fixture
def project(tmp_path: Path) -> Path:
    for kind in ("bugs", "features", "enhancements", "epics"):
        (tmp_path / ".issues" / kind).mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write_issue(
    project: Path,
    issue_id: str,
    *,
    frontmatter: str = "",
    body: str = "## Summary\n\nPlain.\n",
) -> Path:
    path = project / ".issues" / "enhancements" / f"P3-{issue_id}-test.md"
    path.write_text(
        f"---\nid: {issue_id}\ntitle: T\ntype: enhancement\nstatus: open\npriority: P3\n"
        f"{frontmatter}---\n\n# {issue_id}: T\n\n{body}"
    )
    return path


def _write_run(
    project: Path,
    *args: str,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [*_cli(), "run-record", "write", *args],
        cwd=str(project),
        capture_output=True,
        text=True,
        timeout=60,
    )


def _read_json(run_dir: Path, writer: str, issue_id: str) -> dict:
    return json.loads((run_dir / "run-records" / writer / f"{issue_id}.json").read_text())


def _sub(action: str, run_dir: Path, issue_id: str) -> str:
    """Interpolate a state action the way the test harnesses do (token rewrite)."""
    replacements = {
        "${context.run_dir:shell}": f"'{run_dir}'",
        "${context.run_dir}": str(run_dir),
        "${captured.issue_id.output:shell}": f"'{issue_id}'",
        "${captured.issue_id.output?}": issue_id,
        "${captured.issue_id.output}": issue_id,
        "${context.outcome_threshold:shell}": "65",
        "${context.readiness_threshold:shell}": "85",
        "${context.input:shell}": f"'{issue_id}'",
    }
    for token, value in replacements.items():
        action = action.replace(token, value)
    # Emulate the FSM interpolator's escaped-brace restoration so `$${VAR}`
    # written in the YAML reaches bash as the intended `${VAR}`.
    return action.replace("$${", "${")


def _run_state(
    project: Path, states: dict, state: str, run_dir: Path, issue_id: str
) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if _ll_issues_dir():
        env["PATH"] = f"{_ll_issues_dir()}:{env['PATH']}"
    return subprocess.run(
        ["bash", "-c", _sub(states[state]["action"], run_dir, issue_id)],
        cwd=str(project),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


# ---------------------------------------------------------------------------
# Record schema / round-trip
# ---------------------------------------------------------------------------


class TestRunRecordRoundTrip:
    def test_round_trip(self, tmp_path: Path) -> None:
        mod = _record_mod()
        record = mod.RunRecord(
            writer="refine-to-ready-issue",
            issue_id="ENH-3597",
            outcome="deferred",
            child_ids=("ENH-1", "ENH-2"),
            evidence_refs=("refine-failure-evidence.txt",),
            legacy_class="gate_unmet",
            readiness=42,
            outcome_confidence=17,
        )
        path = mod.write_run_record(tmp_path, record)
        assert path == tmp_path / "run-records" / "refine-to-ready-issue" / "ENH-3597.json"
        back = mod.read_run_record(tmp_path, "refine-to-ready-issue", "ENH-3597")
        assert back == record

    def test_json_shape(self, tmp_path: Path) -> None:
        mod = _record_mod()
        mod.write_run_record(
            tmp_path,
            mod.RunRecord(writer="refine-to-ready-issue", issue_id="BUG-1", outcome="blocked"),
        )
        data = _read_json(tmp_path, "refine-to-ready-issue", "BUG-1")
        assert set(data) == RECORD_KEYS
        assert data["outcome"] == "blocked"
        assert data["child_ids"] == []
        assert data["evidence_refs"] == []
        assert data["legacy_class"] is None
        assert data["readiness"] is None
        assert data["outcome_confidence"] is None

    def test_read_absent_returns_none(self, tmp_path: Path) -> None:
        assert _record_mod().read_run_record(tmp_path, "refine-to-ready-issue", "ENH-1") is None

    def test_read_malformed_returns_none(self, tmp_path: Path) -> None:
        target = tmp_path / "run-records" / "refine-to-ready-issue" / "ENH-1.json"
        target.parent.mkdir(parents=True)
        target.write_text("{not json")
        assert _record_mod().read_run_record(tmp_path, "refine-to-ready-issue", "ENH-1") is None

    def test_read_writer_mismatch_returns_none(self, tmp_path: Path) -> None:
        mod = _record_mod()
        mod.write_run_record(
            tmp_path,
            mod.RunRecord(writer="refine-to-ready-issue", issue_id="ENH-1", outcome="ready"),
        )
        assert mod.read_run_record(tmp_path, "prepare-issue", "ENH-1") is None

    def test_read_issue_mismatch_returns_none(self, tmp_path: Path) -> None:
        mod = _record_mod()
        mod.write_run_record(
            tmp_path,
            mod.RunRecord(writer="refine-to-ready-issue", issue_id="ENH-1", outcome="ready"),
        )
        assert mod.read_run_record(tmp_path, "refine-to-ready-issue", "ENH-2") is None

    def test_prepare_issue_writer_accepted(self, tmp_path: Path) -> None:
        """AC4: the schema and writer accept writer=prepare-issue (ENH-3601)."""
        mod = _record_mod()
        record = mod.RunRecord(writer="prepare-issue", issue_id="ENH-2", outcome="ready")
        path = mod.write_run_record(tmp_path, record)
        assert path == tmp_path / "run-records" / "prepare-issue" / "ENH-2.json"
        assert mod.read_run_record(tmp_path, "prepare-issue", "ENH-2") == record


# ---------------------------------------------------------------------------
# outcome_from_legacy_class mapping (issue Proposed Solution, first match wins)
# ---------------------------------------------------------------------------


class TestOutcomeMapping:
    CASES = [
        # (legacy_class, broke_down, thresholds_met, status, expected)
        ("gate_unmet", False, True, "open", "deferred"),
        ("spike_inconclusive", False, True, "open", "deferred"),
        ("infra", False, True, "open", "retryable_error"),
        ("decision_unresolved", False, True, "open", "blocked"),
        ("proposal_unsound", False, True, "open", "blocked"),
        ("quality", False, True, "open", "blocked"),
        (None, False, True, "open", "ready"),
        (None, False, False, "open", "blocked"),
        (None, True, True, "open", "decomposed"),  # rule 2 beats rule 6
        ("infra", True, True, "open", "decomposed"),  # rule 2 beats rule 3
        ("gate_unmet", False, True, "cancelled", "cancelled"),  # rule 1 beats rule 5
        (None, False, True, "Cancelled", "cancelled"),  # status normalized
        (None, False, True, None, "ready"),
    ]

    @pytest.mark.parametrize("legacy,broke,thr,status,expected", CASES)
    def test_mapping(
        self, legacy: str | None, broke: bool, thr: bool, status: str | None, expected: str
    ) -> None:
        assert _record_mod().outcome_from_legacy_class(legacy, broke, thr, status) == expected


# ---------------------------------------------------------------------------
# Two issues in one shared run_dir never cross-read (AC3)
# ---------------------------------------------------------------------------


class TestTwoIssueIsolation:
    def test_shared_run_dir_isolation(self, tmp_path: Path) -> None:
        mod = _record_mod()
        mod.write_run_record(
            tmp_path,
            mod.RunRecord(writer="refine-to-ready-issue", issue_id="ENH-A", outcome="blocked"),
        )
        mod.write_run_record(
            tmp_path,
            mod.RunRecord(writer="refine-to-ready-issue", issue_id="ENH-B", outcome="ready"),
        )
        a = mod.read_run_record(tmp_path, "refine-to-ready-issue", "ENH-A")
        b = mod.read_run_record(tmp_path, "refine-to-ready-issue", "ENH-B")
        assert a is not None and a.outcome == "blocked" and a.issue_id == "ENH-A"
        assert b is not None and b.outcome == "ready" and b.issue_id == "ENH-B"
        # A fresh re-run of ENH-A that never reaches a terminal leaves no
        # readable stale record only if the entry deletion ran; simulate it.
        (tmp_path / "run-records" / "refine-to-ready-issue" / "ENH-A.json").unlink()
        assert mod.read_run_record(tmp_path, "refine-to-ready-issue", "ENH-A") is None


# ---------------------------------------------------------------------------
# CLI: ll-issues run-record write against a real tmp project
# ---------------------------------------------------------------------------

ID = "ENH-9701"


class TestCmdRunRecordWrite:
    def test_ready_issue(self, project: Path, tmp_path: Path) -> None:
        _write_issue(project, ID, frontmatter="confidence_score: 90\noutcome_confidence: 70\n")
        result = _write_run(
            project, ID, "--run-dir", str(tmp_path), "--writer", "refine-to-ready-issue"
        )
        assert result.returncode == 0, result.stderr
        data = _read_json(tmp_path, "refine-to-ready-issue", ID)
        assert data["outcome"] == "ready"
        assert data["readiness"] == 90
        assert data["outcome_confidence"] == 70
        assert data["legacy_class"] is None
        assert f"[RUN_RECORD_WRITTEN] {ID} ready" in result.stdout

    def test_below_threshold_is_blocked(self, project: Path, tmp_path: Path) -> None:
        _write_issue(project, ID, frontmatter="confidence_score: 90\noutcome_confidence: 10\n")
        result = _write_run(
            project, ID, "--run-dir", str(tmp_path), "--writer", "refine-to-ready-issue"
        )
        assert result.returncode == 0, result.stderr
        assert _read_json(tmp_path, "refine-to-ready-issue", ID)["outcome"] == "blocked"

    def test_scores_absent_is_blocked_not_ready(self, project: Path, tmp_path: Path) -> None:
        """AC2: scores absent (check-readiness exit 3) is not a pass."""
        _write_issue(project, ID)
        result = _write_run(
            project, ID, "--run-dir", str(tmp_path), "--writer", "refine-to-ready-issue"
        )
        assert result.returncode == 0, result.stderr
        data = _read_json(tmp_path, "refine-to-ready-issue", ID)
        assert data["outcome"] == "blocked"
        assert data["readiness"] is None and data["outcome_confidence"] is None

    def test_waiver_honored(self, project: Path, tmp_path: Path) -> None:
        """AC2: the ready predicate is autodev check_passed's — waiver honored."""
        _write_issue(
            project,
            ID,
            frontmatter="confidence_score: 90\noutcome_confidence: 10\noutcome_gate_waived: true\n",
        )
        result = _write_run(
            project, ID, "--run-dir", str(tmp_path), "--writer", "refine-to-ready-issue"
        )
        assert result.returncode == 0, result.stderr
        assert _read_json(tmp_path, "refine-to-ready-issue", ID)["outcome"] == "ready"

    @pytest.mark.parametrize(
        "frontmatter,legacy,expected",
        [
            ("confidence_score: 90\noutcome_confidence: 70\n", "gate_unmet", "deferred"),
            ("confidence_score: 90\noutcome_confidence: 70\n", "infra", "retryable_error"),
            ("confidence_score: 90\noutcome_confidence: 70\n", "proposal_unsound", "blocked"),
            ("confidence_score: 90\noutcome_confidence: 70\n", "quality", "blocked"),
            ("confidence_score: 90\noutcome_confidence: 70\n", None, "ready"),
        ],
    )
    def test_legacy_class_mapping_via_cli(
        self, project: Path, tmp_path: Path, frontmatter: str, legacy: str | None, expected: str
    ) -> None:
        _write_issue(project, ID, frontmatter=frontmatter)
        args = [ID, "--run-dir", str(tmp_path), "--writer", "refine-to-ready-issue"]
        if legacy is not None:
            args += ["--legacy-class", legacy]
        result = _write_run(project, *args)
        assert result.returncode == 0, result.stderr
        data = _read_json(tmp_path, "refine-to-ready-issue", ID)
        assert data["outcome"] == expected
        assert data["legacy_class"] == legacy

    def test_cancelled_status_wins(self, project: Path, tmp_path: Path) -> None:
        _write_issue(
            project,
            ID,
            frontmatter="status: cancelled\nconfidence_score: 90\noutcome_confidence: 70\n",
        )
        result = _write_run(
            project,
            ID,
            "--run-dir",
            str(tmp_path),
            "--writer",
            "refine-to-ready-issue",
            "--legacy-class",
            "gate_unmet",
        )
        assert result.returncode == 0, result.stderr
        assert _read_json(tmp_path, "refine-to-ready-issue", ID)["outcome"] == "cancelled"

    def test_broke_down_flag_is_decomposed_and_children_derived(
        self, project: Path, tmp_path: Path
    ) -> None:
        parent = _write_issue(project, ID)
        parent.write_text(parent.read_text().replace("status: open", "status: done"))
        _write_issue(project, "ENH-9702", frontmatter=f"parent: {ID}\nstatus: open\n")
        _write_issue(project, "ENH-9703", frontmatter="parent: ENH-9999\nstatus: open\n")
        (tmp_path / "refine-broke-down").write_text("1")
        result = _write_run(
            project, ID, "--run-dir", str(tmp_path), "--writer", "refine-to-ready-issue"
        )
        assert result.returncode == 0, result.stderr
        data = _read_json(tmp_path, "refine-to-ready-issue", ID)
        assert data["outcome"] == "decomposed"
        assert data["child_ids"] == ["ENH-9702"]

    def test_explicit_child_ids_override_derivation(self, project: Path, tmp_path: Path) -> None:
        _write_issue(project, ID, frontmatter="confidence_score: 90\noutcome_confidence: 70\n")
        (tmp_path / "refine-broke-down").write_text("1")
        result = _write_run(
            project,
            ID,
            "--run-dir",
            str(tmp_path),
            "--writer",
            "refine-to-ready-issue",
            "--child-ids",
            "ENH-X",
            "ENH-Y",
        )
        assert result.returncode == 0, result.stderr
        assert _read_json(tmp_path, "refine-to-ready-issue", ID)["child_ids"] == ["ENH-X", "ENH-Y"]

    def test_evidence_refs_recorded(self, project: Path, tmp_path: Path) -> None:
        _write_issue(project, ID, frontmatter="confidence_score: 90\noutcome_confidence: 70\n")
        result = _write_run(
            project,
            ID,
            "--run-dir",
            str(tmp_path),
            "--writer",
            "refine-to-ready-issue",
            "--evidence-refs",
            "refine-failure-evidence.txt",
        )
        assert result.returncode == 0, result.stderr
        assert _read_json(tmp_path, "refine-to-ready-issue", ID)["evidence_refs"] == [
            "refine-failure-evidence.txt"
        ]

    def test_prepare_issue_writer_via_cli(self, project: Path, tmp_path: Path) -> None:
        """AC4: the CLI accepts writer=prepare-issue (ENH-3601's wrapper)."""
        _write_issue(project, ID, frontmatter="confidence_score: 90\noutcome_confidence: 70\n")
        result = _write_run(project, ID, "--run-dir", str(tmp_path), "--writer", "prepare-issue")
        assert result.returncode == 0, result.stderr
        assert _read_json(tmp_path, "prepare-issue", ID)["outcome"] == "ready"

    def test_unknown_issue_exits_2(self, project: Path, tmp_path: Path) -> None:
        result = _write_run(
            project, "ENH-4242", "--run-dir", str(tmp_path), "--writer", "refine-to-ready-issue"
        )
        assert result.returncode == 2
        assert not (tmp_path / "run-records").exists() or not list(
            (tmp_path / "run-records").rglob("*.json")
        )

    def test_subcommand_in_help(self, project: Path) -> None:
        result = subprocess.run(
            [*_cli(), "--help"], cwd=str(project), capture_output=True, text=True, timeout=30
        )
        assert "run-record" in result.stdout


class TestWriteTypedRunRecordHelper:
    """ENH-3630: direct in-process tests of the shared helper.

    ``cmd_run_record_write`` is a thin wrapper (see the class above); these
    call ``write_typed_run_record`` itself, the entry point ``prep apply``
    also uses, so both writers are pinned to one contract.
    """

    def _config(self, project: Path):
        from little_loops.config import BRConfig

        return BRConfig(project)

    def test_unresolved_issue_returns_none(self, project: Path, tmp_path: Path) -> None:
        from little_loops.cli.issues.run_record import write_typed_run_record

        record = write_typed_run_record(
            self._config(project), "ENH-4242", tmp_path, "refine-to-ready-issue"
        )
        assert record is None

    def test_ready_matches_cli(self, project: Path, tmp_path: Path) -> None:
        from little_loops.cli.issues.run_record import write_typed_run_record

        _write_issue(project, ID, frontmatter="confidence_score: 90\noutcome_confidence: 70\n")
        record = write_typed_run_record(
            self._config(project), ID, tmp_path, "refine-to-ready-issue"
        )
        assert record is not None
        assert record.outcome == "ready"
        assert record.readiness == 90
        assert record.outcome_confidence == 70
        assert _read_json(tmp_path, "refine-to-ready-issue", ID)["outcome"] == "ready"

    def test_broke_down_param_drives_decomposed_without_the_file(
        self, project: Path, tmp_path: Path
    ) -> None:
        """The helper takes ``broke_down`` as an in-process value (Program Design)."""
        from little_loops.cli.issues.run_record import write_typed_run_record

        parent = _write_issue(project, ID)
        parent.write_text(parent.read_text().replace("status: open", "status: done"))
        _write_issue(project, "ENH-9702", frontmatter=f"parent: {ID}\nstatus: open\n")
        record = write_typed_run_record(
            self._config(project),
            ID,
            tmp_path,
            "refine-to-ready-issue",
            broke_down=True,
        )
        assert record is not None
        assert record.outcome == "decomposed"
        assert record.child_ids == ("ENH-9702",)
        assert not (tmp_path / "refine-broke-down").exists()

    @pytest.mark.parametrize(
        "frontmatter,legacy",
        [
            ("confidence_score: 90\noutcome_confidence: 70\n", None),
            ("confidence_score: 90\noutcome_confidence: 10\n", None),
            ("confidence_score: 60\noutcome_confidence: 70\n", None),
            ("confidence_score: 90\noutcome_confidence: 10\noutcome_gate_waived: true\n", None),
            ("confidence_score: 90\noutcome_confidence: 70\n", "gate_unmet"),
            ("", None),
        ],
    )
    def test_ready_iff_check_passed_would_pass(
        self, project: Path, tmp_path: Path, frontmatter: str, legacy: str | None
    ) -> None:
        """AC2: outcome == ready iff `check-readiness --honor-waiver` and `check-design` exit 0."""
        _write_issue(project, ID, frontmatter=frontmatter)
        check = subprocess.run(
            [*_cli(), "check-readiness", ID, "--honor-waiver"],
            cwd=str(project),
            capture_output=True,
            text=True,
            timeout=30,
        )
        design = subprocess.run(
            [*_cli(), "check-design", ID],
            cwd=str(project),
            capture_output=True,
            text=True,
            timeout=30,
        )
        args = [ID, "--run-dir", str(tmp_path), "--writer", "refine-to-ready-issue"]
        if legacy is not None:
            args += ["--legacy-class", legacy]
        result = _write_run(project, *args)
        assert result.returncode == 0, result.stderr
        outcome = _read_json(tmp_path, "refine-to-ready-issue", ID)["outcome"]
        if legacy is not None:
            assert outcome != "ready"  # classed exits are never ready
        else:
            passes = check.returncode == 0 and design.returncode == 0
            assert (outcome == "ready") == passes, (
                f"outcome={outcome} but check-readiness exit={check.returncode}, "
                f"check-design exit={design.returncode}"
            )

    def test_design_gate_failure_makes_done_record_blocked(
        self, project: Path, tmp_path: Path
    ) -> None:
        """ENH-3625: READY scores but a failing Program Design gate → BLOCKED."""
        (project / ".ll").mkdir(exist_ok=True)
        (project / ".ll" / "program-design-cutover.json").write_text('{"date": "2000-01-01"}')
        _write_issue(project, ID, frontmatter="confidence_score: 90\noutcome_confidence: 70\n")
        check = subprocess.run(
            [*_cli(), "check-design", ID],
            cwd=str(project),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert check.returncode == 1
        result = _write_run(
            project, ID, "--run-dir", str(tmp_path), "--writer", "refine-to-ready-issue"
        )
        assert result.returncode == 0, result.stderr
        assert _read_json(tmp_path, "refine-to-ready-issue", ID)["outcome"] == "blocked"


# ---------------------------------------------------------------------------
# Loop wiring: every terminal-bearing state calls the writer (AC1)
# ---------------------------------------------------------------------------


class TestLoopCallSites:
    @pytest.mark.parametrize("state", TERMINAL_BEARING_STATES)
    def test_state_writes_record(self, loop_states: dict, state: str) -> None:
        assert "run-record write" in loop_states[state].get("action", ""), state

    @pytest.mark.parametrize(
        "state,legacy",
        sorted(LEGACY_CLASS_STATES.items()),
    )
    def test_record_state_passes_its_legacy_class(
        self, loop_states: dict, state: str, legacy: str
    ) -> None:
        assert f"--legacy-class {legacy}" in loop_states[state]["action"], state

    def test_classify_terminal_passes_class_var(self, loop_states: dict) -> None:
        assert '--legacy-class "$CLASS"' in loop_states["classify_terminal"]["action"]

    @pytest.mark.parametrize("gate", DONE_PATH_GATES)
    def test_done_path_gate_writes_no_record(self, loop_states: dict, gate: str) -> None:
        """ENH-3610: the gate only routes; check_decision_before_done → write_done_record
        writes the record, so a record exists only when `done` is really next."""
        assert "run-record write" not in loop_states[gate]["action"], gate
        assert loop_states[gate]["on_yes"] == "check_decision_before_done"

    def test_write_broke_down_has_no_legacy_class(self, loop_states: dict) -> None:
        action = loop_states["write_broke_down"]["action"]
        assert "run-record write" in action
        assert "--legacy-class" not in action

    def test_resolve_issue_deletes_writer_record_on_entry(self, loop_states: dict) -> None:
        action = loop_states["resolve_issue"]["action"]
        # ENH-3607: canonical-ID clear replaces the raw-ID rm -f.
        assert (
            'run-record clear "$${ID}" --run-dir ${context.run_dir} --writer refine-to-ready-issue'
        ) in action
        assert "run-records/refine-to-ready-issue/$${ID}.json" not in action
        # BUG-3593 pin: the spike-runs counter must stay untouched.
        assert "spike" not in action
        # The deletion must key on the ID this run resolved, computed in-shell.
        assert "ID=$(" in action

    def test_no_work_writes_no_record(self, loop_states: dict) -> None:
        assert "run-record" not in loop_states["no_work"].get("action", "")
        assert "run-record" not in loop_states["check_issue_resolved"]["action"]

    def test_every_write_names_the_writer_and_run_dir(self) -> None:
        text = LOOP.read_text()
        for i, line in enumerate(text.splitlines()):
            if "run-record write" in line and "rm -f" not in line:
                window = "\n".join(text.splitlines()[i : i + 3])
                assert "--run-dir ${context.run_dir}" in window, line
                assert "--writer refine-to-ready-issue" in window, line

    def test_no_new_terminal_states_or_routing(self, loop_states: dict) -> None:
        """Additive only: terminal set and failure flag unchanged."""
        assert loop_states["done"] == {"terminal": True}
        assert loop_states["no_work"] == {"terminal": True}
        assert loop_states["failed"]["terminal"] is True
        assert loop_states["failed"]["failure"] is True


# ---------------------------------------------------------------------------
# Real state actions under bash with the real ll-issues (per-terminal outcome)
# ---------------------------------------------------------------------------


class TestTerminalExecution:
    def test_record_gate_unmet(self, project: Path, tmp_path: Path, loop_states: dict) -> None:
        _write_issue(project, ID, frontmatter="confidence_score: 90\noutcome_confidence: 70\n")
        result = _run_state(project, loop_states, "record_gate_unmet", tmp_path, ID)
        assert result.returncode == 0, result.stderr
        # ENH-3600: no refine-terminal-class sentinel — the record alone carries it.
        assert not (tmp_path / "refine-terminal-class").exists()
        data = _read_json(tmp_path, "refine-to-ready-issue", ID)
        assert data["outcome"] == "deferred"
        assert data["legacy_class"] == "gate_unmet"

    def test_mark_rate_limit_infra(self, project: Path, tmp_path: Path, loop_states: dict) -> None:
        _write_issue(project, ID)
        result = _run_state(project, loop_states, "mark_rate_limit_infra", tmp_path, ID)
        assert result.returncode == 0, result.stderr
        assert not (tmp_path / "refine-terminal-class").exists()
        data = _read_json(tmp_path, "refine-to-ready-issue", ID)
        assert data["outcome"] == "retryable_error"

    def test_write_broke_down(self, project: Path, tmp_path: Path, loop_states: dict) -> None:
        _write_issue(project, ID)
        result = _run_state(project, loop_states, "write_broke_down", tmp_path, ID)
        assert result.returncode == 0, result.stderr
        assert (tmp_path / "refine-broke-down").read_text() == "1"
        assert _read_json(tmp_path, "refine-to-ready-issue", ID)["outcome"] == "decomposed"

    def test_write_done_record_writes_ready(
        self, project: Path, tmp_path: Path, loop_states: dict
    ) -> None:
        # ENH-3610: the no-class record is written by write_done_record, which the
        # done-bound gates reach through check_decision_before_done.
        _write_issue(project, ID, frontmatter="confidence_score: 90\noutcome_confidence: 70\n")
        result = _run_state(project, loop_states, "write_done_record", tmp_path, ID)
        assert result.returncode == 0, result.stderr
        assert _read_json(tmp_path, "refine-to-ready-issue", ID)["outcome"] == "ready"

    def test_check_missing_artifacts_pass_writes_no_record(
        self, project: Path, tmp_path: Path, loop_states: dict
    ) -> None:
        # check-flag exits 0 when the flag IS true — the done-bound exit; the record
        # is deferred to write_done_record (ENH-3610).
        _write_issue(
            project,
            ID,
            frontmatter="confidence_score: 90\noutcome_confidence: 70\nmissing_artifacts: true\n",
        )
        result = _run_state(project, loop_states, "check_missing_artifacts", tmp_path, ID)
        assert result.returncode == 0, result.stderr
        assert not (tmp_path / "run-records").exists() or not list(
            (tmp_path / "run-records").rglob("*.json")
        )

    def test_check_missing_artifacts_fail_writes_no_record(
        self, project: Path, tmp_path: Path, loop_states: dict
    ) -> None:
        """The write rides only the done-bound exit (exit 1 routes on)."""
        _write_issue(
            project,
            ID,
            frontmatter="confidence_score: 90\noutcome_confidence: 70\nmissing_artifacts: false\n",
        )
        result = _run_state(project, loop_states, "check_missing_artifacts", tmp_path, ID)
        assert result.returncode == 1
        assert not (tmp_path / "run-records").exists() or not list(
            (tmp_path / "run-records").rglob("*.json")
        )

    def test_classify_terminal_quality_is_blocked(
        self, project: Path, tmp_path: Path, loop_states: dict
    ) -> None:
        _write_issue(project, ID)
        action = loop_states["classify_terminal"]["action"]
        script = (
            re.sub(
                r"\$\{captured\.([A-Za-z0-9_.]+?)\??\}",
                lambda m: ID if m.group(1) == "issue_id.output" else "",
                action,
            )
            .replace("${context.run_dir}", str(tmp_path))
            .replace("$${", "${")
        )
        env = dict(os.environ)
        if _ll_issues_dir():
            env["PATH"] = f"{_ll_issues_dir()}:{env['PATH']}"
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=str(project),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert not (tmp_path / "refine-terminal-class").exists()
        data = _read_json(tmp_path, "refine-to-ready-issue", ID)
        assert data["outcome"] == "blocked"
        assert data["legacy_class"] == "quality"

    def test_two_issues_one_run_dir_via_states(
        self, project: Path, tmp_path: Path, loop_states: dict
    ) -> None:
        """AC3, real-FSM idiom: A's record never reads as B's."""
        _write_issue(project, "ENH-9701")
        _write_issue(project, "ENH-9702")
        for issue in ("ENH-9701", "ENH-9702"):
            result = _run_state(project, loop_states, "mark_rate_limit_infra", tmp_path, issue)
            assert result.returncode == 0, result.stderr
        mod = _record_mod()
        a = mod.read_run_record(tmp_path, "refine-to-ready-issue", "ENH-9701")
        b = mod.read_run_record(tmp_path, "refine-to-ready-issue", "ENH-9702")
        assert a is not None and a.issue_id == "ENH-9701"
        assert b is not None and b.issue_id == "ENH-9702"

    def test_resolve_issue_deletes_stale_record(
        self, project: Path, tmp_path: Path, loop_states: dict
    ) -> None:
        _write_issue(project, ID)
        stale = tmp_path / "run-records" / "refine-to-ready-issue" / f"{ID}.json"
        stale.parent.mkdir(parents=True)
        stale.write_text('{"writer": "refine-to-ready-issue"}')
        result = _run_state(project, loop_states, "resolve_issue", tmp_path, ID)
        assert result.returncode == 0, result.stderr
        assert result.stdout == ID
        assert not stale.exists()
        # Legacy counters still seeded byte-identically.
        assert (tmp_path / "refine-broke-down").read_text() == "0"


# ---------------------------------------------------------------------------
# Mirror: .claude/workflows/refine-to-ready.js Finalize phase (AC7)
# ---------------------------------------------------------------------------


class TestMirror:
    @pytest.mark.skipif(not MIRROR.exists(), reason="machine-local workflow mirror absent")
    def test_finalize_phase_writes_run_record(self) -> None:
        text = MIRROR.read_text()
        finalize_at = text.index("Finalize")
        write_at = text.index("run-record write")
        assert write_at > finalize_at


# ---------------------------------------------------------------------------
# ENH-3607: read/clear path, token vocabulary, threshold pass-through
# ---------------------------------------------------------------------------

NO_CLASS_WRITE_STATES = (
    "write_done_record",
    "write_broke_down",
)


def _run_sub(project: Path, sub: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [*_cli(), "run-record", sub, *args],
        cwd=str(project),
        capture_output=True,
        text=True,
        timeout=60,
    )


def _rec(**kw):
    rr = _record_mod()
    base = {"writer": "refine-to-ready-issue", "issue_id": ID, "outcome": "ready"}
    base.update(kw)
    return rr.RunRecord(**base)


class TestRecordToken:
    @pytest.mark.parametrize(
        "kw,token",
        [
            ({"outcome": "ready"}, "READY"),
            ({"outcome": "blocked"}, "BLOCKED"),
            (
                {"outcome": "blocked", "legacy_class": "decision_unresolved"},
                "BLOCKED:decision_unresolved",
            ),
            (
                {"outcome": "blocked", "legacy_class": "proposal_unsound"},
                "BLOCKED:proposal_unsound",
            ),
            ({"outcome": "blocked", "legacy_class": "quality"}, "BLOCKED:quality"),
            (
                {"outcome": "deferred", "legacy_class": "spike_inconclusive"},
                "DEFERRED:spike_inconclusive",
            ),
            ({"outcome": "deferred", "legacy_class": "gate_unmet"}, "DEFERRED:gate_unmet"),
            (
                {
                    "outcome": "retryable_error",
                    "legacy_class": "infra",
                    "evidence_refs": ("rate_limit_exhausted",),
                },
                "RETRYABLE_ERROR:rate_limited",
            ),
            ({"outcome": "retryable_error", "legacy_class": "infra"}, "RETRYABLE_ERROR:infra"),
            ({"outcome": "decomposed", "legacy_class": "quality"}, "DECOMPOSED"),
            ({"outcome": "cancelled", "legacy_class": "quality"}, "CANCELLED"),
        ],
    )
    def test_mapping(self, kw: dict, token: str) -> None:
        rr = _record_mod()
        assert rr.record_token(_rec(**kw)) == token
        assert token in rr.RUN_RECORD_TOKENS

    def test_none_is_missing_and_vocabulary_is_covered(self) -> None:
        rr = _record_mod()
        assert rr.record_token(None) == "MISSING"
        assert len(rr.RUN_RECORD_TOKENS) == 12
        assert len(set(rr.RUN_RECORD_TOKENS)) == 12

    def test_unknown_class_never_reads_ready(self) -> None:
        rr = _record_mod()
        assert rr.record_token(_rec(outcome="blocked", legacy_class="bogus")) == "MISSING"


class TestRunRecordReadClear:
    def test_missing_cases(self, project: Path, tmp_path: Path) -> None:
        _write_issue(project, ID)
        base = ("--run-dir", str(tmp_path), "--writer", "refine-to-ready-issue")
        r = _run_sub(project, "read", ID, *base)
        assert r.returncode == 0 and r.stdout.strip() == "MISSING"
        r = _run_sub(project, "read", "ENH-9999999", *base)  # unresolvable
        assert r.returncode == 0 and r.stdout.strip() == "MISSING"
        d = tmp_path / "run-records" / "refine-to-ready-issue"
        d.mkdir(parents=True)
        (d / f"{ID}.json").write_text("{not json")
        assert _run_sub(project, "read", ID, *base).stdout.strip() == "MISSING"
        # writer mismatch and ID mismatch inside the file
        (d / f"{ID}.json").write_text(json.dumps(_rec(writer="prepare-issue").to_dict()))
        assert _run_sub(project, "read", ID, *base).stdout.strip() == "MISSING"
        (d / f"{ID}.json").write_text(json.dumps(_rec(issue_id="ENH-1").to_dict()))
        assert _run_sub(project, "read", ID, *base).stdout.strip() == "MISSING"

    def test_reads_back_via_any_id_form_and_clear(self, project: Path, tmp_path: Path) -> None:
        _write_issue(project, ID, frontmatter="confidence_score: 90\noutcome_confidence: 70\n")
        base = ("--run-dir", str(tmp_path), "--writer", "refine-to-ready-issue")
        num = re.search(r"\d+", ID).group(0)
        assert _write_run(project, num, *base).returncode == 0
        for form in (num, ID, f"P3-{ID}"):
            r = _run_sub(project, "read", form, *base, "--format", "token")
            assert r.returncode == 0 and r.stdout.strip() == "READY", form
        record = tmp_path / "run-records" / "refine-to-ready-issue" / f"{ID}.json"
        assert record.exists()
        assert _run_sub(project, "clear", num, *base).returncode == 0
        assert not record.exists()
        assert _run_sub(project, "clear", num, *base).returncode == 0  # absent -> still 0

    def test_rate_limited_record_reads_rate_limited(self, project: Path, tmp_path: Path) -> None:
        _write_issue(project, ID)
        base = ("--run-dir", str(tmp_path), "--writer", "refine-to-ready-issue")
        assert (
            _write_run(
                project,
                ID,
                *base,
                "--legacy-class",
                "infra",
                "--evidence-refs",
                "rate_limit_exhausted",
            ).returncode
            == 0
        )
        assert _run_sub(project, "read", ID, *base).stdout.strip() == "RETRYABLE_ERROR:rate_limited"


class TestEnh3607LoopWiring:
    @pytest.mark.parametrize("state", NO_CLASS_WRITE_STATES)
    def test_no_class_writes_pass_thresholds(self, loop_states: dict, state: str) -> None:
        action = loop_states[state]["action"]
        assert "--readiness-threshold ${context.readiness_threshold:shell}" in action, state
        assert "--outcome-threshold ${context.outcome_threshold:shell}" in action, state

    def test_run_spike_waits_out_rate_limits(self, loop_states: dict) -> None:
        st = loop_states["run_spike"]
        assert st["fragment"] == "with_rate_limit_handling"
        assert st["rate_limit_max_wait_seconds"] == 14400
        assert st["on_rate_limit_exhausted"] == "mark_rate_limit_infra"

    def test_mark_rate_limit_infra_records_evidence(self, loop_states: dict) -> None:
        action = loop_states["mark_rate_limit_infra"]["action"]
        assert "--legacy-class infra" in action
        assert "--evidence-refs rate_limit_exhausted" in action

    def test_mark_rate_limit_infra_record_reads_rate_limited(
        self, project: Path, tmp_path: Path, loop_states: dict
    ) -> None:
        _write_issue(project, ID)
        r = _run_state(project, loop_states, "mark_rate_limit_infra", tmp_path, ID)
        assert r.returncode == 0, r.stderr
        out = _run_sub(
            project, "read", ID, "--run-dir", str(tmp_path), "--writer", "refine-to-ready-issue"
        )
        assert out.stdout.strip() == "RETRYABLE_ERROR:rate_limited"

    def test_autodev_routes_only_rate_limited_to_finalize(self) -> None:
        autodev = yaml.safe_load((LOOP.parent / "autodev.yaml").read_text())["states"]
        assert autodev["refine_current"]["on_failure"] == "route_refine_outcome"
        assert "on_no" not in autodev["refine_current"]
        st = autodev["route_refine_outcome"]
        assert st["evaluate"]["type"] == "classify"
        assert st["route"]["RETRYABLE_ERROR:rate_limited"] == "finalize_rate_limited"
        assert st["route"]["_"] == "skip_inflight"
        assert st["route"]["_error"] == "skip_inflight"
        assert "run-record read ${captured.input.output:shell}" in st["action"]


class TestRunRecordForward:
    """ENH-3605: ``run-record forward`` re-writes one writer's record under another."""

    BASE = ("--from", "refine-to-ready-issue", "--writer", "prepare-issue")

    def test_forwards_record_and_prints_token(self, project: Path, tmp_path: Path) -> None:
        _write_issue(project, ID)
        inner = _rec(
            outcome="blocked",
            legacy_class="quality",
            child_ids=("ENH-1", "ENH-2"),
            evidence_refs=("x",),
            readiness=80,
            outcome_confidence=60,
        )
        rr = _record_mod()
        rr.write_run_record(tmp_path, inner)
        r = _run_sub(project, "forward", ID, "--run-dir", str(tmp_path), *self.BASE)
        assert r.returncode == 0 and r.stdout.strip() == "BLOCKED:quality"
        out = _read_json(tmp_path, "prepare-issue", ID)
        expected = inner.to_dict() | {"writer": "prepare-issue"}
        assert out == expected
        # the forwarded record is accepted by `read --writer prepare-issue`
        r = _run_sub(project, "read", ID, "--run-dir", str(tmp_path), "--writer", "prepare-issue")
        assert r.stdout.strip() == "BLOCKED:quality"

    def test_rate_limit_evidence_survives(self, project: Path, tmp_path: Path) -> None:
        _write_issue(project, ID)
        rr = _record_mod()
        rr.write_run_record(
            tmp_path,
            _rec(
                outcome="retryable_error",
                legacy_class="infra",
                evidence_refs=("rate_limit_exhausted",),
            ),
        )
        r = _run_sub(project, "forward", ID, "--run-dir", str(tmp_path), *self.BASE)
        assert r.stdout.strip() == "RETRYABLE_ERROR:rate_limited"

    def test_missing_source_prints_missing_and_writes_nothing(
        self, project: Path, tmp_path: Path
    ) -> None:
        _write_issue(project, ID)
        r = _run_sub(project, "forward", ID, "--run-dir", str(tmp_path), *self.BASE)
        assert r.returncode == 0 and r.stdout.strip() == "MISSING"
        assert not (tmp_path / "run-records" / "prepare-issue").exists()

    def test_canonical_id_resolution(self, project: Path, tmp_path: Path) -> None:
        _write_issue(project, ID)
        rr = _record_mod()
        rr.write_run_record(tmp_path, _rec(outcome="ready"))
        num = re.search(r"\d+", ID).group(0)
        r = _run_sub(project, "forward", num, "--run-dir", str(tmp_path), *self.BASE)
        assert r.stdout.strip() == "READY"
        assert (tmp_path / "run-records" / "prepare-issue" / f"{ID}.json").exists()
