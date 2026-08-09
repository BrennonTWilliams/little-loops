"""Tests for little_loops.ready_issue — retry on an UNKNOWN ready-issue verdict.

Regression coverage for the autodev failure in
``.loops/runs/autodev-20260801T214427/``: a single ready-issue turn replied
"I don't see an actual request in your message — just system context.",
exited 0, parsed to ``UNKNOWN``, and discarded 14m17s of successful
refine/wire/confidence work because ``UNKNOWN`` shared a terminal branch with a
genuine ``NOT_READY``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from little_loops.config import BRConfig
from little_loops.issue_parser import IssueInfo
from little_loops.ready_issue import (
    IMPERATIVE_TAIL,
    build_retry_command,
    run_ready_issue_with_retry,
)

# The exact non-compliant reply observed in session
# aaf47f73-e638-4d68-acb7-13fe44e851a1 — exit 0, no tool calls, no VERDICT.
NON_COMPLIANT_REPLY = (
    "I don't see an actual request in your message — just system context. "
    "What would you like me to help with?"
)

READY_OUTPUT = """
## VERDICT
READY
"""

NOT_READY_OUTPUT = """
## VERDICT
NOT_READY

## CONCERNS
- Acceptance criteria are not testable
"""


def _completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess("cmd", returncode, stdout, "")


class _Runner:
    """Records every command it is asked to run and replays canned outputs."""

    def __init__(self, *outputs: subprocess.CompletedProcess[str]) -> None:
        self.outputs = list(outputs)
        self.commands: list[str] = []

    def __call__(self, command: str) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        return self.outputs[min(len(self.commands) - 1, len(self.outputs) - 1)]


@pytest.fixture
def config(temp_project_dir: Path) -> BRConfig:
    cfg = MagicMock(spec=BRConfig)
    cfg.project_root = temp_project_dir
    cfg.repo_path = temp_project_dir
    return cfg


class TestRunReadyIssueWithRetry:
    """Direct unit tests of the helper's retry contract."""

    def test_unknown_then_ready_retries_once_and_wins(self, config: BRConfig) -> None:
        run = _Runner(_completed(NON_COMPLIANT_REPLY), _completed(READY_OUTPUT))

        parsed, result = run_ready_issue_with_retry(
            target="ENH-2971",
            initial_command="/ll:ready-issue ENH-2971",
            run=run,
            config=config,
            retries=1,
        )

        assert len(run.commands) == 2
        assert parsed["verdict"] == "READY"
        assert parsed["is_ready"] is True
        assert result.returncode == 0

    def test_retry_command_is_differentiated(self, config: BRConfig) -> None:
        """The retry must carry an explicit directive, not re-roll the same prompt."""
        run = _Runner(_completed(NON_COMPLIANT_REPLY), _completed(READY_OUTPUT))

        # expand_skill now appends the directive itself (ENH-2988); the mock
        # return value must include it since the mock bypasses the real call.
        expanded = "# Ready Issue\nbody" + IMPERATIVE_TAIL.format(target="ENH-2971")
        with patch("little_loops.skill_expander.expand_skill", return_value=expanded):
            run_ready_issue_with_retry(
                target="ENH-2971",
                initial_command="/ll:ready-issue ENH-2971",
                run=run,
                config=config,
                retries=1,
            )

        first, retry = run.commands
        assert retry != first
        assert "Now execute the instructions above for: ENH-2971" in retry
        assert "## VERDICT" in retry

    def test_unknown_twice_stops_at_the_retry_budget(self, config: BRConfig) -> None:
        run = _Runner(_completed(NON_COMPLIANT_REPLY))

        parsed, _ = run_ready_issue_with_retry(
            target="ENH-2971",
            initial_command="/ll:ready-issue ENH-2971",
            run=run,
            config=config,
            retries=1,
        )

        assert len(run.commands) == 2  # initial + exactly one retry
        assert parsed["verdict"] == "UNKNOWN"
        assert parsed["is_ready"] is False

    def test_genuine_not_ready_is_never_retried(self, config: BRConfig) -> None:
        """A real rejection must not burn a second model call."""
        run = _Runner(_completed(NOT_READY_OUTPUT))

        parsed, _ = run_ready_issue_with_retry(
            target="ENH-2971",
            initial_command="/ll:ready-issue ENH-2971",
            run=run,
            config=config,
            retries=1,
        )

        assert len(run.commands) == 1
        assert parsed["verdict"] == "NOT_READY"

    @pytest.mark.parametrize("verdict", ["READY", "CORRECTED", "CLOSE", "BLOCKED"])
    def test_parseable_verdicts_are_never_retried(self, config: BRConfig, verdict: str) -> None:
        run = _Runner(_completed(f"\n## VERDICT\n{verdict}\n"))

        parsed, _ = run_ready_issue_with_retry(
            target="ENH-2971",
            initial_command="/ll:ready-issue ENH-2971",
            run=run,
            config=config,
            retries=1,
        )

        assert len(run.commands) == 1
        assert parsed["verdict"] == verdict

    def test_nonzero_return_code_is_never_retried(self, config: BRConfig) -> None:
        """A failed invocation is a different failure mode the callers own."""
        run = _Runner(_completed("", returncode=1))

        parsed, result = run_ready_issue_with_retry(
            target="ENH-2971",
            initial_command="/ll:ready-issue ENH-2971",
            run=run,
            config=config,
            retries=1,
        )

        assert len(run.commands) == 1
        assert result.returncode == 1
        assert parsed["verdict"] == "UNKNOWN"

    def test_retries_zero_disables_the_retry(self, config: BRConfig) -> None:
        run = _Runner(_completed(NON_COMPLIANT_REPLY))

        run_ready_issue_with_retry(
            target="ENH-2971",
            initial_command="/ll:ready-issue ENH-2971",
            run=run,
            config=config,
            retries=0,
        )

        assert len(run.commands) == 1

    def test_multiple_retries_are_honored(self, config: BRConfig) -> None:
        run = _Runner(
            _completed(NON_COMPLIANT_REPLY),
            _completed(NON_COMPLIANT_REPLY),
            _completed(READY_OUTPUT),
        )

        parsed, _ = run_ready_issue_with_retry(
            target="ENH-2971",
            initial_command="/ll:ready-issue ENH-2971",
            run=run,
            config=config,
            retries=2,
        )

        assert len(run.commands) == 3
        assert parsed["verdict"] == "READY"

    def test_retry_is_logged(self, config: BRConfig) -> None:
        run = _Runner(_completed(NON_COMPLIANT_REPLY), _completed(READY_OUTPUT))
        messages: list[str] = []

        run_ready_issue_with_retry(
            target="ENH-2971",
            initial_command="/ll:ready-issue ENH-2971",
            run=run,
            config=config,
            retries=1,
            log=messages.append,
        )

        assert len(messages) == 1
        assert "ENH-2971" in messages[0]

    def test_empty_stdout_does_not_crash(self, config: BRConfig) -> None:
        """stdout can be None on some CompletedProcess paths."""
        run = _Runner(subprocess.CompletedProcess("cmd", 0, None, ""))  # type: ignore[arg-type]

        parsed, _ = run_ready_issue_with_retry(
            target="ENH-2971",
            initial_command="/ll:ready-issue ENH-2971",
            run=run,
            config=config,
            retries=0,
        )

        assert parsed["verdict"] == "UNKNOWN"


