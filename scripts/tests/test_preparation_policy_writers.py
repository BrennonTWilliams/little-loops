"""ENH-3630: in-process integration tests for the preparation_policy writers.

Unlike test_preparation_policy.py (pure decide() table tests, no I/O), these exercise
prep_step / prep_record / prep_apply against a real ``.issues/`` tree and run_dir,
pinning the in-process writes (checked ``apply_status_transition``, ``clear_scores``,
the shared ``write_typed_run_record`` helper) and apply's crash-safety.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from little_loops.config import BRConfig
from little_loops.preparation_policy import (
    Fact,
    StepKind,
    append_fact,
    facts_path,
    load_facts,
    prep_apply,
    prep_record,
    prep_step,
)

ID = "ENH-9801"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    for kind in ("bugs", "features", "enhancements", "epics"):
        (tmp_path / ".issues" / kind).mkdir(parents=True, exist_ok=True)
    (tmp_path / ".ll").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write_issue(project: Path, issue_id: str, *, frontmatter: str = "") -> Path:
    path = project / ".issues" / "enhancements" / f"P3-{issue_id}-test.md"
    path.write_text(
        f"---\nid: {issue_id}\ntitle: T\ntype: enhancement\nstatus: open\npriority: P3\n"
        f"{frontmatter}---\n\n# {issue_id}: T\n\n## Summary\n\nPlain.\n"
    )
    return path


def _config(project: Path) -> BRConfig:
    return BRConfig(project)


def _inner_record(config: BRConfig, run_dir: Path, **kw: object) -> str:
    """Write the inner ``refine-to-ready-issue`` run record; return the record id."""
    from little_loops.cli.issues.run_record import canonical_record_id
    from little_loops.run_record import RunRecord, write_run_record

    rid = canonical_record_id(config, ID)
    write_run_record(run_dir, RunRecord(writer="refine-to-ready-issue", issue_id=rid, **kw))  # type: ignore[arg-type]
    return rid


class TestFactLogIdempotency:
    def test_appending_same_key_twice_writes_one_line(self, tmp_path: Path) -> None:
        fact = Fact("1", 1, "intent", StepKind.RUN_CHILD.value, {"role": "first"})
        assert append_fact(tmp_path, ID, fact) is True
        assert append_fact(tmp_path, ID, fact) is False
        lines = facts_path(tmp_path, ID).read_text().splitlines()
        assert len(lines) == 1

    def test_replayed_dequeue_skipping_a_pass_number_is_harmless(self, tmp_path: Path) -> None:
        """A gap in pass numbers (e.g. pass "1" then "3") doesn't confuse in_pass()."""
        append_fact(tmp_path, ID, Fact("1", 1, "intent", StepKind.RUN_CHILD.value, {}))
        append_fact(
            tmp_path, ID, Fact("1", 1, "done", StepKind.RUN_CHILD.value, {"terminal": "done"})
        )
        facts = load_facts(tmp_path, ID)
        pass3 = facts.__class__(pass_id="3", facts=facts.facts)
        assert pass3.dones() == []
        assert pass3.in_pass() == []


class TestPrepStepReady:
    def test_first_step_clears_records_and_runs_child(self, project: Path) -> None:
        _write_issue(project, ID)
        run_dir = project / "run"
        step = prep_step(
            _config(project), ID, run_dir, readiness_threshold=85, outcome_threshold=65
        )
        assert step.kind is StepKind.RUN_CHILD
        assert step.payload.get("role") == "first"
        assert step.payload.get("preconditions") == ["clear_records"]

    def test_ready_child_finishes_and_apply_writes_ready_record(self, project: Path) -> None:
        _write_issue(project, ID, frontmatter="confidence_score: 90\noutcome_confidence: 80\n")
        run_dir = project / "run"
        config = _config(project)
        prep_step(config, ID, run_dir, readiness_threshold=85, outcome_threshold=65)
        # Fake the inner run's record (written after the RUN_CHILD precondition clear).
        rid = _inner_record(config, run_dir, outcome="ready")
        prep_record(config, ID, run_dir)
        step = prep_step(config, ID, run_dir, readiness_threshold=85, outcome_threshold=65)
        assert step.kind is StepKind.FINISH
        assert step.payload.get("outcome") == "ready"

        exit_code = prep_apply(config, ID, run_dir, readiness_threshold=85, outcome_threshold=65)
        assert exit_code == 0
        record = (run_dir / "run-records" / "prepare-issue" / f"{rid}.json").read_text()
        assert '"outcome": "ready"' in record


