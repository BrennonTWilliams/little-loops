"""Worker pool for parallel issue processing with git worktree isolation.

Each worker operates in an isolated git worktree, allowing concurrent issue
processing without file conflicts.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from little_loops.parallel.output_parsing import parse_ready_issue_output
from little_loops.parallel.types import ParallelConfig, WorkerResult
from little_loops.subprocess_utils import run_claude_command as _run_claude_base

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.issue_parser import IssueInfo
    from little_loops.logger import Logger


class WorkerPool:
    """Thread pool for processing issues in isolated git worktrees.

    Each worker:
    1. Creates a dedicated git worktree and branch
    2. Runs issue validation and implementation via Claude CLI
    3. Commits changes locally
    4. Returns results for merge coordination

    Example:
        >>> pool = WorkerPool(parallel_config, br_config, logger)
        >>> pool.start()
        >>> future = pool.submit(issue_info)
        >>> result = future.result()  # WorkerResult
        >>> pool.shutdown()
    """

    def __init__(
        self,
        parallel_config: ParallelConfig,
        br_config: BRConfig,
        logger: Logger,
        repo_path: Path | None = None,
    ) -> None:
        """Initialize the worker pool.

        Args:
            parallel_config: Parallel processing configuration
            br_config: Project configuration (for category actions)
            logger: Logger for worker output
            repo_path: Path to the git repository (default: current directory)
        """
        self.parallel_config = parallel_config
        self.br_config = br_config
        self.logger = logger
        self.repo_path = repo_path or Path.cwd()
        self._executor: ThreadPoolExecutor | None = None
        self._active_workers: dict[str, Future[WorkerResult]] = {}
        # Track active subprocesses for forceful termination on shutdown
        self._active_processes: dict[str, subprocess.Popen[str]] = {}
        self._process_lock = threading.Lock()
        # Track callbacks currently executing
        self._pending_callbacks: set[str] = set()
        self._callback_lock = threading.Lock()

    def start(self) -> None:
        """Start the worker pool."""
        if self._executor is not None:
            return

        # Ensure worktree base directory exists
        worktree_base = self.repo_path / self.parallel_config.worktree_base
        worktree_base.mkdir(parents=True, exist_ok=True)

        self._executor = ThreadPoolExecutor(
            max_workers=self.parallel_config.max_workers,
            thread_name_prefix="issue-worker",
        )
        self.logger.info(f"Worker pool started with {self.parallel_config.max_workers} workers")

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the worker pool.

        Args:
            wait: Whether to wait for pending tasks to complete
        """
        if self._executor is None:
            return

        self.logger.info("Shutting down worker pool...")

        # First, terminate all active subprocesses to unblock worker threads
        if not wait:
            self.terminate_all_processes()

        self._executor.shutdown(wait=wait)
        self._executor = None

    def terminate_all_processes(self) -> None:
        """Forcefully terminate all active subprocesses.

        Called when we need to abort workers immediately,
        such as on timeout or shutdown.
        """
        with self._process_lock:
            for issue_id, process in list(self._active_processes.items()):
                if process.poll() is None:  # Still running
                    self.logger.warning(f"Terminating subprocess for {issue_id} (PID {process.pid})")
                    try:
                        # Send SIGTERM first for graceful termination
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            # Force kill if SIGTERM didn't work
                            self.logger.warning(f"Force killing {issue_id} (PID {process.pid})")
                            process.kill()
                            process.wait(timeout=2)
                    except Exception as e:
                        self.logger.error(f"Failed to terminate {issue_id}: {e}")
            self._active_processes.clear()

    def submit(
        self,
        issue: IssueInfo,
        on_complete: Callable[[WorkerResult], None] | None = None,
    ) -> Future[WorkerResult]:
        """Submit an issue for processing.

        Args:
            issue: Issue to process
            on_complete: Optional callback when processing completes

        Returns:
            Future that will contain the WorkerResult
        """
        if self._executor is None:
            raise RuntimeError("Worker pool not started")

        future = self._executor.submit(self._process_issue, issue)
        self._active_workers[issue.issue_id] = future

        if on_complete:
            future.add_done_callback(
                lambda f: self._handle_completion(f, on_complete, issue.issue_id)
            )

        return future

    def _handle_completion(
        self,
        future: Future[WorkerResult],
        callback: Callable[[WorkerResult], None],
        issue_id: str,
    ) -> None:
        """Handle worker completion and invoke callback."""
        with self._callback_lock:
            self._pending_callbacks.add(issue_id)
        try:
            result = future.result()
            callback(result)
        except Exception as e:
            self.logger.error(f"Worker completion callback failed: {e}")
        finally:
            with self._callback_lock:
                self._pending_callbacks.discard(issue_id)

    def _process_issue(self, issue: IssueInfo) -> WorkerResult:
        """Process a single issue in an isolated worktree.

        Args:
            issue: Issue to process

        Returns:
            WorkerResult with processing outcome
        """
        start_time = time.time()
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        branch_name = f"parallel/{issue.issue_id.lower()}-{timestamp}"
        worktree_path = (
            self.repo_path
            / self.parallel_config.worktree_base
            / f"worker-{issue.issue_id.lower()}-{timestamp}"
        )

        try:
            # Step 1: Create worktree with new branch
            self._setup_worktree(worktree_path, branch_name)

            # Step 2: Run ready_issue validation
            ready_cmd = self.parallel_config.get_ready_command(issue.issue_id)
            ready_result = self._run_claude_command(
                ready_cmd,
                worktree_path,
                issue_id=issue.issue_id,
            )

            if ready_result.returncode != 0:
                return WorkerResult(
                    issue_id=issue.issue_id,
                    success=False,
                    branch_name=branch_name,
                    worktree_path=worktree_path,
                    duration=time.time() - start_time,
                    error=f"ready_issue failed: {ready_result.stderr}",
                    stdout=ready_result.stdout,
                    stderr=ready_result.stderr,
                )

            # Step 3: Parse ready_issue output and check verdict
            ready_parsed = parse_ready_issue_output(ready_result.stdout)

            # Handle CLOSE verdict - issue should not be implemented
            if ready_parsed.get("should_close"):
                return WorkerResult(
                    issue_id=issue.issue_id,
                    success=True,  # Closure is a valid outcome
                    branch_name=branch_name,
                    worktree_path=worktree_path,
                    duration=time.time() - start_time,
                    should_close=True,
                    close_reason=ready_parsed.get("close_reason"),
                    close_status=ready_parsed.get("close_status"),
                    stdout=ready_result.stdout,
                    stderr=ready_result.stderr,
                )

            # Handle NOT_READY verdict
            if not ready_parsed["is_ready"]:
                concerns = ready_parsed.get("concerns", [])
                concern_msg = "; ".join(concerns) if concerns else "Issue not ready"
                return WorkerResult(
                    issue_id=issue.issue_id,
                    success=False,
                    branch_name=branch_name,
                    worktree_path=worktree_path,
                    duration=time.time() - start_time,
                    error=f"ready_issue verdict: {ready_parsed['verdict']} - {concern_msg}",
                    stdout=ready_result.stdout,
                    stderr=ready_result.stderr,
                )

            # Track if issue was corrected (corrections stay in worktree)
            was_corrected = ready_parsed.get("was_corrected", False)

            # Step 4: Get action from BRConfig
            action = self.br_config.get_category_action(issue.issue_type)

            # Step 5: Run manage_issue implementation
            manage_cmd = self.parallel_config.get_manage_command(
                issue.issue_type, action, issue.issue_id
            )
            manage_result = self._run_claude_command(
                manage_cmd,
                worktree_path,
                issue_id=issue.issue_id,
            )

            # Step 6: Get list of changed files
            changed_files = self._get_changed_files(worktree_path)

            # Step 7: Verify actual work was done
            work_verified, verification_error = self._verify_work_was_done(changed_files)

            if manage_result.returncode != 0:
                return WorkerResult(
                    issue_id=issue.issue_id,
                    success=False,
                    branch_name=branch_name,
                    worktree_path=worktree_path,
                    changed_files=changed_files,
                    duration=time.time() - start_time,
                    error=f"manage_issue failed: {manage_result.stderr}",
                    stdout=manage_result.stdout,
                    stderr=manage_result.stderr,
                )

            if not work_verified:
                return WorkerResult(
                    issue_id=issue.issue_id,
                    success=False,
                    branch_name=branch_name,
                    worktree_path=worktree_path,
                    changed_files=changed_files,
                    duration=time.time() - start_time,
                    error=verification_error,
                    stdout=manage_result.stdout,
                    stderr=manage_result.stderr,
                )

            return WorkerResult(
                issue_id=issue.issue_id,
                success=True,
                branch_name=branch_name,
                worktree_path=worktree_path,
                changed_files=changed_files,
                duration=time.time() - start_time,
                error=None,
                stdout=manage_result.stdout,
                stderr=manage_result.stderr,
                was_corrected=was_corrected,
            )

        except Exception as e:
            return WorkerResult(
                issue_id=issue.issue_id,
                success=False,
                branch_name=branch_name,
                worktree_path=worktree_path,
                duration=time.time() - start_time,
                error=str(e),
            )

    def _setup_worktree(self, worktree_path: Path, branch_name: str) -> None:
        """Create a git worktree with a new branch.

        Args:
            worktree_path: Path for the new worktree
            branch_name: Name of the new branch
        """
        # Remove existing worktree if present
        if worktree_path.exists():
            self._cleanup_worktree(worktree_path)

        # Create new worktree with branch
        result = subprocess.run(
            ["git", "worktree", "add", "-b", branch_name, str(worktree_path)],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to create worktree: {result.stderr}")

        # Copy git identity from main repo
        for config_key in ["user.email", "user.name"]:
            value_result = subprocess.run(
                ["git", "config", config_key],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            )
            if value_result.returncode == 0 and value_result.stdout.strip():
                subprocess.run(
                    ["git", "config", config_key, value_result.stdout.strip()],
                    cwd=worktree_path,
                    capture_output=True,
                )

        # Copy .claude settings from main repo to worktree (for auth tokens, etc.)
        main_claude_dir = self.repo_path / ".claude"
        worktree_claude_dir = worktree_path / ".claude"

        if main_claude_dir.exists():
            settings_file = main_claude_dir / "settings.local.json"
            if settings_file.exists():
                worktree_claude_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(settings_file, worktree_claude_dir / "settings.local.json")
                self.logger.info("Copied .claude/settings.local.json to worktree")

        self.logger.info(f"Created worktree at {worktree_path} on branch {branch_name}")

        # Verify model if --show-model flag is set (requires API call)
        if self.parallel_config.show_model:
            model = self._detect_worktree_model_via_api(worktree_path)
            if model:
                self.logger.info(f"  Using model: {model}")
            else:
                self.logger.warning("  Could not detect Claude CLI model")

    def _detect_worktree_model_via_api(self, worktree_path: Path) -> str | None:
        """Detect the model Claude will use by making an API call.

        Runs a minimal Claude command with JSON output and parses the modelUsage
        field to verify settings.local.json is being respected.

        Args:
            worktree_path: Path to the worktree to test

        Returns:
            Model name (e.g., "claude-sonnet-4-20250514") or None if unable to detect
        """
        try:
            # Use a minimal prompt that requires an API call to get modelUsage
            result = subprocess.run(
                [
                    "claude",
                    "-p",
                    "reply with just 'ok'",
                    "--output-format",
                    "json",
                ],
                cwd=worktree_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                data: dict[str, Any] = json.loads(result.stdout.strip())
                model_usage: dict[str, Any] = data.get("modelUsage", {})
                # Return the first (primary) model from modelUsage
                if model_usage:
                    return cast(str, next(iter(model_usage.keys())))
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            pass
        return None

    def _cleanup_worktree(self, worktree_path: Path) -> None:
        """Remove a git worktree and its associated branch.

        Args:
            worktree_path: Path to the worktree to remove
        """
        if not worktree_path.exists():
            return

        # Get branch name before removing worktree
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
        branch_name = branch_result.stdout.strip() if branch_result.returncode == 0 else None

        # Remove worktree
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            cwd=self.repo_path,
            capture_output=True,
            timeout=30,
        )

        # If worktree removal failed, force delete directory
        if worktree_path.exists():
            shutil.rmtree(worktree_path, ignore_errors=True)

        # Delete the branch if it was a parallel branch
        if branch_name and branch_name.startswith("parallel/"):
            subprocess.run(
                ["git", "branch", "-D", branch_name],
                cwd=self.repo_path,
                capture_output=True,
                timeout=10,
            )

    def _run_claude_command(
        self,
        command: str,
        working_dir: Path,
        issue_id: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run a Claude CLI command with real-time output streaming.

        Args:
            command: The command to run (e.g., "/ll:ready_issue BUG-123")
            working_dir: Directory to run the command in
            issue_id: Optional issue ID for subprocess tracking

        Returns:
            CompletedProcess with stdout and stderr
        """
        stream_output = self.parallel_config.stream_subprocess_output

        def stream_callback(line: str, is_stderr: bool) -> None:
            if stream_output:
                if is_stderr:
                    print(f"  {line}", file=sys.stderr)
                else:
                    self.logger.info(f"  {line}")

        def on_start(process: subprocess.Popen[str]) -> None:
            if issue_id:
                with self._process_lock:
                    self._active_processes[issue_id] = process

        def on_end(process: subprocess.Popen[str]) -> None:
            if issue_id:
                with self._process_lock:
                    self._active_processes.pop(issue_id, None)

        return _run_claude_base(
            command=command,
            timeout=self.parallel_config.timeout_per_issue,
            working_dir=working_dir,
            stream_callback=stream_callback if stream_output else None,
            on_process_start=on_start if issue_id else None,
            on_process_end=on_end if issue_id else None,
        )

    def _get_changed_files(self, worktree_path: Path) -> list[str]:
        """Get list of files changed in the worktree.

        Args:
            worktree_path: Path to the worktree

        Returns:
            List of changed file paths relative to repo root
        """
        result = subprocess.run(
            ["git", "diff", "--name-only", "main", "HEAD"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return []

        return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]

    def _verify_work_was_done(self, changed_files: list[str]) -> tuple[bool, str]:
        """Verify that actual implementation work was done.

        Checks that changed files include source code, not just issue files,
        documentation, or other non-implementation artifacts.

        Args:
            changed_files: List of files changed during processing

        Returns:
            Tuple of (success, error_message)
        """
        if not changed_files:
            return False, "No files were changed during implementation"

        # Patterns that indicate non-implementation changes
        non_code_patterns = (
            ".issues/",
            ".speckit/",
            "thoughts/",
            "docs/",
            ".md",
            ".txt",
            ".json",
            ".yaml",
            ".yml",
            ".toml",
        )

        # Patterns that indicate actual code changes
        code_patterns = (
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".rs",
            ".go",
            ".java",
            ".c",
            ".cpp",
            ".h",
            ".hpp",
            ".rb",
            ".php",
            ".swift",
            ".kt",
            ".cs",
            ".scala",
            ".clj",
            ".ex",
            ".exs",
        )

        code_files = []
        non_code_files = []

        for file_path in changed_files:
            is_code = any(file_path.endswith(ext) for ext in code_patterns)
            is_non_code_dir = any(pattern in file_path for pattern in non_code_patterns[:4])

            if is_code and not is_non_code_dir:
                code_files.append(file_path)
            else:
                non_code_files.append(file_path)

        if not code_files:
            if non_code_files:
                return False, (
                    f"Only non-code files changed ({len(non_code_files)} files): "
                    f"{', '.join(non_code_files[:3])}{'...' if len(non_code_files) > 3 else ''}"
                )
            return False, "No implementation files were modified"

        return True, ""

    @property
    def active_count(self) -> int:
        """Number of currently active workers.

        Includes both workers with running futures AND workers whose futures
        are done but callbacks haven't completed yet.
        """
        running_futures = sum(1 for f in self._active_workers.values() if not f.done())
        with self._callback_lock:
            pending_callback_count = len(self._pending_callbacks)
        return running_futures + pending_callback_count

    def cleanup_all_worktrees(self) -> None:
        """Clean up all worker worktrees."""
        worktree_base = self.repo_path / self.parallel_config.worktree_base
        if not worktree_base.exists():
            return

        for worktree_dir in worktree_base.iterdir():
            if worktree_dir.is_dir() and worktree_dir.name.startswith("worker-"):
                self._cleanup_worktree(worktree_dir)

        self.logger.info("Cleaned up all worker worktrees")