class TestBuildRetryCommand:
    """The retry prompt is always the hardened expanded form when available."""

    def test_expanded_body_gets_the_imperative_tail(self, config: BRConfig) -> None:
        # expand_skill now appends the directive itself (ENH-2988); the mock
        # return value must include it since the mock bypasses the real call.
        expanded = "# Ready Issue\nbody" + IMPERATIVE_TAIL.format(target="ENH-2971")
        with patch("little_loops.skill_expander.expand_skill", return_value=expanded):
            cmd = build_retry_command("ENH-2971", config)

        assert cmd.startswith("# Ready Issue")
        assert cmd.endswith(IMPERATIVE_TAIL.format(target="ENH-2971"))

    def test_falls_back_to_plain_slash_without_the_tail(self, config: BRConfig) -> None:
        """Trailing prose on a slash command would be swallowed as $ARGUMENTS."""
        with patch("little_loops.skill_expander.expand_skill", return_value=None):
            cmd = build_retry_command("ENH-2971", config)

        assert cmd == "/ll:ready-issue ENH-2971"
        assert "Now execute" not in cmd

    def test_real_expansion_targets_the_issue(self, config: BRConfig) -> None:
        """End-to-end against the actual commands/ready-issue.md, no mocks."""
        cmd = build_retry_command("ENH-2971", config)

        assert "ENH-2971" in cmd
        # Either the expanded body (long) or the slash fallback, but the tail
        # only ever accompanies the expanded form.
        if cmd != "/ll:ready-issue ENH-2971":
            assert cmd.endswith(IMPERATIVE_TAIL.format(target="ENH-2971"))


