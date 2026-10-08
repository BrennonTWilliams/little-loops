"""Bounded, read-only scoped-commit activity loader for ``capture-issues`` (FEAT-3713).

The only git consumer of the ``ll-next`` arena. It runs **at most two** subprocesses from the
resolved project root:

1. ``git --no-lazy-fetch rev-parse HEAD --is-shallow-repository`` -- the captured HEAD and
   shallow-clone status in one call, and
2. one streamed ``git --no-lazy-fetch log`` from that HEAD that lists, per commit,
   ``%x00<hash> <committer-epoch>`` followed by its first-parent-merge-diff paths (``-z``,
   ``--name-only``, ``--relative``, ``--root``, ``--no-renames``).

Read policy (arena-only; no existing Git helper changes): the enforcing global
``--no-lazy-fetch`` option (Git >= 2.45.0, release notes of 2.45.0) so a partial clone's missing
promisor objects make the evidence *unavailable* instead of fetching; external diff, textconv
and signature helpers are disabled and output is colourless with an explicit format;
``GIT_OPTIONAL_LOCKS=0`` so git cannot refresh the index; every inherited ``GIT_TRACE*`` target is
disabled in the child environment (``GIT_TRACE2``, ``GIT_TRACE2_EVENT`` and
``GIT_TRACE2_PERF`` explicitly ``0``) so a read-only command cannot create a trace file. An older
Git rejects the global option (exit 129), which maps to ``git_unsupported``; nothing is retried.

Framing: records are ``NUL``-token streams (``""``, ``"<hash> <ct>"``, then the commit's paths,
the first prefixed by a single ``\\n``). A path is never empty, so an empty token is always a record
boundary and no filename (not even one embedding control bytes) can forge a header.

The work is bounded by fixed internal defaults (not configuration): at most
:data:`MAX_RECORDS` completed commit records, :data:`MAX_BYTES` combined stdout/stderr and a
shared :data:`BUDGET_SECONDS` monotonic budget across both processes. The process is
stopped and reaped on a work cap, expiry or proven threshold saturation. Only fully decoded
records count; a truncated record is never evidence. A nonzero exit that this collector did not
cause discards the tentative count (activity *unavailable*, never zero). The bounds are
nonpreemptive for OS pipe buffering and in-flight decoding of one read chunk.
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from little_loops.next_arena.scan_state import ScanScope

__all__ = [
    "BUDGET_SECONDS",
    "MAX_BYTES",
    "MAX_RECORDS",
    "MIN_GIT_VERSION",
    "LogDecoder",
    "ScanActivity",
    "child_environment",
    "head_command",
    "load_scope_activity",
    "log_command",
]

#: Git release that introduced the global ``--no-lazy-fetch`` option (2.45.0 release notes).
MIN_GIT_VERSION = "2.45.0"
MAX_RECORDS = 5000
MAX_BYTES = 16 * 1024 * 1024
BUDGET_SECONDS = 2.0
_CHUNK = 64 * 1024
_STDERR_KEEP = 4096

# Unavailable reasons (gate ``activity`` codes) and truncation reasons.
GIT_UNSUPPORTED = "git_unsupported"
GIT_MISSING = "git_missing"
NOT_A_GIT_REPOSITORY = "not_a_git_repository"
GIT_FAILED = "git_failed"
DECODE_ERROR = "decode_error"
TRUNCATED_RECORDS = "record_cap"
TRUNCATED_BYTES = "byte_cap"
TRUNCATED_DEADLINE = "deadline"
SATURATED = "saturated"

_HEADER_RE = re.compile(rb"^([0-9a-f]{40}|[0-9a-f]{64}) (-?[0-9]+)$")
_HEAD_RE = re.compile(r"^[0-9a-f]{40}$|^[0-9a-f]{64}$")


class ProcessLike(Protocol):
    """The subset of :class:`subprocess.Popen` the loader uses (also implemented by fakes)."""

    stdout: IO[bytes] | None
    stderr: IO[bytes] | None
    returncode: int | None

    def wait(self, timeout: float | None = None) -> int: ...

    def kill(self) -> None: ...


PopenFactory = Callable[..., ProcessLike]
Clock = Callable[[], float]


def child_environment(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """The child environment: no inherited ``GIT_TRACE*``, optional locks off, English output."""
    source = os.environ if base is None else base
    env = {k: v for k, v in source.items() if not k.upper().startswith("GIT_TRACE")}
    env.update(
        {
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TRACE": "0",
            "GIT_TRACE2": "0",
            "GIT_TRACE2_EVENT": "0",
            "GIT_TRACE2_PERF": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        }
    )
    return env


def head_command() -> list[str]:
    """Argv of the single HEAD + shallow-status call."""
    return ["git", "--no-lazy-fetch", "rev-parse", "HEAD", "--is-shallow-repository"]


def log_command(head: str, since_epoch: int) -> list[str]:
    """Argv of the streamed scoped-activity log from the captured *head*.

    ``--since-as-filter`` (Git 2.37) only reduces output; the exact inclusive UTC window is
    enforced again by :class:`LogDecoder`. ``--diff-merges=first-parent`` lists merge diffs
    against the first parent without ``--first-parent`` ancestry pruning.
    """
    return [
        "git",
        "--no-lazy-fetch",
        "log",
        head,
        "--format=%x00%H %ct",
        "--root",
        "--no-renames",
        "--diff-merges=first-parent",
        "--name-only",
        "-z",
        "--relative",
        f"--since-as-filter={since_epoch}",
        "--no-ext-diff",
        "--no-textconv",
        "--no-show-signature",
        "--no-color",
    ]


def _epoch_us(moment: datetime) -> int:
    """Integer microseconds since the epoch of a timezone-aware *moment* (no float rounding)."""
    delta = moment.astimezone(UTC) - datetime(1970, 1, 1, tzinfo=UTC)
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


@dataclass(frozen=True)
class ScanActivity:
    """Captured scoped-commit activity (evidence for the ``activity`` gate).

    ``available`` is ``False`` when no trustworthy count exists (``unavailable_reason`` says why);
    activity is then *unknown*, never zero. When available, exactly one of: ``complete`` (the
    traversal finished, ``scoped_commit_count`` is exact), ``saturated`` (``lower_bound`` commits
    were observed, so the threshold is met and the exact total is unknown) or a truncation
    (``truncation_reason`` ``record_cap``/``byte_cap``/``deadline``; ``lower_bound`` is what was
    observed below the threshold).
    """

    available: bool
    unavailable_reason: str | None
    detail: str | None
    head: str | None
    shallow: bool | None
    threshold: int
    lookback_days: int
    window_start: str | None
    window_end: str | None
    scoped_commit_count: int | None
    lower_bound: int | None
    saturated: bool
    complete: bool
    truncation_reason: str | None
    records_visited: int
    bytes_consumed: int
    git_calls: int

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready mapping."""
        return {
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
            "detail": self.detail,
            "head": self.head,
            "shallow": self.shallow,
            "threshold": self.threshold,
            "lookback_days": self.lookback_days,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "scoped_commit_count": self.scoped_commit_count,
            "scoped_commit_count_lower_bound": self.lower_bound,
            "saturated": self.saturated,
            "complete": self.complete,
            "truncation_reason": self.truncation_reason,
            "records_visited": self.records_visited,
            "bytes_consumed": self.bytes_consumed,
            "git_calls": self.git_calls,
        }


