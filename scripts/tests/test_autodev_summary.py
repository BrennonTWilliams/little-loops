"""Tests for ``little_loops.autodev_summary`` (autodev run finalization).

The parity tests replay golden fixtures recorded from the shell action autodev's
``finalize_done`` state carried before the extraction
(``fixtures/autodev_summary/_generate.py``): each scenario's issue statuses are
materialised as real issue files, so status resolution runs through the same
frontmatter/resolver path ``ll-issues show`` used.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from little_loops import autodev_summary as ads

FIXTURES = Path(__file__).parent / "fixtures" / "autodev_summary"
SCRIPTS_DIR = Path(__file__).parent.parent
SCENARIOS = sorted(p.name for p in FIXTURES.iterdir() if (p / "scenario.json").is_file())


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_autodev_fixture_gen", FIXTURES / "_generate.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GEN = _load_generator()


def _setup(tmp_path: Path, scenario: str) -> tuple[Path, Path, dict]:
    """Build the scenario's project + run dir; return (project, run_dir, scenario.json)."""
    meta = json.loads((FIXTURES / scenario / "scenario.json").read_text())
    project = GEN.make_project(tmp_path, meta["statuses"])
    run_dir = project / "run"
    inputs = FIXTURES / scenario / "inputs"
    # git does not track empty directories, so a scenario with no run-dir
    # inputs (e.g. no_op_empty_*) has no inputs/ dir in a fresh checkout.
    if inputs.is_dir():
        shutil.copytree(inputs, run_dir)
    else:
        run_dir.mkdir(parents=True)
    return project, run_dir, meta


def _ledgers(run_dir: Path) -> dict[str, str | None]:
    return {
        name: (run_dir / name).read_text() if (run_dir / name).exists() else None
        for name in (ads.PASSED, ads.UNVERIFIED)
    }


def _stub(statuses: dict[str, str]) -> ads.StatusResolver:
    return lambda issue_id: statuses.get(issue_id, "")


# ------------------------------------------------------------------ parity


def test_fixture_set_is_populated() -> None:
    assert len(SCENARIOS) >= 30
    assert set(SCENARIOS) == set(GEN.SCENARIOS)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_matches_legacy_shell_action(
    scenario: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsysbinary: pytest.CaptureFixture[bytes],
) -> None:
    """summary.json bytes, stdout, exit code and ledger side effects all match."""
    project, run_dir, meta = _setup(tmp_path, scenario)
    expected = FIXTURES / scenario
    monkeypatch.chdir(project)  # statuses resolve from cwd, like `ll-issues show`
    code = ads.main(["--run-dir", str(run_dir), "--quality-gate", meta["quality_gate"]])
    out = capsysbinary.readouterr().out.decode("utf-8")

    summary_text = (run_dir / "summary.json").read_text()
    assert summary_text == (expected / "expected_summary.json").read_text()
    summary = json.loads(summary_text)
    assert list(summary) == list(ads.AutodevSummary.KEYS)
    assert out == (expected / "expected_stdout.txt").read_text()
    assert code == int((expected / "expected_exit").read_text())
    assert _ledgers(run_dir) == json.loads((expected / "expected_ledgers.json").read_text())


def test_cli_module_entry_point(tmp_path: Path) -> None:
    """`python3 -m little_loops.autodev_summary` works from the project root."""
    project, run_dir, meta = _setup(tmp_path, "quality_failed_not_promoted")
    env = {**os.environ, "PYTHONPATH": str(SCRIPTS_DIR)}
    result = subprocess.run(
        [sys.executable, "-m", "little_loops.autodev_summary", "--run-dir", str(run_dir)],
        cwd=project,
        capture_output=True,
        text=True,
        env=env,
    )
    expected = FIXTURES / "quality_failed_not_promoted"
    assert result.returncode == 0, result.stderr
    assert result.stdout == (expected / "expected_stdout.txt").read_text()
    assert (run_dir / "summary.json").read_text() == (
        expected / "expected_summary.json"
    ).read_text()


# ------------------------------------------------------- verdict / exit code


