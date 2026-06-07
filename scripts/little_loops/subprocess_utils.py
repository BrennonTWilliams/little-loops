"""Subprocess utilities for Claude CLI invocation.

Provides shared functionality for running Claude CLI commands with
real-time output streaming, timeout handling, and context handoff detection.
"""

from __future__ import annotations

import json
import logging
import os
import re
import selectors
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from little_loops.host_runner import resolve_host

logger = logging.getLogger(__name__)

# Callback type: (line: str, is_stderr: bool) -> None
OutputCallback = Callable[[str, bool], None]

# Process lifecycle callback: (process: Popen) -> None
ProcessCallback = Callable[[subprocess.Popen[str]], None]

# Model detection callback: (model: str) -> None
ModelCallback = Callable[[str], None]

# Usage callback: (input_tokens: int, output_tokens: int) -> None
# Kept for back-compat with issue_manager.py and worker_pool.py callers.
UsageCallback = Callable[[int, int], None]


@dataclass
class TokenUsage:
    """Token usage from a single host-CLI invocation."""

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    model: str


# Detailed usage callback — receives all four token fields plus model ID.
DetailedUsageCallback = Callable[[TokenUsage], None]

# Context handoff detection pattern
CONTEXT_HANDOFF_PATTERN = re.compile(r"CONTEXT_HANDOFF:\s*Ready for fresh session")
CONTINUATION_PROMPT_PATH = Path(".ll/ll-continue-prompt.md")

# Sentinel file written when a session ends with high context usage (Option G).
# Consumed by run_with_continuation; NOT deleted by session-cleanup.sh.
SENTINEL_PATH = Path(".ll/ll-context-handoff-needed")

# Chars of captured_stdout to include in Option J guillotine prompt (≈3K tokens).
_GUILLOTINE_TAIL_CHARS = 12_000
# Lines of original_command to include for task intent.
_GUILLOTINE_MAX_TASK_LINES = 20


def detect_context_handoff(output: str) -> bool:
    """Check if output contains a context handoff signal.

    Args:
        output: Command output to check

    Returns:
        True if context handoff was signaled
    """
    return bool(CONTEXT_HANDOFF_PATTERN.search(output))


def read_continuation_prompt(repo_path: Path | None = None) -> str | None:
    """Read the continuation prompt file if it exists.

    Args:
        repo_path: Optional repository root path

    Returns:
        Contents of continuation prompt, or None if not found
    """
    prompt_path = (repo_path or Path.cwd()) / CONTINUATION_PROMPT_PATH
    if prompt_path.exists():
        return prompt_path.read_text()
    return None


def read_sentinel(repo_path: Path | None = None) -> dict | None:
    """Read and consume the context-handoff sentinel file if it exists.

    The sentinel is written by context-handoff-sentinel.sh (Stop hook) or
    the Python layer in run_with_continuation when a session ends with high
    context usage but no CONTEXT_HANDOFF signal.

    Args:
        repo_path: Optional repository root path

    Returns:
        Parsed sentinel dict, or None if not present
    """
    sentinel_path = (repo_path or Path.cwd()) / SENTINEL_PATH
    if not sentinel_path.exists():
        return None
    try:
        data = json.loads(sentinel_path.read_text())
        sentinel_path.unlink(missing_ok=True)
        return data
    except Exception:
        sentinel_path.unlink(missing_ok=True)
        return {}


def write_sentinel(
    repo_path: Path | None = None,
    token_count: int = 0,
    context_limit: int = 200_000,
) -> None:
    """Write the context-handoff sentinel file.

    Args:
        repo_path: Optional repository root path
        token_count: Total tokens used in the session
        context_limit: Context window size
    """
    import datetime

    sentinel_path = (repo_path or Path.cwd()) / SENTINEL_PATH
    usage_percent = int(token_count * 100 / context_limit) if context_limit > 0 else 0
    try:
        sentinel_path.parent.mkdir(parents=True, exist_ok=True)
        sentinel_path.write_text(
            json.dumps(
                {
                    "written_at": datetime.datetime.now(datetime.UTC).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                    "token_count": token_count,
                    "context_limit": context_limit,
                    "usage_percent": usage_percent,
                }
            )
        )
    except Exception:
        pass