class TestPrepRecordClassifiesFromRunRecord:
    """ENH-3623: ``prep record`` classifies a RUN_CHILD step from the child's run record.

    The ``RUN_CHILD`` precondition clears ``run-records/refine-to-ready-issue/<ID>.json``
    and every inner terminal writes it, so: absent -> the inner loop errored; a legacy
    class -> it ended ``failed``; otherwise it ended ``done``. The loop's
    ``captured.run_child`` (whose ``failure_terminal`` can outlive the run that set it)
    is never consulted -- ``record_step`` does not even pass it
    (``test_prepare_issue.py::TestStructure::test_record_step_never_reads_the_child_capture``).
    """

    def _first_step(self, project: Path) -> tuple[BRConfig, Path]:
        _write_issue(project, ID, frontmatter="confidence_score: 90\noutcome_confidence: 80\n")
        run_dir = project / "run"
        config = _config(project)
        prep_step(config, ID, run_dir, readiness_threshold=85, outcome_threshold=65)
        return config, run_dir

    def test_absent_record_is_inner_error(self, project: Path) -> None:
        config, run_dir = self._first_step(project)
        done = prep_record(config, ID, run_dir)
        assert done is not None
        assert (done.payload["terminal"], done.payload["token"]) == ("error", "MISSING")
        step = prep_step(config, ID, run_dir, readiness_threshold=85, outcome_threshold=65)
        assert step.kind is StepKind.STOP
        assert step.payload.get("outcome") == "inner_error"

    def test_legacy_class_record_is_a_child_stop(self, project: Path) -> None:
        config, run_dir = self._first_step(project)
        _inner_record(config, run_dir, outcome="blocked", legacy_class="quality")
        done = prep_record(config, ID, run_dir)
        assert done is not None
        assert (done.payload["terminal"], done.payload["token"]) == ("failed", "BLOCKED:quality")
        step = prep_step(config, ID, run_dir, readiness_threshold=85, outcome_threshold=65)
        assert step.kind is StepKind.STOP
        assert step.payload.get("outcome") == "child_stop"

    def test_done_record_ignores_a_stale_failure_capture(self, project: Path) -> None:
        """A previous run_child that ended `failed` cannot flip this pass: the record
        (fresh, the precondition cleared the old one) is the only input."""
        config, run_dir = self._first_step(project)
        _inner_record(config, run_dir, outcome="ready")
        done = prep_record(config, ID, run_dir)
        assert done is not None
        assert (done.payload["terminal"], done.payload["token"]) == ("done", "READY")
        step = prep_step(config, ID, run_dir, readiness_threshold=85, outcome_threshold=65)
        assert step.kind is StepKind.FINISH
        assert step.payload.get("outcome") == "ready"

    def test_run_child_precondition_clears_the_previous_record(self, project: Path) -> None:
        """A stale record from a previous pass cannot be classified as this pass's run."""
        _write_issue(project, ID, frontmatter="confidence_score: 90\noutcome_confidence: 80\n")
        run_dir = project / "run"
        config = _config(project)
        _inner_record(config, run_dir, outcome="blocked", legacy_class="quality")
        prep_step(config, ID, run_dir, readiness_threshold=85, outcome_threshold=65)
        done = prep_record(config, ID, run_dir)
        assert done is not None and done.payload["terminal"] == "error"