class TestIssueManagerWiring:
    """ll-auto's Phase 1 recovers instead of failing the whole run."""

    @pytest.fixture
    def mock_config(self, temp_project_dir: Path) -> BRConfig:
        config = MagicMock(spec=BRConfig)
        config.project_root = temp_project_dir
        config.repo_path = temp_project_dir
        config.automation = MagicMock()
        config.automation.timeout_seconds = 60
        config.automation.stream_output = False
        config.automation.max_continuations = 3
        config.automation.ready_issue_unknown_retries = 1
        config.get_category_action.return_value = "fix"
        config.get_state_file.return_value = temp_project_dir / ".auto-state.json"
        return config

    @pytest.fixture
    def sample_issue(self, temp_project_dir: Path) -> IssueInfo:
        issues_dir = temp_project_dir / ".issues" / "enhancements"
        issues_dir.mkdir(parents=True)
        issue_file = issues_dir / "P3-ENH-2971-test.md"
        issue_file.write_text("# ENH-2971: Test\n\n## Summary\nTest")
        return IssueInfo(
            path=issue_file,
            issue_type="enhancements",
            priority="P3",
            issue_id="ENH-2971",
            title="Test",
        )

    def test_phase1_recovers_and_reaches_phase2(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        """The observed failure, replayed: first turn non-compliant, second fine."""
        from little_loops.issue_manager import process_issue_inplace

        commands: list[str] = []
        outputs = [
            _completed(NON_COMPLIANT_REPLY),
            _completed(f"\n## VERDICT\nREADY\n\n## VALIDATED_FILE\n{sample_issue.path}\n"),
        ]

        def fake_run(command: str, *args: object, **kwargs: object) -> object:
            commands.append(command)
            return outputs[min(len(commands) - 1, len(outputs) - 1)]

        # expand_skill now appends the directive itself (ENH-2988); the mock
        # return value must include it since the mock bypasses the real call.
        expanded = "# Ready Issue\nbody" + IMPERATIVE_TAIL.format(target="ENH-2971")

        with (
            patch("little_loops.issue_manager.run_claude_command", side_effect=fake_run),
            patch("little_loops.issue_manager.run_with_continuation") as mock_impl,
            patch("little_loops.issue_manager.verify_issue_completed", return_value=True),
            patch("little_loops.issue_manager.check_git_status", return_value=([], [])),
            # A MagicMock config makes the real expander bail to None; stub it so
            # the assertion below tests the hardened retry prompt, not the fallback.
            patch("little_loops.skill_expander.expand_skill", return_value=expanded),
        ):
            mock_impl.return_value = MagicMock(
                returncode=0, stdout="## RESULT\n- Status: COMPLETED", stderr=""
            )
            process_issue_inplace(sample_issue, mock_config, MagicMock())

        # Two ready-issue calls, and Phase 2 was actually reached — the whole
        # point: before the fix this run died at Phase 1 with verdict UNKNOWN.
        assert len(commands) == 2
        assert "Now execute the instructions above for: ENH-2971" in commands[1]
        mock_impl.assert_called_once()

    def test_phase1_still_fails_when_retry_also_whiffs(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        from little_loops.issue_manager import process_issue_inplace

        commands: list[str] = []

        def fake_run(command: str, *args: object, **kwargs: object) -> object:
            commands.append(command)
            return _completed(NON_COMPLIANT_REPLY)

        with (
            patch("little_loops.issue_manager.run_claude_command", side_effect=fake_run),
            patch("little_loops.issue_manager.run_with_continuation") as mock_impl,
            patch("little_loops.issue_manager.check_git_status", return_value=([], [])),
        ):
            result = process_issue_inplace(sample_issue, mock_config, MagicMock())

        assert len(commands) == 2
        assert not result.success
        assert "UNKNOWN" in (result.failure_reason or "")
        mock_impl.assert_not_called()

    def test_config_knob_of_zero_disables_the_retry(
        self, mock_config: BRConfig, sample_issue: IssueInfo
    ) -> None:
        from little_loops.issue_manager import process_issue_inplace

        mock_config.automation.ready_issue_unknown_retries = 0
        commands: list[str] = []

        def fake_run(command: str, *args: object, **kwargs: object) -> object:
            commands.append(command)
            return _completed(NON_COMPLIANT_REPLY)

        with (
            patch("little_loops.issue_manager.run_claude_command", side_effect=fake_run),
            patch("little_loops.issue_manager.run_with_continuation"),
            patch("little_loops.issue_manager.check_git_status", return_value=([], [])),
        ):
            process_issue_inplace(sample_issue, mock_config, MagicMock())

        assert len(commands) == 1


class TestAutomationConfigKnob:
    """The knob round-trips through AutomationConfig.from_dict."""

    def test_default_is_one_retry(self) -> None:
        from little_loops.config.automation import AutomationConfig

        assert AutomationConfig().ready_issue_unknown_retries == 1
        assert AutomationConfig.from_dict({}).ready_issue_unknown_retries == 1

    def test_explicit_value_is_honored(self) -> None:
        from little_loops.config.automation import AutomationConfig

        cfg = AutomationConfig.from_dict({"ready_issue_unknown_retries": 0})
        assert cfg.ready_issue_unknown_retries == 0

    def test_schema_documents_the_knob(self) -> None:
        import importlib.resources
        import json

        schema_path = importlib.resources.files("little_loops").joinpath("config-schema.json")
        schema = json.loads(schema_path.read_text())
        knob = schema["properties"]["automation"]["properties"]["ready_issue_unknown_retries"]

        assert knob["type"] == "integer"
        assert knob["default"] == 1
        assert knob["minimum"] == 0