def assemble_guillotine_prompt(
    original_command: str,
    captured_stdout: str,
    token_stats: dict,
) -> str:
    """Assemble a fresh-session continuation prompt for Option J (parent-side guillotine).

    Called when context > 90% or "Prompt is too long" is detected with no handoff.
    The resulting prompt is passed to a BRAND-NEW claude -p session (not --resume),
    so it starts with 0 tokens.

    Args:
        original_command: The original task command / skill invocation
        captured_stdout: All Claude text output captured so far
        token_stats: Dict with keys: input_tokens, output_tokens, context_limit,
                     trigger_reason (optional)

    Returns:
        Assembled continuation prompt string
    """
    task_lines = original_command.strip().splitlines()[:_GUILLOTINE_MAX_TASK_LINES]
    task_excerpt = "\n".join(task_lines)
    if len(original_command.strip().splitlines()) > _GUILLOTINE_MAX_TASK_LINES:
        task_excerpt += f"\n... (truncated to {_GUILLOTINE_MAX_TASK_LINES} lines)"

    stdout_tail = (captured_stdout or "")[-_GUILLOTINE_TAIL_CHARS:]
    if not stdout_tail:
        stdout_tail = "(no output captured before interruption)"

    input_tokens = token_stats.get("input_tokens", 0)
    output_tokens = token_stats.get("output_tokens", 0)
    context_limit = token_stats.get("context_limit", 200_000)
    trigger_reason = token_stats.get("trigger_reason", "context > 90%")

    scratch_listing = _list_scratch_files()

    return f"""\
⚠ CONTEXT LIMIT REACHED — FRESH SESSION CONTINUATION

The previous automation session exhausted its context window before completing.
This fresh session (new context window, starts at 0 tokens) is continuing from
that interrupted session.

## Original Task
{task_excerpt}

## Session Progress at Interruption
- Approximate tokens used: {input_tokens + output_tokens:,} / {context_limit:,}
- Trigger reason: {trigger_reason}

## Last Session Output (what was happening at interruption)
{stdout_tail}

## Scratch Pad Files Available
{scratch_listing}

## Instructions for This Session
1. Do NOT restart from scratch — the previous session made progress (see above)
2. Read the "Last Session Output" section to understand exactly where we were
3. Check the scratch pad files before re-running expensive operations
4. Continue implementation from the interruption point
5. Complete normally: test, commit, close the issue as usual
"""


def _list_scratch_files() -> str:
    """List files in .loops/tmp/scratch/ with sizes for the guillotine prompt."""
    scratch_dir = Path(".loops/tmp/scratch")
    if not scratch_dir.exists():
        return "None"
    try:
        files = sorted(scratch_dir.iterdir())
        if not files:
            return "None"
        lines = []
        for f in files:
            try:
                size_kb = f.stat().st_size // 1024
                lines.append(f"  {f.name} ({size_kb}KB)")
            except Exception:
                lines.append(f"  {f.name}")
        return "\n".join(lines)
    except Exception:
        return "None"


