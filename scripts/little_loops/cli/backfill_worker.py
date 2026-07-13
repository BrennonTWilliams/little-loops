"""Detached backfill worker spawned by the session_start hook (BUG-1882).

Invoked as ``python -m little_loops.cli.backfill_worker <db_path> <path>
[--rebuild]``, where *path* is either a single ``.jsonl`` transcript file or a
project folder whose ``*.jsonl`` files are globbed. Runs
:func:`backfill_incremental` and exits. Because it is spawned with
``start_new_session=True`` it outlives the short-lived hook subprocess.

``--rebuild`` (ENH-2581) additionally materializes the JSONL-derived cache
tables from ``raw_events`` in the same call — passed by the hook only when
``SCHEMA_VERSION`` has changed since the last rebuild (see
``session_start.py``). This file has no argparse by design (minimal-parsing
style); ``--rebuild`` is checked ad hoc to match.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    rebuild = "--rebuild" in args
    positional = [a for a in args if a != "--rebuild"]
    if len(positional) < 2:
        print(
            f"Usage: {sys.argv[0]} <db_path> <jsonl_file_or_project_dir> [--rebuild]",
            file=sys.stderr,
        )
        return 1

    db_path = Path(positional[0])
    path_arg = Path(positional[1])

    if path_arg.is_file() and positional[1].endswith(".jsonl"):
        jsonl_files: list[Path] = [path_arg]
    elif path_arg.is_dir():
        jsonl_files = list(path_arg.glob("*.jsonl"))
    else:
        print(f"backfill_worker: path not found: {positional[1]!r}", file=sys.stderr)
        return 1

    from little_loops.session_store import backfill_incremental

    backfill_incremental(db_path, jsonl_files=jsonl_files, also_rebuild=rebuild)
    return 0


if __name__ == "__main__":
    sys.exit(main())