class TestAdviseGoNoGoVeto:
    """ENH-3590: the veto-only consult on a go/no-go waiver, via a real
    ``.issues/`` tree and run_dir. Seeds a completed GO_NO_GO pass directly
    (the go-no-go skill's own model-driven waiver stamp is not under test
    here); exercises the new ADVISE_GO_NO_GO leg end to end."""

    def _to_advise_step(self, project: Path) -> tuple[BRConfig, Path]:
        _write_issue(
            project,
            ID,
            frontmatter=(
                "confidence_score: 90\noutcome_confidence: 50\n"
                "status: deferred\ndeferred_reason: oversized_atomic\n"
                "outcome_gate_waived: true\n"
            ),
        )
        run_dir = project / "run"
        # current_pass() reads pass "0" until ENH-3623 Phase B's dequeue_next
        # writes prep-pass-<ID> (module docstring); match it so the seeded
        # facts are visible to prep_step/prep_record's own load_facts() calls.
        append_fact(run_dir, ID, Fact("0", 1, "intent", StepKind.GO_NO_GO.value, {}))
        append_fact(run_dir, ID, Fact("0", 1, "done", StepKind.GO_NO_GO.value, {}))
        return _config(project), run_dir

    def _issue_text(self, project: Path) -> str:
        return (project / ".issues" / "enhancements" / f"P3-{ID}-test.md").read_text()

    def test_flag_on_reaches_advise_step_without_reopening(self, project: Path) -> None:
        config, run_dir = self._to_advise_step(project)
        step = prep_step(
            config,
            ID,
            run_dir,
            readiness_threshold=85,
            outcome_threshold=65,
            advise_go_no_go=True,
        )
        assert step.kind is StepKind.ADVISE_GO_NO_GO
        assert "preconditions" not in step.payload
        assert "status: deferred" in self._issue_text(project)

    def test_veto_clears_the_waiver_and_stops(self, project: Path) -> None:
        config, run_dir = self._to_advise_step(project)
        prep_step(
            config, ID, run_dir, readiness_threshold=85, outcome_threshold=65, advise_go_no_go=True
        )
        (run_dir / f"advise-{ID}.verdict").write_text('{"token": "VETO", "context_hash": "x"}')
        done = prep_record(config, ID, run_dir)
        assert done is not None and done.payload["token"] == "VETO"
        assert "outcome_gate_waived" not in self._issue_text(project)
        step = prep_step(
            config, ID, run_dir, readiness_threshold=85, outcome_threshold=65, advise_go_no_go=True
        )
        assert step.kind is StepKind.STOP
        assert step.payload.get("outcome") == "oversized_atomic"

    def test_proceed_reopens_and_continues(self, project: Path) -> None:
        config, run_dir = self._to_advise_step(project)
        prep_step(
            config, ID, run_dir, readiness_threshold=85, outcome_threshold=65, advise_go_no_go=True
        )
        (run_dir / f"advise-{ID}.verdict").write_text('{"token": "PROCEED", "context_hash": "x"}')
        prep_record(config, ID, run_dir)
        assert "outcome_gate_waived: true" in self._issue_text(project)  # untouched by PROCEED
        step = prep_step(
            config, ID, run_dir, readiness_threshold=85, outcome_threshold=65, advise_go_no_go=True
        )
        assert step.kind is StepKind.FINISH
        assert step.payload.get("outcome") == "ready"


class TestRescorePrecondition:
    """BUG-3588 / ENH-3623: the first RESCORE of an origin clears the stale scores
    before the slash command runs, so a rescoring that writes nothing reads absent."""

    def test_first_rescore_clears_scores_and_retry_does_not(self, project: Path) -> None:
        path = _write_issue(
            project,
            ID,
            frontmatter="confidence_score: 70\noutcome_confidence: 80\nmissing_artifacts: true\n",
        )
        run_dir = project / "run"
        config = _config(project)
        for kind in (StepKind.RUN_CHILD, StepKind.WIRE, StepKind.REFINE_GAP):
            step = prep_step(config, ID, run_dir, readiness_threshold=85, outcome_threshold=65)
            assert step.kind is kind
            if kind is StepKind.RUN_CHILD:
                _inner_record(config, run_dir, outcome="blocked")
            prep_record(config, ID, run_dir)
        step = prep_step(config, ID, run_dir, readiness_threshold=85, outcome_threshold=65)
        assert step.kind is StepKind.RESCORE and step.payload.get("attempt") == 1
        assert "confidence_score" not in path.read_text()
        assert "outcome_confidence" not in path.read_text()
        prep_record(config, ID, run_dir)
        retry = prep_step(config, ID, run_dir, readiness_threshold=85, outcome_threshold=65)
        assert retry.kind is StepKind.RESCORE and retry.payload.get("attempt") == 2
        assert "preconditions" not in retry.payload


