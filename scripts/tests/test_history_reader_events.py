"""Tests for events.py: the four small tail domains (verdict events, advisor consults, research triage, review events) (ENH-2775 split from test_history_reader.py). TestNewEventReaders is a grab-bag class kept whole per ENH-2775's Suggested Approach; its methods use function-local imports throughout, so this file needs no history_reader/session_store imports at module level."""

from __future__ import annotations

from pathlib import Path


class TestNewEventReaders:
    """ENH-2458/2459/2460/2462: readers for commit, test-run, and skill completion data."""

    def test_recent_skill_events_includes_completion_columns(self, tmp_path: Path) -> None:
        from little_loops.history_reader import recent_skill_events
        from little_loops.session_store import record_skill_event, skill_event_context

        db = tmp_path / "history.db"
        with skill_event_context(db, "s1", "refine-issue", "ENH-1"):
            pass
        record_skill_event(db, "s2", "refine-issue", "ENH-2")  # dispatch-only

        events = recent_skill_events("refine-issue", db=db)
        assert len(events) == 2
        # Newest first: dispatch-only row has NULL completion columns
        assert events[0].success is None
        assert events[1].success == 1
        assert events[1].exit_code == 0
        assert events[1].duration_ms is not None

    def test_summarize_skills_success_rate(self, tmp_path: Path) -> None:
        import pytest as _pytest

        from little_loops.history_reader import summarize_skills
        from little_loops.session_store import record_skill_event, skill_event_context

        db = tmp_path / "history.db"
        with skill_event_context(db, "s1", "check-code", ""):
            pass
        with _pytest.raises(RuntimeError):
            with skill_event_context(db, "s2", "check-code", ""):
                raise RuntimeError("boom")
        record_skill_event(db, "s3", "check-code", "")  # dispatch-only, no completion

        stats = summarize_skills(db=db)
        assert len(stats) == 1
        s = stats[0]
        assert s["skill_name"] == "check-code"
        assert s["invocations"] == 3
        assert s["completions"] == 2
        assert s["successes"] == 1
        assert s["success_rate"] == 0.5

    def test_recent_commit_events_filters(self, tmp_path: Path) -> None:
        from little_loops.history_reader import recent_commit_events
        from little_loops.session_store import record_commit_event

        db = tmp_path / "history.db"
        record_commit_event(db, "sha1", "fix BUG-1", branch="main", ts="2026-07-01T10:00:00Z")
        record_commit_event(
            db, "sha2", "Closes ENH-2458", branch="feat/x", ts="2026-07-01T11:00:00Z"
        )

        all_events = recent_commit_events(db=db)
        assert [e.commit_sha for e in all_events] == ["sha2", "sha1"]

        by_issue = recent_commit_events(issue_id="ENH-2458", db=db)
        assert len(by_issue) == 1
        assert by_issue[0].commit_sha == "sha2"

        by_branch = recent_commit_events(branch="main", db=db)
        assert len(by_branch) == 1
        assert by_branch[0].issue_id == "BUG-1"

    def test_commit_issue_for_sha_reverse_lookup(self, tmp_path: Path) -> None:
        """FEAT-2867: SHA -> issue_id, the reverse of recent_commit_events(issue_id=...)."""
        from little_loops.history_reader import commit_issue_for_sha
        from little_loops.session_store import record_commit_event

        db = tmp_path / "history.db"
        record_commit_event(db, "sha1", "fix BUG-1", ts="2026-07-01T10:00:00Z")

        assert commit_issue_for_sha("sha1", db=db) == "BUG-1"
        assert commit_issue_for_sha("nonexistent", db=db) is None
        assert commit_issue_for_sha("sha1", db=tmp_path / "missing.db") is None

    def test_recent_prompt_opt_events_filters(self, tmp_path: Path) -> None:
        from little_loops.history_reader import recent_prompt_opt_events
        from little_loops.session_store import record_prompt_opt_event

        db = tmp_path / "history.db"
        record_prompt_opt_event(
            db,
            ts="2026-07-23T10:00:00Z",
            session_id="s1",
            mode="quick",
            offered=True,
        )
        record_prompt_opt_event(
            db,
            ts="2026-07-23T11:00:00Z",
            session_id="s2",
            mode="thorough",
            offered=False,
            bypass_reason="short",
        )

        all_events = recent_prompt_opt_events(db=db)
        assert [e.session_id for e in all_events] == ["s2", "s1"]

        by_mode = recent_prompt_opt_events(mode="quick", db=db)
        assert len(by_mode) == 1
        assert by_mode[0].session_id == "s1"

        since_events = recent_prompt_opt_events(since="2026-07-23T10:30:00Z", db=db)
        assert len(since_events) == 1
        assert since_events[0].session_id == "s2"

    def test_prompt_opt_offer_rate(self, tmp_path: Path) -> None:
        import pytest as _pytest

        from little_loops.history_reader import prompt_opt_offer_rate
        from little_loops.session_store import record_prompt_opt_event

        db = tmp_path / "history.db"
        assert prompt_opt_offer_rate(db=db) is None

        record_prompt_opt_event(db, ts="2026-07-23T10:00:00Z", session_id="s1", offered=True)
        record_prompt_opt_event(db, ts="2026-07-23T10:01:00Z", session_id="s2", offered=False)
        record_prompt_opt_event(db, ts="2026-07-23T10:02:00Z", session_id="s3", offered=False)

        assert prompt_opt_offer_rate(db=db) == _pytest.approx(1 / 3)

    def test_recent_learning_tests_and_find(self, tmp_path: Path) -> None:
        from little_loops.history_reader import find_learning_test, recent_learning_tests
        from little_loops.learning_tests import Assertion, LearnTestRecord, write_record
        from little_loops.session_store import record_learning_test_event

        registry_dir = tmp_path / "registry"
        registry_dir.mkdir()
        path = write_record(
            LearnTestRecord(
                target="anthropic",
                date="2026-07-19",
                status="proven",
                assertions=[Assertion(claim="streaming works", result="pass")],
                raw_output_path=None,
            ),
            base_dir=registry_dir,
        )

        db = tmp_path / "history.db"
        record_learning_test_event(db, "anthropic", str(path))

        events = recent_learning_tests(db=db)
        assert len(events) == 1
        assert events[0].record_id == "anthropic"
        assert events[0].status == "proven"

        by_status = recent_learning_tests(status="stale", db=db)
        assert by_status == []

        found = find_learning_test("anthropic", db=db)
        assert found is not None
        assert found.target == "anthropic"

        assert find_learning_test("no-such-target", db=db) is None

    def test_recent_test_runs_and_pass_rate(self, tmp_path: Path) -> None:
        from little_loops.history_reader import recent_test_runs
        from little_loops.session_store import record_test_run_event

        db = tmp_path / "history.db"
        record_test_run_event(
            db,
            ts="2026-07-01T10:00:00Z",
            total=10,
            passed=9,
            failed=1,
            head_sha="aaa",
            branch="main",
        )
        record_test_run_event(db, ts="2026-07-01T11:00:00Z", total=0, head_sha="bbb")

        runs = recent_test_runs(db=db)
        assert len(runs) == 2
        assert runs[1].pass_rate == 0.9
        assert runs[0].pass_rate is None  # total=0 → undefined

        by_sha = recent_test_runs(head_sha="aaa", db=db)
        assert len(by_sha) == 1
        assert by_sha[0].branch == "main"

    def test_recent_verdict_events_and_pass_rate(self, tmp_path: Path) -> None:
        from little_loops.history_reader import recent_verdict_events, verdict_pass_rate
        from little_loops.session_store import record_verdict_event

        db = tmp_path / "history.db"
        record_verdict_event(
            db,
            ts="2026-07-23T10:00:00Z",
            session_id=None,
            verdict_kind="ready-issue",
            target_kind="issue",
            target_id="BUG-2501",
            verdict="pass",
            severity_counts={"p0": 0, "p1": 2},
            confidence=97,
        )
        record_verdict_event(
            db,
            ts="2026-07-23T11:00:00Z",
            session_id=None,
            verdict_kind="ready-issue",
            target_kind="issue",
            target_id="BUG-2501",
            verdict="fail",
        )

        rows = recent_verdict_events(db=db)
        assert len(rows) == 2
        assert rows[0].ts > rows[1].ts
        assert rows[0].verdict == "fail"

        by_target = recent_verdict_events(target_id="BUG-2501", db=db)
        assert len(by_target) == 2

        rates = verdict_pass_rate(db=db)
        assert len(rates) == 1
        assert rates[0]["verdict_kind"] == "ready-issue"
        assert rates[0]["invocations"] == 2
        assert rates[0]["successes"] == 1
        assert rates[0]["success_rate"] == 0.5

    def test_query_advisor_consults_and_consult_stats(self, tmp_path: Path) -> None:
        from little_loops.history_reader import consult_stats, query_advisor_consults
        from little_loops.session_store import write_advisor_consult

        db = tmp_path / "history.db"
        write_advisor_consult(
            db,
            session_id="s1",
            task_key="issue:FEAT-3300",
            signal="confidence_gate",
            advisor_host="claude-code",
            advisor_model="claude-opus-5",
            main_model="claude-sonnet-5",
            outcome="issued",
            latency_ms=4200,
            input_tokens=500,
            output_tokens=200,
            ts="2026-08-24T10:00:00Z",
        )
        write_advisor_consult(
            db,
            session_id="s1",
            task_key="issue:FEAT-3300",
            signal="loop_stall",
            advisor_host=None,
            advisor_model=None,
            main_model="claude-sonnet-5",
            outcome="budget_exhausted",
            ts="2026-08-24T11:00:00Z",
        )

        rows = query_advisor_consults(db)
        assert len(rows) == 2
        assert rows[0].ts > rows[1].ts
        assert rows[0].outcome == "budget_exhausted"

        since_rows = query_advisor_consults(db, since="2026-08-24T10:30:00Z")
        assert len(since_rows) == 1
        assert since_rows[0].outcome == "budget_exhausted"

        stats = consult_stats(db, days=30)
        assert stats.total == 2
        assert stats.skipped == 1
        assert stats.total_tokens == 700
        assert stats.by_signal == {"confidence_gate": 1, "loop_stall": 1}

    def test_research_triage_stats(self, tmp_path: Path) -> None:
        from little_loops.history_reader import research_triage_stats
        from little_loops.session_store import write_research_triage

        db = tmp_path / "history.db"
        # A first-refine invocation: refined_at is None, excluded from the headline rates.
        write_research_triage(
            db,
            issue_id="ENH-1",
            refined_at=None,
            session_id="s1",
            axes=[("locator", False, "no_qualified_refs", "")],
            ts="2026-08-24T09:00:00Z",
        )
        # Two re-refine invocations on the locator axis: one covered, one stale.
        write_research_triage(
            db,
            issue_id="ENH-2",
            refined_at="2026-08-23T00:00:00Z",
            session_id="s1",
            axes=[("locator", True, None, "Integration Map → pkg/mod.py")],
            ts="2026-08-24T10:00:00Z",
        )
        write_research_triage(
            db,
            issue_id="ENH-3",
            refined_at="2026-08-23T00:00:00Z",
            session_id="s1",
            axes=[("locator", False, "stale", "stale: pkg/mod.py changed …")],
            ts="2026-08-24T11:00:00Z",
        )
        # A program_design_unmet override row: excluded from the rates, counted separately.
        write_research_triage(
            db,
            issue_id="ENH-4",
            refined_at="2026-08-23T00:00:00Z",
            session_id="s1",
            axes=[("analyzer", False, "program_design_unmet", "Program Design gate: missing")],
            ts="2026-08-24T12:00:00Z",
        )

        stats = research_triage_stats(db)
        assert stats.first_refine_rows == 1
        assert stats.program_design_unmet_count == 1
        assert stats.re_refine_rows == 2

        locator = stats.per_axis["locator"]
        assert locator.total == 2
        assert locator.covered == 1
        assert locator.stale == 1
        assert locator.production_rate == 0.5
        assert locator.coverage_only_rate == 1.0

        assert stats.aggregate.total == 2
        assert stats.aggregate.production_rate == 0.5

    def test_research_triage_stats_empty_db_returns_zeros(self, tmp_path: Path) -> None:
        from little_loops.history_reader import research_triage_stats

        stats = research_triage_stats(tmp_path / "missing.db")
        assert stats.first_refine_rows == 0
        assert stats.re_refine_rows == 0
        assert stats.per_axis == {}
        assert stats.aggregate.total == 0

    def test_consult_stats_empty_db_returns_zeros(self, tmp_path: Path) -> None:
        from little_loops.history_reader import consult_stats

        db = tmp_path / "history.db"
        from little_loops.session_store import ensure_db

        ensure_db(db)
        stats = consult_stats(db)
        assert stats.total == 0
        assert stats.by_signal == {}
        assert stats.total_tokens == 0
        assert stats.skipped == 0

    def test_recent_review_events_and_velocity(self, tmp_path: Path) -> None:
        from little_loops.history_reader import recent_review_events, review_velocity
        from little_loops.session_store import record_review_event

        db = tmp_path / "history.db"
        record_review_event(
            db,
            ts="2026-07-06T10:00:00Z",
            session_id=None,
            reviewer_skill="audit-architecture",
            target_kind="repo",
            verdict="warn",
            severity_counts={"p0": 1, "p1": 3, "p2": 7, "info": 12},
            findings_count=23,
        )
        record_review_event(
            db,
            ts="2026-07-06T11:00:00Z",
            session_id=None,
            reviewer_skill="audit-loop-run",
            target_kind="loop",
            target_id="rn-implement",
            verdict="refused",
            severity_counts={"p0": 0, "p1": 0, "p2": 0, "info": 0},
            findings_count=0,
        )

        rows = recent_review_events(db=db)
        assert len(rows) == 2
        assert rows[0].ts > rows[1].ts
        assert rows[0].verdict == "refused"

        by_skill = recent_review_events(reviewer_skill="audit-architecture", db=db)
        assert len(by_skill) == 1
        assert by_skill[0].reviewer_skill == "audit-architecture"

        weeks = review_velocity(db=db)
        assert len(weeks) == 1
        assert weeks[0]["reviews"] == 2
        assert weeks[0]["p0"] == 1
        assert weeks[0]["p1"] == 3
        assert weeks[0]["p2"] == 7
        assert weeks[0]["info"] == 12

    def test_find_session_for_issue_transition(self, tmp_path: Path) -> None:
        from little_loops.history_reader import find_session_for_issue_transition
        from little_loops.session_store import connect

        db = tmp_path / "history.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, issue_num, transition, session_id) "
                "VALUES('2026-07-01T10:00:00Z', 'ENH-2462', 2462, 'done', 'sess-closer')"
            )
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, issue_num, transition) "
                "VALUES('2026-07-01T09:00:00Z', 'ENH-9', 9, 'done')"
            )
            conn.commit()
        finally:
            conn.close()

        assert find_session_for_issue_transition("ENH-2462", "done", db=db) == "sess-closer"
        assert find_session_for_issue_transition("ENH-9", "done", db=db) is None  # legacy row
        assert find_session_for_issue_transition("ENH-404", "done", db=db) is None

    def test_related_issue_events_session_filter(self, tmp_path: Path) -> None:
        from little_loops.history_reader import related_issue_events
        from little_loops.session_store import connect

        db = tmp_path / "history.db"
        conn = connect(db)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, issue_num, transition, session_id) "
                "VALUES('2026-07-01T10:00:00Z', 'ENH-2462', 2462, 'open', 'sess-a')"
            )
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, issue_num, transition, session_id) "
                "VALUES('2026-07-01T11:00:00Z', 'ENH-2462', 2462, 'done', 'sess-b')"
            )
            conn.commit()
        finally:
            conn.close()

        all_events = related_issue_events("ENH-2462", db=db)
        assert len(all_events) == 2
        assert {e.session_id for e in all_events} == {"sess-a", "sess-b"}

        only_b = related_issue_events("ENH-2462", session_id="sess-b", db=db)
        assert len(only_b) == 1
        assert only_b[0].transition == "done"

    def test_recent_orchestration_runs_filters(self, tmp_path: Path) -> None:
        from little_loops import history_reader, session_store

        recorder = getattr(session_store, "record_orchestration_run", None)
        reader = getattr(history_reader, "recent_orchestration_runs", None)
        assert callable(recorder), "record_orchestration_run must exist"
        assert callable(reader), "recent_orchestration_runs must exist"

        db = tmp_path / "history.db"
        recorder(
            db,
            run_id="batch-a",
            driver="ll-auto",
            issue_id="BUG-1",
            status="completed",
            duration_s=2.0,
            ended_at="2026-07-17T10:00:00Z",
        )
        recorder(
            db,
            run_id="batch-b",
            driver="ll-sprint",
            issue_id="BUG-2",
            status="failed",
            failure_reason="boom",
            duration_s=4.0,
            ended_at="2026-07-17T11:00:00Z",
        )

        rows = reader(db=db)
        assert [row.run_id for row in rows] == ["batch-b", "batch-a"]
        assert reader(driver="ll-auto", db=db)[0].issue_id == "BUG-1"
        assert reader(issue_id="BUG-2", db=db)[0].driver == "ll-sprint"
        assert reader(since="2026-07-17T10:30:00Z", db=db)[0].run_id == "batch-b"

    def test_aggregate_orchestration_runs(self, tmp_path: Path) -> None:
        from little_loops import history_reader, session_store

        recorder = getattr(session_store, "record_orchestration_run", None)
        aggregate = getattr(history_reader, "aggregate_orchestration_runs", None)
        assert callable(recorder), "record_orchestration_run must exist"
        assert callable(aggregate), "aggregate_orchestration_runs must exist"

        db = tmp_path / "history.db"
        recorder(
            db,
            run_id="r1",
            driver="ll-auto",
            issue_id="BUG-1",
            status="completed",
            duration_s=2.0,
        )
        recorder(
            db,
            run_id="r2",
            driver="ll-auto",
            issue_id="BUG-2",
            status="failed",
            duration_s=4.0,
        )
        stats = aggregate(group_by="driver", db=db)
        assert stats == [
            {
                "driver": "ll-auto",
                "runs": 2,
                "completed": 1,
                "success_rate": 0.5,
                "avg_duration_s": 3.0,
            }
        ]

    def test_recent_orchestration_runs_empty_on_missing_db(self, tmp_path: Path) -> None:
        from little_loops import history_reader

        reader = getattr(history_reader, "recent_orchestration_runs", None)
        assert callable(reader), "recent_orchestration_runs must exist"
        assert reader(db=tmp_path / "nope" / "history.db") == []

    def test_recent_loop_runs_filters(self, tmp_path: Path) -> None:
        from little_loops import history_reader, session_store

        recorder = getattr(session_store, "record_loop_run_summary", None)
        reader = getattr(history_reader, "recent_loop_runs", None)
        assert callable(recorder), "record_loop_run_summary must exist"
        assert callable(reader), "recent_loop_runs must exist"

        db = tmp_path / "history.db"
        recorder(
            db,
            run_id="20260717T100000-rn-implement",
            loop_name="rn-implement",
            terminated_by="terminal",
            ended_at="2026-07-17T10:00:00Z",
        )
        recorder(
            db,
            run_id="20260717T110000-rn-refine",
            loop_name="rn-refine",
            terminated_by="error",
            ended_at="2026-07-17T11:00:00Z",
        )

        rows = reader(db=db)
        assert [row.run_id for row in rows] == [
            "20260717T110000-rn-refine",
            "20260717T100000-rn-implement",
        ]
        assert reader(loop_name="rn-implement", db=db)[0].loop_name == "rn-implement"
        assert reader(since="2026-07-17T10:30:00Z", db=db)[0].run_id == (
            "20260717T110000-rn-refine"
        )

    def test_find_loop_run(self, tmp_path: Path) -> None:
        from little_loops import history_reader, session_store

        recorder = getattr(session_store, "record_loop_run_summary", None)
        finder = getattr(history_reader, "find_loop_run", None)
        assert callable(recorder), "record_loop_run_summary must exist"
        assert callable(finder), "find_loop_run must exist"

        db = tmp_path / "history.db"
        recorder(db, run_id="run-1", loop_name="rn-implement", terminated_by="terminal")

        found = finder("run-1", db=db)
        assert found is not None
        assert found.loop_name == "rn-implement"
        assert finder("no-such-run", db=db) is None

    def test_find_loop_run_exposes_failure_terminal(self, tmp_path: Path) -> None:
        """FEAT-3182: failure_terminal is on the loop_runs allowlist the evidence
        exporter reads; LoopRun previously omitted this existing column."""
        from little_loops import history_reader, session_store

        db = tmp_path / "history.db"
        session_store.record_loop_run_summary(
            db,
            run_id="run-failed",
            loop_name="rn-implement",
            terminated_by="terminal",
            failure_terminal=True,
        )

        found = history_reader.find_loop_run("run-failed", db=db)
        assert found is not None
        assert found.failure_terminal == 1

    def test_recent_orchestration_runs_exposes_ll_version(self, tmp_path: Path) -> None:
        """FEAT-3404: ll_version is readable through the typed reader path."""
        from little_loops import history_reader, session_store

        db = tmp_path / "history.db"
        session_store.record_orchestration_run(
            db,
            run_id="run-ver",
            driver="ll-auto",
            issue_id="FEAT-3404",
            status="completed",
            ll_version="4.2.0",
        )

        found = history_reader.recent_orchestration_runs(issue_id="FEAT-3404", db=db)
        assert found[0].ll_version == "4.2.0"

    def test_find_loop_run_exposes_ll_version(self, tmp_path: Path) -> None:
        """FEAT-3404: ll_version is readable through the typed reader path."""
        from little_loops import history_reader, session_store

        db = tmp_path / "history.db"
        session_store.record_loop_run_summary(
            db,
            run_id="run-loop-ver",
            loop_name="rn-implement",
            terminated_by="terminal",
            ll_version="4.2.0",
        )

        found = history_reader.find_loop_run("run-loop-ver", db=db)
        assert found is not None
        assert found.ll_version == "4.2.0"

    def test_aggregate_loop_runs(self, tmp_path: Path) -> None:
        from little_loops import history_reader, session_store

        recorder = getattr(session_store, "record_loop_run_summary", None)
        aggregate = getattr(history_reader, "aggregate_loop_runs", None)
        assert callable(recorder), "record_loop_run_summary must exist"
        assert callable(aggregate), "aggregate_loop_runs must exist"

        db = tmp_path / "history.db"
        recorder(
            db, run_id="run-1", loop_name="rn-implement", iterations=2, terminated_by="terminal"
        )
        recorder(
            db, run_id="run-2", loop_name="rn-implement", iterations=4, terminated_by="terminal"
        )

        stats = aggregate(group_by="loop_name", db=db)
        assert stats == [{"loop_name": "rn-implement", "runs": 2, "avg_iterations": 3.0}]

    def test_recent_loop_runs_empty_on_missing_db(self, tmp_path: Path) -> None:
        from little_loops import history_reader

        reader = getattr(history_reader, "recent_loop_runs", None)
        assert callable(reader), "recent_loop_runs must exist"
        assert reader(db=tmp_path / "nope" / "history.db") == []
        finder = getattr(history_reader, "find_loop_run", None)
        assert finder("run-1", db=tmp_path / "nope" / "history.db") is None
        aggregate = getattr(history_reader, "aggregate_loop_runs", None)
        assert aggregate(db=tmp_path / "nope" / "history.db") == []

    def test_readers_return_empty_on_missing_db(self, tmp_path: Path) -> None:
        from little_loops.history_reader import (
            find_session_for_issue_transition,
            hook_failure_rate,
            hook_latency_p95,
            prompt_opt_offer_rate,
            recent_commit_events,
            recent_hook_events,
            recent_lifecycle_events,
            recent_prompt_opt_events,
            recent_review_events,
            recent_skill_events,
            recent_test_runs,
            recent_verdict_events,
            review_velocity,
            summarize_skills,
            verdict_pass_rate,
        )

        db = tmp_path / "nope" / "history.db"
        # ensure_db creates on demand, so these return empty rather than raising
        assert recent_skill_events(db=db) == []
        assert summarize_skills(db=db) == []
        assert recent_commit_events(db=db) == []
        assert recent_test_runs(db=db) == []
        assert recent_lifecycle_events(db=db) == []
        assert find_session_for_issue_transition("X-1", "done", db=db) is None
        assert recent_hook_events(db=db) == []
        assert hook_failure_rate("PostToolUse", db=db) is None
        assert hook_latency_p95("PostToolUse", db=db) is None
        assert recent_prompt_opt_events(db=db) == []
        assert prompt_opt_offer_rate(db=db) is None
        assert recent_verdict_events(db=db) == []
        assert verdict_pass_rate(db=db) == []
        assert recent_review_events(db=db) == []
        assert review_velocity(db=db) == []
