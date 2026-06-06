"""ll-logs: Discover, extract, analyze log entries from ~/.claude/projects/."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from little_loops.cli.loop.info import (  # private symbol: cross-module coupling; verify signature on upgrade
    _format_history_event,
)
from little_loops.cli.output import configure_output, print_json, table, use_color_enabled
from little_loops.cli_args import add_json_arg
from little_loops.config import BRConfig
from little_loops.logger import Logger
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context
from little_loops.user_messages import get_project_folder

_COMMAND_NAME_RE = re.compile(r"<command-name>/ll:")


def _is_ll_relevant(record: dict) -> bool:
    """Return True if a JSONL record indicates ll activity.

    Detects three signal types:
    (a) queue-operation enqueue with /ll: content
    (b) user records with <command-name>/ll: pattern in message content
    """
    record_type = record.get("type")

    # (a) queue-operation: only enqueue records with /ll: content signal ll activity
    if record_type == "queue-operation":
        return (
            record.get("operation") == "enqueue"
            and isinstance(record.get("content"), str)
            and record["content"].startswith("/ll:")
        )

    # (b) user records: check message content for <command-name>/ll: pattern
    if record_type == "user":
        message = record.get("message", {})
        if not isinstance(message, dict):
            return False
        content = message.get("content")
        if isinstance(content, str):
            return bool(_COMMAND_NAME_RE.search(content))
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text", "")
                    if isinstance(text, str) and _COMMAND_NAME_RE.search(text):
                        return True

    # (c) assistant records: check for Bash tool-use invoking an ll- command
    if record_type == "assistant":
        message = record.get("message", {})
        content = message.get("content", [])
        if isinstance(content, list):
            for block in content:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "tool_use"
                    and block.get("name") == "Bash"
                ):
                    cmd = block.get("input", {}).get("command", "")
                    if re.search(r"\bll-\w+", cmd):
                        return True

    return False


def _has_ll_activity(project_folder: Path) -> bool:
    """Return True if any non-agent JSONL file in project_folder has ll activity."""
    jsonl_files = [f for f in project_folder.glob("*.jsonl") if not f.name.startswith("agent-")]

    for jsonl_file in jsonl_files:
        try:
            with open(jsonl_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if _is_ll_relevant(record):
                        return True
        except OSError:
            continue

    return False


def _extract_cwd_from_project(project_dir: Path) -> Path | None:
    """Extract the project working directory from cwd fields in JSONL records.

    Claude Code encodes project paths by replacing '/' with '-', which is
    lossy for paths containing hyphens. Reading the cwd field from JSONL
    records gives the canonical path without ambiguity.
    """
    jsonl_files = [f for f in project_dir.glob("*.jsonl") if not f.name.startswith("agent-")]
    for jsonl_file in jsonl_files:
        try:
            with open(jsonl_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        cwd = record.get("cwd")
                        if isinstance(cwd, str) and cwd:
                            return Path(cwd)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue
    return None


def discover_all_projects(logger: Logger, *, host: str | None = None) -> list[Path]:
    """Discover all projects with ll activity for the given host.

    Iterates the host's session directory (e.g. ``~/.claude/projects/`` for
    Claude Code, ``~/.codex/projects/`` for Codex), resolves each directory
    name back to an absolute path, checks for ll-relevant JSONL records, and
    returns a sorted list of paths that exist on disk.

    Args:
        logger: Logger instance for warnings.
        host: Host identifier. If None, auto-detects from ``LL_HOOK_HOST``
            env var (default ``"claude-code"``).

    Returns:
        Sorted list of decoded absolute paths for projects with ll activity.
    """
    import os as _os

    if host is None:
        host = _os.environ.get("LL_HOOK_HOST", "claude-code")

    if host == "claude-code":
        projects_root = Path.home() / ".claude" / "projects"
    elif host == "codex":
        projects_root = Path.home() / ".codex" / "projects"
    elif host == "opencode":
        projects_root = Path.home() / ".opencode" / "projects"
    elif host == "pi":
        projects_root = Path.home() / ".pi" / "projects"
    else:
        return []

    if not projects_root.exists():
        return []

    results: list[Path] = []

    for project_dir in projects_root.iterdir():
        if not project_dir.is_dir():
            continue

        # Prefer cwd field from JSONL records; fall back to lossy decode.
        # The lossy decode ("-Users-foo-bar" -> "/Users/foo/bar") breaks for
        # paths that contain hyphens (e.g. "little-loops", macOS per-user
        # temp dirs like /tmp/claude-501/).
        decoded_path = _extract_cwd_from_project(project_dir) or Path(
            project_dir.name.replace("-", "/")
        )

        if not decoded_path.exists():
            logger.warning(f"Decoded path does not exist: {decoded_path}")
            continue

        if _has_ll_activity(project_dir):
            results.append(decoded_path)

    return sorted(results)


def _cmd_matches(record: dict, cmd: str) -> bool:
    """Return True if record contains a Bash tool-use whose command includes cmd."""
    message = record.get("message", {})
    content = message.get("content", [])
    if isinstance(content, list):
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_use"
                and block.get("name") == "Bash"
            ):
                command = block.get("input", {}).get("command", "")
                if cmd in command:
                    return True
    return False


_LL_BASH_RE = re.compile(r"\b(ll-[\w-]+)")
_QUEUE_SKILL_RE = re.compile(r"^/ll:(\S+)")
_COMMAND_NAME_SKILL_RE = re.compile(r"<command-name>/ll:(\S+)")


@dataclass
class InvocationEvent:
    """A single ll invocation event extracted from a JSONL record."""

    tool_name: str
    timestamp: str
    session_id: str


def _extract_ll_event_streams(
    project_folder: Path, *, window_days: int | None = None
) -> dict[str, list[InvocationEvent]]:
    """Extract per-session ordered ll-invocation event streams from JSONL files.

    Walks JSONL files (skipping ``agent-*``), filters to records with ll activity,
    extracts the tool/skill name, and returns a dict mapping ``sessionId`` to a
    timestamp-sorted list of ``InvocationEvent``.

    Args:
        project_folder: Path to the claude project session directory.
        window_days: If set, filter records to within N days of the latest record.

    Returns:
        Dict of ``{session_id: [InvocationEvent, ...]}`` with events sorted by timestamp.
    """
    events_by_session: dict[str, list[InvocationEvent]] = {}

    jsonl_files = [
        f for f in project_folder.glob("*.jsonl") if not f.name.startswith("agent-")
    ]
    if not jsonl_files:
        return events_by_session

    # Collect all raw events first for window-days filtering
    all_events: list[InvocationEvent] = []
    latest_ts: str | None = None

    for jsonl_file in jsonl_files:
        try:
            with open(jsonl_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    tool_name = _extract_tool_name(record)
                    if tool_name is None:
                        continue

                    ts = record.get("timestamp", "")
                    sid = record.get("sessionId", "")

                    evt = InvocationEvent(tool_name=tool_name, timestamp=ts, session_id=sid)
                    all_events.append(evt)

                    if ts and (latest_ts is None or ts > latest_ts):
                        latest_ts = ts
        except OSError:
            continue

    # Apply window-days filter
    if window_days is not None and latest_ts:
        cutoff = _parse_iso_timestamp(latest_ts) - timedelta(days=window_days)
        all_events = [e for e in all_events if _parse_iso_timestamp(e.timestamp) >= cutoff]

    # Bucket by session and sort
    for evt in all_events:
        events_by_session.setdefault(evt.session_id, []).append(evt)

    for session_id in events_by_session:
        events_by_session[session_id].sort(key=lambda e: e.timestamp)

    return events_by_session


def _extract_tool_name(record: dict) -> str | None:
    """Extract the ll tool/skill name from a JSONL record.

    Detects three signal types (matching ``_is_ll_relevant``):
    (a) queue-operation enqueue with ``/ll:<name>`` → skill name
    (b) user records with ``<command-name>/ll:<name>`` → skill name
    (c) assistant Bash tool-use invoking ``ll-<tool>`` → CLI tool name
    """
    record_type = record.get("type")

    # (a) queue-operation enqueue
    if record_type == "queue-operation" and record.get("operation") == "enqueue":
        content = record.get("content", "")
        if isinstance(content, str) and content.startswith("/ll:"):
            m = _QUEUE_SKILL_RE.match(content)
            if m:
                return m.group(1)

    # (b) user records with <command-name>/ll: pattern
    if record_type == "user":
        message = record.get("message", {})
        if not isinstance(message, dict):
            return None
        content = message.get("content")
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text", "")
                    if text:
                        break
        if text:
            m = _COMMAND_NAME_SKILL_RE.search(text)
            if m:
                # Extract skill name, stripping trailing </command-name> if present
                name = m.group(1)
                if name.endswith("</command-name>"):
                    name = name[: -len("</command-name>")]
                return name

    # (c) assistant Bash tool-use invoking ll-<tool>
    if record_type == "assistant":
        message = record.get("message", {})
        content = message.get("content", [])
        if isinstance(content, list):
            for block in content:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "tool_use"
                    and block.get("name") == "Bash"
                ):
                    cmd = block.get("input", {}).get("command", "")
                    m = _LL_BASH_RE.search(cmd)
                    if m:
                        return m.group(1)

    return None


def _parse_iso_timestamp(ts: str) -> datetime:
    """Parse an ISO 8601 timestamp string to a timezone-aware datetime.

    Handles both ``Z``-suffixed and ``+00:00`` offset formats. Returns
    ``datetime.min`` with UTC tzinfo for unparseable input.
    """
    if not ts:
        return datetime.min.replace(tzinfo=UTC)
    try:
        # Handle Z suffix
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=UTC)


@dataclass
class Edge:
    """A transition edge within an n-gram chain."""

    from_: str
    to: str
    freq: float


@dataclass
class ChainResult:
    """An n-gram chain with occurrence count and per-edge transition frequencies."""

    chain: list[str]
    count: int
    edges: list[Edge]

    def to_dict(self) -> dict:
        return {
            "chain": self.chain,
            "count": self.count,
            "edges": [
                {"from": e.from_, "to": e.to, "freq": e.freq} for e in self.edges
            ],
        }


def _count_ngrams(
    events_by_session: dict[str, list[InvocationEvent]],
    min_len: int = 2,
) -> Counter:
    """Count n-grams across per-session event streams.

    Args:
        events_by_session: Per-session ordered event streams.
        min_len: Minimum n-gram length (window size).

    Returns:
        Counter mapping ``(tool_1, tool_2, ...)`` tuples to occurrence counts.
    """
    counter: Counter = Counter()
    for events in events_by_session.values():
        names = [e.tool_name for e in events]
        # For chains shorter than min_len, still consider them as single n-grams
        # but note: min_len is the minimum, so we use range(min_len, len(names)+1)
        for n in range(min_len, len(names) + 1):
            for i in range(len(names) - n + 1):
                ngram = tuple(names[i: i + n])
                counter[ngram] += 1
    return counter


def _build_chain_results(
    counter: Counter,
    min_count: int = 1,
    top: int | None = None,
) -> list[ChainResult]:
    """Build ranked ``ChainResult`` list from n-gram counter.

    Args:
        counter: n-gram counter from ``_count_ngrams``.
        min_count: Minimum occurrence count to include.
        top: If set, limit to top N chains by frequency.

    Returns:
        List of ``ChainResult`` sorted by count descending.
    """
    results: list[ChainResult] = []
    for ngram, count in counter.most_common():
        if count < min_count:
            continue
        edges = _compute_edges(ngram, counter)
        results.append(ChainResult(chain=list(ngram), count=count, edges=edges))

    if top is not None:
        results = results[:top]

    return results


def _compute_edges(ngram: tuple[str, ...], counter: Counter) -> list[Edge]:
    """Compute per-edge transition frequencies for an n-gram chain.

    For each adjacent pair ``(from, to)`` in the chain, computes the frequency
    as the proportion of times ``from → to`` appears out of all transitions
    originating from ``from`` across the entire corpus.
    """
    edges: list[Edge] = []
    # Build a transition counter for all pairs in the corpus
    all_transitions: Counter = Counter()
    out_degree: Counter = Counter()
    for ngram_key, count in counter.items():
        for i in range(len(ngram_key) - 1):
            pair = (ngram_key[i], ngram_key[i + 1])
            all_transitions[pair] += count
            out_degree[ngram_key[i]] += count

    for i in range(len(ngram) - 1):
        from_ = ngram[i]
        to = ngram[i + 1]
        pair = (from_, to)
        total_out = out_degree.get(from_, 0)
        freq = all_transitions.get(pair, 0) / total_out if total_out > 0 else 0.0
        edges.append(Edge(from_=from_, to=to, freq=round(freq, 4)))

    return edges


def _cmd_sequences(args: argparse.Namespace, logger: Logger) -> int:
    """Extract n-grams of ll invocations from JSONL log files."""
    if args.project:
        cwd_path: Path = args.project
        project_folder = get_project_folder(cwd_path)
        if project_folder is None:
            logger.error(f"No session project folder found for: {cwd_path}")
            return 1
        project_items = [(cwd_path, project_folder)]
    else:
        decoded_paths = discover_all_projects(logger)
        project_items = []
        for decoded_path in decoded_paths:
            folder = get_project_folder(decoded_path)
            if folder is not None:
                project_items.append((decoded_path, folder))

    # Aggregate events across all projects
    all_events: dict[str, list[InvocationEvent]] = {}
    for _cwd_path, project_folder in project_items:
        events = _extract_ll_event_streams(
            project_folder, window_days=args.window_days
        )
        for sid, evt_list in events.items():
            all_events.setdefault(sid, []).extend(evt_list)

    # Sort each session's events by timestamp
    for sid in all_events:
        all_events[sid].sort(key=lambda e: e.timestamp)

    # Count n-grams
    counter = _count_ngrams(all_events, min_len=args.min_len)
    results = _build_chain_results(counter, min_count=args.min_count, top=args.top)

    if args.json:
        print_json([r.to_dict() for r in results])
    else:
        if not results:
            print("No sequences found.")
            return 0

        # Print ranked table
        for rank, r in enumerate(results, 1):
            chain_str = " → ".join(r.chain)
            print(f"{rank}. [{r.count}] {chain_str}")
            for edge in r.edges:
                print(f"     {edge.from_} → {edge.to}: {edge.freq:.4f}")

    return 0


def generate_index(logs_dir: Path) -> None:
    """Generate logs/index.md summarising extracted projects."""
    rows = []

    if logs_dir.exists():
        for subdir in sorted(logs_dir.iterdir()):
            if not subdir.is_dir():
                continue

            jsonl_files = [f for f in subdir.glob("*.jsonl") if not f.name.startswith("agent-")]
            if not jsonl_files:
                continue

            timestamps: list[str] = []
            for jsonl_file in jsonl_files:
                try:
                    with open(jsonl_file, encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                record = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            ts = record.get("timestamp")
                            if ts:
                                timestamps.append(ts)
                except OSError:
                    continue

            if timestamps:
                earliest = min(timestamps)[:10]
                latest = max(timestamps)[:10]
                date_range = f"{earliest} – {latest}" if earliest != latest else earliest
            else:
                date_range = ""

            rows.append((subdir.name, len(jsonl_files), date_range))

    lines = ["# Logs Index", ""]
    if rows:
        lines.append("| Project | Sessions | Date Range |")
        lines.append("|---------|----------|------------|")
        for name, count, date_range in rows:
            lines.append(f"| {name} | {count} | {date_range} |")
    else:
        lines.append("*No projects extracted yet.*")
    lines.append("")

    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "index.md").write_text("\n".join(lines), encoding="utf-8")


def _cmd_extract(args: argparse.Namespace, logger: Logger) -> int:
    """Extract ll-relevant JSONL records to logs/<slug>/<session-id>.jsonl."""
    if args.project:
        cwd_path: Path = args.project
        project_folder = get_project_folder(cwd_path)
        if project_folder is None:
            logger.error(f"No session project folder found for: {cwd_path}")
            return 1
        project_items = [(cwd_path, project_folder)]
    else:
        decoded_paths = discover_all_projects(logger)
        project_items = []
        for decoded_path in decoded_paths:
            folder = get_project_folder(decoded_path)
            if folder is not None:
                project_items.append((decoded_path, folder))

    for cwd_path, project_folder in project_items:
        slug = cwd_path.resolve().name
        buckets: dict[str, list[dict]] = {}

        jsonl_files = [f for f in project_folder.glob("*.jsonl") if not f.name.startswith("agent-")]
        for jsonl_file in jsonl_files:
            try:
                with open(jsonl_file, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if _is_ll_relevant(record):
                            session_id = record.get("sessionId", "")
                            buckets.setdefault(session_id, []).append(record)
            except OSError:
                continue

        if args.cmd:
            filtered: dict[str, list[dict]] = {}
            for session_id, records in buckets.items():
                matching = [r for r in records if _cmd_matches(r, args.cmd)]
                if matching:
                    filtered[session_id] = matching
            buckets = filtered

        out_base = Path.cwd() / "logs" / slug
        for session_id, records in buckets.items():
            out_file = out_base / f"{session_id}.jsonl"
            out_file.parent.mkdir(parents=True, exist_ok=True)
            with open(out_file, "w", encoding="utf-8") as f:
                for record in records:
                    f.write(json.dumps(record) + "\n")

    generate_index(Path.cwd() / "logs")
    return 0


def _cmd_tail(args: argparse.Namespace, loops_dir: Path) -> int:
    """Stream live events from an active loop session."""
    events_file = loops_dir / ".running" / f"{args.loop}.events.jsonl"

    if not events_file.exists():
        print(f"No active session for loop '{args.loop}'", file=sys.stderr)
        return 1

    width = shutil.get_terminal_size().columns
    try:
        with open(events_file, encoding="utf-8") as f:
            f.seek(0, 2)
            while True:
                line = f.readline()
                if line:
                    line = line.strip()
                    if line:
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        formatted = _format_history_event(event, verbose=False, width=width)
                        if formatted is not None:
                            print(formatted)
                else:
                    time.sleep(0.1)
    except KeyboardInterrupt:
        return 0

    return 0


_CORRECTION_WINDOW_SEC = 30


def _aggregate_skill_stats(
    db_path: Path,
    *,
    window_days: int | None = None,
) -> dict[str, dict[str, int]] | None:
    """Aggregate per-skill invocation and correction counts from history.db.

    Returns None when the database is absent, or an empty dict when the database
    has no skill_events rows. Corrections are attributed to the most recent skill
    event in the same session within _CORRECTION_WINDOW_SEC seconds.
    """
    if not db_path.exists():
        return None

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        try:
            skill_rows = conn.execute(
                "SELECT ts, session_id, skill_name FROM skill_events ORDER BY ts"
            ).fetchall()
        except sqlite3.OperationalError:
            return None

        if not skill_rows:
            return {}

        if window_days is not None:
            latest_ts = skill_rows[-1]["ts"] or ""
            cutoff = _parse_iso_timestamp(latest_ts) - timedelta(days=window_days)
            skill_rows = [
                r for r in skill_rows if _parse_iso_timestamp(r["ts"] or "") >= cutoff
            ]

        stats: dict[str, dict[str, int]] = defaultdict(
            lambda: {"invocations": 0, "corrections": 0}
        )
        for row in skill_rows:
            stats[row["skill_name"] or "unknown"]["invocations"] += 1

        session_skills: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for row in skill_rows:
            sid = row["session_id"] or ""
            session_skills[sid].append((row["ts"] or "", row["skill_name"] or "unknown"))

        try:
            corr_rows = conn.execute(
                "SELECT ts, session_id FROM user_corrections ORDER BY ts"
            ).fetchall()
        except sqlite3.OperationalError:
            corr_rows = []

        for corr in corr_rows:
            c_ts = corr["ts"] or ""
            sid = corr["session_id"] or ""
            candidates = session_skills.get(sid, [])
            best_skill: str | None = None
            best_ts: str = ""
            for s_ts, s_name in candidates:
                if s_ts <= c_ts and s_ts >= best_ts:
                    best_ts = s_ts
                    best_skill = s_name
            if best_skill is not None:
                elapsed = (
                    _parse_iso_timestamp(c_ts) - _parse_iso_timestamp(best_ts)
                ).total_seconds()
                if 0 <= elapsed <= _CORRECTION_WINDOW_SEC:
                    stats[best_skill]["corrections"] += 1

        return dict(stats)
    finally:
        conn.close()


def _cmd_stats(args: argparse.Namespace, logger: Logger) -> int:
    """Aggregate skill invocation frequency and correction rate from history.db."""
    if args.project:
        db_paths = [Path(args.project) / ".ll" / "history.db"]
    else:
        decoded_paths = discover_all_projects(logger)
        db_paths = [p / ".ll" / "history.db" for p in decoded_paths]

    merged: dict[str, dict[str, int]] = defaultdict(
        lambda: {"invocations": 0, "corrections": 0}
    )
    found_any_db = False
    for db_path in db_paths:
        result = _aggregate_skill_stats(db_path, window_days=args.window_days)
        if result is None:
            continue
        found_any_db = True
        for skill, counts in result.items():
            merged[skill]["invocations"] += counts["invocations"]
            merged[skill]["corrections"] += counts["corrections"]

    if not merged:
        if not found_any_db:
            logger.warning("No history.db found — run with an active ll project.")
        else:
            print("No skill events recorded yet.")
        return 0

    sort_key = getattr(args, "sort", "freq")
    if sort_key == "corrections":
        ranked = sorted(
            merged.items(), key=lambda kv: kv[1]["corrections"], reverse=True
        )
    else:
        ranked = sorted(
            merged.items(), key=lambda kv: kv[1]["invocations"], reverse=True
        )

    if args.json:
        rows_json = [
            {
                "skill": skill,
                "invocations": counts["invocations"],
                "corrections": counts["corrections"],
                "correction_rate": (
                    round(counts["corrections"] / counts["invocations"], 4)
                    if counts["invocations"] > 0
                    else 0.0
                ),
                "errors": None,
                "error_rate": None,
            }
            for skill, counts in ranked
        ]
        print_json(rows_json)
        return 0

    headers = ["Skill", "Invocations", "Corrections", "Corr%", "Errors"]
    rows = []
    for skill, counts in ranked:
        inv = counts["invocations"]
        corr = counts["corrections"]
        corr_pct = f"{corr / inv * 100:.1f}%" if inv > 0 else "0.0%"
        rows.append([skill, str(inv), str(corr), corr_pct, "N/A"])

    print(table(headers, rows))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for ll-logs."""
    parser = argparse.ArgumentParser(
        prog="ll-logs",
        description="Discover and extract ll-relevant JSONL entries from Claude Code logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s discover              # List all projects with ll activity
  %(prog)s tail --loop <name>   # Stream live events from an active loop session
  %(prog)s extract --all             # Extract all projects to logs/
  %(prog)s extract --project /path  # Extract one project to logs/<slug>/
  %(prog)s extract --all --cmd ll-history  # Filter to ll-history invocations
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    discover_parser = subparsers.add_parser(
        "discover",
        help="List all Claude projects with ll activity (one path per line, sorted)",
    )
    add_json_arg(discover_parser)

    tail_parser = subparsers.add_parser(
        "tail",
        help="Stream live events from an active loop session",
    )
    tail_parser.add_argument("--loop", required=True, metavar="NAME", help="Loop name to tail")

    extract_parser = subparsers.add_parser(
        "extract",
        help="Extract ll-relevant JSONL records to logs/<slug>/<session-id>.jsonl",
    )
    target_group = extract_parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument(
        "--project",
        type=Path,
        metavar="DIR",
        help="Working directory of the target project",
    )
    target_group.add_argument(
        "--all",
        action="store_true",
        help="Extract all projects with ll activity",
    )
    extract_parser.add_argument(
        "--cmd",
        metavar="TOOL",
        help="Filter to records containing this ll- tool name (e.g. ll-history)",
    )

    sequences_parser = subparsers.add_parser(
        "sequences",
        help="Extract tool-chain n-grams of ll invocations from JSONL logs",
    )
    sequences_target = sequences_parser.add_mutually_exclusive_group(required=True)
    sequences_target.add_argument(
        "--project",
        type=Path,
        metavar="DIR",
        help="Working directory of the target project",
    )
    sequences_target.add_argument(
        "--all",
        action="store_true",
        help="Analyze all projects with ll activity",
    )
    sequences_parser.add_argument(
        "--min-len",
        type=int,
        default=2,
        metavar="N",
        help="Minimum n-gram length (default: 2)",
    )
    sequences_parser.add_argument(
        "--min-count",
        type=int,
        default=1,
        metavar="M",
        help="Minimum occurrence count to include (default: 1)",
    )
    sequences_parser.add_argument(
        "--top",
        type=int,
        default=None,
        metavar="N",
        help="Limit output to top N chains by frequency",
    )
    sequences_parser.add_argument(
        "--window-days",
        type=int,
        default=None,
        metavar="D",
        help="Only consider records within D days of latest record",
    )
    add_json_arg(sequences_parser)

    stats_parser = subparsers.add_parser(
        "stats",
        help="Aggregate skill invocation frequency and correction rate from history.db",
    )
    stats_target = stats_parser.add_mutually_exclusive_group(required=True)
    stats_target.add_argument(
        "--project",
        type=Path,
        metavar="DIR",
        help="Working directory of the target project",
    )
    stats_target.add_argument(
        "--all",
        action="store_true",
        help="Aggregate across all projects with ll activity",
    )
    stats_parser.add_argument(
        "--window-days",
        type=int,
        default=None,
        metavar="D",
        help="Only consider records within D days of latest record",
    )
    stats_parser.add_argument(
        "--sort",
        choices=["freq", "corrections"],
        default="freq",
        help="Sort output by invocation frequency or correction count (default: freq)",
    )
    add_json_arg(stats_parser)

    return parser


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments. Exposed for testing."""
    return _build_parser().parse_args()


def main_logs() -> int:
    """Entry point for ll-logs command.

    Returns:
        0 on success, 1 when no subcommand given or on error.
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-logs", sys.argv[1:]):
        configure_output()
        logger = Logger(use_color=use_color_enabled())

        parser = _build_parser()
        args = parser.parse_args()

        if not args.command:
            parser.print_help()
            return 1

        if args.command == "discover":
            projects = discover_all_projects(logger)
            if args.json:
                print_json({"paths": [str(p) for p in projects]})
            else:
                for path in projects:
                    print(path)
            return 0

        if args.command == "tail":
            config = BRConfig(Path.cwd())
            loops_dir = Path(config.loops.loops_dir)
            return _cmd_tail(args, loops_dir)

        if args.command == "extract":
            return _cmd_extract(args, logger)

        if args.command == "sequences":
            return _cmd_sequences(args, logger)

        if args.command == "stats":
            return _cmd_stats(args, logger)

        return 1
