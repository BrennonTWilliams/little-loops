"""Tests for the ``pre_done`` hook handler (FEAT-3118).

Python-direct unit tests for ``little_loops.hooks.pre_done.handle``. The
subprocess/adapter integration path is covered by
``test_hooks_integration.py``; the CLI dispatcher routing path is covered by
``test_hook_intents.py::TestHooksMainModule``.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.advisor import AdvisorVerdict, ConsultOutcome, TaskKey
from little_loops.hooks import pre_done
from little_loops.hooks.types import LLHookEvent, LLHookResult


@pytest.fixture(autouse=True)
def _clear_task_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force resolve_task_key() onto the session tier, deterministically.

    Automation contexts (ll-auto/ll-loop) export LL_ISSUE_ID/LL_LOOP_RUN_ID,
    which would otherwise outrank the payload session_id these tests assert
    against.
    """
    monkeypatch.delenv("LL_ISSUE_ID", raising=False)
    monkeypatch.delenv("LL_LOOP_RUN_ID", raising=False)


def _event(session_id: str | None = "session-1", **payload: object) -> LLHookEvent:
    return LLHookEvent(
        host="claude-code", intent="pre_done", payload=dict(payload), session_id=session_id
    )


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    # find_project_root requires an existing `.ll/` alongside `.git` to resolve a root.
    # Ignored so the dedup state file this handler writes under .ll/advisor-budget/
    # doesn't itself show up as an untracked change and defeat the dedup it powers.
    (root / ".ll").mkdir(exist_ok=True)
    (root / ".gitignore").write_text(".ll/\n", encoding="utf-8")
    (root / "tracked.txt").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt", ".gitignore"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=root, check=True)


def _make_verdict() -> AdvisorVerdict:
    return AdvisorVerdict(
        recommendation="looks solid",
        risks=["watch the timeout"],
        confidence=0.8,
        dissent="",
        signal="pre_done",
        host="claude-code",
        model="opus",
    )


class TestNoOpPaths:
    def test_non_git_root_is_noop(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = pre_done.handle(_event(cwd=str(tmp_path)))
        assert isinstance(result, LLHookResult)
        assert result.exit_code == 0
        assert result.feedback is None

    def test_empty_diff_is_noop(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _init_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("little_loops.advisor.consult_for_trigger") as mock_consult:
            result = pre_done.handle(_event())
        assert result.exit_code == 0
        mock_consult.assert_not_called()


class TestConsultSurfacing:
    def test_successful_verdict_is_surfaced(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _init_repo(tmp_path)
        (tmp_path / "tracked.txt").write_text("hello\nworld\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)

        outcome = ConsultOutcome(task_key=TaskKey("session", "s1"), verdict=_make_verdict())
        with patch("little_loops.advisor.consult_for_trigger", return_value=outcome) as mock:
            result = pre_done.handle(_event())

        mock.assert_called_once()
        assert result.exit_code == 0
        assert result.feedback is not None
        assert "looks solid" in result.feedback

        dedup_file = tmp_path / ".ll" / "advisor-budget" / "session-session-1.pre_done.json"
        assert dedup_file.is_file()
        assert json.loads(dedup_file.read_text())["last_diff_sha"]

    def test_failed_consult_is_fail_soft(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _init_repo(tmp_path)
        (tmp_path / "tracked.txt").write_text("hello\nworld\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
        outcome = ConsultOutcome(
            task_key=TaskKey("session", "s1"), skipped_reason="timeout", error="host timed out"
        )
        with patch("little_loops.advisor.consult_for_trigger", return_value=outcome):
            result = pre_done.handle(_event())

        assert result.exit_code == 0
        assert result.feedback is None


class TestDedup:
    def test_second_call_with_unchanged_diff_skips_consult(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _init_repo(tmp_path)
        (tmp_path / "tracked.txt").write_text("hello\nworld\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)

        outcome = ConsultOutcome(task_key=TaskKey("session", "s1"), verdict=_make_verdict())
        with patch("little_loops.advisor.consult_for_trigger", return_value=outcome) as mock:
            first = pre_done.handle(_event())
            second = pre_done.handle(_event())

        assert first.exit_code == 0
        assert second.exit_code == 0
        mock.assert_called_once()

    def test_third_call_after_mutation_consults_again(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _init_repo(tmp_path)
        (tmp_path / "tracked.txt").write_text("hello\nworld\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)

        outcome = ConsultOutcome(task_key=TaskKey("session", "s1"), verdict=_make_verdict())
        with patch("little_loops.advisor.consult_for_trigger", return_value=outcome) as mock:
            pre_done.handle(_event())
            (tmp_path / "tracked.txt").write_text("hello\nworld\nagain\n", encoding="utf-8")
            pre_done.handle(_event())

        assert mock.call_count == 2

    def test_skipped_consult_does_not_poison_dedup(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _init_repo(tmp_path)
        (tmp_path / "tracked.txt").write_text("hello\nworld\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)

        failed = ConsultOutcome(task_key=TaskKey("session", "s1"), skipped_reason="failed")
        verdict_outcome = ConsultOutcome(task_key=TaskKey("session", "s1"), verdict=_make_verdict())
        with patch(
            "little_loops.advisor.consult_for_trigger", side_effect=[failed, verdict_outcome]
        ) as mock:
            pre_done.handle(_event())
            pre_done.handle(_event())

        assert mock.call_count == 2


class TestTimeoutClamp:
    def test_timeout_over_190_short_circuits(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _init_repo(tmp_path)
        (tmp_path / "tracked.txt").write_text("hello\nworld\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        config_path = tmp_path / ".ll"
        config_path.mkdir(exist_ok=True)
        (config_path / "ll-config.json").write_text(
            json.dumps({"advisor": {"enabled": True, "timeout_seconds": 200}}),
            encoding="utf-8",
        )

        with patch("little_loops.advisor.consult_for_trigger") as mock_consult:
            result = pre_done.handle(_event())

        assert result.exit_code == 0
        mock_consult.assert_not_called()


class TestSessionIdSeeding:
    def test_seeds_claude_session_id_when_unset(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _init_repo(tmp_path)
        (tmp_path / "tracked.txt").write_text("hello\nworld\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)

        outcome = ConsultOutcome(task_key=TaskKey("session", "s1"), verdict=_make_verdict())
        with patch("little_loops.advisor.consult_for_trigger", return_value=outcome):
            pre_done.handle(_event(session_id="from-payload"))

        import os

        assert os.environ.get("CLAUDE_SESSION_ID") == "from-payload"

    def test_leaves_preexisting_session_id_alone(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _init_repo(tmp_path)
        (tmp_path / "tracked.txt").write_text("hello\nworld\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CLAUDE_SESSION_ID", "already-set")

        outcome = ConsultOutcome(task_key=TaskKey("session", "s1"), verdict=_make_verdict())
        with patch("little_loops.advisor.consult_for_trigger", return_value=outcome):
            pre_done.handle(_event(session_id="from-payload"))

        import os

        assert os.environ.get("CLAUDE_SESSION_ID") == "already-set"
