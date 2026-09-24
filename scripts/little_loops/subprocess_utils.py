"""Subprocess utilities for Claude CLI invocation.

Provides shared functionality for running Claude CLI commands with
real-time output streaming, timeout handling, and context handoff detection.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import re
import selectors
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from little_loops.context_window import context_window_for
from little_loops.host_runner import (
    AutomationContext,
    project_child_env,
    resolve_host,
)

if TYPE_CHECKING:
    from little_loops.parallel.types import SprintWorkerContext

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

# Result-seen callback: (result_seen: bool) -> None (BUG-2731). Surfaces
# whether a stream-json "result" event was observed before the subprocess
# exited, without widening run_claude_command()'s CompletedProcess return
# type — same mutable-closure precedent as peak_rss_mb (fsm/runners.py).
ResultSeenCallback = Callable[[bool], None]

# Session-ID detection callback: (session_id: str) -> None (FEAT-2711). The
# `system`/`init` stream-json event carries `session_id` alongside `model`;
# this was previously parsed and discarded. Same mutable-closure precedent as
# on_model_detected — lets FSM callers key continuity-chain compaction to the
# session that just ran without widening the CompletedProcess return type.
SessionIdCallback = Callable[[str], None]


TokenProvenance = Literal["measured", "estimated", "unknown"]
TokenScopeKind = Literal["request", "invocation", "session", "context", "unknown"]
ObservedAtBasis = Literal["event", "received"]


@dataclass
class TokenUsage:
    """Token usage from a single host-CLI invocation (ENH-3538).

    Components are ``None`` when the host did not report them; ``None`` is
    *unknown*, never an implicit zero.
    """

    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None
    cache_creation_tokens: int | None
    model: str
    is_batch: bool = False
    """True when this usage came from the Message Batches API (FEAT-2716),
    eligible for the flat 50% batch discount in :func:`~little_loops.pricing.estimate_cost_usd`.
    Defaults to False so every existing construction site is unaffected."""
    provenance: TokenProvenance = "unknown"
    """Trust classification of the observation. No acquisition path is ``measured`` yet."""
    host: str | None = None
    """Runtime host that produced the observation (``claude-code``, ``codex``, ...)."""
    scope_kind: TokenScopeKind = "unknown"
    observed_at: str | None = None
    observed_at_basis: ObservedAtBasis | None = None


# Detailed usage callback — receives all four token fields plus model ID.
DetailedUsageCallback = Callable[[TokenUsage], None]


def _stamp_usage(usage: TokenUsage, host: str) -> TokenUsage:
    """Attach the invoking host, invocation scope and receipt time (ENH-3538).

    Stamped in :func:`run_claude_command` where the ``HostRunner`` is resolved,
    before any usage callback fires. Terminal events carry no timestamp, so the
    observation time is the receipt time (``observed_at_basis='received'``).
    """
    if usage.host is not None and usage.host != host:
        logger.warning(
            "usage host %r disagrees with runner host %r; keeping runner", usage.host, host
        )
    return dataclasses.replace(
        usage,
        host=host,
        scope_kind="invocation",
        observed_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        observed_at_basis="received",
    )


def known_input_lower_bound(usage: TokenUsage) -> tuple[int, int]:
    """Return ``(input + cache_read, output)`` summing only the known components.

    A lower bound for budget guards that must not go silent when a component is
    missing (ENH-3538).
    """
    return (
        (usage.input_tokens or 0) + (usage.cache_read_tokens or 0),
        usage.output_tokens or 0,
    )


def _fire_legacy_usage(on_usage: UsageCallback, usage: TokenUsage) -> None:
    """Invoke the legacy two-int callback only when input/output/cache_read are all known."""
    if usage.input_tokens is None or usage.output_tokens is None or usage.cache_read_tokens is None:
        logger.debug("legacy UsageCallback suppressed: incomplete usage observation")
        return
    on_usage(usage.input_tokens + usage.cache_read_tokens, usage.output_tokens)


def usage_from_event(event: dict[str, Any], *, default_model: str) -> TokenUsage | None:
    """Parse a stream-json/NDJSON terminal event's usage block into a :class:`TokenUsage`.

    The single place that knows the Claude ``result`` event's usage key names
    (``cache_read_input_tokens``/``cache_creation_input_tokens``) and Codex's
    ``turn.completed`` event's key names (``cached_input_tokens``/
    ``cache_write_input_tokens``, no ``model`` field) (ENH-3464 Decision 8a).
    Returns ``None`` when *event* isn't a recognized terminal event type or
    carries no ``usage`` block. A missing or explicit-``null`` component stays
    ``None`` (unknown); only a reported ``0`` is zero. This supersedes ENH-3464
    Decision 3: an omitted Codex ``cache_write_input_tokens`` is unknown until
    BUG-3531 Decision 6 establishes otherwise (ENH-3538).
    """
    etype = event.get("type")
    usage = event.get("usage")
    if not usage:
        return None
    if etype == "result":
        return TokenUsage(
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            cache_read_tokens=usage.get("cache_read_input_tokens"),
            cache_creation_tokens=usage.get("cache_creation_input_tokens"),
            model=event.get("model", default_model),
        )
    if etype == "turn.completed":
        return TokenUsage(
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            cache_read_tokens=usage.get("cached_input_tokens"),
            cache_creation_tokens=usage.get("cache_write_input_tokens"),
            model=default_model,
        )
    return None


def usage_from_stream_lines(stdout: str) -> tuple[TokenUsage | None, int | None]:
    """Parse a runner's captured stdout for tokens + tool-call count (ENH-3464 Decision 8b).

    Used by ``_run_skill()``/``_run_prompt()`` to derive
    :class:`~little_loops.runner_spec.RunnerResult`'s efficiency fields post
    hoc from already-captured stdout (no streaming callback wiring). Tries a
    whole-string ``json.loads`` first — the shape ``claude --output-format
    json`` produces (single JSON object, possibly pretty-printed
    multi-line), mirroring :func:`~little_loops.host_runner.run_blocking_json`'s
    parse-order precedent — and returns ``tool_calls=None`` in that case (the
    PROMPT/DSL path never observes ``assistant`` events, Decision 4). If the
    whole string doesn't parse (stream-json / Codex NDJSON, multiple
    top-level objects), falls back to per-line parsing: the last
    ``result``/``turn.completed`` event's usage via :func:`usage_from_event`,
    plus a tally of ``tool_use`` blocks inside ``assistant`` events.
    ``tool_calls`` is ``None`` when no ``assistant`` event was observed at
    all (nothing to distinguish from an unreachable PROMPT-path 0), and an
    integer count (possibly 0) once at least one was seen.
    """
    stripped = stdout.strip()
    if not stripped:
        return None, None
    try:
        envelope = json.loads(stripped)
    except json.JSONDecodeError:
        envelope = None
    if isinstance(envelope, dict):
        return usage_from_event(envelope, default_model="unknown"), None

    detected_model = "unknown"
    tool_call_count = 0
    saw_assistant = False
    usage: TokenUsage | None = None
    for line in stripped.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        etype = event.get("type")
        if etype == "system" and event.get("subtype") == "init" and "model" in event:
            detected_model = event["model"]
        elif etype == "assistant":
            saw_assistant = True
            msg = event.get("message", {})
            for block in msg.get("content", []):
                if block.get("type") == "tool_use":
                    tool_call_count += 1
        elif etype in ("result", "turn.completed"):
            parsed = usage_from_event(event, default_model=detected_model)
            if parsed is not None:
                usage = parsed
    return usage, (tool_call_count if saw_assistant else None)


@dataclass(frozen=True)
class ToolCall:
    """A single ordered tool-call captured live from a stream-json run.

    Mirrors ``scripts/tests/spike/eval_trace_capture/trace_capture.py``'s
    ``ToolCall`` shape, proven in the FEAT-2878 spike. ``index`` is the
    call's 0-based position in the ordered trace for this invocation.
    """

    index: int
    name: str
    input: dict[str, object]


# Tool-call callback: (call: ToolCall) -> None (FEAT-2878). Invoked live,
# once per ordered tool_use block parsed out of an "assistant" stream-json
# event, so a caller can build/assert an ordered tool-call trace during a
# run instead of only reconstructing it post-hoc from on-disk JSONL logs.
ToolCallCallback = Callable[[ToolCall], None]

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
# Max scratch-pad files to list; the dir can accumulate thousands over a long
# automation run and an unbounded listing would blow up the prompt size the
# guillotine exists to cap.
_GUILLOTINE_MAX_SCRATCH_FILES = 30


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
    context_limit: int | None = None,
) -> None:
    """Write the context-handoff sentinel file.

    Args:
        repo_path: Optional repository root path
        token_count: Total tokens used in the session
        context_limit: Context window size
    """
    import datetime

    if context_limit is None:
        context_limit = context_window_for(None)
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
    sprint_context: SprintWorkerContext | None = None,
    issue_id: str | None = None,
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
    context_limit = token_stats.get("context_limit") or context_window_for(None)
    trigger_reason = token_stats.get("trigger_reason", "context > 90%")

    scratch_listing = _list_scratch_files()

    body = f"""\
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

    if sprint_context is not None:
        framing = (
            f"## Sprint Worker Context\n"
            f"You are a sprint worker. Process exactly ONE issue: {sprint_context.issue_id}\n"
            f"After completing this issue, exit immediately — do NOT process other issues.\n"
            f"Do NOT ask for further instructions. Exit with code 0.\n"
            f"Branch: {sprint_context.branch}\n\n"
        )
        return framing + body

    if issue_id is not None:
        framing = (
            f"## Scope Constraint\n"
            f"Process exactly ONE issue: {issue_id}\n"
            f"After completing this issue, exit immediately — do NOT process other issues.\n"
            f"Do NOT ask for further instructions. Exit with code 0.\n\n"
        )
        return framing + body

    return body