class TestPrepApplyDeferredWritesStatus:
    def _oversized_atomic_facts(self, run_dir: Path) -> None:
        """Hand-craft a pass whose open intent is a STOP:oversized_atomic (no waiver).

        Pass id "0" -- current_pass() defaults to "0" with no prep-pass-<ID> file
        (ENH-3623 Phase B writes it; absent until then), so the facts must agree.
        """
        append_fact(
            run_dir, ID, Fact("0", 0, "obs", "pass_start", {"pre_readiness": "", "pre_ids": []})
        )
        append_fact(
            run_dir,
            ID,
            Fact("0", 1, "intent", StepKind.STOP.value, {"outcome": "oversized_atomic"}),
        )

    def test_deferred_stop_sets_status_and_writes_row(self, project: Path) -> None:
        _write_issue(project, ID, frontmatter="confidence_score: 90\noutcome_confidence: 50\n")
        run_dir = project / "run"
        config = _config(project)
        self._oversized_atomic_facts(run_dir)

        exit_code = prep_apply(config, ID, run_dir, readiness_threshold=85, outcome_threshold=65)
        assert exit_code == 1

        issue_path = project / ".issues" / "enhancements" / f"P3-{ID}-test.md"
        content = issue_path.read_text()
        assert "status: deferred" in content
        assert "deferred_reason: oversized_atomic" in content
        skipped = (run_dir / "autodev-skipped.txt").read_text()
        assert f"{ID}  oversized_atomic" in skipped

    def test_replay_after_apply_is_idempotent(self, project: Path) -> None:
        """Re-running apply on an already-applied pass returns the same exit, no new row."""
        _write_issue(project, ID, frontmatter="confidence_score: 90\noutcome_confidence: 50\n")
        run_dir = project / "run"
        config = _config(project)
        self._oversized_atomic_facts(run_dir)
        first = prep_apply(config, ID, run_dir, readiness_threshold=85, outcome_threshold=65)
        second = prep_apply(config, ID, run_dir, readiness_threshold=85, outcome_threshold=65)
        assert first == second == 1
        skipped = (run_dir / "autodev-skipped.txt").read_text()
        assert skipped.count(f"{ID}  oversized_atomic") == 1