@pytest.mark.parametrize(
    ("staged", "statuses", "extra", "verdict", "code"),
    [
        ("FEAT-1\n", {"FEAT-1": "done"}, {}, "success", ads.EXIT_OK),
        ("FEAT-1\nFEAT-2\n", {"FEAT-1": "done", "FEAT-2": "open"}, {}, "partial", ads.EXIT_OK),
        ("FEAT-1\n", {"FEAT-1": "open"}, {}, "phantom", ads.EXIT_PHANTOM),
        ("", {}, {ads.NOT_STARTED: "FEAT-9  x\n"}, "not_started", ads.EXIT_OK),
        ("", {}, {}, "no-op", ads.EXIT_OK),
        ("FEAT-1\n", {"FEAT-1": "open"}, {ads.STOP_REASON: "rate_limit"}, "rate_limited", 0),
    ],
)
def test_exit_code_per_verdict(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    staged: str,
    statuses: dict[str, str],
    extra: dict[str, str],
    verdict: str,
    code: int,
) -> None:
    (tmp_path / ads.STAGED).write_text(staged)
    for name, content in extra.items():
        (tmp_path / name).write_text(content)
    rc = ads.main(
        ["--run-dir", str(tmp_path), "--quality-gate", "false"], status_of=_stub(statuses)
    )
    assert rc == code
    assert json.loads((tmp_path / "summary.json").read_text())["verdict"] == verdict


