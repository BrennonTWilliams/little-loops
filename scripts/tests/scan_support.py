"""Shared fakes and builders for the ``capture-issues`` scan tests (FEAT-3713)."""

from __future__ import annotations

import io
import os
import subprocess
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from little_loops.next_arena.scan_activity import ScanActivity, load_scope_activity
from little_loops.next_arena.scan_state import ScanScope, resolve_scan_scope

HEAD = "a" * 40
AS_OF = datetime(2026, 10, 8, 12, 0, 0, tzinfo=UTC)
AS_OF_EPOCH = int(AS_OF.timestamp())
DAY = 86400


def sha(n: int) -> str:
    """A deterministic 40-hex commit id."""
    return f"{n:040x}"


def record(commit: str, ct: int, paths: Sequence[str | bytes] = ()) -> bytes:
    """One ``git log`` record exactly as the collector's format emits it."""
    out = b"\x00" + f"{commit} {ct}".encode() + b"\x00"
    if paths:
        raw = [p if isinstance(p, bytes) else p.encode("utf-8", "surrogateescape") for p in paths]
        out += b"\n" + b"\x00".join(raw) + b"\x00"
    return out


def stream(*records: bytes) -> bytes:
    return b"".join(records)


class ChunkedOut:
    """A stdout stand-in yielding preset chunks via ``read1`` (``b""`` at EOF)."""

    def __init__(self, chunks: Iterable[bytes], on_read: Callable[[], None] | None = None) -> None:
        self._chunks = list(chunks)
        self._on_read = on_read
        self.reads = 0

    def read1(self, _n: int = -1) -> bytes:
        self.reads += 1
        if self._on_read is not None:
            self._on_read()
        return self._chunks.pop(0) if self._chunks else b""

    read = read1


class FakeProc:
    """A ``Popen`` stand-in: preset stdout chunks/stderr/returncode; records ``kill``."""

    def __init__(
        self,
        stdout: bytes | Iterable[bytes] = b"",
        stderr: bytes = b"",
        returncode: int = 0,
        *,
        chunk: int | None = None,
        on_read: Callable[[], None] | None = None,
    ) -> None:
        if isinstance(stdout, bytes):
            size = chunk or max(len(stdout), 1)
            parts = [stdout[i : i + size] for i in range(0, len(stdout), size)] or []
        else:
            parts = list(stdout)
        self.stdout = ChunkedOut(parts, on_read)
        self.stderr = io.BytesIO(stderr)
        self._rc = returncode
        self.returncode: int | None = None
        self.killed = False

    def wait(self, timeout: float | None = None) -> int:
        self.returncode = -9 if self.killed else self._rc
        return self.returncode

    def kill(self) -> None:
        self.killed = True


class FakePopen:
    """A scripted popen factory: one :class:`FakeProc` per call, in order; records every call."""

    def __init__(self, *procs: FakeProc | BaseException) -> None:
        self._procs = list(procs)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, argv: list[str], **kwargs: Any) -> FakeProc:
        self.calls.append({"argv": list(argv), **kwargs})
        item = self._procs.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    @property
    def procs_started(self) -> int:
        return len(self.calls)


def head_proc(head: str = HEAD, shallow: bool = False, *, returncode: int = 0) -> FakeProc:
    return FakeProc(f"{head}\n{'true' if shallow else 'false'}\n".encode(), returncode=returncode)


class FakeClock:
    """A monotonic clock advancing *step* seconds on every read."""

    def __init__(self, start: float = 0.0, step: float = 0.0) -> None:
        self.now = start
        self.step = step

    def __call__(self) -> float:
        value = self.now
        self.now += self.step
        return value


def scope_for(
    tmp_path: Path, focus: Sequence[str] = ("src",), exclude: Sequence[str] = ()
) -> ScanScope:
    for d in focus:
        if d not in (".", "") and not d.startswith("/"):
            (tmp_path / d).mkdir(parents=True, exist_ok=True)
    return resolve_scan_scope(list(focus), list(exclude), tmp_path)


def load(
    tmp_path: Path,
    popen: Callable[..., Any],
    *,
    scope: ScanScope | None = None,
    threshold: int = 20,
    lookback_days: int = 30,
    clock: Callable[[], float] | None = None,
    as_of: datetime = AS_OF,
) -> ScanActivity:
    kwargs: dict[str, Any] = {}
    if clock is not None:
        kwargs["clock"] = clock
    return load_scope_activity(
        tmp_path,
        scope if scope is not None else scope_for(tmp_path),
        as_of=as_of,
        threshold=threshold,
        lookback_days=lookback_days,
        popen=popen,
        **kwargs,
    )


# ------------------------------------------------------------------------------ real git


def git_available() -> bool:
    """True when the installed Git accepts the enforcing ``--no-lazy-fetch`` global option."""
    try:
        done = subprocess.run(
            ["git", "--no-lazy-fetch", "--version"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0


def git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    merged = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
        **(env or {}),
    }
    done = subprocess.run(
        ["git", *args], cwd=cwd, env=merged, capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


def commit_at(
    repo: Path, when: int, message: str = "c", *, files: dict[str, str] | None = None
) -> str:
    """Write *files*, stage everything and commit with author/committer time *when*."""
    for name, text in (files or {}).items():
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    git(repo, "add", "-A", "--", ".")
    stamp = f"{when} +0000"
    git(
        repo,
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        message,
        env={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp},
    )
    return git(repo, "rev-parse", "HEAD")


def init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "commit.gpgsign", "false")
    return path