def run_claude_command(
    command: str,
    timeout: int = 3600,
    working_dir: Path | None = None,
    stream_callback: OutputCallback | None = None,
    on_process_start: ProcessCallback | None = None,
    on_process_end: ProcessCallback | None = None,
    idle_timeout: int = 0,
    on_model_detected: ModelCallback | None = None,
    on_usage: UsageCallback | None = None,
    on_usage_detailed: DetailedUsageCallback | None = None,
    agent: str | None = None,
    tools: list[str] | None = None,
    resume_session: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Invoke Claude CLI command with real-time output streaming.

    Args:
        command: Command to pass to Claude CLI
        timeout: Timeout in seconds (0 for no timeout)
        working_dir: Optional working directory for the command
        stream_callback: Optional callback for streaming output lines.
            Called with (line, is_stderr) for each line of output.
        on_process_start: Optional callback invoked after process starts.
            Receives the Popen object for tracking/management.
        on_process_end: Optional callback invoked after process completes.
            Receives the Popen object. Called in finally block.
        idle_timeout: Kill process if no output for this many seconds (0 to disable).
        on_model_detected: Optional callback invoked with the model name from the
            stream-json system/init event. Called at most once per invocation.
        on_usage: Optional callback invoked with (input_tokens, output_tokens) from
            the stream-json result event. input_tokens includes cache_read_input_tokens.
        on_usage_detailed: Optional callback invoked with a TokenUsage dataclass
            carrying all four token fields (input, output, cache_read, cache_creation)
            plus the model ID from the stream-json result event.
        resume_session: If True, passes --continue to the Claude CLI to continue the
            most recent conversation. Used for the Option E explicit-handoff path.

    Returns:
        CompletedProcess with stdout/stderr captured

    Raises:
        subprocess.TimeoutExpired: If command exceeds timeout or idle timeout.
            When triggered by idle timeout, the output field is set to "idle_timeout".
    """
    runner = resolve_host()
    invocation = runner.build_streaming(
        prompt=command,
        working_dir=working_dir,
        resume=resume_session,
        agent=agent,
        tools=tools,
    )
    cmd_args = [invocation.binary, *invocation.args]

    env = os.environ.copy()
    env.update(invocation.env)
    if "GIT_DIR" in invocation.env:
        logger.debug("Worktree detected: GIT_DIR=%s", invocation.env["GIT_DIR"])

    process = subprocess.Popen(
        cmd_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,  # Line buffered
        cwd=working_dir,
        env=env,
    )

    if on_process_start:
        on_process_start(process)

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    detected_model: str = "unknown"

    # Use selectors for non-blocking read from both streams
    with selectors.DefaultSelector() as sel:
        if process.stdout:
            sel.register(process.stdout, selectors.EVENT_READ)
        if process.stderr:
            sel.register(process.stderr, selectors.EVENT_READ)

        start_time = time.time()
        last_output_time = start_time
        # End-of-turn detection: the stream-json "result" event is the canonical
        # signal that the headless `claude -p` session is done. We break on it
        # instead of waiting for pipe EOF, because background Workflow/Task child
        # processes inherit the stdout/stderr write-ends and a pipe only reports
        # EOF when the *last* writer closes it — so EOF may never arrive even
        # though the turn finished, hanging the reader until the wall-clock
        # timeout fires on a successful run.
        result_seen = False

        try:
            while sel.get_map():
                now = time.time()
                if timeout and (now - start_time) > timeout:
                    process.kill()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        logger.warning(
                            "Process %s did not terminate within 10s after kill",
                            process.pid,
                        )
                    raise subprocess.TimeoutExpired(cmd_args, timeout)

                if idle_timeout and (now - last_output_time) > idle_timeout:
                    process.kill()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        logger.warning(
                            "Process %s did not terminate within 10s after kill",
                            process.pid,
                        )
                    raise subprocess.TimeoutExpired(cmd_args, idle_timeout, output="idle_timeout")

                ready = sel.select(timeout=1.0)
                for key, _ in ready:
                    line = key.fileobj.readline()  # type: ignore[union-attr]
                    if not line:
                        sel.unregister(key.fileobj)
                        continue

                    last_output_time = time.time()
                    line = line.rstrip("\n")
                    is_stderr = key.fileobj is process.stderr

                    if not is_stderr:
                        try:
                            event = json.loads(line)
                            etype = event.get("type")
                            if etype == "system" and event.get("subtype") == "init":
                                if "model" in event:
                                    detected_model = event["model"]
                                    if on_model_detected:
                                        on_model_detected(event["model"])
                                continue  # don't add to stdout_lines
                            elif etype == "assistant":
                                msg = event.get("message", {})
                                text_parts = [
                                    block["text"]
                                    for block in msg.get("content", [])
                                    if block.get("type") == "text"
                                ]
                                text = "\n\n".join(text_parts)
                                if not text:
                                    continue
                                for sub_line in text.splitlines() or [""]:
                                    stdout_lines.append(sub_line)
                                    if stream_callback:
                                        stream_callback(sub_line, is_stderr)
                                continue
                            elif etype == "result":
                                usage = event.get("usage", {})
                                if on_usage and usage:
                                    on_usage(
                                        usage.get("input_tokens", 0)
                                        + usage.get("cache_read_input_tokens", 0),
                                        usage.get("output_tokens", 0),
                                    )
                                if on_usage_detailed and usage:
                                    on_usage_detailed(
                                        TokenUsage(
                                            input_tokens=usage.get("input_tokens", 0),
                                            output_tokens=usage.get("output_tokens", 0),
                                            cache_read_tokens=usage.get(
                                                "cache_read_input_tokens", 0
                                            ),
                                            cache_creation_tokens=usage.get(
                                                "cache_creation_input_tokens", 0
                                            ),
                                            model=event.get("model", detected_model),
                                        )
                                    )
                                if event.get("is_error"):
                                    error_text = event.get("error") or event.get("result", "")
                                    if error_text:
                                        stderr_lines.append(f"[result] {error_text}")
                                # Turn is done. Finish draining the current ready
                                # batch (so trailing buffered lines aren't lost),
                                # then break the loop below instead of blocking on
                                # a pipe EOF that inherited background-task FDs may
                                # never deliver.
                                result_seen = True
                                continue  # skip other event types (tool_use, etc.)
                            else:
                                continue  # skip other event types (tool_use, etc.)
                        except (json.JSONDecodeError, KeyError, TypeError):
                            pass  # non-JSON line: pass through as raw text

                    if is_stderr:
                        stderr_lines.append(line)
                    else:
                        stdout_lines.append(line)

                    if stream_callback:
                        stream_callback(line, is_stderr)

                # The "result" event ended the turn and the current ready batch
                # has now been fully drained; stop reading rather than blocking
                # for a pipe EOF that may never arrive.
                if result_seen:
                    break

            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "Process %s did not exit within 30s after streams closed, killing",
                    process.pid,
                )
                process.kill()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    logger.warning(
                        "Process %s did not terminate within 10s after kill",
                        process.pid,
                    )
        finally:
            if on_process_end:
                on_process_end(process)

    return subprocess.CompletedProcess(
        cmd_args,
        process.returncode if process.returncode is not None else -9,
        stdout="\n".join(stdout_lines),
        stderr="\n".join(stderr_lines),
    )