def _list_scratch_files() -> str:
    """List files in .loops/tmp/scratch/ with sizes for the guillotine prompt."""
    scratch_dir = Path(".loops/tmp/scratch")
    if not scratch_dir.exists():
        return "None"
    try:
        files = sorted(scratch_dir.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
        if not files:
            return "None"
        shown = files[:_GUILLOTINE_MAX_SCRATCH_FILES]
        lines = []
        for f in shown:
            try:
                size_kb = f.stat().st_size // 1024
                lines.append(f"  {f.name} ({size_kb}KB)")
            except Exception:
                lines.append(f"  {f.name}")
        remaining = len(files) - len(shown)
        if remaining > 0:
            lines.append(f"  ... and {remaining} more file(s)")
        return "\n".join(lines)
    except Exception:
        return "None"


_shutdown_event = threading.Event()


def request_shutdown() -> None:
    """Signal every in-flight ``run_claude_command()`` read loop to abort (BUG-3312).

    Set by an external SIGINT/SIGTERM handler. The read loop observes this
    within ~1s (its existing ``sel.select(timeout=1.0)`` cadence) and kills
    the active process group via ``_kill_process_group()``. Module-level so
    it covers every caller of ``run_claude_command`` (ll-auto, ll-parallel,
    sprint workers, the FSM executor) without threading a new parameter
    through each call chain.
    """
    _shutdown_event.set()


def clear_shutdown() -> None:
    """Reset the shutdown signal. Callers should invoke this at run start so
    state doesn't leak between runs in the same process (e.g. tests)."""
    _shutdown_event.clear()


def is_shutdown_requested() -> bool:
    """Whether ``request_shutdown()`` has been called and not yet cleared."""
    return _shutdown_event.is_set()


def safe_killpg(pgid: int | None, sig: int) -> bool:
    """Validate ``pgid`` then call ``os.killpg(pgid, sig)`` (BUG-3208 single guard).

    Every ``os.killpg`` call in this codebase routes through here so the
    kill(-1, SIGKILL) broadcast trap has exactly one place to be prevented.

    The trap: ``os.killpg(pgid)`` is ``kill(-pgid)``. When ``pgid == 1``
    the kernel treats ``kill(-1, SIGKILL)`` as "signal every process the
    caller can reach with the same real UID" — the xdist controller,
    sibling workers, the hosted runner. ``MagicMock().__index__()`` returns
    1, so any caller that mocks ``subprocess.Popen`` (leaving ``proc.pid``
    as a ``MagicMock``) and reaches a ``os.getpgid(proc.pid)`` /
    ``os.killpg(pgid, sig)`` site without a guard will nuke the whole
    process tree.

    Returns:
        True if ``os.killpg`` was actually issued successfully.
        False if the call was refused — pgid invalid (None, non-int, or
        <= 1) or ``os.killpg`` raised ``ProcessLookupError`` /
        ``PermissionError`` / ``OSError`` / ``AttributeError`` (Windows
        where ``os.killpg`` itself is absent). Callers must use a
        single-PID fallback when this returns False; do not silently
        retry the group kill.

    AttributeError is caught (rather than propagated) so each call site
    keeps its existing Windows fallback shape (``process.kill()``,
    ``os.kill(pid, sig)``, ``proc.terminate()``) without needing a
    separate ``try/except`` per call.
    """
    if pgid is None or not isinstance(pgid, int) or pgid <= 1:
        return False
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError, OSError, AttributeError):
        return False
    return True