class LogDecoder:
    """Incremental, allocation-bounded decoder of the NUL-token ``git log`` stream.

    Feed raw chunks with :meth:`feed`; call :meth:`finish` at clean EOF. Tracks completed records,
    distinct in-window scoped commits (each commit appears once per ``git log``) and stops
    accepting work once :attr:`stop_reason` is set (``saturated`` or ``record_cap``). Paths are
    tested as they stream by (``matches``) and never stored.
    """

    _START, _HEADER, _PATHS = 0, 1, 2

    def __init__(
        self,
        matches: Callable[[str], bool],
        *,
        window_start_us: int,
        window_end_us: int,
        threshold: int,
        max_records: int = MAX_RECORDS,
    ) -> None:
        self._matches = matches
        self._lo = window_start_us
        self._hi = window_end_us
        self._threshold = threshold
        self._max_records = max_records
        self._buffer = bytearray()
        self._state = self._START
        self._first_path = True
        self._in_window = False
        self._hit = False
        self.records_completed = 0
        self.scoped_count = 0
        self.stop_reason: str | None = None
        self.error: str | None = None
        self._at_cap = False

    # -- public -----------------------------------------------------------------------

    @property
    def done(self) -> bool:
        """True once no further input can change the outcome."""
        return self.stop_reason is not None or self.error is not None

    def feed(self, data: bytes) -> None:
        """Consume *data*; complete NUL-terminated tokens are processed immediately."""
        if self.done:
            return
        self._buffer.extend(data)
        start = 0
        while True:
            end = self._buffer.find(b"\x00", start)
            if end < 0:
                break
            self._token(bytes(self._buffer[start:end]))
            start = end + 1
            if self.done:
                break
        del self._buffer[:start]

    def finish(self) -> bool:
        """Finalize at clean EOF; ``True`` when the stream was well formed and fully consumed."""
        if self.done:
            return self.error is None
        if self._buffer:
            self.error = "truncated token at end of stream"
            return False
        if self._state == self._PATHS:
            self._complete_record(boundary=False)
        return self.error is None

    # -- state machine -----------------------------------------------------------------

    def _token(self, token: bytes) -> None:
        if self._state == self._START:
            if token:
                self.error = "stream does not start with a record boundary"
                return
            self._state = self._HEADER
            return
        if self._state == self._HEADER:
            match = _HEADER_RE.match(token)
            if match is None:
                self.error = "malformed record header"
                return
            if self._at_cap:
                self.stop_reason = TRUNCATED_RECORDS  # more output exists past the work cap
                return
            self._in_window = self._lo <= int(match.group(2)) * 1_000_000 <= self._hi
            self._hit = False
            self._first_path = True
            self._state = self._PATHS
            return
        if token == b"":
            self._complete_record(boundary=True)
            return
        if self._first_path:
            self._first_path = False
            if token.startswith(b"\n"):
                token = token[1:]
        if self._in_window and not self._hit and token:
            if self._matches(token.decode("utf-8", "surrogateescape")):
                self._hit = True

    def _complete_record(self, *, boundary: bool) -> None:
        self.records_completed += 1
        if self._in_window and self._hit:
            self.scoped_count += 1
            if self.scoped_count >= self._threshold:
                self.stop_reason = SATURATED
        if self.records_completed >= self._max_records:
            self._at_cap = True
        self._state = self._HEADER if boundary else self._START


