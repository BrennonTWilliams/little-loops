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

from little_loops.parallel.git_lock import GitLock
from little_loops.parallel.output_parsing import parse_ready_issue_output
from little_loops.parallel.types import ParallelConfig, WorkerResult
from little_loops.subprocess_utils import (
    detect_context_handoff,
    read_continuation_prompt,
)
from little_loops.subprocess_utils import (
    run_claude_command as _run_claude_base,
)
from little_loops.work_verification import verify_work_was_done

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
        git_lock: GitLock | None = None,
    ) -> None:
        """Initialize the worker pool.

        Args:
            parallel_config: Parallel processing configuration
            br_config: Project configuration (for category actions)
            logger: Logger for worker output
            repo_path: Path to the git repository (default: current directory)
            git_lock: Shared lock for git operations (created if not provided)
        """
        self.parallel_config = parallel_config
        self.br_config = br_config
        self.logger = logger
        self.repo_path = repo_path or Path.cwd()
        self._git_lock = git_lock or GitLock(logger)
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
                    self.logger.warning(
                        f"Terminating subprocess for {issue_id} (PID {process.pid})"
                    )
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

        # Capture baseline of main repo status before worker starts
        # Used to detect files incorrectly written to main repo
        baseline_status = self._get_main_repo_baseline()

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
                if concerns:
                    concern_msg = "; ".join(concerns)
                elif ready_parsed["verdict"] == "UNKNOWN":
                    # For UNKNOWN verdicts, show a snippet of output for debugging
                    raw_out = (ready_result.stdout or "")[:200].strip()
                    concern_msg = (
                        f"Could not parse verdict. Output: {raw_out}..."
                        if raw_out
                        else "No output from ready_issue"
                    )
                else:
                    concern_msg = "Issue not ready"
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

            # Step 5: Run manage_issue implementation (with continuation support)
            manage_cmd = self.parallel_config.get_manage_command(
                issue.issue_type, action, issue.issue_id
            )
            manage_result = self._run_with_continuation(
                manage_cmd,
                worktree_path,
                issue_id=issue.issue_id,
            )

            # Step 6: Get list of changed files
            changed_files = self._get_changed_files(worktree_path)

            # Step 7: Verify actual work was done
            # Pass full filename for better doc-only keyword matching
            issue_filename = issue.path.stem if issue.path else ""
            work_verified, verification_error = self._verify_work_was_done(
                changed_files, issue.issue_id, issue_filename
            )

            # Step 8: Detect files leaked to main repo instead of worktree
            leaked_files = self._detect_main_repo_leaks(issue.issue_id, baseline_status)
            if leaked_files:
                self.logger.warning(
                    f"{issue.issue_id} leaked {len(leaked_files)} file(s) to main repo: "
                    f"{leaked_files}"
                )
                # Clean up leaked files to prevent stash conflicts during merge.
                # The actual work is preserved in the worktree branch.
                self._cleanup_leaked_files(leaked_files)

            if manage_result.returncode != 0:
                return WorkerResult(
                    issue_id=issue.issue_id,
                    success=False,
                    branch_name=branch_name,
                    worktree_path=worktree_path,
                    changed_files=changed_files,
                    leaked_files=leaked_files,
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
                    leaked_files=leaked_files,
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
                leaked_files=leaked_files,
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
        result = self._git_lock.run(
            ["worktree", "add", "-b", branch_name, str(worktree_path)],
            cwd=self.repo_path,
            timeout=60,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to create worktree: {result.stderr}")

        # Copy git identity from main repo
        for config_key in ["user.email", "user.name"]:
            value_result = self._git_lock.run(
                ["config", config_key],
                cwd=self.repo_path,
            )
            if value_result.returncode == 0 and value_result.stdout.strip():
                # Worktree config operations don't need the main repo lock
                subprocess.run(
                    ["git", "config", config_key, value_result.stdout.strip()],
                    cwd=worktree_path,
                    capture_output=True,
                )

        # Copy .claude/ directory to establish project root for Claude Code (BUG-007)
        # Claude Code uses .claude/ directory as highest priority for project root detection.
        # Without this, Claude may detect the main repo as project root in worktrees,
        # causing file writes to leak to the main repository.
        claude_dir = self.repo_path / ".claude"
        if claude_dir.exists() and claude_dir.is_dir():
            dest_claude_dir = worktree_path / ".claude"
            if dest_claude_dir.exists():
                shutil.rmtree(dest_claude_dir)
            shutil.copytree(claude_dir, dest_claude_dir)
            self.logger.info("Copied .claude/ directory to worktree")

        # Copy additional configured files from main repo to worktree
        for file_path in self.parallel_config.worktree_copy_files:
            if file_path.startswith(".claude/"):
                continue  # Already copied with full .claude/ directory above
            src = self.repo_path / file_path
            if src.exists():
                dest = worktree_path / file_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                self.logger.info(f"Copied {file_path} to worktree")
            else:
                self.logger.debug(f"Skipped {file_path} (not found in main repo)")

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

        # Get branch name before removing worktree (worktree operation, no lock needed)
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
        branch_name = branch_result.stdout.strip() if branch_result.returncode == 0 else None

        # Remove worktree (main repo operation)
        self._git_lock.run(
            ["worktree", "remove", "--force", str(worktree_path)],
            cwd=self.repo_path,
            timeout=30,
        )

        # If worktree removal failed, force delete directory
        if worktree_path.exists():
            shutil.rmtree(worktree_path, ignore_errors=True)

        # Delete the branch if it was a parallel branch (main repo operation)
        if branch_name and branch_name.startswith("parallel/"):
            self._git_lock.run(
                ["branch", "-D", branch_name],
                cwd=self.repo_path,
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

    def _run_with_continuation(
        self,
        command: str,
        working_dir: Path,
        issue_id: str | None = None,
        max_continuations: int = 3,
    ) -> subprocess.CompletedProcess[str]:
        """Run a Claude command with automatic continuation on context handoff.

        If the command signals CONTEXT_HANDOFF, reads the continuation prompt
        from the worktree and spawns a fresh Claude session to continue.

        Args:
            command: The command to run
            working_dir: Directory (worktree) to run the command in
            issue_id: Optional issue ID for subprocess tracking
            max_continuations: Maximum number of continuation attempts

        Returns:
            Combined CompletedProcess with all session outputs
        """
        all_stdout: list[str] = []
        all_stderr: list[str] = []
        current_command = command
        continuation_count = 0

        while continuation_count <= max_continuations:
            result = self._run_claude_command(
                current_command,
                working_dir,
                issue_id=issue_id,
            )

            all_stdout.append(result.stdout)
            all_stderr.append(result.stderr)

            # Check for context handoff signal
            if detect_context_handoff(result.stdout):
                self.logger.info(f"[{issue_id}] Detected CONTEXT_HANDOFF signal")

                # Read continuation prompt from worktree
                prompt_content = read_continuation_prompt(working_dir)
                if not prompt_content:
                    self.logger.warning(
                        f"[{issue_id}] Context handoff signaled but no continuation prompt found"
                    )
                    break

                if continuation_count >= max_continuations:
                    self.logger.warning(
                        f"[{issue_id}] Reached max continuations ({max_continuations}), stopping"
                    )
                    break

                continuation_count += 1
                self.logger.info(
                    f"[{issue_id}] Starting continuation session #{continuation_count}"
                )

                # Use continuation prompt as the new command
                current_command = prompt_content.replace('"', '\\"')
                continue

            # No handoff signal, we're done
            break

        return subprocess.CompletedProcess(
            args=result.args,
            returncode=result.returncode,
            stdout="\n---CONTINUATION---\n".join(all_stdout),
            stderr="\n---CONTINUATION---\n".join(all_stderr),
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

    def _verify_work_was_done(
        self, changed_files: list[str], issue_id: str, issue_filename: str = ""
    ) -> tuple[bool, str]:
        """Verify that actual implementation work was done.

        Uses the shared verify_work_was_done() function to check that changed
        files include meaningful work, not just issue files or other artifacts.

        Args:
            changed_files: List of files changed during processing
            issue_id: The issue ID being processed (unused, kept for compatibility)
            issue_filename: Full issue filename (unused, kept for compatibility)

        Returns:
            Tuple of (success, error_message)
        """
        if not changed_files:
            return False, "No files were changed during implementation"

        # Check if code changes are required
        if not self.parallel_config.require_code_changes:
            return True, ""

        # Use shared verification function
        if verify_work_was_done(self.logger, changed_files):
            return True, ""

        return False, "Only excluded files modified (e.g., .issues/, thoughts/)"

    def _detect_main_repo_leaks(self, issue_id: str, baseline_status: set[str]) -> list[str]:
        """Detect files incorrectly written to main repo instead of worktree.

        Claude Code may write files to the main repository instead of the
        worktree due to project root detection issues (see GitHub #8771).
        This method detects such leaks by comparing main repo status before
        and after worker execution.

        Args:
            issue_id: ID of the issue being processed (for pattern matching)
            baseline_status: Set of file paths from git status before worker started

        Returns:
            List of file paths that were leaked to main repo
        """
        # Get current status of main repo
        result = self._git_lock.run(
            ["status", "--porcelain"],
            cwd=self.repo_path,
            timeout=30,
        )

        if result.returncode != 0:
            return []

        current_files: set[str] = set()
        for line in result.stdout.strip().split("\n"):
            if not line or len(line) < 3:
                continue
            # Extract file path (after status codes and space)
            file_path = line[3:].strip()
            # Handle renamed files (old -> new)
            if " -> " in file_path:
                file_path = file_path.split(" -> ")[-1]
            current_files.add(file_path)

        # Find new files that appeared during worker execution
        new_files = current_files - baseline_status

        # Filter to files likely related to this issue
        issue_id_lower = issue_id.lower()
        leaked_files: list[str] = []

        for file_path in new_files:
            # Skip state file (managed by orchestrator)
            if file_path.endswith(".parallel-manage-state.json"):
                continue
            # Skip .gitignore (may be modified by ll-parallel)
            if file_path == ".gitignore":
                continue

            # Check if file is related to this issue
            file_lower = file_path.lower()
            if issue_id_lower in file_lower:
                leaked_files.append(file_path)
            # Also catch source files that shouldn't be modified in main
            elif file_path.startswith(("backend/", "src/", "lib/", "tests/")):
                leaked_files.append(file_path)
            # Catch thoughts/plans files
            elif file_path.startswith("thoughts/"):
                leaked_files.append(file_path)

        return leaked_files

    def _cleanup_leaked_files(self, leaked_files: list[str]) -> int:
        """Discard leaked files from main repo working directory.

        Claude Code sometimes writes files to the main repo instead of the
        worktree. These files cause stash conflicts during merge operations.
        Since the actual work is preserved in the worktree branch, we can
        safely discard these leaked changes from the main repo.

        Args:
            leaked_files: List of file paths leaked to main repo

        Returns:
            Number of files successfully cleaned up
        """
        if not leaked_files:
            return 0

        cleaned = 0

        # Get status to determine which files are tracked vs untracked
        status_result = self._git_lock.run(
            ["status", "--porcelain", "--"] + leaked_files,
            cwd=self.repo_path,
            timeout=30,
        )

        tracked_files: list[str] = []
        untracked_files: list[str] = []

        for line in status_result.stdout.splitlines():
            if not line or len(line) < 3:
                continue
            status_code = line[:2]
            file_path = line[3:].split(" -> ")[-1].strip()

            if status_code.startswith("?"):
                # Untracked file - need to delete
                untracked_files.append(file_path)
            else:
                # Tracked file - can use git checkout to discard
                tracked_files.append(file_path)

        # Discard changes to tracked files
        if tracked_files:
            checkout_result = self._git_lock.run(
                ["checkout", "--"] + tracked_files,
                cwd=self.repo_path,
                timeout=30,
            )
            if checkout_result.returncode == 0:
                cleaned += len(tracked_files)
            else:
                self.logger.warning(
                    f"Failed to discard tracked leaked files: {checkout_result.stderr}"
                )

        # Delete untracked files
        for file_path in untracked_files:
            full_path = self.repo_path / file_path
            try:
                if full_path.exists():
                    full_path.unlink()
                    cleaned += 1
            except OSError as e:
                self.logger.warning(f"Failed to delete leaked file {file_path}: {e}")

        if cleaned > 0:
            self.logger.info(f"Cleaned up {cleaned} leaked file(s) from main repo")

        return cleaned

    def _get_main_repo_baseline(self) -> set[str]:
        """Get baseline of modified/untracked files in main repo.

        Returns:
            Set of file paths currently showing in git status
        """
        result = self._git_lock.run(
            ["status", "--porcelain"],
            cwd=self.repo_path,
            timeout=30,
        )

        if result.returncode != 0:
            return set()

        files: set[str] = set()
        for line in result.stdout.strip().split("\n"):
            if not line or len(line) < 3:
                continue
            file_path = line[3:].strip()
            if " -> " in file_path:
                file_path = file_path.split(" -> ")[-1]
            files.add(file_path)

        return files

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