def test_max_steps_stop_reason_overrides_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The step-cap handler passes --stop-reason max_steps: an interrupted run, not phantom."""
    (tmp_path / ads.STAGED).write_text("FEAT-1\n")
    (tmp_path / ads.QUEUE).write_text("FEAT-2\nFEAT-3\n")
    (tmp_path / ads.INFLIGHT).write_text("FEAT-4")
    rc = ads.main(
        ["--run-dir", str(tmp_path), "--quality-gate", "false", "--stop-reason", "max_steps"],
        status_of=_stub({"FEAT-1": "done"}),
    )
    out = capsys.readouterr().out
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert rc == ads.EXIT_OK
    assert summary["verdict"] == "max_steps"
    assert summary["stop_reason"] == "max_steps"
    assert summary["pending"] == 2 and summary["abandoned"] == 1
    assert "Stopped early: max_steps — pending (2): FEAT-2,FEAT-3  (re-run to continue)" in out


def test_stop_reason_flag_overrides_stamp_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ads.STOP_REASON).write_text("rate_limit")
    ads.main(["--run-dir", str(tmp_path), "--stop-reason", "max_steps"], status_of=_stub({}))
    assert json.loads((tmp_path / "summary.json").read_text())["verdict"] == "max_steps"


def test_verdict_ladder_order() -> None:
    assert ads.compute_verdict(1, 0, 0, 0, "completed") == "success"
    assert ads.compute_verdict(1, 1, 0, 0, "completed") == "partial"
    assert ads.compute_verdict(1, 0, 1, 0, "completed") == "partial"
    assert ads.compute_verdict(0, 0, 1, 1, "completed") == "phantom"
    assert ads.compute_verdict(0, 0, 0, 1, "completed") == "not_started"
    assert ads.compute_verdict(0, 0, 0, 0, "completed") == "no-op"
    assert ads.compute_verdict(1, 0, 0, 0, "rate_limit") == "rate_limited"
    assert ads.compute_verdict(0, 1, 0, 0, "max_steps") == "max_steps"
    assert ads.compute_verdict(0, 1, 0, 0, "manual") == "phantom"


# ------------------------------------------------------------ error handling


def test_missing_run_dir_is_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = ads.main(["--run-dir", str(tmp_path / "nope")], status_of=_stub({}))
    assert rc == ads.EXIT_ERROR
    assert "run dir not found" in capsys.readouterr().err


def test_run_dir_that_is_a_file_is_error(tmp_path: Path) -> None:
    run_file = tmp_path / "run"
    run_file.write_text("")
    assert ads.main(["--run-dir", str(run_file)], status_of=_stub({})) == ads.EXIT_ERROR


def test_unwritable_summary_is_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(ads, "atomic_write", boom)
    assert ads.main(["--run-dir", str(tmp_path)], status_of=_stub({})) == ads.EXIT_ERROR
    assert "disk full" in capsys.readouterr().err


def test_missing_required_arg_exits_error() -> None:
    with pytest.raises(SystemExit) as exc:
        ads.main([])
    assert exc.value.code == ads.EXIT_ERROR


# ----------------------------------------------- module-level contract pins
# (formerly literal-substring pins on the inline finalize_done shell action)


def test_staged_ledger_drives_unverified_set(tmp_path: Path) -> None:
    """autodev-staged.txt is the source of the promoted/unverified split
    (test_autodev_decision_gate relies on un-staging a deferred issue)."""
    assert ads.STAGED == "autodev-staged.txt"
    (tmp_path / ads.STAGED).write_text("ENH-1\n")
    ads.promote_staged(tmp_path, quality_gate=False, status_of=_stub({"ENH-1": "open"}))
    assert (tmp_path / ads.UNVERIFIED).read_text() == "ENH-1\n"


def test_proof_gate_infra_ledger_is_sourced(tmp_path: Path) -> None:
    """BUG-3603: autodev-proof-gate-infra.txt feeds summary.json proof_gate_infra."""
    assert ads.PROOF_GATE_INFRA == "autodev-proof-gate-infra.txt"
    (tmp_path / ads.PROOF_GATE_INFRA).write_text("FEAT-701\n")
    assert ads.build_summary(tmp_path, cancelled_ids=[]).proof_gate_infra == 1


def test_inflight_sentinel_is_surfaced(tmp_path: Path) -> None:
    """BUG-1226/BUG-2908: a residual autodev-inflight sentinel is reported as
    abandoned and ledgered as inflight_at_finalize."""
    assert ads.INFLIGHT == "autodev-inflight"
    (tmp_path / ads.INFLIGHT).write_text("FEAT-7\n")
    summary = ads.build_summary(tmp_path, cancelled_ids=[])
    assert summary.abandoned == 1 and summary.inflight_unresolved == 1
    assert (tmp_path / ads.UNVERIFIED).read_text() == "FEAT-7  inflight_at_finalize\n"
    assert "FEAT-7  inflight_at_finalize" in ads.render_report(summary)


def test_summary_emits_abandoned_key(tmp_path: Path) -> None:
    """MR-13: the abandoned count must reach summary.json. The verdict logic moved
    out of the YAML, so the key contract is pinned here instead."""
    (tmp_path / ads.INFLIGHT).write_text("FEAT-7")
    summary = ads.build_summary(tmp_path, cancelled_ids=[])
    assert '"abandoned":1' in summary.to_json()
    assert summary.verdict == "phantom"


def test_summary_key_order() -> None:
    keys = list(ads.AutodevSummary(verdict="no-op").to_dict())
    assert keys == list(ads.AutodevSummary.KEYS)
    assert len(keys) == 18
    assert keys[:2] == ["verdict", "closed"]
    assert keys[-6:] == [
        "closed_implemented",
        "closed_cancelled",
        "quality_failed",
        "quality_gate_infra",
        "record_absent",
        "record_ledger_mismatch",
    ]


# --------------------------------------------------------- executor step cap


def test_step_cap_runs_finalize_step_capped_and_writes_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A forced low max_steps drives the executor into autodev's real on_max_steps
    handler, which runs the finalization once and writes summary.json with
    stop_reason max_steps (the handler's routing target is never executed)."""
    import yaml

    from little_loops.fsm.executor import FSMExecutor
    from little_loops.fsm.validation import load_and_validate

    autodev = yaml.safe_load((SCRIPTS_DIR / "little_loops" / "loops" / "autodev.yaml").read_text())
    project = GEN.make_project(tmp_path, {"FEAT-1": "done", "FEAT-2": "open"})
    run_dir = project / "run"
    run_dir.mkdir()
    (run_dir / ads.STAGED).write_text("FEAT-1\n")
    (run_dir / ads.QUEUE).write_text("FEAT-2\nFEAT-3\n")
    probe = {
        "name": "autodev-step-cap-probe",
        "initial": "spin",
        "max_steps": 3,
        "on_max_steps": autodev["on_max_steps"],
        "import": autodev["import"],
        "context": {"run_dir": str(run_dir), "quality_gate": "false"},
        "states": {
            "spin": {"action": "true", "action_type": "shell", "next": "spin"},
            **{
                name: autodev["states"][name]
                for name in ("finalize_done", "finalize_step_capped", "done", "failed")
            },
        },
    }
    probe_path = tmp_path / "loops" / "autodev-step-cap-probe.yaml"
    probe_path.parent.mkdir()
    probe_path.write_text(yaml.safe_dump(probe, sort_keys=False))
    fsm, _ = load_and_validate(probe_path, raise_on_error=False)

    monkeypatch.chdir(project)
    monkeypatch.setenv("PYTHONPATH", str(SCRIPTS_DIR))
    events: list[dict] = []
    result = FSMExecutor(fsm, event_callback=events.append, working_dir=project).run()

    assert result.terminated_by == "max_steps"
    entered = [e.get("state") for e in events if e.get("event") == "state_enter"]
    assert "finalize_step_capped" in entered and "finalize_done" not in entered
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["stop_reason"] == "max_steps"
    assert summary["verdict"] == "max_steps"
    assert (summary["closed"], summary["pending"]) == (1, 2)
    assert (run_dir / ads.PASSED).read_text() == "FEAT-1\n"