def _start_failure(reason: str, detail: str, **kwargs: Any) -> ScanActivity:
    base: dict[str, Any] = {
        "available": False,
        "unavailable_reason": reason,
        "detail": detail,
        "head": None,
        "shallow": None,
        "threshold": 0,
        "lookback_days": 0,
        "window_start": None,
        "window_end": None,
        "scoped_commit_count": None,
        "lower_bound": None,
        "saturated": False,
        "complete": False,
        "truncation_reason": None,
        "records_visited": 0,
        "bytes_consumed": 0,
        "git_calls": 0,
    }
    base.update(kwargs)
    return ScanActivity(**base)


@dataclass
class _Run:
    """Outcome of one bounded subprocess."""

    out: bytes
    err: bytes
    returncode: int | None
    consumed: int
    stopped: str | None  # why this collector stopped the process, or None for natural EOF
    exec_error: str | None = None
    exec_missing: bool = False


def _classify_exit(code: int, err: bytes) -> tuple[str, str]:
    text = err.decode("utf-8", "replace").strip().splitlines()
    tail = text[-1] if text else ""
    if code == 129:
        return (
            GIT_UNSUPPORTED,
            f"git rejected --no-lazy-fetch (usage error, exit 129; requires Git >= "
            f"{MIN_GIT_VERSION}): {tail}".rstrip(": "),
        )
    if "not a git repository" in tail.lower():
        return NOT_A_GIT_REPOSITORY, tail
    return GIT_FAILED, f"git exited {code}: {tail}".rstrip(": ")