def _kill_process_group(process: subprocess.Popen, grace_seconds: float = 0.0) -> None:
    """SIGTERM the process group, then SIGKILL after grace_seconds if still alive.

    grace_seconds=0 (default) preserves the historical immediate-SIGKILL
    behavior for callers that need it. A positive grace_seconds sends SIGTERM
    first and gives the group that long to wind down (e.g. finish a commit or
    lifecycle write, ENH-3130) before escalating to SIGKILL.

    Uses ``safe_killpg`` (POSIX) so background Workflow/Task children
    launched by the session are reaped together with the main process,
    and the kill(-1) broadcast trap (BUG-3208) is rejected at the single
    guard. On any failure (invalid pgid, OSError, missing os.killpg on
    Windows) the helper falls back to ``process.kill()`` / ``terminate()``.
    """
    try:
        pgid = os.getpgid(process.pid)
    except (OSError, AttributeError):
        pgid = None

    if grace_seconds <= 0:
        if not safe_killpg(pgid, signal.SIGKILL):
            process.kill()
        return

    if not safe_killpg(pgid, signal.SIGTERM):
        process.terminate()

    try:
        process.wait(timeout=grace_seconds)
        return
    except subprocess.TimeoutExpired:
        pass

    if not safe_killpg(pgid, signal.SIGKILL):
        process.kill()


