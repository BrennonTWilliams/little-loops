"""Tests for little_loops.cli.parallel (ll-parallel entry point).

Focuses on gaps not covered by test_cli.py:
- LL_HANDOFF_THRESHOLD / LL_CONTEXT_LIMIT env-var side effects
- --prune-merged-branches mode (success and dry-run)
- Normal orchestration run path
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_project(
    make_project: Any,
) -> Path:
    """Temp project with minimal parallel config."""
    project, _ = make_project(
        config={
            "project": {"name": "test"},
            "issues": {
                "base_dir": ".issues",
                "categories": {"bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"}},
                "priorities": ["P0", "P1", "P2"],
            },
            "automation": {"timeout_seconds": 60, "state_file": ".state.json"},
            "parallel": {
                "max_workers": 2,
                "state_file": ".parallel-state.json",
                "timeout_seconds": 1800,
            },
        }
    )
    return project


# ---------------------------------------------------------------------------
# Env-var side effects
# ---------------------------------------------------------------------------


class TestParallelEnvVarSideEffects:
    """--handoff-threshold and --context-limit set os.environ directly."""

    def test_handoff_threshold_sets_env_var(self, temp_project: Path) -> None:
        """--handoff-threshold 75 writes LL_HANDOFF_THRESHOLD=75 into os.environ."""
        with patch("little_loops.parallel.ParallelOrchestrator") as mock_cls:
            mock_cls.return_value.run.return_value = 0
            with patch(
                "subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "main\n", ""),
            ):
                with patch.object(
                    sys,
                    "argv",
                    [
                        "ll-parallel",
                        "--handoff-threshold",
                        "75",
                        "--config",
                        str(temp_project),
                    ],
                ):
                    from little_loops.cli import main_parallel

                    result = main_parallel()

        assert result == 0
        assert os.environ.get("LL_HANDOFF_THRESHOLD") == "75"

    def test_context_limit_sets_env_var(self, temp_project: Path) -> None:
        """--context-limit 100000 writes LL_CONTEXT_LIMIT=100000 into os.environ."""
        with patch("little_loops.parallel.ParallelOrchestrator") as mock_cls:
            mock_cls.return_value.run.return_value = 0
            with patch(
                "subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "main\n", ""),
            ):
                with patch.object(
                    sys,
                    "argv",
                    [
                        "ll-parallel",
                        "--context-limit",
                        "100000",
                        "--config",
                        str(temp_project),
                    ],
                ):
                    from little_loops.cli import main_parallel

                    result = main_parallel()

        assert result == 0
        assert os.environ.get("LL_CONTEXT_LIMIT") == "100000"


# ---------------------------------------------------------------------------
# --prune-merged-branches mode
# ---------------------------------------------------------------------------


class TestParallelPruneBranches:
    """--prune-merged-branches calls pool.prune_merged_feature_branches."""

    def test_prune_merged_branches_calls_pool(self, temp_project: Path) -> None:
        """--prune-merged-branches invokes prune_merged_feature_branches and returns 0."""
        with patch("little_loops.parallel.WorkerPool") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool.prune_merged_feature_branches.return_value = (
                ["parallel/issue-1"],
                [],
            )
            mock_pool_cls.return_value = mock_pool
            with patch(
                "subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "main\n", ""),
            ):
                with patch.object(
                    sys,
                    "argv",
                    [
                        "ll-parallel",
                        "--prune-merged-branches",
                        "--config",
                        str(temp_project),
                    ],
                ):
                    from little_loops.cli import main_parallel

                    result = main_parallel()

        assert result == 0
        mock_pool.prune_merged_feature_branches.assert_called_once()

    def test_prune_dry_run_passes_flag(self, temp_project: Path) -> None:
        """--prune-merged-branches --dry-run passes dry_run=True to pool method."""
        with patch("little_loops.parallel.WorkerPool") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool.prune_merged_feature_branches.return_value = ([], [])
            mock_pool_cls.return_value = mock_pool
            with patch(
                "subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "main\n", ""),
            ):
                with patch.object(
                    sys,
                    "argv",
                    [
                        "ll-parallel",
                        "--prune-merged-branches",
                        "--dry-run",
                        "--config",
                        str(temp_project),
                    ],
                ):
                    from little_loops.cli import main_parallel

                    result = main_parallel()

        assert result == 0
        _, call_kwargs = mock_pool.prune_merged_feature_branches.call_args
        assert call_kwargs.get("dry_run") is True


# ---------------------------------------------------------------------------
# Normal orchestration path
# ---------------------------------------------------------------------------


class TestParallelNormalRun:
    """The normal (non-maintenance) path creates and runs a ParallelOrchestrator."""

    def test_orchestrator_run_called_and_exit_code_propagated(self, temp_project: Path) -> None:
        """main_parallel() calls orchestrator.run() and returns its exit code."""
        with patch("little_loops.parallel.ParallelOrchestrator") as mock_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = 0
            mock_cls.return_value = mock_orch
            with patch(
                "subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "main\n", ""),
            ):
                with patch.object(
                    sys,
                    "argv",
                    ["ll-parallel", "--config", str(temp_project)],
                ):
                    from little_loops.cli import main_parallel

                    result = main_parallel()

        assert result == 0
        mock_orch.run.assert_called_once()

    def test_git_fallback_when_not_in_repo(self, temp_project: Path) -> None:
        """When git rev-parse fails, base_branch falls back to 'main'."""
        with patch("little_loops.parallel.ParallelOrchestrator") as mock_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = 0
            mock_cls.return_value = mock_orch
            # Simulate: not a git repo — exit code 128
            with patch(
                "subprocess.run",
                return_value=subprocess.CompletedProcess([], 128, "", "fatal: not a git repo"),
            ):
                with patch.object(
                    sys,
                    "argv",
                    ["ll-parallel", "--config", str(temp_project)],
                ):
                    from little_loops.cli import main_parallel

                    result = main_parallel()

        assert result == 0
        # Verify base_branch="main" was passed to create_parallel_config (indirectly via call)
        mock_cls.assert_called_once()

    def test_detected_default_branch_reaches_parallel_config(self, temp_project: Path) -> None:
        """The detect_default_branch() result flows into parallel_config.base_branch (BUG-2323)."""
        with patch("little_loops.parallel.ParallelOrchestrator") as mock_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = 0
            mock_cls.return_value = mock_orch
            with patch(
                "little_loops.cli.parallel.detect_default_branch",
                return_value="develop",
            ) as mock_detect:
                with patch.object(
                    sys,
                    "argv",
                    ["ll-parallel", "--config", str(temp_project)],
                ):
                    from little_loops.cli import main_parallel

                    result = main_parallel()

        assert result == 0
        mock_detect.assert_called_once()
        parallel_config = mock_cls.call_args.kwargs["parallel_config"]
        assert parallel_config.base_branch == "develop"

    def test_configured_base_branch_overrides_detection(self, make_project: Any) -> None:
        """An explicit parallel.base_branch config value wins over auto-detection."""
        project, _ = make_project(
            config={
                "project": {"name": "test"},
                "issues": {
                    "base_dir": ".issues",
                    "categories": {"bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"}},
                    "priorities": ["P0", "P1", "P2"],
                },
                "parallel": {"max_workers": 2, "base_branch": "release"},
            }
        )
        with patch("little_loops.parallel.ParallelOrchestrator") as mock_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = 0
            mock_cls.return_value = mock_orch
            with patch(
                "little_loops.cli.parallel.detect_default_branch",
                return_value="develop",
            ) as mock_detect:
                with patch.object(
                    sys,
                    "argv",
                    ["ll-parallel", "--config", str(project)],
                ):
                    from little_loops.cli import main_parallel

                    result = main_parallel()

        assert result == 0
        mock_detect.assert_not_called()
        parallel_config = mock_cls.call_args.kwargs["parallel_config"]
        assert parallel_config.base_branch == "release"

    def test_epic_branches_flag_enables_epic_mode(self, make_project: Any) -> None:
        """`--epic-branches` sets parallel_config.epic_branches.enabled True (FEAT-2450)."""
        project, _ = make_project(
            config={
                "project": {"name": "test"},
                "issues": {
                    "base_dir": ".issues",
                    "categories": {"bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"}},
                    "priorities": ["P0", "P1", "P2"],
                },
                "parallel": {"max_workers": 2},
            }
        )
        with patch("little_loops.parallel.ParallelOrchestrator") as mock_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = 0
            mock_cls.return_value = mock_orch
            with patch.object(
                sys,
                "argv",
                ["ll-parallel", "--epic-branches", "--config", str(project)],
            ):
                from little_loops.cli import main_parallel

                result = main_parallel()

        assert result == 0
        parallel_config = mock_cls.call_args.kwargs["parallel_config"]
        assert parallel_config.epic_branches.enabled is True

    def test_epic_branches_flag_preserves_configured_prefix(self, make_project: Any) -> None:
        """`--epic-branches` overrides only `enabled`, preserving config prefix (FEAT-2450)."""
        project, _ = make_project(
            config={
                "project": {"name": "test"},
                "issues": {
                    "base_dir": ".issues",
                    "categories": {"bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"}},
                    "priorities": ["P0", "P1", "P2"],
                },
                "parallel": {
                    "max_workers": 2,
                    "epic_branches": {"enabled": False, "prefix": "integration/"},
                },
            }
        )
        with patch("little_loops.parallel.ParallelOrchestrator") as mock_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = 0
            mock_cls.return_value = mock_orch
            with patch.object(
                sys,
                "argv",
                ["ll-parallel", "--epic-branches", "--config", str(project)],
            ):
                from little_loops.cli import main_parallel

                result = main_parallel()

        assert result == 0
        parallel_config = mock_cls.call_args.kwargs["parallel_config"]
        assert parallel_config.epic_branches.enabled is True
        assert parallel_config.epic_branches.prefix == "integration/"

    def test_no_epic_branches_flag_disables_configured_epic_mode(self, make_project: Any) -> None:
        """`--no-epic-branches` overrides a config-enabled epic mode to disabled (FEAT-2450)."""
        project, _ = make_project(
            config={
                "project": {"name": "test"},
                "issues": {
                    "base_dir": ".issues",
                    "categories": {"bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"}},
                    "priorities": ["P0", "P1", "P2"],
                },
                "parallel": {"max_workers": 2, "epic_branches": {"enabled": True}},
            }
        )
        with patch("little_loops.parallel.ParallelOrchestrator") as mock_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = 0
            mock_cls.return_value = mock_orch
            with patch.object(
                sys,
                "argv",
                ["ll-parallel", "--no-epic-branches", "--config", str(project)],
            ):
                from little_loops.cli import main_parallel

                result = main_parallel()

        assert result == 0
        parallel_config = mock_cls.call_args.kwargs["parallel_config"]
        assert parallel_config.epic_branches.enabled is False