def _run_stream(
    argv: list[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    popen: PopenFactory,
    clock: Clock,
    deadline: float,
    byte_budget: int,
    on_chunk: Callable[[bytes], bool] | None,
    keep_stdout: bool,
) -> _Run:
    """Run *argv* under the shared deadline and byte budget; never raises for process trouble."""
    try:
        proc = popen(
            argv,
            cwd=str(cwd),
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        return _Run(b"", b"", None, 0, None, exec_error=str(exc), exec_missing=True)
    except OSError as exc:
        return _Run(b"", b"", None, 0, None, exec_error=str(exc))

    lock = threading.Lock()
    consumed = [0]
    err_kept = bytearray()
    killed_for: list[str] = []

    def kill(reason: str) -> None:
        with lock:
            if not killed_for:
                killed_for.append(reason)
        try:
            proc.kill()
        except Exception:  # noqa: BLE001 - already-exited processes are fine
            pass

    def drain_stderr() -> None:
        stream = proc.stderr
        if stream is None:
            return
        while True:
            try:
                chunk = stream.read(_CHUNK)
            except (OSError, ValueError):
                return
            if not chunk:
                return
            with lock:
                consumed[0] += len(chunk)
                over = consumed[0] >= byte_budget
                if len(err_kept) < _STDERR_KEEP:
                    err_kept.extend(chunk[: _STDERR_KEEP - len(err_kept)])
            if over:
                kill(TRUNCATED_BYTES)
                return

    reader = threading.Thread(target=drain_stderr, daemon=True)
    reader.start()
    watchdog = threading.Timer(max(0.0, deadline - clock()), lambda: kill(TRUNCATED_DEADLINE))
    watchdog.daemon = True
    watchdog.start()

    out = bytearray()
    stopped: str | None = None
    try:
        stream = proc.stdout
        while stream is not None:
            if clock() >= deadline:
                stopped = TRUNCATED_DEADLINE
                break
            reader_fn = getattr(stream, "read1", None) or stream.read
            try:
                chunk = reader_fn(_CHUNK)
            except (OSError, ValueError):
                chunk = b""
            if killed_for and not chunk:
                stopped = killed_for[0]
                break
            if not chunk:
                break
            with lock:
                consumed[0] += len(chunk)
                over = consumed[0] >= byte_budget
            if keep_stdout:
                out.extend(chunk)
            if on_chunk is not None and on_chunk(chunk):
                stopped = "decoder"  # the decoder says no further input can change the result
                break
            if over:
                stopped = TRUNCATED_BYTES
                break
            if killed_for:
                stopped = killed_for[0]
                break
    finally:
        watchdog.cancel()
        if stopped is not None:
            kill(stopped)
        try:
            proc.wait(timeout=max(0.25, deadline - clock()) if stopped is None else 5.0)
        except Exception:  # noqa: BLE001 - a stuck process is killed and reaped below
            kill(TRUNCATED_DEADLINE)
            stopped = stopped or TRUNCATED_DEADLINE
            try:
                proc.wait(timeout=5.0)
            except Exception:  # noqa: BLE001
                pass
        reader.join(timeout=1.0)
    with lock:
        total = consumed[0]
        err = bytes(err_kept)
    return _Run(bytes(out), err, proc.returncode, total, stopped)


def load_scope_activity(
    project_root: Path,
    scope: ScanScope,
    *,
    as_of: datetime,
    threshold: int,
    lookback_days: int,
    popen: PopenFactory = subprocess.Popen,
    clock: Clock = time.monotonic,
) -> ScanActivity:
    """Load the scoped commit activity for *scope* with at most two git subprocesses.

    Counts distinct commits reachable from the captured HEAD whose committer time lies in the
    inclusive UTC interval ``[as_of - lookback_days, as_of]`` and that touch a path in *scope*
    (once per commit across overlapping directories; first-parent merge diffs, root commits,
    deletions and renames-out/in all count). See the module docstring for the read policy and
    bounds.
    """
    env = child_environment()
    started = clock()
    deadline = started + BUDGET_SECONDS
    window_end = as_of.astimezone(UTC)
    window_start = window_end - timedelta(days=lookback_days)
    common: dict[str, Any] = {
        "threshold": threshold,
        "lookback_days": lookback_days,
        "window_start": window_start.isoformat().replace("+00:00", "Z"),
        "window_end": window_end.isoformat().replace("+00:00", "Z"),
    }

    head_run = _run_stream(
        head_command(),
        cwd=project_root,
        env=env,
        popen=popen,
        clock=clock,
        deadline=deadline,
        byte_budget=MAX_BYTES,
        on_chunk=None,
        keep_stdout=True,
    )
    if head_run.exec_error is not None:
        reason = GIT_MISSING if head_run.exec_missing else GIT_FAILED
        return _start_failure(reason, head_run.exec_error, git_calls=0, **common)
    if head_run.stopped is not None:
        return _start_failure(
            GIT_FAILED,
            f"HEAD lookup stopped by the shared budget ({head_run.stopped})",
            git_calls=1,
            bytes_consumed=head_run.consumed,
            **common,
        )
    if head_run.returncode != 0:
        reason, detail = _classify_exit(head_run.returncode or 1, head_run.err)
        return _start_failure(
            reason, detail, git_calls=1, bytes_consumed=head_run.consumed, **common
        )
    lines = head_run.out.decode("utf-8", "replace").split()
    if len(lines) != 2 or not _HEAD_RE.match(lines[0]) or lines[1] not in ("true", "false"):
        return _start_failure(
            GIT_FAILED,
            "unexpected rev-parse output",
            git_calls=1,
            bytes_consumed=head_run.consumed,
            **common,
        )
    head, shallow = lines[0], lines[1] == "true"
    common.update({"head": head, "shallow": shallow})

    decoder = LogDecoder(
        scope.contains,
        window_start_us=_epoch_us(window_start),
        window_end_us=_epoch_us(window_end),
        threshold=threshold,
    )

    def on_chunk(chunk: bytes) -> bool:
        decoder.feed(chunk)
        return decoder.done

    # Git's date filter has whole-second precision: floor the lower bound as a prefilter only.
    since_epoch = _epoch_us(window_start) // 1_000_000
    log_run = _run_stream(
        log_command(head, since_epoch),
        cwd=project_root,
        env=env,
        popen=popen,
        clock=clock,
        deadline=deadline,
        byte_budget=MAX_BYTES - head_run.consumed,
        on_chunk=on_chunk,
        keep_stdout=False,
    )
    total_bytes = head_run.consumed + log_run.consumed
    common.update({"records_visited": decoder.records_completed, "bytes_consumed": total_bytes})
    if log_run.exec_error is not None:
        return _start_failure(
            GIT_MISSING if log_run.exec_missing else GIT_FAILED,
            log_run.exec_error,
            git_calls=1,
            **common,
        )
    common["git_calls"] = 2

    if decoder.error is not None:
        return _start_failure(DECODE_ERROR, decoder.error, **common)
    if decoder.stop_reason == SATURATED:
        return ScanActivity(
            available=True,
            unavailable_reason=None,
            detail=None,
            scoped_commit_count=None,
            lower_bound=decoder.scoped_count,
            saturated=True,
            complete=False,
            truncation_reason=SATURATED,
            **common,
        )
    stopped_by_us = log_run.stopped
    if decoder.stop_reason == TRUNCATED_RECORDS:
        stopped_by_us = TRUNCATED_RECORDS
    if stopped_by_us == "decoder":  # pragma: no cover - decoder stops are saturation or the cap
        stopped_by_us = decoder.stop_reason
    if stopped_by_us is not None:
        return ScanActivity(
            available=True,
            unavailable_reason=None,
            detail=None,
            scoped_commit_count=None,
            lower_bound=decoder.scoped_count,
            saturated=False,
            complete=False,
            truncation_reason=stopped_by_us,
            **common,
        )
    # Natural EOF: the process, not this collector, decides success.
    if log_run.returncode != 0:
        reason, detail = _classify_exit(log_run.returncode or 1, log_run.err)
        return _start_failure(reason, detail, **common)
    if not decoder.finish():
        return _start_failure(DECODE_ERROR, decoder.error or "malformed stream", **common)
    common["records_visited"] = decoder.records_completed
    if decoder.stop_reason == SATURATED:  # the final record, completed at EOF, reached the bar
        return ScanActivity(
            available=True,
            unavailable_reason=None,
            detail=None,
            scoped_commit_count=None,
            lower_bound=decoder.scoped_count,
            saturated=True,
            complete=False,
            truncation_reason=SATURATED,
            **common,
        )
    return ScanActivity(
        available=True,
        unavailable_reason=None,
        detail=None,
        scoped_commit_count=decoder.scoped_count,
        lower_bound=None,
        saturated=False,
        complete=True,
        truncation_reason=None,
        **common,
    )
