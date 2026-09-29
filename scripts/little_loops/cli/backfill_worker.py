"""Detached transcript backfill worker spawned by lifecycle hooks (BUG-1882).

Invoked as ``python -m little_loops.cli.backfill_worker <db_path> <path>
[--rebuild] [--host HOST]``, where *path* is either a single ``.jsonl``
transcript file or a project folder whose ``*.jsonl`` files are globbed. Runs
:func:`backfill_incremental` and exits. Because it is spawned with
``start_new_session=True`` it outlives the short-lived hook subprocess.

``--rebuild`` (ENH-2581) additionally materializes the JSONL-derived cache
tables from ``raw_events`` in the same call — passed by the hook only when
``SCHEMA_VERSION`` has changed since the last rebuild (see
``session_start.py``). ``--host`` (ENH-3166) names the host whose transcripts
*path* holds, so ``raw_events`` rows are stamped with the ingested host
instead of the ambient one; an unrecognized host is rejected (ENH-3422 D8).
This file has no argparse by design (minimal-parsing style); both flags are
checked ad hoc to match, and ``--host`` validation follows this file's own
``return 1`` convention rather than raising ``SystemExit``.

``--usage-trigger --requested-at-ns N`` is the Claude/Codex Stop path (ENH-3651/3549).
It serializes workers per database, coalesces requests already covered by a
successful later start, and schedules a trailing refresh after a throttle.
The worker also rereads once after a short settlement window so a transcript
write racing Stop can be included without holding up the hook.
"""

from __future__ import annotations

import fcntl
import json
import sys
import time
from pathlib import Path

_USAGE_THROTTLE_SECONDS = 5.0
_USAGE_SETTLE_SECONDS = 0.25
_USAGE_FINAL_RETRY_SECONDS = 1.75


def _refresh_usage_source(db_path: Path, source: Path, *, host: str) -> None:
    """Run the shared source-tail ingest and derive path (bound by lifecycle)."""
    from little_loops.session_store.lifecycle import refresh_usage_source

    refresh_usage_source(db_path, source, host=host)


def _run_usage_trigger(db_path: Path, source: Path, host: str, requested_at_ns: int) -> int:
    """Serialize, throttle, and retry one detached Stop-triggered refresh."""
    lock_path = db_path.with_name(f"{db_path.name}.usage-refresh.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            lock.seek(0)
            try:
                state = json.load(lock)
            except (json.JSONDecodeError, ValueError):
                state = {}
            if not isinstance(state, dict):
                state = {}
            source_key = str(source.expanduser().resolve())
            source_starts = state.get("source_started_ns", {})
            if not isinstance(source_starts, dict):
                source_starts = {}
            source_starts = {
                str(key): value
                for key, value in source_starts.items()
                if isinstance(value, int) and value > 0
            }
            last_started_ns = source_starts.get(source_key, 0)
            last_finished_ns = state.get("last_success_finished_ns", 0)
            if not isinstance(last_started_ns, int):
                last_started_ns = 0
            if not isinstance(last_finished_ns, int):
                last_finished_ns = 0
            # A worker that started after this Stop request and succeeded has
            # already covered it. A Stop during an in-flight worker needs a
            # trailing run, even if that worker happened to read late enough.
            if last_started_ns >= requested_at_ns:
                return 0

            due_ns = last_finished_ns + int(_USAGE_THROTTLE_SECONDS * 1e9)
            delay = (due_ns - time.time_ns()) / 1e9
            if delay > 0:
                time.sleep(delay)
            started_ns = time.time_ns()
            time.sleep(_USAGE_SETTLE_SECONDS)
            if not source.is_file():
                print(f"backfill_worker: path not found: {str(source)!r}", file=sys.stderr)
                return 1
            _refresh_usage_source(db_path, source, host=host)
            # Stop can precede the final transcript flush. This bounded second
            # pass catches a late append even when no subsequent hook fires.
            time.sleep(_USAGE_FINAL_RETRY_SECONDS)
            _refresh_usage_source(db_path, source, host=host)
            finished_ns = time.time_ns()
            source_starts[source_key] = started_ns
            # Keep the lock state bounded as old sessions accumulate.
            source_starts = dict(
                sorted(source_starts.items(), key=lambda item: item[1], reverse=True)[:128]
            )
            lock.seek(0)
            lock.truncate()
            json.dump(
                {
                    "last_success_started_ns": started_ns,
                    "last_success_finished_ns": finished_ns,
                    "source_started_ns": source_starts,
                },
                lock,
            )
            lock.flush()
    except Exception as exc:  # detached worker must leave a retryable failure
        print(f"backfill_worker: usage refresh failed: {exc}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    rebuild = "--rebuild" in args
    usage_trigger = "--usage-trigger" in args
    requested_at_ns: int | None = None
    host: str | None = None
    positional: list[str] = []
    skip_next = False
    for i, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if arg == "--rebuild":
            continue
        if arg == "--usage-trigger":
            continue
        if arg == "--requested-at-ns":
            if i + 1 < len(args):
                try:
                    requested_at_ns = int(args[i + 1])
                except ValueError:
                    requested_at_ns = None
                skip_next = True
            continue
        if arg == "--host":
            if i + 1 < len(args):
                host = args[i + 1]
                skip_next = True
            continue
        positional.append(arg)
    if len(positional) < 2:
        print(
            f"Usage: {sys.argv[0]} <db_path> <jsonl_file_or_project_dir> "
            "[--rebuild] [--host HOST] [--usage-trigger --requested-at-ns N]",
            file=sys.stderr,
        )
        return 1

    if host is not None:
        from little_loops.session_store import REGISTERED_HOSTS

        if host not in REGISTERED_HOSTS:
            print(
                f"backfill_worker: unknown --host {host!r}; expected one of "
                f"{', '.join(REGISTERED_HOSTS)}",
                file=sys.stderr,
            )
            return 1

    db_path = Path(positional[0])
    path_arg = Path(positional[1])

    if usage_trigger:
        if (
            rebuild
            or host not in {"claude-code", "codex"}
            or requested_at_ns is None
            or requested_at_ns <= 0
        ):
            print(
                "backfill_worker: --usage-trigger requires --host claude-code or codex "
                "and a positive --requested-at-ns, without --rebuild",
                file=sys.stderr,
            )
            return 1
        if path_arg.suffix != ".jsonl":
            print("backfill_worker: --usage-trigger requires a .jsonl file", file=sys.stderr)
            return 1
        return _run_usage_trigger(db_path, path_arg, host, requested_at_ns)

    if path_arg.is_file() and positional[1].endswith(".jsonl"):
        jsonl_files: list[Path] = [path_arg]
    elif path_arg.is_dir():
        # Directory args are project folders: resolve the session glob from
        # the host layout so qwen sessions under chats/ are found (ENH-3166).
        from little_loops.session_store import host_layout_for

        layout = host_layout_for(host if host is not None else "claude-code")
        jsonl_files = list(path_arg.glob(layout.session_glob))
    else:
        print(f"backfill_worker: path not found: {positional[1]!r}", file=sys.stderr)
        return 1

    from little_loops.session_store import backfill_incremental
    from little_loops.session_store.backend import HistoryUnsupported

    try:
        backfill_incremental(db_path, jsonl_files=jsonl_files, also_rebuild=rebuild, host=host)
    except HistoryUnsupported as exc:  # e.g. --rebuild against a remote store (FEAT-3535)
        print(f"backfill_worker: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