# --------------------------------------------------- record-driven accounting
# (ENH-3600: record_absent / record_ledger_mismatch)


def _write_record(run_dir: Path, issue_id: str, outcome: str, **kwargs: object) -> None:
    from little_loops.run_record import RunRecord, write_run_record

    write_run_record(
        run_dir, RunRecord(writer="prepare-issue", issue_id=issue_id, outcome=outcome, **kwargs)
    )


def _prep_pass(run_dir: Path, issue_id: str) -> None:
    (run_dir / f"{ads.PREP_PASS_PREFIX}{issue_id}").write_text("1")


def test_record_absent_when_no_record_and_no_ledger_row(tmp_path: Path) -> None:
    _prep_pass(tmp_path, "ENH-1")
    summary = ads.build_summary(tmp_path, cancelled_ids=[])
    assert summary.record_absent == 1
    assert summary.record_absent_ids == ["ENH-1"]
    assert summary.record_ledger_mismatch == 0
    assert summary.verdict == "no-op"  # never changes verdict


def test_record_absent_excludes_dequeue_time_skip(tmp_path: Path) -> None:
    """A dequeue-time skip has both a prep-pass file and a skipped row; excluded."""
    _prep_pass(tmp_path, "ENH-1")
    (tmp_path / ads.SKIPPED).write_text("ENH-1  already_done\n")
    summary = ads.build_summary(tmp_path, cancelled_ids=[])
    assert summary.record_absent == 0
    assert summary.record_ledger_mismatch == 0


def test_record_absent_excludes_inflight_id(tmp_path: Path) -> None:
    """An abandoned in-flight ID is folded into UNVERIFIED first; never record_absent."""
    _prep_pass(tmp_path, "ENH-1")
    (tmp_path / ads.INFLIGHT).write_text("ENH-1")
    summary = ads.build_summary(tmp_path, cancelled_ids=[])
    assert summary.abandoned == 1
    assert summary.record_absent == 0


def test_record_absent_zero_on_healthy_run_with_prepared_ready_issue(tmp_path: Path) -> None:
    _prep_pass(tmp_path, "ENH-1")
    _write_record(tmp_path, "ENH-1", "ready")
    (tmp_path / ads.PASSED).write_text("ENH-1\n")
    summary = ads.build_summary(tmp_path, cancelled_ids=[])
    assert summary.record_absent == 0
    assert summary.record_ledger_mismatch == 0


def test_dequeued_twice_counts_once(tmp_path: Path) -> None:
    """The prep-pass-<ID> file is rewritten, not appended, so a re-dequeued ID
    has exactly one file and the last pass's record wins."""
    _prep_pass(tmp_path, "ENH-1")
    (tmp_path / f"{ads.PREP_PASS_PREFIX}ENH-1").write_text("2")  # second pass, same file
    summary = ads.build_summary(tmp_path, cancelled_ids=[])
    assert summary.record_absent == 1
    assert summary.record_absent_ids == ["ENH-1"]


