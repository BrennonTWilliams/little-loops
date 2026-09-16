"""Tests for `ll-loop evidence` (FEAT-3182): the deterministic verification-
evidence bundle exporter.

Promoted from `scripts/tests/spike/verify_evidence_bundle/` (deleted on this
promotion, step 3g) with the fixture rebuilt to match the extended
`archive_run()` layout (probe files land directly in the archive dir, not
nested under a separate run_dir) plus new coverage for the gap taxonomy the
Program Design/Design Review passes added: missing_head_sha,
missing_issue_path, issue_not_committed_at_head, head_sha_changed_across_resume,
worktree_changed_during_run, missing_probe_files (adversarial-only),
loop_runs_row_stale, and missing_loop_complete.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from little_loops.cli.loop.evidence import (
    _EVIDENTIARY_SOURCES,
    ContextEntry,
    allowlisted_loop_run_dict,
    assemble_bundle,
    cmd_evidence,
    compute_git_predicates,
)
from little_loops.fsm.persistence import BEST_EFFORT_FILENAME

from .helpers import copy_git_template

_LOOP_RUNS_ROW = allowlisted_loop_run_dict(
    {
        "run_id": "20260902T120000-verify-feat-3182",
        "loop_name": "verify-feat-3182",
        "started_at": "2026-09-02T12:00:00+00:00",
        "ended_at": "2026-09-02T12:04:11+00:00",
        "final_state": "done",
        "iterations": 4,
        "terminated_by": "terminal",
        "failure_terminal": 0,
        "head_sha": "a" * 40,
        "branch": "main",
        "error": None,
        "evaluator_score": None,
    }
)

_GIT_PREDICATES = {
    "head_sha_live": "true",
    "head_sha_is_ancestor_of_head": "true",
    "issue_blob_sha": "b" * 40,
}


def _events_jsonl(events: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(e) for e in events)


def _loop_start(**overrides: Any) -> dict[str, Any]:
    event = {
        "event": "loop_start",
        "head_sha": "a" * 40,
        "branch": "main",
        "worktree_digest": "digest-start",
        "loop_yaml_path": "/tmp/does-not-exist.yaml",
        "loop_yaml_sha256": "c" * 64,
    }
    event.update(overrides)
    return event


def _loop_complete(**overrides: Any) -> dict[str, Any]:
    event = {
        "event": "loop_complete",
        "final_state": "done",
        "terminated_by": "terminal",
        "iterations": 4,
        "worktree_digest": "digest-start",
    }
    event.update(overrides)
    return event


def build_archive_dir(
    tmp_path: Path,
    *,
    loop_name: str = "verify-feat-3182",
    issue_path: str | None = ".issues/features/P2-FEAT-3182-sample.md",
    events: list[dict[str, Any]] | None = None,
    probe_files: dict[str, dict] | None = None,
) -> Path:
    """Build a fixture archive dir matching the extended archive_run() layout."""
    archive_dir = tmp_path / "20260902T120000-verify-feat-3182"
    archive_dir.mkdir(parents=True, exist_ok=True)

    context: dict[str, Any] = {"issue_id": "FEAT-3182"}
    if issue_path is not None:
        context["issue_path"] = issue_path
    state = {
        "loop_name": loop_name,
        "context": context,
        "captured": {
            "criterion-1": {
                "verdict": "yes",
                "reason": "Bundle contents are enumerable and source-traced.",
            },
        },
    }
    (archive_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")

    if events is None:
        events = [
            {"event": "state_enter", "state": "verify-criterion-1"},
            _loop_start(),
            {
                "event": "evaluate",
                "state": "verify-criterion-1",
                "llm_model": "claude-sonnet-5",
                "llm_prompt": "Does the bundle enumerate every entry's source?",
                "reason": "Every EvidenceEntry declares a source field.",
                "evidence": "bundle.py:EvidenceEntry.source",
                "raw": {"verdict": "yes"},
            },
            _loop_complete(),
        ]
    (archive_dir / "events.jsonl").write_text(_events_jsonl(events), encoding="utf-8")

    for name, content in (probe_files or {}).items():
        (archive_dir / name).write_text(json.dumps(content), encoding="utf-8")

    return archive_dir


_ADVERSARIAL_PROBE_FILES = {
    "probe-boundary.json": {"probe_class": "boundary", "break_found": False},
    "probe-malformed-hostile.json": {"probe_class": "malformed", "break_found": False},
    "probe-failure-mode.json": {"probe_class": "failure_mode", "break_found": False},
}


class TestEvidenceEntryTracing:
    def test_llm_sourced_fields_never_land_in_evidentiary(self, tmp_path: Path) -> None:
        run_dir = build_archive_dir(tmp_path)
        bundle = assemble_bundle(_LOOP_RUNS_ROW, run_dir, _GIT_PREDICATES)

        assert bundle.context_non_evidentiary, "fixture must exercise the LLM-sourced path"
        evidentiary_keys = {e.key for e in bundle.evidentiary}
        for entry in bundle.context_non_evidentiary:
            assert entry.key not in evidentiary_keys
        assert not any(k.startswith("captured.") for k in evidentiary_keys)
        assert not any(k.startswith("evaluate.") for k in evidentiary_keys)

    def test_every_evidentiary_entry_traces_to_deterministic_source(self, tmp_path: Path) -> None:
        run_dir = build_archive_dir(tmp_path)
        bundle = assemble_bundle(_LOOP_RUNS_ROW, run_dir, _GIT_PREDICATES)

        assert bundle.evidentiary, "fixture must produce at least one evidentiary entry"
        for entry in bundle.evidentiary:
            assert entry.source in _EVIDENTIARY_SOURCES
        for entry in bundle.evidentiary:
            if entry.key.startswith("credential_scan."):
                assert entry.source == "scanner"
            else:
                assert entry.source != "scanner"

    def test_bundle_is_plain_json_no_custom_types(self, tmp_path: Path) -> None:
        run_dir = build_archive_dir(tmp_path)
        bundle = assemble_bundle(_LOOP_RUNS_ROW, run_dir, _GIT_PREDICATES)

        reencoded = json.dumps(bundle.to_dict(), sort_keys=True)
        assert json.loads(reencoded) == bundle.to_dict()

    def test_carries_schema_version_and_comment_no_timestamp(self, tmp_path: Path) -> None:
        run_dir = build_archive_dir(tmp_path)
        bundle = assemble_bundle(_LOOP_RUNS_ROW, run_dir, _GIT_PREDICATES)
        data = bundle.to_dict()

        assert data["schema_version"] == 1
        assert "ll-loop evidence" in data["_comment"]
        assert "ts" not in data and "timestamp" not in data and "generated_at" not in data


class TestReproducibility:
    def test_rerun_over_unchanged_inputs_is_byte_identical(self, tmp_path: Path) -> None:
        run_dir = build_archive_dir(tmp_path)
        first = assemble_bundle(_LOOP_RUNS_ROW, run_dir, _GIT_PREDICATES).canonical_json()
        second = assemble_bundle(_LOOP_RUNS_ROW, run_dir, _GIT_PREDICATES).canonical_json()
        assert first == second


class TestAllowlist:
    def test_error_and_evaluator_score_never_land_in_evidentiary(self) -> None:
        row = allowlisted_loop_run_dict(
            {
                "run_id": "r1",
                "loop_name": "x",
                "error": "boom",
                "evaluator_score": 0.9,
            }
        )
        assert "error" not in row
        assert "evaluator_score" not in row

    def test_failure_terminal_is_allowlisted(self) -> None:
        row = allowlisted_loop_run_dict({"run_id": "r1", "loop_name": "x", "failure_terminal": 1})
        assert row["failure_terminal"] == 1


class TestGapTaxonomy:
    def test_missing_run_dir_produces_explicit_gap(self, tmp_path: Path) -> None:
        absent = tmp_path / "no-such-run"
        bundle = assemble_bundle(_LOOP_RUNS_ROW, absent, _GIT_PREDICATES)

        assert bundle.has_gaps
        assert any(g.category == "missing_run_dir" for g in bundle.gaps)
        assert any(e.source == "history_db_row" for e in bundle.evidentiary)

    def test_missing_loop_runs_row_produces_explicit_gap(self, tmp_path: Path) -> None:
        run_dir = build_archive_dir(tmp_path)
        bundle = assemble_bundle(None, run_dir, _GIT_PREDICATES)

        assert bundle.has_gaps
        assert any(g.category == "missing_loop_runs_row" for g in bundle.gaps)

    def test_missing_head_sha_when_loop_start_lacks_it(self, tmp_path: Path) -> None:
        events = [_loop_start(head_sha=None, branch=None, worktree_digest=None), _loop_complete()]
        run_dir = build_archive_dir(tmp_path, events=events)
        bundle = assemble_bundle(_LOOP_RUNS_ROW, run_dir, {})

        assert any(g.category == "missing_head_sha" for g in bundle.gaps)

    def test_missing_issue_path_when_context_lacks_it(self, tmp_path: Path) -> None:
        run_dir = build_archive_dir(tmp_path, issue_path=None)
        bundle = assemble_bundle(_LOOP_RUNS_ROW, run_dir, _GIT_PREDICATES)

        assert any(g.category == "missing_issue_path" for g in bundle.gaps)

    def test_issue_not_committed_at_head_when_blob_sha_absent(self, tmp_path: Path) -> None:
        run_dir = build_archive_dir(tmp_path)
        predicates = {k: v for k, v in _GIT_PREDICATES.items() if k != "issue_blob_sha"}
        bundle = assemble_bundle(_LOOP_RUNS_ROW, run_dir, predicates)

        assert any(g.category == "issue_not_committed_at_head" for g in bundle.gaps)

    def test_head_sha_changed_across_resume(self, tmp_path: Path) -> None:
        events = [
            _loop_start(),
            _loop_start(head_sha="d" * 40),
            _loop_complete(),
        ]
        run_dir = build_archive_dir(tmp_path, events=events)
        bundle = assemble_bundle(_LOOP_RUNS_ROW, run_dir, _GIT_PREDICATES)

        assert any(g.category == "head_sha_changed_across_resume" for g in bundle.gaps)

    def test_worktree_changed_during_run(self, tmp_path: Path) -> None:
        events = [_loop_start(), _loop_complete(worktree_digest="digest-end")]
        run_dir = build_archive_dir(tmp_path, events=events)
        bundle = assemble_bundle(_LOOP_RUNS_ROW, run_dir, _GIT_PREDICATES)

        assert any(g.category == "worktree_changed_during_run" for g in bundle.gaps)

    def test_missing_loop_complete_when_no_such_event(self, tmp_path: Path) -> None:
        events = [_loop_start()]
        run_dir = build_archive_dir(tmp_path, events=events)
        bundle = assemble_bundle(_LOOP_RUNS_ROW, run_dir, _GIT_PREDICATES)

        assert any(g.category == "missing_loop_complete" for g in bundle.gaps)

    def test_loop_runs_row_stale_when_row_disagrees_with_last_loop_complete(
        self, tmp_path: Path
    ) -> None:
        events = [_loop_start(), _loop_complete(final_state="failed", terminated_by="terminal")]
        run_dir = build_archive_dir(tmp_path, events=events)
        bundle = assemble_bundle(
            _LOOP_RUNS_ROW, run_dir, _GIT_PREDICATES
        )  # row says final_state=done

        assert any(g.category == "loop_runs_row_stale" for g in bundle.gaps)

    def test_zero_probes_in_adversarial_mode_is_a_gap(self, tmp_path: Path) -> None:
        run_dir = build_archive_dir(tmp_path, loop_name="adversarial-feat-3182")
        bundle = assemble_bundle(_LOOP_RUNS_ROW, run_dir, _GIT_PREDICATES)

        assert any(g.category == "missing_probe_files" for g in bundle.gaps)

    def test_zero_probes_in_criteria_mode_is_not_a_gap(self, tmp_path: Path) -> None:
        run_dir = build_archive_dir(tmp_path, loop_name="verify-feat-3182")
        bundle = assemble_bundle(_LOOP_RUNS_ROW, run_dir, _GIT_PREDICATES)

        assert not any(g.category == "missing_probe_files" for g in bundle.gaps)

    def test_three_probes_in_adversarial_mode_is_not_a_gap(self, tmp_path: Path) -> None:
        run_dir = build_archive_dir(
            tmp_path, loop_name="adversarial-feat-3182", probe_files=_ADVERSARIAL_PROBE_FILES
        )
        bundle = assemble_bundle(_LOOP_RUNS_ROW, run_dir, _GIT_PREDICATES)

        assert not any(g.category == "missing_probe_files" for g in bundle.gaps)
        count_entry = next(e for e in bundle.evidentiary if e.key == "probe_file_count")
        assert count_entry.value == 3


def _fake_aws_key() -> str:
    """Fragment-assembled fake AWS access key -- never a committed literal."""
    return "".join(["AKIA", "1234", "ABCD", "5678", "WXYZ"])


class TestCredentialScan:
    def test_clean_run_has_zero_hits_and_scalar_keys(self, tmp_path: Path) -> None:
        run_dir = build_archive_dir(tmp_path)
        bundle = assemble_bundle(_LOOP_RUNS_ROW, run_dir, _GIT_PREDICATES)

        scan_entries = {
            e.key: e for e in bundle.evidentiary if e.key.startswith("credential_scan.")
        }
        assert scan_entries["credential_scan.hit_count"].value == 0
        assert scan_entries["credential_scan.hits"].value == []
        for key in ("tool", "version", "rules_sha", "hit_count", "hits"):
            assert scan_entries[f"credential_scan.{key}"].source == "scanner"
        assert not any(g.category == "credential_hits" for g in bundle.gaps)

    def test_hit_in_events_jsonl(self, tmp_path: Path) -> None:
        token = _fake_aws_key()
        events = [
            _loop_start(),
            {
                "event": "evaluate",
                "state": "verify-criterion-1",
                "llm_model": "claude-sonnet-5",
                "raw": {"quoted": token},
            },
            _loop_complete(),
        ]
        run_dir = build_archive_dir(tmp_path, events=events)
        bundle = assemble_bundle(_LOOP_RUNS_ROW, run_dir, _GIT_PREDICATES)

        hits = next(e for e in bundle.evidentiary if e.key == "credential_scan.hits").value
        assert len(hits) == 1
        assert hits[0]["target"] == "events.jsonl"
        assert hits[0]["rule"] == "aws_access_key"
        assert any(g.category == "credential_hits" for g in bundle.gaps)
        assert bundle.has_gaps

        for entry in bundle.evidentiary:
            if entry.key.startswith("credential_scan."):
                assert token not in json.dumps(entry.value)
        for gap in bundle.gaps:
            assert token not in gap.detail
        assert any(token in json.dumps(c.value) for c in bundle.context_non_evidentiary)

    def test_hit_in_context_extra(self, tmp_path: Path) -> None:
        token = _fake_aws_key()
        run_dir = build_archive_dir(tmp_path)
        context_extra = [
            ContextEntry(key="loop_runs.error", value=f"boom: {token}", llm_sourced=False)
        ]
        bundle = assemble_bundle(
            _LOOP_RUNS_ROW, run_dir, _GIT_PREDICATES, context_extra=context_extra
        )

        hits = next(e for e in bundle.evidentiary if e.key == "credential_scan.hits").value
        assert any(h["target"] == "context:loop_runs.error" for h in hits)

    def test_no_double_counting_for_context_covered_by_file_scan(self, tmp_path: Path) -> None:
        token = _fake_aws_key()
        events = [
            _loop_start(),
            {
                "event": "evaluate",
                "state": "verify-criterion-1",
                "llm_model": "claude-sonnet-5",
                "raw": {"quoted": token},
            },
            _loop_complete(),
        ]
        run_dir = build_archive_dir(tmp_path, events=events)
        bundle = assemble_bundle(_LOOP_RUNS_ROW, run_dir, _GIT_PREDICATES)

        hits = next(e for e in bundle.evidentiary if e.key == "credential_scan.hits").value
        assert len(hits) == 1
        assert not any(h["target"].startswith("context:evaluate.") for h in hits)

    def test_best_effort_json_hashed_and_credential_scanned(self, tmp_path: Path) -> None:
        """ENH-3473: best_effort.json, when present in the archive, is hashed
        into the bundle and included in the credential-pattern scan targets."""
        token = _fake_aws_key()
        run_dir = build_archive_dir(tmp_path)
        (run_dir / BEST_EFFORT_FILENAME).write_text(
            json.dumps({"metadata": {"best_effort": True}, "captured": {"secret": token}}),
            encoding="utf-8",
        )

        bundle = assemble_bundle(_LOOP_RUNS_ROW, run_dir, _GIT_PREDICATES)

        hash_keys = {e.key for e in bundle.evidentiary if e.key.startswith("file.")}
        assert f"file.{BEST_EFFORT_FILENAME}.sha256" in hash_keys

        hits = next(e for e in bundle.evidentiary if e.key == "credential_scan.hits").value
        assert any(h["target"] == BEST_EFFORT_FILENAME for h in hits)

    def test_missing_run_dir_still_emits_scan_record_and_scans_context_extra(
        self, tmp_path: Path
    ) -> None:
        token = _fake_aws_key()
        absent = tmp_path / "no-such-run"
        context_extra = [
            ContextEntry(key="loop_runs.error", value=f"boom: {token}", llm_sourced=False)
        ]
        bundle = assemble_bundle(_LOOP_RUNS_ROW, absent, {}, context_extra=context_extra)

        scan_keys = {e.key for e in bundle.evidentiary if e.key.startswith("credential_scan.")}
        assert scan_keys == {
            "credential_scan.tool",
            "credential_scan.version",
            "credential_scan.rules_sha",
            "credential_scan.hit_count",
            "credential_scan.hits",
        }
        assert any(c.key == "loop_runs.error" for c in bundle.context_non_evidentiary)
        hits = next(e for e in bundle.evidentiary if e.key == "credential_scan.hits").value
        assert any(h["target"] == "context:loop_runs.error" for h in hits)
        assert any(g.category == "missing_run_dir" for g in bundle.gaps)
        assert any(g.category == "credential_hits" for g in bundle.gaps)

    def test_reproducibility_with_hits_is_byte_identical(self, tmp_path: Path) -> None:
        token = _fake_aws_key()
        events = [
            _loop_start(),
            {
                "event": "evaluate",
                "state": "verify-criterion-1",
                "llm_model": "claude-sonnet-5",
                "raw": {"quoted": token},
            },
            _loop_complete(),
        ]
        run_dir = build_archive_dir(tmp_path, events=events)
        first = assemble_bundle(_LOOP_RUNS_ROW, run_dir, _GIT_PREDICATES).canonical_json()
        second = assemble_bundle(_LOOP_RUNS_ROW, run_dir, _GIT_PREDICATES).canonical_json()
        assert first == second

    def test_segregation_credential_scan_keys_never_in_context(self, tmp_path: Path) -> None:
        run_dir = build_archive_dir(tmp_path)
        bundle = assemble_bundle(_LOOP_RUNS_ROW, run_dir, _GIT_PREDICATES)

        context_keys = {c.key for c in bundle.context_non_evidentiary}
        assert not any(k.startswith("credential_scan.") for k in context_keys)


class TestComputeGitPredicates:
    def test_no_head_sha_returns_empty(self, tmp_path: Path) -> None:
        assert compute_git_predicates(tmp_path, None, None) == {}

    def test_live_ancestor_ref_and_issue_blob(self, tmp_path: Path) -> None:
        repo = copy_git_template(tmp_path)
        (repo / "issue.md").write_text("hello\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "init"], cwd=repo, capture_output=True, check=True
        )
        head_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()

        predicates = compute_git_predicates(repo, head_sha, "issue.md")

        assert predicates["head_sha_live"] == "true"
        assert predicates["head_sha_is_ancestor_of_head"] == "true"
        assert "issue_blob_sha" in predicates

    def test_unknown_head_sha_is_not_live(self, tmp_path: Path) -> None:
        repo = copy_git_template(tmp_path)
        (repo / "f.txt").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "init"], cwd=repo, capture_output=True, check=True
        )

        predicates = compute_git_predicates(repo, "f" * 40, None)

        assert predicates["head_sha_live"] == "false"
        assert "issue_blob_sha" not in predicates


class TestCmdEvidenceEndToEnd:
    def test_resolves_run_reads_row_and_writes_output(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        import argparse

        from little_loops.session_store import record_loop_run_summary, resolve_history_db

        repo = copy_git_template(tmp_path)
        issue_rel = ".issues/features/P2-FEAT-3182-sample.md"
        issue_path = repo / issue_rel
        issue_path.parent.mkdir(parents=True, exist_ok=True)
        issue_path.write_text("# FEAT-3182\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "init"], cwd=repo, capture_output=True, check=True
        )
        head_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()

        monkeypatch.chdir(repo)
        loops_dir = repo / ".loops"
        history_dir = loops_dir / ".history"
        run_id = "20260902T120000-verify-feat-3182"
        archive_dir = history_dir / run_id
        archive_dir.mkdir(parents=True)
        state = {
            "loop_name": "verify-feat-3182",
            "context": {"issue_id": "FEAT-3182", "issue_path": issue_rel},
            "captured": {},
        }
        (archive_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
        events = [
            _loop_start(head_sha=head_sha, branch="main"),
            _loop_complete(worktree_digest="digest-start"),
        ]
        (archive_dir / "events.jsonl").write_text(_events_jsonl(events), encoding="utf-8")

        db_path = resolve_history_db()
        record_loop_run_summary(
            db_path,
            run_id=run_id,
            loop_name="verify-feat-3182",
            terminated_by="terminal",
            final_state="done",
            iterations=4,
            head_sha=head_sha,
            branch="main",
        )

        output_path = tmp_path / "bundle.json"
        args = argparse.Namespace(run=run_id, latest=None, output=output_path, json=False)
        exit_code = cmd_evidence(args, loops_dir)

        assert exit_code == 0
        assert output_path.exists()
        written = json.loads(output_path.read_text(encoding="utf-8"))
        assert written["schema_version"] == 1
        assert not written["has_gaps"], written["gaps"]
        keys = {e["key"] for e in written["evidentiary"]}
        assert "run.head_sha" in keys
        assert "git.issue_blob_sha" in keys

    def test_unresolvable_run_returns_exit_1(self, tmp_path: Path) -> None:
        import argparse

        loops_dir = tmp_path / ".loops"
        args = argparse.Namespace(run="no-such-run", latest=None, output=None, json=False)
        assert cmd_evidence(args, loops_dir) == 1

    def test_credential_hit_returns_exit_2_and_still_writes_output(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        import argparse

        from little_loops.session_store import record_loop_run_summary, resolve_history_db

        token = _fake_aws_key()
        repo = copy_git_template(tmp_path)
        issue_rel = ".issues/features/P2-FEAT-3182-sample.md"
        issue_path = repo / issue_rel
        issue_path.parent.mkdir(parents=True, exist_ok=True)
        issue_path.write_text("# FEAT-3182\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "init"], cwd=repo, capture_output=True, check=True
        )
        head_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()

        monkeypatch.chdir(repo)
        loops_dir = repo / ".loops"
        history_dir = loops_dir / ".history"
        run_id = "20260902T120000-verify-feat-3182"
        archive_dir = history_dir / run_id
        archive_dir.mkdir(parents=True)
        state = {
            "loop_name": "verify-feat-3182",
            "context": {"issue_id": "FEAT-3182", "issue_path": issue_rel},
            "captured": {},
        }
        (archive_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
        events = [
            _loop_start(head_sha=head_sha, branch="main"),
            {"event": "evaluate", "state": "s1", "llm_model": "claude-sonnet-5", "raw": token},
            _loop_complete(worktree_digest="digest-start"),
        ]
        (archive_dir / "events.jsonl").write_text(_events_jsonl(events), encoding="utf-8")

        db_path = resolve_history_db()
        record_loop_run_summary(
            db_path,
            run_id=run_id,
            loop_name="verify-feat-3182",
            terminated_by="terminal",
            final_state="done",
            iterations=4,
            head_sha=head_sha,
            branch="main",
        )

        output_path = tmp_path / "bundle.json"
        args = argparse.Namespace(run=run_id, latest=None, output=output_path, json=False)
        exit_code = cmd_evidence(args, loops_dir)

        assert exit_code == 2
        assert output_path.exists()
        written = json.loads(output_path.read_text(encoding="utf-8"))
        assert written["has_gaps"]
        assert any(g["category"] == "credential_hits" for g in written["gaps"])
