"""Tests for ll-issues advise-consult (ENH-3632).

Shared second-model readiness consult helper: replay, preflight, in-process
consult via `little_loops.advisor.consult_for_trigger`, verdict mapping, and
context trimming. Modeled on `test_ll_issues_next_obligation.py::TestCli` and
`test_run_record.py::TestRecordToken`.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.advisor import AdvisorVerdict, ConsultOutcome, TaskKey
from little_loops.cli.issues.advise_consult import (
    cmd_advise_consult,
    map_advise_verdict,
    trim_consult_context,
)
from little_loops.config import BRConfig

_TASK_KEY = TaskKey(kind="issue", value="ENH-9999")


@pytest.fixture(autouse=True)
def _clean_ll_issue_id_env():
    yield
    os.environ.pop("LL_ISSUE_ID", None)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    for kind in ("bugs", "features", "enhancements", "epics"):
        (tmp_path / ".issues" / kind).mkdir(parents=True, exist_ok=True)
    (tmp_path / ".ll").mkdir(exist_ok=True)
    return tmp_path


def _write_issue(
    project: Path, issue_id: str = "ENH-9999", body: str = "## Summary\n\nPlain.\n"
) -> Path:
    path = project / ".issues" / "enhancements" / f"P3-{issue_id}-test.md"
    path.write_text(
        f"---\nid: {issue_id}\ntitle: T\ntype: enhancement\nstatus: open\npriority: P3\n"
        f"---\n\n# {issue_id}: T\n\n{body}"
    )
    return path


def _args(
    issue_id: str, run_dir: Path, *, write_note: bool = False, question: str = "Ready?"
) -> argparse.Namespace:
    return argparse.Namespace(
        issue_id=issue_id,
        run_dir=str(run_dir),
        signal="refine_ready",
        question=question,
        write_note=write_note,
    )


def _configured(project: Path) -> BRConfig:
    config = BRConfig(project)
    config.advisor.host = "claude-code"
    return config


def _verdict(recommendation: str, confidence: float = 0.8) -> AdvisorVerdict:
    return AdvisorVerdict(
        recommendation=recommendation,
        risks=["some risk"],
        confidence=confidence,
        dissent="",
        signal="refine_ready",
        host="claude-code",
        model="opus",
    )


def _outcome(*, verdict=None, skipped_reason=None, error=None) -> ConsultOutcome:
    return ConsultOutcome(
        task_key=_TASK_KEY, verdict=verdict, skipped_reason=skipped_reason, error=error
    )


class TestTrimConsultContext:
    ISSUE_TEXT = """---
id: ENH-9999
title: Example
status: open
confidence_score: 90
---

# ENH-9999: Example

## Summary

Plain summary text that should survive trimming.

## Confidence Check Notes

Notes from a prior confidence-check run that should be dropped.

## Proposed Solution

Real directive content that should survive.

### Codebase Research Findings

_Added by /ll:refine-issue_ - stale anchor notes that should be dropped.

## Implementation Steps

1. Do the thing.

## Advisor Veto

A prior VETO recommendation that should never be shown back to the advisor.