def run_claude_command(
    command: str,
    timeout: int = 3600,
    working_dir: Path | None = None,
    stream_callback: OutputCallback | None = None,
    on_process_start: ProcessCallback | None = None,
    on_process_end: ProcessCallback | None = None,
    *,
    on_model_detected: ModelCallback | None = None,
    on_usage: UsageCallback | None = None,
    on_usage_detailed: DetailedUsageCallback | None = None,
    agent: str | None = None,
    tools: list[str] | None = None,
    resume_session: bool = False,
    model: str | None = None,
    automation: AutomationContext | None = None,
    post_stream_close_grace_seconds: int = 300,
    timeout_kill_grace_seconds: float = 0.0,
    on_result_seen: ResultSeenCallback | None = None,
    on_session_id_detected: SessionIdCallback | None = None,
    on_tool_call: ToolCallCallback | None = None,
    workspace_root: Path | None = None,
    extra_env: dict[str, str] | None = None,
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
        on_model_detected: Optional callback invoked with the model name from the
            stream-json system/init event. Called at most once per invocation.
        on_usage: Optional callback invoked with (input_tokens, output_tokens) from
            the stream-json result event. input_tokens includes cache_read_input_tokens.
        on_usage_detailed: Optional callback invoked with a TokenUsage dataclass
            carrying all four token fields (input, output, cache_read, cache_creation)
            plus the model ID from the stream-json result event.
        resume_session: If True, passes --continue to the Claude CLI to continue the
            most recent conversation. Used for the Option E explicit-handoff path.
        automation: ENH-3097 collapsed automation signal (profile,
            disable_background_tasks, idle_timeout), forwarded as-is to
            ``build_streaming()`` and read locally for the selector loop's
            idle threshold. ``None`` disables automation entirely (no
            profile, no background-task disabling, no idle kill).
        post_stream_close_grace_seconds: Grace period (seconds) to wait for the
            process to exit on its own after stdout/stderr streams close before
            force-killing the process group. Must accommodate synchronous
            parallel Agent tool calls (`run_in_background: false`) that can
            still be running when the parent's own streams close (BUG-2718).
        timeout_kill_grace_seconds: Grace period (seconds) given to the process
            group after a wall-clock or idle timeout fires: SIGTERM is sent
            first, and SIGKILL only follows if the group is still alive after
            this many seconds. 0 (default) preserves the historical immediate
            SIGKILL behavior (ENH-3130).
        on_result_seen: Optional callback invoked once, right before return,
            with whether a stream-json "result" event was observed (BUG-2731).
            Lets callers distinguish an exit-143-after-result infra teardown
            (re-runnable) from a genuine mid-turn crash, without widening this
            function's CompletedProcess return type.
        on_session_id_detected: Optional callback invoked with the host CLI's
            `session_id` from the stream-json system/init event (FEAT-2711).
            Called at most once per invocation, alongside on_model_detected.
        on_tool_call: Optional callback invoked live, once per ordered
            ``tool_use`` block parsed out of an "assistant" stream-json
            event (FEAT-2878). Lets a caller build/assert an ordered
            tool-call trace (name, order, input) during the run, instead of
            only reconstructing it post-hoc from on-disk JSONL logs.
        workspace_root: Optional path forwarded to ``build_streaming()`` to
            request that tool access be confined to that directory
            (FEAT-2878). Only honored by hosts advertising
            ``HostCapabilities.workspace_sandboxed`` — see that flag's
            docstring for the current support matrix.
        extra_env: Optional extra environment variables merged over the
            child's environment via ``project_child_env(invocation,
            extra=extra_env)`` (e.g. ``LL_ISSUE_ID``, FEAT-3116's
            task-identity env contract).

    Returns:
        CompletedProcess with stdout/stderr captured

    Raises:
        subprocess.TimeoutExpired: If command exceeds timeout or idle timeout,
            or if request_shutdown() was called (BUG-3312). When triggered by
            idle timeout, the output field is set to "idle_timeout"; when
            triggered by a shutdown request, it is set to "interrupted".
    """
    effective_idle_timeout: float = (automation.idle_timeout or 0) if automation else 0

    runner = resolve_host()
    invocation = runner.build_streaming(
        prompt=command,
        working_dir=working_dir,
        resume=resume_session,
        agent=agent,
        tools=tools,
        model=model,
        automation=automation,
        workspace_root=workspace_root,
    )
    cmd_args = [invocation.binary, *invocation.args]

    env = project_child_env(invocation, extra=extra_env)
    if "GIT_DIR" in invocation.env:
        logger.debug("Worktree detected: GIT_DIR=%s", invocation.env["GIT_DIR"])

    try:
        process = subprocess.Popen(
            cmd_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
            cwd=working_dir,
            env=env,
            start_new_session=True,
        )
    except Exception as exc:
        return subprocess.CompletedProcess(
            args=cmd_args,
            returncode=1,
            stdout="",
            stderr=f"Subprocess spawn failed: {exc}",
        )

    if on_process_start:
        on_process_start(process)

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    detected_model: str = "unknown"
    tool_call_count = 0
    result_seen = False

    def _process_line(line: str, is_stderr: bool) -> None:
        """Dispatch one decoded, newline-stripped stream-json line.

        Shared by both read paths below (raw-fd drain and the readline()
        fallback) so the event-parsing contract stays in exactly one place.
        Mutates ``result_seen``/``detected_model``/``tool_call_count`` via
        closure (the enclosing function's locals) and appends to the
        ``stdout_lines``/``stderr_lines`` lists in place.
        """
        nonlocal detected_model, tool_call_count, result_seen
        line = line.rstrip("\n")

        if not is_stderr:
            try:
                event = json.loads(line)
                etype = event.get("type")
                if etype == "system" and event.get("subtype") == "init":
                    if "model" in event:
                        detected_model = event["model"]
                        if on_model_detected:
                            on_model_detected(event["model"])
                    if event.get("session_id") and on_session_id_detected:
                        on_session_id_detected(str(event["session_id"]))
                    return  # don't add to stdout_lines
                elif etype == "assistant":
                    msg = event.get("message", {})
                    text_parts = [
                        block["text"]
                        for block in msg.get("content", [])
                        if block.get("type") == "text"
                    ]
                    text = "\n\n".join(text_parts)
                    if on_tool_call:
                        for block in msg.get("content", []):
                            if block.get("type") != "tool_use":
                                continue
                            call = ToolCall(
                                index=tool_call_count,
                                name=block.get("name", ""),
                                input=block.get("input", {}),
                            )
                            tool_call_count += 1
                            on_tool_call(call)
                    if not text:
                        return
                    for sub_line in text.splitlines() or [""]:
                        stdout_lines.append(sub_line)
                        if stream_callback:
                            stream_callback(sub_line, is_stderr)
                    return
                elif etype == "result":
                    parsed_usage = usage_from_event(event, default_model=detected_model)
                    if parsed_usage is not None:
                        parsed_usage = _stamp_usage(parsed_usage, runner.name)
                        if on_usage:
                            _fire_legacy_usage(on_usage, parsed_usage)
                        if on_usage_detailed:
                            on_usage_detailed(parsed_usage)
                    if event.get("is_error"):
                        error_text = event.get("error") or event.get("result", "")
                        if error_text:
                            stderr_lines.append(f"[result] {error_text}")
                    # Turn is done. The caller stops draining and breaks the
                    # read loop instead of blocking on a pipe EOF that
                    # inherited background-task FDs may never deliver.
                    result_seen = True
                    return  # skip other event types (tool_use, etc.)
                elif etype == "turn.completed":
                    # Codex `exec --json` terminal event (FEAT-2123). Field
                    # names differ from Claude's "result" usage block; see
                    # exec_events.rs::Usage in openai/codex (no cache-read
                    # split, no model field — Codex reports a single
                    # cached_input_tokens count and never echoes the model).
                    parsed_usage = usage_from_event(event, default_model=detected_model)
                    if parsed_usage is not None and on_usage_detailed:
                        on_usage_detailed(_stamp_usage(parsed_usage, runner.name))
                    return  # skip other event types (item.*, etc.)
                else:
                    return  # skip other event types (tool_use, etc.)
            except (json.JSONDecodeError, KeyError, TypeError):
                pass  # non-JSON line: pass through as raw text

        if is_stderr:
            stderr_lines.append(line)
        else:
            stdout_lines.append(line)

        if stream_callback:
            stream_callback(line, is_stderr)

    # Raw, non-blocking fd for each stream when the underlying object
    # supports it (a real subprocess pipe) — None for a fileno()-less fake
    # (e.g. io.StringIO in tests), which falls back to the plain readline()
    # path below unchanged. Needed to safely drain more than one
    # already-available line per stream: TextIOWrapper.readline() reads
    # ahead via read1() (one syscall's worth, e.g. up to 8KB), so when a
    # writer flushes several short JSON lines back-to-back before going
    # quiet, a single syscall can pull more than one line into
    # TextIOWrapper's own internal buffer — invisible to `selectors`, which
    # only observes OS-level pipe readiness. Without draining that buffer
    # here, a line already sitting there (e.g. the terminal `result` event)
    # can go unread forever once the writer stops producing new bytes.
    # `os.set_blocking(fd, False)` is required to make the drain provably
    # safe: readline() on a NON-blocking pipe can return "" for "no data
    # right now" (indistinguishable from real EOF) instead of raising, so
    # the drain instead reads raw bytes via `os.read()` and splits lines
    # itself, where the OS gives an unambiguous BlockingIOError vs b"".
    def _raw_fd_for(stream: object) -> int | None:
        try:
            fd = stream.fileno()  # type: ignore[attr-defined]
            os.set_blocking(fd, False)
        except (AttributeError, OSError, ValueError):
            return None
        return fd

    stdout_raw_fd = _raw_fd_for(process.stdout) if process.stdout else None
    stderr_raw_fd = _raw_fd_for(process.stderr) if process.stderr else None
    stdout_leftover = ""
    stderr_leftover = ""

    # Use selectors for non-blocking read from both streams
    with selectors.DefaultSelector() as sel:
        if process.stdout:
            sel.register(process.stdout, selectors.EVENT_READ)
        if process.stderr:
            sel.register(process.stderr, selectors.EVENT_READ)

        start_time = time.time()
        last_output_time = start_time

        def _drain_raw(fd: int, leftover: str, is_stderr: bool) -> tuple[str, bool]:
            """Drain every complete line already available on *fd*.

            Returns the updated leftover (undecoded/incomplete trailing text)
            and whether the fd hit true EOF (peer closed) this call.
            """
            nonlocal last_output_time
            eof = False
            while True:
                newline_idx = leftover.find("\n")
                if newline_idx == -1:
                    try:
                        chunk = os.read(fd, 65536)
                    except BlockingIOError:
                        break
                    if not chunk:
                        eof = True
                        if leftover:
                            last_output_time = time.time()
                            _process_line(leftover, is_stderr)
                            leftover = ""
                        break
                    last_output_time = time.time()
                    leftover += chunk.decode("utf-8", errors="replace")
                    continue
                line, leftover = leftover[: newline_idx + 1], leftover[newline_idx + 1 :]
                _process_line(line, is_stderr)
                if result_seen:
                    break
            return leftover, eof

        # End-of-turn detection: the stream-json "result" event is the canonical
        # signal that the headless `claude -p` session is done. We break on it
        # instead of waiting for pipe EOF, because background Workflow/Task child
        # processes inherit the stdout/stderr write-ends and a pipe only reports
        # EOF when the *last* writer closes it — so EOF may never arrive even
        # though the turn finished, hanging the reader until the wall-clock
        # timeout fires on a successful run.

        try:
            while sel.get_map():
                now = time.time()
                if _shutdown_event.is_set():
                    _kill_process_group(process, grace_seconds=timeout_kill_grace_seconds)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        logger.warning(
                            "Process %s did not terminate within 10s after kill",
                            process.pid,
                        )
                    raise subprocess.TimeoutExpired(cmd_args, 0, output="interrupted")

                if timeout and (now - start_time) > timeout:
                    _kill_process_group(process, grace_seconds=timeout_kill_grace_seconds)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        logger.warning(
                            "Process %s did not terminate within 10s after kill",
                            process.pid,
                        )
                    raise subprocess.TimeoutExpired(cmd_args, timeout)

                if effective_idle_timeout and (now - last_output_time) > effective_idle_timeout:
                    _kill_process_group(process, grace_seconds=timeout_kill_grace_seconds)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        logger.warning(
                            "Process %s did not terminate within 10s after kill",
                            process.pid,
                        )
                    raise subprocess.TimeoutExpired(
                        cmd_args, effective_idle_timeout, output="idle_timeout"
                    )

                ready = sel.select(timeout=1.0)
                for key, _ in ready:
                    is_stderr = key.fileobj is process.stderr
                    raw_fd = stderr_raw_fd if is_stderr else stdout_raw_fd

                    if raw_fd is None:
                        # Fallback for a fileno()-less fake stream (e.g.
                        # io.StringIO in tests): identical to the original
                        # single-readline-per-ready-event behavior.
                        line = key.fileobj.readline()  # type: ignore[union-attr]
                        if not line:
                            sel.unregister(key.fileobj)
                            continue
                        last_output_time = time.time()
                        _process_line(line, is_stderr)
                    else:
                        # Drain every already-available line on this fd
                        # before returning to select() — see the comment
                        # above _drain_raw's definition for why a single
                        # readline() per ready-event isn't sufficient.
                        if is_stderr:
                            stderr_leftover, eof = _drain_raw(raw_fd, stderr_leftover, is_stderr)
                        else:
                            stdout_leftover, eof = _drain_raw(raw_fd, stdout_leftover, is_stderr)
                        if eof:
                            sel.unregister(key.fileobj)

                    if result_seen:
                        break

                # The "result" event ended the turn and the current ready batch
                # has now been fully drained; stop reading rather than blocking
                # for a pipe EOF that may never arrive.
                if result_seen:
                    break

            logger.debug(
                "Process %s streams closed via %s; waiting up to %ss before kill",
                process.pid,
                "result event" if result_seen else "natural EOF, no result event",
                post_stream_close_grace_seconds,
            )
            try:
                process.wait(timeout=post_stream_close_grace_seconds)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "Process %s did not exit within %ss after streams closed, killing",
                    process.pid,
                    post_stream_close_grace_seconds,
                )
                _kill_process_group(process)
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

    if on_result_seen:
        on_result_seen(result_seen)

    return subprocess.CompletedProcess(
        cmd_args,
        process.returncode if process.returncode is not None else -9,
        stdout="\n".join(stdout_lines),
        stderr="\n".join(stderr_lines),
    )