class TestPrepApplyCrashInjection:
    """AC: a crash between apply's writes, then a re-run, converges on one terminal."""

    def _oversized_atomic_facts(self, run_dir: Path) -> None:
        append_fact(
            run_dir, ID, Fact("0", 0, "obs", "pass_start", {"pre_readiness": "", "pre_ids": []})
        )
        append_fact(
            run_dir,
            ID,
            Fact("0", 1, "intent", StepKind.STOP.value, {"outcome": "oversized_atomic"}),
        )

    def test_crash_after_row_before_status_write_then_replay_converges(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_issue(project, ID, frontmatter="confidence_score: 90\noutcome_confidence: 50\n")
        run_dir = project / "run"
        config = _config(project)
        self._oversized_atomic_facts(run_dir)

        import little_loops.preparation_policy as pp

        monkeypatch.setattr(
            pp,
            "_set_status_checked",
            lambda *a, **kw: (_ for _ in ()).throw(OSError("simulated crash")),
        )
        with pytest.raises(OSError, match="simulated crash"):
            prep_apply(config, ID, run_dir, readiness_threshold=85, outcome_threshold=65)

        # The row was written (before the crash point) and won't be duplicated on replay.
        skipped_after_crash = (run_dir / "autodev-skipped.txt").read_text()
        assert skipped_after_crash.count(f"{ID}  oversized_atomic") == 1
        # No done fact was appended for this pass -- the crash happened mid-apply.
        assert load_facts(run_dir, ID).dones() == []

        monkeypatch.undo()
        exit_code = prep_apply(config, ID, run_dir, readiness_threshold=85, outcome_threshold=65)
        assert exit_code == 1
        skipped_final = (run_dir / "autodev-skipped.txt").read_text()
        assert skipped_final.count(f"{ID}  oversized_atomic") == 1  # not double-appended
        applied = [f for f in load_facts(run_dir, ID).dones() if f.step in (StepKind.STOP.value,)]
        assert len(applied) == 1  # exactly one terminal
        content = (project / ".issues" / "enhancements" / f"P3-{ID}-test.md").read_text()
        assert "status: deferred" in content

    def test_crash_after_status_write_before_run_record_then_replay_converges(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ENH-3630 Step 5: the second of the two real crash splits in this branch.

        The ``_DEFER_STOPS`` branch's actual write order is ``row -> rm_inflight ->
        set-status -> run-record`` (not the row->set-status->run-record->inflight-clear
        order the AC text sketched -- ``rm_inflight`` has no progress mark of its own
        and runs unconditionally right after the row, so the row-before-status test
        above already exercises that boundary). This pins the remaining split: a crash
        after ``mark("status")`` persists but before the run-record write, then a
        replay that must not re-run ``set-status`` (idempotent) and must still end with
        exactly one terminal record.
        """
        _write_issue(project, ID, frontmatter="confidence_score: 90\noutcome_confidence: 50\n")
        run_dir = project / "run"
        config = _config(project)
        self._oversized_atomic_facts(run_dir)

        import little_loops.cli.issues.run_record as run_record_mod

        monkeypatch.setattr(
            run_record_mod,
            "write_typed_run_record",
            lambda *a, **kw: (_ for _ in ()).throw(OSError("simulated crash")),
        )
        with pytest.raises(OSError, match="simulated crash"):
            prep_apply(config, ID, run_dir, readiness_threshold=85, outcome_threshold=65)

        content_after_crash = (
            project / ".issues" / "enhancements" / f"P3-{ID}-test.md"
        ).read_text()
        assert "status: deferred" in content_after_crash  # set-status ran before the crash
        assert not (run_dir / "autodev-inflight").exists()
        assert load_facts(run_dir, ID).dones() == []  # no terminal recorded yet

        monkeypatch.undo()
        exit_code = prep_apply(config, ID, run_dir, readiness_threshold=85, outcome_threshold=65)
        assert exit_code == 1
        # set-status is not re-invoked on replay (mark("status") short-circuits it);
        # deferred_by / deferred_reason would be stamped twice otherwise.
        content_final = (project / ".issues" / "enhancements" / f"P3-{ID}-test.md").read_text()
        assert content_final.count("status: deferred") == 1
        applied = [f for f in load_facts(run_dir, ID).dones() if f.step in (StepKind.STOP.value,)]
        assert len(applied) == 1  # exactly one terminal


class TestPrepApplyNoOpenIntent:
    """AC: no open FINISH/STOP intent writes RETRYABLE_ERROR:infra."""

    def test_no_open_intent_is_ladder_error_and_writes_retryable_infra(self, project: Path) -> None:
        _write_issue(project, ID, frontmatter="confidence_score: 90\noutcome_confidence: 80\n")
        run_dir = project / "run"
        config = _config(project)
        # A pass with a done RUN_CHILD but no follow-up intent at all (e.g. the
        # wrapper crashed between record and the next step) -- open_intent() is None.
        append_fact(
            run_dir, ID, Fact("0", 0, "obs", "pass_start", {"pre_readiness": "", "pre_ids": []})
        )
        append_fact(
            run_dir, ID, Fact("0", 1, "intent", StepKind.RUN_CHILD.value, {"role": "first"})
        )
        append_fact(
            run_dir,
            ID,
            Fact("0", 1, "done", StepKind.RUN_CHILD.value, {"terminal": "done", "token": "READY"}),
        )

        exit_code = prep_apply(config, ID, run_dir, readiness_threshold=85, outcome_threshold=65)
        assert exit_code == 1

        from little_loops.cli.issues.run_record import canonical_record_id
        from little_loops.run_record import read_run_record, record_token

        rid = canonical_record_id(config, ID)
        token = record_token(read_run_record(run_dir, "prepare-issue", rid))
        assert token == "RETRYABLE_ERROR:infra"


class TestSnapshotIssueQ1MarkerReadRegardlessOfBlocking:
    """BUG-3624 (Q1): superseded_marker_count is read even with blocking format gaps.

    The spike's `0 if blocking else superseded_marker_count(path)` masked the
    contradiction trigger exactly when a blocking gap coexisted with a marker.
    Exercises snapshot_issue() itself (not just decide()), since the fix lives in
    the I/O function, not the pure layer.
    """

    def test_markers_counted_even_when_format_check_has_a_blocking_gap(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from little_loops.issue_parser import FormatGaps
        from little_loops.preparation_policy import snapshot_issue

        _write_issue(project, ID)
        config = _config(project)

        monkeypatch.setattr(
            "little_loops.issue_parser.check_format_gaps",
            lambda path: FormatGaps(missing=["## Summary"]),  # has_blocking_gaps=True
        )
        monkeypatch.setattr("little_loops.issue_parser.superseded_marker_count", lambda path: 3)

        snap = snapshot_issue(
            config, ID, project / "run", readiness_threshold=85, outcome_threshold=65
        )
        # The blocking gap ("## Summary" missing) does not zero out the marker count.
        assert snap.superseded_markers == 3


class TestReasonValidationEveryDeferStop:
    """AC: every (status, reason) pair the policy emits passes the reason check."""

    def test_every_defer_stop_reason_is_a_valid_deferral_code(self) -> None:
        from little_loops.cli.issues.set_status import reason_error_for_status
        from little_loops.preparation_policy import _DEFER_STOPS

        for _outcome, (reason, _legacy) in _DEFER_STOPS.items():
            assert reason_error_for_status("deferred", reason) is None


# ---------------------------------------------------------------------------
# ENH-3623: crash injection for every apply outcome branch. ENH-3600: no
# failed-bound terminal writes the retired refine-terminal-class sentinel.
# ---------------------------------------------------------------------------

#: outcome -> (issue frontmatter, inner record kwargs or None, expected exit, token)
_APPLY_BRANCHES: dict[str, tuple[str, dict[str, object] | None, int, str]] = {
    "ready": ("confidence_score: 90\noutcome_confidence: 80\n", None, 0, "READY"),
    "cancelled": (
        "confidence_score: 90\noutcome_confidence: 80\n",
        {"outcome": "cancelled"},
        0,
        "CANCELLED",
    ),
    "decomposed": ("", None, 0, "DECOMPOSED"),
    "child_stop": (
        "",
        {"outcome": "blocked", "legacy_class": "quality"},
        1,
        "BLOCKED:quality",
    ),
    "rate_limited": ("", None, 1, "RETRYABLE_ERROR:rate_limited"),
    "scores_absent": ("", None, 1, "RETRYABLE_ERROR:infra"),
    "inner_error": ("", None, 1, "RETRYABLE_ERROR:infra"),
    "ladder_error": ("", None, 1, "RETRYABLE_ERROR:infra"),
    "low_readiness": (
        "confidence_score: 70\noutcome_confidence: 80\n",
        None,
        1,
        "DEFERRED:gate_unmet",
    ),
    "decision_unresolved": ("", None, 1, "BLOCKED:decision_unresolved"),
}


def _open_terminal(project: Path, outcome: str) -> tuple[BRConfig, Path]:
    frontmatter, inner, _code, _token = _APPLY_BRANCHES[outcome]
    _write_issue(project, ID, frontmatter=frontmatter)
    run_dir = project / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "autodev-inflight").write_text(ID)
    config = _config(project)
    if inner is not None:
        _inner_record(config, run_dir, **inner)
    append_fact(
        run_dir, ID, Fact("0", 0, "obs", "pass_start", {"pre_readiness": "", "pre_ids": []})
    )
    if outcome not in ("rate_limited", "ladder_error"):
        kind = StepKind.FINISH if outcome in ("ready", "cancelled", "decomposed") else StepKind.STOP
        append_fact(run_dir, ID, Fact("0", 1, "intent", kind.value, {"outcome": outcome}))
    return config, run_dir


def _apply(config: BRConfig, run_dir: Path, outcome: str) -> int:
    return prep_apply(
        config,
        ID,
        run_dir,
        readiness_threshold=85,
        outcome_threshold=65,
        rate_limited=outcome == "rate_limited",
    )


def _token(config: BRConfig, run_dir: Path) -> str:
    from little_loops.cli.issues.run_record import canonical_record_id
    from little_loops.run_record import read_run_record, record_token

    return record_token(read_run_record(run_dir, "prepare-issue", canonical_record_id(config, ID)))


def _rows(run_dir: Path) -> list[str]:
    ledger = run_dir / "autodev-skipped.txt"
    return ledger.read_text().splitlines() if ledger.exists() else []


class TestPrepApplyEveryBranch:
    @pytest.mark.parametrize("outcome", sorted(_APPLY_BRANCHES))
    def test_apply_writes_one_terminal_record(self, project: Path, outcome: str) -> None:
        config, run_dir = _open_terminal(project, outcome)
        _frontmatter, _inner, code, token = _APPLY_BRANCHES[outcome]
        assert _apply(config, run_dir, outcome) == code
        assert _token(config, run_dir) == token
        applied = [f for f in load_facts(run_dir, ID).dones() if f.step in ("FINISH", "STOP")]
        assert len(applied) == 1

    @pytest.mark.parametrize(
        "outcome", sorted(o for o, (_f, _i, code, _t) in _APPLY_BRANCHES.items() if code == 1)
    )
    def test_failed_bound_terminal_writes_no_sentinel(self, project: Path, outcome: str) -> None:
        """ENH-3600: no failed-bound terminal writes refine-terminal-class anymore —
        autodev's skip_inflight classifies from the run record's routing token alone."""
        config, run_dir = _open_terminal(project, outcome)
        (run_dir / "refine-terminal-class").unlink(missing_ok=True)
        assert _apply(config, run_dir, outcome) == 1
        assert not (run_dir / "refine-terminal-class").exists()


def _crash(target: str) -> object:
    def boom(*_a: object, **_kw: object) -> None:
        raise OSError(f"simulated crash in {target}")

    return boom


#: Where a crash lands: after the ledger row (before its progress mark), in
#: set-status, in the run-record write, or after every write but before the
#: terminal done fact. The inflight clear is an idempotent unlink between the row
#: and set-status.
_CRASH_POINTS = ("ledger_row", "set_status", "run_record", "done_fact")


class TestPrepApplyCrashEveryBranch:
    """AC: a crash between any two of apply's writes, then a replay, never
    double-appends a ledger row and ends with exactly one terminal."""

    @pytest.mark.parametrize("point", sorted(_CRASH_POINTS))
    @pytest.mark.parametrize("outcome", sorted(_APPLY_BRANCHES))
    def test_crash_then_replay_converges(
        self, project: Path, monkeypatch: pytest.MonkeyPatch, outcome: str, point: str
    ) -> None:
        import little_loops.cli.issues.run_record as run_record_mod
        import little_loops.preparation_policy as pp

        clean_root = project / "clean"
        clean_root.mkdir()
        for kind in ("bugs", "features", "enhancements", "epics"):
            (clean_root / ".issues" / kind).mkdir(parents=True)
        clean_cfg, clean_dir = _open_terminal(clean_root, outcome)
        clean_code = _apply(clean_cfg, clean_dir, outcome)
        clean_rows = _rows(clean_dir)

        config, run_dir = _open_terminal(project, outcome)
        real_append = pp.append_fact
        if point == "ledger_row":
            # crash right after the row landed, before its `row` progress mark
            def append(rd: Path, iid: str, fact: Fact) -> bool:
                if fact.step == "apply_progress" and fact.payload.get("value") == "row":
                    raise OSError("simulated crash after the ledger row")
                return real_append(rd, iid, fact)

            monkeypatch.setattr(pp, "append_fact", append)
        elif point == "set_status":
            monkeypatch.setattr(pp, "_set_status_checked", _crash(point))
        elif point == "run_record":
            monkeypatch.setattr(run_record_mod, "write_typed_run_record", _crash(point))
            monkeypatch.setattr(run_record_mod, "forward_run_record", _crash(point))
        else:  # every write landed; the terminal done fact did not

            def append(rd: Path, iid: str, fact: Fact) -> bool:
                if fact.kind == "done" and fact.step in ("FINISH", "STOP"):
                    raise OSError("simulated crash before the done fact")
                return real_append(rd, iid, fact)

            monkeypatch.setattr(pp, "append_fact", append)
        try:
            _apply(config, run_dir, outcome)
        except OSError:
            pass  # not every branch reaches every crash point
        monkeypatch.undo()

        assert _apply(config, run_dir, outcome) == clean_code
        assert _apply(config, run_dir, outcome) == clean_code  # and replay is stable
        assert _rows(run_dir) == clean_rows
        assert _token(config, run_dir) == _token(clean_cfg, clean_dir)
        assert (run_dir / "autodev-inflight").exists() == (clean_dir / "autodev-inflight").exists()
        applied = [f for f in load_facts(run_dir, ID).dones() if f.step in ("FINISH", "STOP")]
        assert len(applied) == 1


class TestSnapshotProbes:
    """ENH-3623: probe semantics the retired autodev selector tests pinned."""

    def test_refine_cap_honors_config_and_defaults_to_five(self, project: Path) -> None:
        from little_loops.preparation_policy import snapshot_issue

        _write_issue(project, ID)
        run_dir = project / "run"
        snap = snapshot_issue(
            _config(project), ID, run_dir, readiness_threshold=85, outcome_threshold=65
        )
        assert (snap.refine_cap, snap.refine_count) == (5, 0)
        (project / ".ll" / "ll-config.json").write_text('{"commands": {"max_refine_count": 3}}')
        snap = snapshot_issue(
            _config(project), ID, run_dir, readiness_threshold=85, outcome_threshold=65
        )
        assert snap.refine_cap == 3

    def test_next_obligation_probe_skips_tier1_and_honors_the_waiver(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import little_loops.cli.issues.next_obligation as nob
        from little_loops.preparation_policy import snapshot_issue

        seen: dict[str, object] = {}

        def fake(config: object, issue_id: str, **kw: object) -> None:
            seen.update(kw)
            return None

        monkeypatch.setattr(nob, "select_next_obligation", fake)
        _write_issue(project, ID)
        snap = snapshot_issue(
            _config(project), ID, project / "run", readiness_threshold=85, outcome_threshold=65
        )
        assert seen["honor_waiver"] is True
        skip = set(seen["skip"])  # type: ignore[arg-type]
        for tier1 in (
            "FORMAT",
            "VERIFY",
            "HEDGES",
            "PLACEHOLDERS",
            "ACCEPTANCE_CRITERIA",
            "DESIGN",
        ):
            assert any(getattr(o, "name", o) == tier1 for o in skip), tier1
        assert snap.obligation_post == "ERROR"  # a None probe result reads as _error

    def test_probe_exception_reads_as_error(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import little_loops.cli.issues.next_obligation as nob
        from little_loops.preparation_policy import snapshot_issue

        def boom(*_a: object, **_kw: object) -> None:
            raise RuntimeError("probe failed")

        monkeypatch.setattr(nob, "select_next_obligation", boom)
        _write_issue(project, ID)
        snap = snapshot_issue(
            _config(project), ID, project / "run", readiness_threshold=85, outcome_threshold=65
        )
        assert snap.obligation_post == "ERROR"


class TestDecisionExhausted:
    def test_open_issue_is_deferred_and_ledgered(self, project: Path) -> None:
        _write_issue(project, ID)
        run_dir = project / "run"
        run_dir.mkdir()
        (run_dir / "autodev-inflight").write_text(ID)
        config = _config(project)
        append_fact(
            run_dir, ID, Fact("0", 0, "obs", "pass_start", {"pre_readiness": "", "pre_ids": []})
        )
        append_fact(
            run_dir,
            ID,
            Fact("0", 1, "intent", StepKind.STOP.value, {"outcome": "decision_exhausted"}),
        )
        assert _apply(config, run_dir, "decision_exhausted") == 1
        assert _rows(run_dir) == [f"{ID}  decision_unresolved"]
        assert _token(config, run_dir) == "BLOCKED:decision_unresolved"
        content = (project / ".issues" / "enhancements" / f"P3-{ID}-test.md").read_text()
        assert "status: deferred" in content and "deferred_reason: decision_unresolved" in content
        assert not (run_dir / "autodev-inflight").exists()

    @pytest.mark.parametrize(
        ("status", "token"), [("done", "DECOMPOSED"), ("cancelled", "CANCELLED")]
    )
    def test_resolved_issue_is_never_deferred(self, project: Path, status: str, token: str) -> None:
        """BUG-2729: a resolved issue at decision exhaustion is never deferred; it ends
        DECOMPOSED (a cancelled one records CANCELLED, outcome_from_legacy_class rule 1)."""
        path = _write_issue(project, ID)
        path.write_text(path.read_text().replace("status: open", f"status: {status}"))
        run_dir = project / "run"
        config = _config(project)
        append_fact(
            run_dir, ID, Fact("0", 0, "obs", "pass_start", {"pre_readiness": "", "pre_ids": []})
        )
        append_fact(
            run_dir,
            ID,
            Fact("0", 1, "intent", StepKind.STOP.value, {"outcome": "decision_exhausted"}),
        )
        assert _apply(config, run_dir, "decision_exhausted") == 0
        assert _rows(run_dir) == []
        assert _token(config, run_dir) == token
        assert f"status: {status}" in path.read_text()