## Session Log
- /ll:refine-issue - 2026-09-27
"""

    def test_strips_frontmatter(self) -> None:
        trimmed = trim_consult_context(self.ISSUE_TEXT)
        assert "confidence_score: 90" not in trimmed
        assert "id: ENH-9999" not in trimmed

    def test_strips_session_log(self) -> None:
        trimmed = trim_consult_context(self.ISSUE_TEXT)
        assert "Session Log" not in trimmed
        assert "/ll:refine-issue - 2026-09-27" not in trimmed

    def test_strips_confidence_check_notes(self) -> None:
        trimmed = trim_consult_context(self.ISSUE_TEXT)
        assert "Confidence Check Notes" not in trimmed
        assert "Notes from a prior confidence-check run" not in trimmed

    def test_strips_codebase_research_findings(self) -> None:
        trimmed = trim_consult_context(self.ISSUE_TEXT)
        assert "Codebase Research Findings" not in trimmed
        assert "stale anchor notes" not in trimmed

    def test_strips_advisor_veto(self) -> None:
        trimmed = trim_consult_context(self.ISSUE_TEXT)
        assert "Advisor Veto" not in trimmed
        assert "should never be shown back to the advisor" not in trimmed

    def test_keeps_directive_sections(self) -> None:
        trimmed = trim_consult_context(self.ISSUE_TEXT)
        assert "Plain summary text that should survive trimming." in trimmed
        assert "Real directive content that should survive." in trimmed
        assert "Do the thing." in trimmed

    def test_length_cap_applied(self) -> None:
        huge = "---\nid: ENH-1\n---\n\n## Summary\n\n" + ("word " * 20000)
        trimmed = trim_consult_context(huge)
        assert len(trimmed) < len(huge)

    def test_no_excluded_sections_only_strips_frontmatter(self) -> None:
        text = "---\nid: ENH-1\n---\n\n## Summary\n\nJust a summary.\n"
        trimmed = trim_consult_context(text)
        assert "id: ENH-1" not in trimmed
        assert trimmed.strip() == "## Summary\n\nJust a summary."


class TestMapAdviseVerdict:
    def test_proceed_lead_word(self) -> None:
        verdict, _reason = map_advise_verdict(_outcome(verdict=_verdict("PROCEED: looks ready")))
        assert verdict == "PROCEED"

    def test_veto_lead_word(self) -> None:
        verdict, _reason = map_advise_verdict(_outcome(verdict=_verdict("VETO: missing tests")))
        assert verdict == "VETO"

    def test_formatted_veto_lead_word(self) -> None:
        verdict, _reason = map_advise_verdict(_outcome(verdict=_verdict("**VETO** — concrete gap")))
        assert verdict == "VETO"

    def test_no_whole_word_fallback_for_veto(self) -> None:
        verdict, _reason = map_advise_verdict(
            _outcome(verdict=_verdict("PROCEED, no reason to VETO this"))
        )
        assert verdict == "PROCEED"

    def test_verdict_none_defaults_to_proceed_only_when_unparseable(self) -> None:
        verdict, _reason = map_advise_verdict(
            _outcome(verdict=_verdict("I am not sure what to recommend"))
        )
        assert verdict == "PROCEED"

    def test_skipped_reason_maps_to_skipped(self) -> None:
        for reason in (
            "disabled",
            "trigger_not_allowed",
            "budget_exhausted",
            "not_configured",
            "floor_violation",
            "failed",
            "timeout",
        ):
            verdict, log_reason = map_advise_verdict(_outcome(skipped_reason=reason))
            assert verdict == "SKIPPED"
            assert log_reason == reason


class TestCmdAdviseConsultPreflight:
    def test_host_unset_skips_without_consulting_or_spending_budget(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_issue(project)
        config = BRConfig(project)
        assert config.advisor.host is None
        run_dir = project / "run"
        run_dir.mkdir()
        with patch("little_loops.advisor.consult_for_trigger") as mock_consult:
            assert cmd_advise_consult(config, _args("ENH-9999", run_dir)) == 0
        mock_consult.assert_not_called()
        assert capsys.readouterr().out.strip() == "SKIPPED"
        assert not (project / ".ll" / "advisor-budget").exists()

    def test_host_unset_still_persists_skip_record(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_issue(project)
        config = BRConfig(project)
        run_dir = project / "run"
        run_dir.mkdir()
        cmd_advise_consult(config, _args("ENH-9999", run_dir))
        payload = json.loads((run_dir / "advise-ENH-9999.json").read_text())
        assert payload["skipped_reason"] == "not_configured"
        assert payload["preflight"] is True


class TestCmdAdviseConsultConsult:
    def test_proceed_persists_and_prints_token(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_issue(project)
        run_dir = project / "run"
        run_dir.mkdir()
        config = _configured(project)
        with patch("little_loops.advisor.consult_for_trigger") as mock_consult:
            mock_consult.return_value = ConsultOutcome(
                task_key=_TASK_KEY, verdict=_verdict("PROCEED: looks solid")
            )
            assert cmd_advise_consult(config, _args("ENH-9999", run_dir)) == 0
        assert capsys.readouterr().out.strip() == "PROCEED"
        assert (run_dir / "advise-ENH-9999.json").exists()
        assert (run_dir / "advise-ENH-9999.verdict").exists()
        assert os.environ.get("LL_ISSUE_ID") == "ENH-9999"

    def test_veto_persists_and_prints_token(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_issue(project)
        run_dir = project / "run"
        run_dir.mkdir()
        config = _configured(project)
        with patch("little_loops.advisor.consult_for_trigger") as mock_consult:
            mock_consult.return_value = ConsultOutcome(
                task_key=_TASK_KEY, verdict=_verdict("VETO: missing tests")
            )
            assert cmd_advise_consult(config, _args("ENH-9999", run_dir)) == 0
        assert capsys.readouterr().out.strip() == "VETO"

    def test_skipped_outcome_persists_skip_record(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_issue(project)
        run_dir = project / "run"
        run_dir.mkdir()
        config = _configured(project)
        with patch("little_loops.advisor.consult_for_trigger") as mock_consult:
            mock_consult.return_value = ConsultOutcome(
                task_key=_TASK_KEY,
                skipped_reason="timeout",
            )
            assert cmd_advise_consult(config, _args("ENH-9999", run_dir)) == 0
        assert capsys.readouterr().out.strip() == "SKIPPED"
        payload = json.loads((run_dir / "advise-ENH-9999.json").read_text())
        assert payload["skipped_reason"] == "timeout"


class TestCmdAdviseConsultReplay:
    def test_second_call_same_id_replays_without_consulting(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_issue(project)
        run_dir = project / "run"
        run_dir.mkdir()
        config = _configured(project)
        with patch("little_loops.advisor.consult_for_trigger") as mock_consult:
            mock_consult.return_value = ConsultOutcome(
                task_key=_TASK_KEY, verdict=_verdict("PROCEED: fine")
            )
            cmd_advise_consult(config, _args("ENH-9999", run_dir))
            capsys.readouterr()
            assert cmd_advise_consult(config, _args("ENH-9999", run_dir)) == 0
        assert mock_consult.call_count == 1
        assert capsys.readouterr().out.strip() == "PROCEED"

    def test_replayed_proceed_discarded_after_context_changes(self, project: Path) -> None:
        path = _write_issue(project)
        run_dir = project / "run"
        run_dir.mkdir()
        config = _configured(project)
        with patch("little_loops.advisor.consult_for_trigger") as mock_consult:
            mock_consult.return_value = ConsultOutcome(
                task_key=_TASK_KEY, verdict=_verdict("PROCEED: fine")
            )
            cmd_advise_consult(config, _args("ENH-9999", run_dir))
            path.write_text(path.read_text() + "\nSome new directive content.\n")
            cmd_advise_consult(config, _args("ENH-9999", run_dir))
        assert mock_consult.call_count == 2

    def test_replayed_proceed_kept_when_only_session_log_changes(self, project: Path) -> None:
        path = _write_issue(project)
        run_dir = project / "run"
        run_dir.mkdir()
        config = _configured(project)
        with patch("little_loops.advisor.consult_for_trigger") as mock_consult:
            mock_consult.return_value = ConsultOutcome(
                task_key=_TASK_KEY, verdict=_verdict("PROCEED: fine")
            )
            cmd_advise_consult(config, _args("ENH-9999", run_dir))
            path.write_text(path.read_text() + "\n## Session Log\n- appended\n")
            cmd_advise_consult(config, _args("ENH-9999", run_dir))
        assert mock_consult.call_count == 1

    def test_veto_sticky_despite_context_change(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = _write_issue(project)
        run_dir = project / "run"
        run_dir.mkdir()
        config = _configured(project)
        with patch("little_loops.advisor.consult_for_trigger") as mock_consult:
            mock_consult.return_value = ConsultOutcome(
                task_key=_TASK_KEY, verdict=_verdict("VETO: missing tests")
            )
            cmd_advise_consult(config, _args("ENH-9999", run_dir))
            path.write_text(path.read_text() + "\nSubstantial rewritten content.\n")
            capsys.readouterr()
            assert cmd_advise_consult(config, _args("ENH-9999", run_dir)) == 0
        assert mock_consult.call_count == 1
        assert capsys.readouterr().out.strip() == "VETO"

    def test_two_ids_consult_twice(self, project: Path) -> None:
        _write_issue(project, "ENH-9999")
        _write_issue(project, "ENH-8888")
        run_dir = project / "run"
        run_dir.mkdir()
        config = _configured(project)
        with patch("little_loops.advisor.consult_for_trigger") as mock_consult:
            mock_consult.return_value = ConsultOutcome(
                task_key=_TASK_KEY, verdict=_verdict("PROCEED: fine")
            )
            cmd_advise_consult(config, _args("ENH-9999", run_dir))
            cmd_advise_consult(config, _args("ENH-8888", run_dir))
        assert mock_consult.call_count == 2


class TestCmdAdviseConsultWriteNote:
    def test_veto_writes_advisor_veto_section(self, project: Path) -> None:
        path = _write_issue(project)
        run_dir = project / "run"
        run_dir.mkdir()
        config = _configured(project)
        with patch("little_loops.advisor.consult_for_trigger") as mock_consult:
            mock_consult.return_value = ConsultOutcome(
                task_key=_TASK_KEY, verdict=_verdict("VETO: missing acceptance criteria")
            )
            cmd_advise_consult(config, _args("ENH-9999", run_dir, write_note=True))
        content = path.read_text()
        assert "## Advisor Veto" in content
        assert "missing acceptance criteria" in content

    def test_proceed_removes_stale_advisor_veto_section(self, project: Path) -> None:
        path = _write_issue(
            project,
            body="## Summary\n\nPlain.\n\n## Advisor Veto\n\nStale VETO: old reason.\n",
        )
        run_dir = project / "run"
        run_dir.mkdir()
        config = _configured(project)
        with patch("little_loops.advisor.consult_for_trigger") as mock_consult:
            mock_consult.return_value = ConsultOutcome(
                task_key=_TASK_KEY, verdict=_verdict("PROCEED: fine now")
            )
            cmd_advise_consult(config, _args("ENH-9999", run_dir, write_note=True))
        content = path.read_text()
        assert "Advisor Veto" not in content

    def test_skipped_leaves_file_alone(self, project: Path) -> None:
        path = _write_issue(project)
        original = path.read_text()
        run_dir = project / "run"
        run_dir.mkdir()
        config = BRConfig(project)  # host unset -> SKIPPED
        cmd_advise_consult(config, _args("ENH-9999", run_dir, write_note=True))
        assert path.read_text() == original


class TestCmdAdviseConsultCrashGuard:
    def test_unexpected_exception_still_prints_skipped_and_exits_zero(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run_dir = project / "run"
        run_dir.mkdir()
        config = _configured(project)
        with patch(
            "little_loops.cli.issues.show._resolve_issue_id", side_effect=RuntimeError("boom")
        ):
            assert cmd_advise_consult(config, _args("ENH-9999", run_dir)) == 0
        assert capsys.readouterr().out.strip() == "SKIPPED"