@pytest.mark.parametrize(
    ("outcome", "kwargs", "ledger_setup", "expect_mismatch"),
    [
        ("blocked", {"legacy_class": "quality"}, lambda rd: None, True),
        (
            "blocked",
            {"legacy_class": "quality"},
            lambda rd: (rd / ads.SKIPPED).write_text("ENH-1  refine_failed\n"),
            False,
        ),
        ("deferred", {"legacy_class": "gate_unmet"}, lambda rd: None, True),
        (
            "deferred",
            {"legacy_class": "gate_unmet"},
            lambda rd: (rd / ads.SKIPPED).write_text("ENH-1  oversized_atomic\n"),
            False,
        ),
        (
            "blocked",
            {"legacy_class": "decision_unresolved"},
            lambda rd: None,
            True,
        ),
        (
            "blocked",
            {"legacy_class": "decision_unresolved"},
            lambda rd: (rd / ads.DECISION_UNRESOLVED).write_text("ENH-1\n"),
            False,
        ),
        ("deferred", {"legacy_class": "spike_inconclusive"}, lambda rd: None, True),
        (
            "deferred",
            {"legacy_class": "spike_inconclusive"},
            lambda rd: (rd / ads.SPIKE_INCONCLUSIVE).write_text("ENH-1\n"),
            False,
        ),
        ("blocked", {"legacy_class": "proposal_unsound"}, lambda rd: None, True),
        (
            "blocked",
            {"legacy_class": "proposal_unsound"},
            lambda rd: (rd / ads.PROPOSAL_UNSOUND).write_text("ENH-1\n"),
            False,
        ),
        ("retryable_error", {}, lambda rd: None, True),
        (
            "retryable_error",
            {},
            lambda rd: (rd / ads.SKIPPED).write_text("ENH-1  refine_failed_infra\n"),
            False,
        ),
        ("cancelled", {}, lambda rd: None, True),
        (
            "cancelled",
            {},
            lambda rd: (rd / ads.SKIPPED).write_text("ENH-1  cancelled\n"),
            False,
        ),
        ("decomposed", {}, lambda rd: None, True),
        (
            "decomposed",
            {},
            lambda rd: (rd / ads.SKIPPED).write_text("ENH-1  decomposed\n"),
            False,
        ),
        # READY and rate-limited accept "any or none": never a mismatch.
        ("ready", {}, lambda rd: None, False),
        (
            "retryable_error",
            {"evidence_refs": ("rate_limit_exhausted",)},
            lambda rd: None,
            False,
        ),
    ],
)
def test_record_ledger_mismatch_per_correspondence_table_row(
    tmp_path: Path, outcome: str, kwargs: dict, ledger_setup: object, expect_mismatch: bool
) -> None:
    _prep_pass(tmp_path, "ENH-1")
    _write_record(tmp_path, "ENH-1", outcome, **kwargs)
    ledger_setup(tmp_path)  # type: ignore[operator]
    summary = ads.build_summary(tmp_path, cancelled_ids=[])
    assert summary.record_ledger_mismatch == (1 if expect_mismatch else 0)
    assert summary.record_absent == 0
    # Never reclassifies the issue or changes verdict/exit code.
    assert summary.verdict in ("no-op", "phantom")
    assert summary.exit_code in (ads.EXIT_OK, ads.EXIT_PHANTOM)


def test_row_present_but_record_missing_is_a_mismatch_not_absent(tmp_path: Path) -> None:
    """The correspondence table's inverse case: a skipped row exists but the
    prepare-issue record is MISSING (a crash inside prep apply)."""
    _prep_pass(tmp_path, "ENH-1")
    (tmp_path / ads.SKIPPED).write_text("ENH-1  refine_failed\n")
    summary = ads.build_summary(tmp_path, cancelled_ids=[])
    assert summary.record_absent == 0
    assert summary.record_ledger_mismatch == 1
    assert summary.record_ledger_mismatch_ids == ["ENH-1"]


def test_decoy_unlisted_ledger_file_has_no_effect(tmp_path: Path) -> None:
    """build_summary reads only run-records/prepare-issue/*.json plus the Scope
    Boundaries files; an unlisted autodev-* file must never feed any count."""
    _prep_pass(tmp_path, "ENH-1")
    (tmp_path / "autodev-scores-absent.txt").write_text("ENH-1\n")  # dead ledger, retired ENH-3623
    summary = ads.build_summary(tmp_path, cancelled_ids=[])
    assert summary.record_absent == 1  # the decoy file did not excuse the missing record


def test_record_lines_print_only_when_nonzero(tmp_path: Path) -> None:
    _prep_pass(tmp_path, "ENH-1")
    summary = ads.build_summary(tmp_path, cancelled_ids=[])
    report = ads.render_report(summary)
    assert "Record-absent [invariant] (1): ENH-1" in report
    assert "Record-ledger-mismatch" not in report


def test_no_record_lines_when_no_prep_pass_files(tmp_path: Path) -> None:
    summary = ads.build_summary(tmp_path, cancelled_ids=[])
    assert summary.record_absent == 0
    assert summary.record_ledger_mismatch == 0
    assert "Record-absent" not in ads.render_report(summary)
    assert "Record-ledger-mismatch" not in ads.render_report(summary)


# -------------------------------------------------------------- status lookup


def test_status_resolver_reads_frontmatter_case_insensitively(tmp_path: Path) -> None:
    project = GEN.make_project(tmp_path, {"FEAT-1": "Done", "BUG-2": "cancelled"})
    resolve = ads.issue_status_resolver(project)
    assert resolve("FEAT-1") == "done"
    assert resolve("BUG-2") == "cancelled"
    assert resolve("ENH-404") == ""


@pytest.mark.parametrize("value", ["false", "FALSE", "0", "no", "Off"])
def test_quality_gate_off_values(value: str) -> None:
    assert not ads.quality_gate_enabled(value)


@pytest.mark.parametrize("value", ["true", "", "1", "yes", "anything"])
def test_quality_gate_on_values(value: str) -> None:
    assert ads.quality_gate_enabled(value)
