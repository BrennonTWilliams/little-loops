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
        prep_record(config, ID, run_dir, child_terminated_by="terminal", child_failure="none")
        # Fake the inner run's record so record_token() sees READY.
        from little_loops.cli.issues.run_record import canonical_record_id
        from little_loops.run_record import RunRecord, write_run_record

        rid = canonical_record_id(config, ID)
        write_run_record(
            run_dir, RunRecord(writer="refine-to-ready-issue", issue_id=rid, outcome="ready")
        )
        step = prep_step(config, ID, run_dir, readiness_threshold=85, outcome_threshold=65)
        assert step.kind is StepKind.FINISH
        assert step.payload.get("outcome") == "ready"

        exit_code = prep_apply(config, ID, run_dir, readiness_threshold=85, outcome_threshold=65)
        assert exit_code == 0
        record = (run_dir / "run-records" / "prepare-issue" / f"{rid}.json").read_text()
        assert '"outcome": "ready"' in record


class TestPrepRecordAbsentRunRecord:
    """ENH-3630 Step 5: dedicated pin for the AC's "absent record" claim.

    ``prep_record`` classifies ``terminal`` from ``child_terminated_by`` alone (see its
    docstring: never from a stale capture file) -- there is no separate
    ``failure_terminal`` capture file for it to read, seeded stale or otherwise, so that
    half of the AC holds structurally. The other half ("an absent record means the
    child errored") only holds when the wrapper itself reports a non-terminal outcome
    (``child_terminated_by`` != ``"terminal"``, e.g. it crashed or was signalled): that
    alone drives ``terminal="error"`` -> ``decide()``'s ``inner_error`` stop, regardless
    of the run record. A clean ``child_terminated_by="terminal"`` with no run record
    (``token="MISSING"``) is NOT an error -- the token only matters for the
    CANCELLED/DECOMPOSED checks in ``after_child``, so it falls through to the normal
    readiness gate. Both halves are pinned here so the claim is exact, not just plausible.
    """

    def test_non_terminal_wrapper_outcome_with_no_run_record_is_inner_error(
        self, project: Path
    ) -> None:
        _write_issue(project, ID, frontmatter="confidence_score: 90\noutcome_confidence: 80\n")
        run_dir = project / "run"
        config = _config(project)
        prep_step(config, ID, run_dir, readiness_threshold=85, outcome_threshold=65)
        # No run-record written anywhere, and the wrapper reports it never reached a
        # terminal (child_terminated_by defaults to "" -- e.g. a crash mid-refine).
        done = prep_record(config, ID, run_dir, child_terminated_by="", child_failure="")
        assert done is not None
        assert done.payload["terminal"] == "error"
        assert done.payload["token"] == "MISSING"
        step = prep_step(config, ID, run_dir, readiness_threshold=85, outcome_threshold=65)
        assert step.kind is StepKind.STOP
        assert step.payload.get("outcome") == "inner_error"

    def test_clean_terminal_with_no_run_record_is_not_an_error(self, project: Path) -> None:
        _write_issue(project, ID, frontmatter="confidence_score: 90\noutcome_confidence: 80\n")
        run_dir = project / "run"
        config = _config(project)
        prep_step(config, ID, run_dir, readiness_threshold=85, outcome_threshold=65)
        # The wrapper says the child reached a real terminal cleanly, but nothing wrote
        # a run record for it (e.g. a slash-command inner run with no writer).
        done = prep_record(
            config, ID, run_dir, child_terminated_by="terminal", child_failure="none"
        )
        assert done is not None
        assert done.payload["terminal"] == "done"
        assert done.payload["token"] == "MISSING"
        # READY scores clear the first gate regardless of the (irrelevant) MISSING token.
        step = prep_step(config, ID, run_dir, readiness_threshold=85, outcome_threshold=65)
        assert step.kind is StepKind.FINISH
        assert step.payload.get("outcome") == "ready"


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
        assert (run_dir / "refine-terminal-class").read_text() == "infra"


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
