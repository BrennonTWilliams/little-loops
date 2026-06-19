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
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from little_loops.cli.loop.info import (  # private symbol: cross-module coupling; verify signature on upgrade
    _format_history_event,
)
from little_loops.cli.output import configure_output, print_json, table, use_color_enabled
from little_loops.cli_args import add_json_arg
from little_loops.config import BRConfig
from little_loops.logger import Logger
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context, resolve_history_db
from little_loops.user_messages import get_project_folder

_COMMAND_NAME_RE = re.compile(r"<command-name>/ll:")
BRIDGE_MARKER = "Bridged from `commands/"


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
            logger.debug(f"Decoded path does not exist: {decoded_path}")
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
_CONTENT_FREE_RE = re.compile(r"^exit\s+code\s+\d+$", re.IGNORECASE)


@dataclass
class InvocationEvent:
    """A single ll invocation event extracted from a JSONL record."""

    tool_name: str
    timestamp: str
    session_id: str


def _extract_ll_event_streams(
    project_folder: Path, *, cutoff: datetime | None = None
) -> dict[str, list[InvocationEvent]]:
    """Extract per-session ordered ll-invocation event streams from JSONL files.

    Walks JSONL files (skipping ``agent-*``), filters to records with ll activity,
    extracts the tool/skill name, and returns a dict mapping ``sessionId`` to a
    timestamp-sorted list of ``InvocationEvent``.

    Args:
        project_folder: Path to the claude project session directory.
        cutoff: If set, exclude records with timestamps before this datetime.

    Returns:
        Dict of ``{session_id: [InvocationEvent, ...]}`` with events sorted by timestamp.
    """
    events_by_session: dict[str, list[InvocationEvent]] = {}

    jsonl_files = [f for f in project_folder.glob("*.jsonl") if not f.name.startswith("agent-")]
    if not jsonl_files:
        return events_by_session

    all_events: list[InvocationEvent] = []

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
        except OSError:
            continue

    # Apply wall-clock cutoff filter
    if cutoff is not None:
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
            "edges": [{"from": e.from_, "to": e.to, "freq": e.freq} for e in self.edges],
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
                ngram = tuple(names[i : i + n])
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

    cutoff = datetime.now(UTC) - timedelta(days=args.window_days) if args.window_days is not None else None

    # Aggregate events across all projects
    all_events: dict[str, list[InvocationEvent]] = {}
    for _cwd_path, project_folder in project_items:
        events = _extract_ll_event_streams(project_folder, cutoff=cutoff)
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
    cutoff: datetime | None = None,
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

        if cutoff is not None:
            skill_rows = [r for r in skill_rows if _parse_iso_timestamp(r["ts"] or "") >= cutoff]

        stats: dict[str, dict[str, int]] = defaultdict(lambda: {"invocations": 0, "corrections": 0})
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


def _load_catalog_names(root_dir: Path) -> set[str]:
    """Load normalized skill/command names from skills/ and commands/ under root_dir.

    Excludes bridge skills (containing BRIDGE_MARKER) and skills/commands with
    disable-model-invocation: true.  Normalizes names by stripping the "ll-" prefix
    so catalog names match the skill_events.skill_name recording convention.
    """
    import yaml

    names: set[str] = set()

    skills_dir = root_dir / "skills"
    if skills_dir.is_dir():
        for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
            try:
                text = skill_md.read_text()
            except OSError:
                continue
            if BRIDGE_MARKER in text:
                continue
            name: str = skill_md.parent.name
            if text.startswith("---"):
                end = text.find("---", 3)
                if end != -1:
                    try:
                        fm = yaml.safe_load(text[3:end]) or {}
                    except yaml.YAMLError:
                        fm = {}
                    if isinstance(fm, dict):
                        dmi = fm.get("disable-model-invocation")
                        if (isinstance(dmi, bool) and dmi) or (
                            isinstance(dmi, str) and dmi.strip().lower() in ("true", "yes", "1")
                        ):
                            continue
                        name = str(fm.get("name") or name)
            if name.startswith("ll-"):
                name = name[3:]
            if name:
                names.add(name)

    commands_dir = root_dir / "commands"
    if commands_dir.is_dir():
        for cmd_md in sorted(commands_dir.glob("*.md")):
            stem = cmd_md.stem
            try:
                text = cmd_md.read_text()
            except OSError:
                names.add(stem)
                continue
            if text.startswith("---"):
                end = text.find("---", 3)
                if end != -1:
                    try:
                        fm = yaml.safe_load(text[3:end]) or {}
                    except yaml.YAMLError:
                        fm = {}
                    if isinstance(fm, dict):
                        dmi = fm.get("disable-model-invocation")
                        if (isinstance(dmi, bool) and dmi) or (
                            isinstance(dmi, str) and dmi.strip().lower() in ("true", "yes", "1")
                        ):
                            continue
            names.add(stem)

    return names


def _cmd_dead_skills(args: argparse.Namespace, logger: Logger) -> int:
    """List catalog skills/commands never or rarely invoked within the window."""
    if args.project:
        db_paths = [Path(args.project) / ".ll" / "history.db"]
        catalog_root = Path(args.project)
    else:
        decoded_paths = discover_all_projects(logger)
        db_paths = [p / ".ll" / "history.db" for p in decoded_paths]
        catalog_root = Path.cwd()

    cutoff = datetime.now(UTC) - timedelta(days=args.window_days) if args.window_days is not None else None

    merged: dict[str, int] = defaultdict(int)
    for db_path in db_paths:
        result = _aggregate_skill_stats(db_path, cutoff=cutoff)
        if result is None:
            continue
        for skill, counts in result.items():
            merged[skill] += counts["invocations"]

    catalog_names = _load_catalog_names(catalog_root)
    if not catalog_names:
        logger.warning(
            "No catalog skills found — run from an ll project root with skills/ directory."
        )
        return 0

    threshold = args.threshold
    rows = []
    for name in sorted(catalog_names):
        count = merged.get(name, 0)
        if count == 0:
            rows.append({"skill": name, "invocations": 0, "tier": "never"})
        elif count <= threshold:
            rows.append({"skill": name, "invocations": count, "tier": "rarely"})

    if args.json:
        print_json(rows)
        return 0

    if not rows:
        print("No dead or rarely-invoked skills found.")
        return 0

    headers = ["Skill", "Invocations", "Tier"]
    table_rows = [[str(r["skill"]), str(r["invocations"]), str(r["tier"])] for r in rows]
    print(table(headers, table_rows))
    return 0


def _load_cli_allowlist(root: Path) -> frozenset[str]:
    """Return ll-* CLI names from [project.scripts] in scripts/pyproject.toml.

    Returns an empty frozenset if the file cannot be read; the allowlist check
    is skipped when the set is empty so fallback behavior is open (no filtering).
    """
    import tomllib

    pyproject = root / "scripts" / "pyproject.toml"
    try:
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
    except (OSError, ValueError):
        return frozenset()
    scripts = data.get("project", {}).get("scripts", {})
    return frozenset(k for k in scripts if k.startswith("ll-"))


def _is_content_free_error(error_text: str) -> bool:
    """Return True if error_text carries no signal beyond a bare exit code."""
    return bool(_CONTENT_FREE_RE.match(error_text.strip()))


_STACK_FRAME_RE = re.compile(r'\s*File "[^"]+", line \d+[^\n]*')
_ABS_PATH_RE = re.compile(r"/(?:[^\s,;\"']+/)+[^\s,;\"']+")
_LINE_NUM_RE = re.compile(r"\bline \d+\b")
_LL_VERIFY_RE = re.compile(r"^ll-verify-\w+")


def _normalize_error_sig(text: str) -> str:
    """Strip volatile parts (paths, line numbers, stack frames) from error text.

    Returns a stable string suitable as a cluster key.
    """
    text = _STACK_FRAME_RE.sub("", text)
    text = _ABS_PATH_RE.sub("<path>", text)
    text = _LINE_NUM_RE.sub("line N", text)
    return re.sub(r"\s+", " ", text).strip()[:300]


def _extract_error_text(content: object) -> str:
    """Extract plain text from a tool_result content field (string or list of text blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text", "")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


@dataclass
class _FailureCluster:
    """Aggregated failure cluster keyed on (cwd_path, tool_name, normalized_sig)."""

    tool_name: str
    normalized_sig: str
    count: int
    sample_error: str
    session_ids: list[str]
    cwd_path: Path = field(default_factory=lambda: Path("."))


def _cmd_scan_failures(args: argparse.Namespace, logger: Logger) -> int:
    """Mine failed ll-* Bash calls from interactive session JSONL logs."""
    from little_loops.issue_lifecycle import FailureType, classify_failure

    _cli_allowlist = _load_cli_allowlist(Path.cwd())

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

    # raw_clusters maps (cwd_path, tool_name, normalized_sig) -> (count, sample_error, session_ids, latest_ts)
    raw_clusters: dict[tuple[Path, str, str], tuple[int, str, list[str], str]] = {}

    for _cwd_path, project_folder in project_items:
        jsonl_files = [f for f in project_folder.glob("*.jsonl") if not f.name.startswith("agent-")]

        for jsonl_file in jsonl_files:
            try:
                with open(jsonl_file, encoding="utf-8") as f:
                    lines = f.readlines()
            except OSError:
                continue

            # pending maps tool_use_id -> (ll_tool_name, timestamp)
            pending: dict[str, tuple[str, str]] = {}

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                record_type = record.get("type")
                ts = record.get("timestamp", "")
                session_id = record.get("sessionId", "")

                if record_type == "assistant":
                    message = record.get("message", {})
                    content = message.get("content", [])
                    if not isinstance(content, list):
                        continue
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") != "tool_use" or block.get("name") != "Bash":
                            continue
                        cmd = block.get("input", {}).get("command", "")
                        m = _LL_BASH_RE.search(cmd)
                        if not m:
                            continue
                        tool_name = m.group(1)
                        # Skip tokens that are not real ll CLIs (e.g. ll-labs, ll-marketing)
                        if _cli_allowlist and tool_name not in _cli_allowlist:
                            continue
                        block_id = block.get("id", "")
                        if block_id:
                            pending[block_id] = (tool_name, ts)

                elif record_type == "user":
                    message = record.get("message", {})
                    content = message.get("content", [])
                    if not isinstance(content, list) or not content:
                        continue
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") != "tool_result":
                            continue
                        tool_use_id = block.get("tool_use_id", "")
                        if tool_use_id not in pending:
                            continue
                        tool_name, _invoke_ts = pending.pop(tool_use_id)

                        # Skip ll-verify-* tools — exit 1 is expected gate behavior
                        if _LL_VERIFY_RE.match(tool_name):
                            continue

                        is_error_flag = block.get("is_error") is True
                        raw_content = block.get("content", "")
                        error_text = _extract_error_text(raw_content)
                        has_traceback = "Traceback (most recent call last)" in error_text

                        if not (is_error_flag or has_traceback):
                            continue

                        returncode = 1 if is_error_flag else 0
                        failure_type, _reason = classify_failure(error_text, returncode)
                        if failure_type == FailureType.TRANSIENT:
                            continue

                        normalized_sig = _normalize_error_sig(error_text)
                        key = (_cwd_path, tool_name, normalized_sig)

                        if key in raw_clusters:
                            cnt, sample, sids, _lts = raw_clusters[key]
                            if session_id not in sids:
                                sids.append(session_id)
                            raw_clusters[key] = (cnt + 1, sample, sids, ts)
                        else:
                            raw_clusters[key] = (1, error_text[:500], [session_id], ts)

    # Apply wall-clock cutoff filter
    if args.window_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=args.window_days)
        raw_clusters = {
            k: v for k, v in raw_clusters.items() if _parse_iso_timestamp(v[3]) >= cutoff
        }

    # Drop content-free clusters (bare "Exit code N" with no error body)
    raw_clusters = {k: v for k, v in raw_clusters.items() if not _is_content_free_error(v[1])}

    clusters: list[_FailureCluster] = sorted(
        [
            _FailureCluster(
                tool_name=k[1],
                normalized_sig=k[2],
                count=v[0],
                sample_error=v[1],
                session_ids=v[2],
                cwd_path=k[0],
            )
            for k, v in raw_clusters.items()
        ],
        key=lambda c: c.count,
        reverse=True,
    )

    if not clusters:
        if not args.json:
            print("No ll-* failures found.")
        else:
            print_json([])
        return 0

    if args.capture:
        capture_foreign = getattr(args, "capture_foreign", False)
        return _capture_failure_clusters(clusters, logger, capture_foreign=capture_foreign)

    if args.json:
        print_json(
            [
                {
                    "tool": c.tool_name,
                    "count": c.count,
                    "normalized_sig": c.normalized_sig,
                    "sample_error": c.sample_error,
                    "session_ids": c.session_ids,
                }
                for c in clusters
            ]
        )
        return 0

    for c in clusters:
        print(f"[{c.count}x] {c.tool_name}")
        print(f"  Sessions: {', '.join(c.session_ids[:5])}")
        for sl in c.sample_error.splitlines()[:5]:
            print(f"  {sl}")
        print()

    return 0


def _capture_failure_clusters(
    clusters: list[_FailureCluster], logger: Logger, capture_foreign: bool = False
) -> int:
    """Create bug issue files for each distinct failure cluster (--capture mode)."""
    from little_loops.issue_lifecycle import create_issue_from_failure
    from little_loops.issue_parser import IssueInfo

    config = BRConfig(Path.cwd())
    current_project = Path.cwd().resolve()
    created = 0
    skipped_foreign = 0

    for c in clusters:
        if not capture_foreign and c.cwd_path.resolve() != current_project:
            skipped_foreign += 1
            continue
        stub_info = IssueInfo(
            path=Path(f"cli/{c.tool_name}"),
            issue_type="bugs",
            priority="P1",
            issue_id=c.tool_name,
            title=f"Tool failure in {c.tool_name}",
        )
        result = create_issue_from_failure(c.sample_error, stub_info, config, logger)
        if result is not None:
            logger.info(f"Created: {result.name}")
            created += 1

    if skipped_foreign:
        logger.info(
            f"Skipped {skipped_foreign} cluster(s) from other projects "
            "(use --capture-foreign to include them)."
        )
    logger.info(f"Captured {created} failure cluster(s) as bug issues.")
    return 0


def _cmd_stats(args: argparse.Namespace, logger: Logger) -> int:
    """Aggregate skill invocation frequency and correction rate from history.db."""
    if args.project:
        db_paths = [Path(args.project) / ".ll" / "history.db"]
    else:
        decoded_paths = discover_all_projects(logger)
        db_paths = [p / ".ll" / "history.db" for p in decoded_paths]

    cutoff = datetime.now(UTC) - timedelta(days=args.window_days) if args.window_days is not None else None

    merged: dict[str, dict[str, int]] = defaultdict(lambda: {"invocations": 0, "corrections": 0})
    found_any_db = False
    for db_path in db_paths:
        result = _aggregate_skill_stats(db_path, cutoff=cutoff)
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
        ranked = sorted(merged.items(), key=lambda kv: kv[1]["corrections"], reverse=True)
    else:
        ranked = sorted(merged.items(), key=lambda kv: kv[1]["invocations"], reverse=True)

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


def _resolve_session_log(session_ref: str, db_path: Path) -> Path | None:
    """Resolve a session reference (session ID or JSONL path) to a JSONL file path.

    Tries in order:
    1. Direct file path if the ref resolves to an existing ``.jsonl`` file
    2. DB lookup of ``session_id → jsonl_path`` in the sessions table
    Returns None if unresolvable.
    """
    candidate = Path(session_ref)
    if candidate.suffix == ".jsonl" and candidate.exists():
        return candidate

    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT jsonl_path FROM sessions WHERE session_id = ?",
                (session_ref,),
            ).fetchone()
            if row and row["jsonl_path"]:
                return Path(row["jsonl_path"])
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()

    return None


def _events_from_jsonl(jsonl_path: Path) -> list[InvocationEvent]:
    """Extract ll invocation events from a single JSONL file, sorted by timestamp."""
    events: list[InvocationEvent] = []
    try:
        with open(jsonl_path, encoding="utf-8") as f:
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
                events.append(InvocationEvent(tool_name=tool_name, timestamp=ts, session_id=sid))
    except OSError:
        pass
    events.sort(key=lambda e: e.timestamp)
    return events


@dataclass
class SessionDiff:
    """Behavioral diff between two ll sessions."""

    session_a: str
    session_b: str
    skills_added: list[str]
    skills_removed: list[str]
    count_deltas: dict[str, dict[str, int]]
    sequence_diff: list[str]

    def to_dict(self) -> dict:
        return {
            "session_a": self.session_a,
            "session_b": self.session_b,
            "skills_added": self.skills_added,
            "skills_removed": self.skills_removed,
            "count_deltas": self.count_deltas,
            "sequence_diff": self.sequence_diff,
        }


def _compute_session_diff(
    session_a: str,
    events_a: list[InvocationEvent],
    session_b: str,
    events_b: list[InvocationEvent],
) -> SessionDiff:
    """Compute the behavioral diff between two session event streams."""
    import difflib
    from collections import Counter as _Counter

    names_a = [e.tool_name for e in events_a]
    names_b = [e.tool_name for e in events_b]

    set_a = set(names_a)
    set_b = set(names_b)
    skills_added = sorted(set_b - set_a)
    skills_removed = sorted(set_a - set_b)

    counter_a: Counter = _Counter(names_a)
    counter_b: Counter = _Counter(names_b)
    count_deltas: dict[str, dict[str, int]] = {}
    for skill in sorted(set_a | set_b):
        ca = counter_a.get(skill, 0)
        cb = counter_b.get(skill, 0)
        if ca != cb:
            count_deltas[skill] = {"a": ca, "b": cb, "delta": cb - ca}

    label_a = f"session_a ({session_a[:8]})" if len(session_a) > 8 else f"session_a ({session_a})"
    label_b = f"session_b ({session_b[:8]})" if len(session_b) > 8 else f"session_b ({session_b})"
    sequence_diff = list(
        difflib.unified_diff(names_a, names_b, fromfile=label_a, tofile=label_b, lineterm="")
    )

    return SessionDiff(
        session_a=session_a,
        session_b=session_b,
        skills_added=skills_added,
        skills_removed=skills_removed,
        count_deltas=count_deltas,
        sequence_diff=sequence_diff,
    )


def _cmd_diff(args: argparse.Namespace, logger: Logger) -> int:
    """Compare two sessions' ll-invocation behavior."""
    db_path = resolve_history_db()

    path_a = _resolve_session_log(args.session_a, db_path)
    if path_a is None:
        logger.error(f"Cannot resolve session: {args.session_a}")
        return 1

    path_b = _resolve_session_log(args.session_b, db_path)
    if path_b is None:
        logger.error(f"Cannot resolve session: {args.session_b}")
        return 1

    events_a = _events_from_jsonl(path_a)
    events_b = _events_from_jsonl(path_b)

    diff = _compute_session_diff(args.session_a, events_a, args.session_b, events_b)

    if args.json:
        print_json(diff.to_dict())
        return 0

    if (
        not diff.skills_added
        and not diff.skills_removed
        and not diff.count_deltas
        and not diff.sequence_diff
    ):
        print("No behavioral differences found.")
        return 0

    if diff.skills_added:
        print(f"Skills added ({len(diff.skills_added)}):")
        for s in diff.skills_added:
            print(f"  + {s}")

    if diff.skills_removed:
        if diff.skills_added:
            print()
        print(f"Skills removed ({len(diff.skills_removed)}):")
        for s in diff.skills_removed:
            print(f"  - {s}")

    if diff.count_deltas:
        print()
        print("Invocation count changes:")
        for skill, counts in sorted(diff.count_deltas.items()):
            delta_str = f"+{counts['delta']}" if counts["delta"] > 0 else str(counts["delta"])
            print(f"  {skill}: {counts['a']} → {counts['b']} ({delta_str})")

    if diff.sequence_diff:
        print()
        print("Sequence diff:")
        for line in diff.sequence_diff:
            print(f"  {line}")

    return 0


_ISSUE_ID_RE = re.compile(r"\b[A-Z]+-\d+\b")


@dataclass
class _EvalInvocation:
    """A reconstructed ll-harness invocation extracted from a JSONL record.

    Carries the runner kind and raw (un-redacted) input-context text that the
    EvalFixture export needs but that ``InvocationEvent`` discards.
    """

    runner: str  # "skill" | "cmd"
    target: str  # skill name (runner==skill) or full shell command (runner==cmd)
    session_id: str
    timestamp: str
    input_context: str  # raw user-message text; "" when none (e.g. Bash invocations)


def _extract_eval_invocation(record: dict) -> _EvalInvocation | None:
    """Reconstruct a single ll-harness invocation from a JSONL record.

    Mirrors ``_extract_tool_name``'s three signals but also captures the runner
    kind and raw input-context text needed for EvalFixture export:
      (a) queue enqueue ``/ll:<name>``      -> runner=skill, target=name
      (b) user ``<command-name>/ll:<name>`` -> runner=skill, target=name
      (c) assistant Bash ``ll-<tool>``      -> runner=cmd,   target=<full command>

    Returns None for records that carry no ll invocation signal.
    """
    record_type = record.get("type")
    sid = record.get("sessionId", "")
    ts = record.get("timestamp", "")

    # (a) queue-operation enqueue
    if record_type == "queue-operation" and record.get("operation") == "enqueue":
        content = record.get("content", "")
        if isinstance(content, str) and content.startswith("/ll:"):
            m = _QUEUE_SKILL_RE.match(content)
            if m:
                return _EvalInvocation("skill", m.group(1), sid, ts, content)

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
                name = m.group(1)
                if name.endswith("</command-name>"):
                    name = name[: -len("</command-name>")]
                return _EvalInvocation("skill", name, sid, ts, text)

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
                    if _LL_BASH_RE.search(cmd):
                        return _EvalInvocation("cmd", cmd, sid, ts, "")

    return None


def _record_has_error(record: dict) -> bool:
    """True if a JSONL record is a ``tool_result`` flagged ``is_error``.

    Used as the session-level ``failed`` outcome signal: session logs expose no
    output-quality judgment, only execution evidence (ARCHITECTURE-017).
    """
    if record.get("type") != "user":
        return False
    message = record.get("message", {})
    if not isinstance(message, dict):
        return False
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_result"
                and block.get("is_error")
            ):
                return True
    return False


def _classify_outcome(metadata: dict, *, has_error: bool) -> str:
    """Map session metadata + error signal to an EvalFixture execution outcome.

    Precedence ``failed`` > ``corrected`` > ``accepted``; ``unknown`` when the DB
    returned no metadata. Per ARCHITECTURE-017 the taxonomy is EXECUTION, not
    output quality. ``metadata`` is the dict from
    ``history_reader.lookup_session_metadata`` (``{}`` when the session is absent).
    """
    if has_error:
        return "failed"
    if not metadata:
        return "unknown"
    if metadata.get("has_corrections"):
        return "corrected"
    return "accepted"


def _redact_input_context(text: str) -> tuple[str | None, bool]:
    """Best-effort, non-blocking redaction of user-message text.

    Applies ``pii.redact_pii`` (email/phone/SSN) then ``_ABS_PATH_RE`` (absolute
    paths). Returns ``(redacted_text_or_None, pii_detected)`` where ``pii_detected``
    is True when either pass altered the text. Never raises and never drops a
    record for unredactable content (ARCHITECTURE-017).
    """
    if not text:
        return None, False
    from little_loops.pii import redact_pii

    redacted = redact_pii(text)
    redacted = _ABS_PATH_RE.sub("<path>", redacted)
    return redacted, redacted != text


def _build_eval_fixture(inv: _EvalInvocation, outcome: str) -> dict:
    """Map a reconstructed invocation + outcome to an EvalFixture v1 record.

    Pure function (no I/O) — the mapping core covered by unit tests. Schema and
    field semantics per decision ARCHITECTURE-017 in ``.ll/decisions.yaml``: the
    fixture replays into ``ll-harness <runner> <target> [runner_args...]
    [--exit-code N] [--semantic TEXT] [--timeout S]`` (ll-harness has no loader).
    """
    input_context, pii_detected = _redact_input_context(inv.input_context)
    issue_match = _ISSUE_ID_RE.search(inv.input_context) if inv.input_context else None
    issue_id = issue_match.group(0) if issue_match else None
    skill_name = inv.target if inv.runner == "skill" else None
    return {
        "runner": inv.runner,
        "target": inv.target,
        "session_id": inv.session_id,
        "timestamp": inv.timestamp,
        "outcome": outcome,
        "runner_args": [],
        "exit_code": None,
        "semantic": None,
        "timeout": 120,
        "input_context": input_context,
        "issue_id": issue_id,
        "skill_name": skill_name,
        "pii_detected": pii_detected,
    }


def _fixture_to_harness_argv(fixture: dict) -> list[str]:
    """Serialize an EvalFixture record back into an ``ll-harness`` argv.

    ll-harness has no fixture loader (ARCHITECTURE-017); a fixture replays by
    serializing its fields into the harness CLI arg surface. Used by the
    round-trip test to prove every exported fixture is a valid harness invocation.
    """
    argv: list[str] = [fixture["runner"], fixture["target"]]
    argv.extend(fixture.get("runner_args") or [])
    if fixture.get("exit_code") is not None:
        argv.extend(["--exit-code", str(fixture["exit_code"])])
    if fixture.get("semantic") is not None:
        argv.extend(["--semantic", str(fixture["semantic"])])
    timeout = fixture.get("timeout")
    if timeout is not None and timeout != 120:
        argv.extend(["--timeout", str(timeout)])
    return argv


def _cmd_eval_export(args: argparse.Namespace) -> int:
    """Export ll-harness eval fixtures reconstructed from session logs (FEAT-1971).

    Walks the current project's JSONL logs, reconstructs each ll invocation, sources
    an execution outcome from ``history_reader.lookup_session_metadata``, redacts the
    input context, and writes EvalFixture v1 records (YAML default, JSON with
    ``--json``). Schema + outcome taxonomy: decision ARCHITECTURE-017 in
    ``.ll/decisions.yaml``.
    """
    from little_loops.history_reader import lookup_session_metadata

    cwd_path = Path(args.project) if args.project else Path.cwd()
    project_folder = get_project_folder(cwd_path)
    if project_folder is None:
        print(f"No session project folder found for: {cwd_path}", file=sys.stderr)
        return 1
    from little_loops.session_store import resolve_history_db

    db_path = resolve_history_db(cwd_path / ".ll" / "history.db")

    # Single JSONL pass: collect raw invocations + per-session error flags together
    # (avoids the double-parse the decision warns against).
    invocations: list[_EvalInvocation] = []
    session_has_error: dict[str, bool] = {}
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
                    if _record_has_error(record):
                        sid = record.get("sessionId", "")
                        if sid:
                            session_has_error[sid] = True
                    inv = _extract_eval_invocation(record)
                    if inv is not None:
                        invocations.append(inv)
        except OSError:
            continue

    # Stable, deterministic order: by timestamp then session.
    invocations.sort(key=lambda e: (e.timestamp, e.session_id))

    metadata_cache: dict[str, dict] = {}
    fixtures: list[dict] = []
    skipped = 0
    for inv in invocations:
        # --skill: keep only skill-runner invocations of the named target.
        if args.skill and not (inv.runner == "skill" and inv.target == args.skill):
            continue

        if inv.session_id not in metadata_cache:
            metadata_cache[inv.session_id] = lookup_session_metadata(inv.session_id, db=db_path)
        outcome = _classify_outcome(
            metadata_cache[inv.session_id],
            has_error=session_has_error.get(inv.session_id, False),
        )
        # No extractable execution outcome -> skip with a logged count.
        if outcome == "unknown":
            skipped += 1
            continue

        fixture = _build_eval_fixture(inv, outcome)

        # --issue: match the extracted issue_id or a literal occurrence in target.
        if args.issue and args.issue != fixture["issue_id"] and args.issue not in inv.target:
            continue

        fixtures.append(fixture)
        if args.limit and len(fixtures) >= args.limit:
            break

    if args.json:
        output = json.dumps(fixtures, indent=2)
    else:
        import yaml

        output = yaml.safe_dump(fixtures, sort_keys=False, default_flow_style=False)

    if args.out:
        out_path = Path(args.out)
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(output, encoding="utf-8")
        except OSError as exc:
            print(f"Failed to write {out_path}: {exc}", file=sys.stderr)
            return 1
        print(f"Wrote {len(fixtures)} fixture(s) to {out_path}", file=sys.stderr)
    else:
        print(output, end="" if output.endswith("\n") else "\n")

    if skipped:
        print(
            f"Skipped {skipped} invocation(s) with no extractable outcome",
            file=sys.stderr,
        )

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
        help="Only consider records within the last D calendar days",
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
        help="Only consider records within the last D calendar days",
    )
    stats_parser.add_argument(
        "--sort",
        choices=["freq", "corrections"],
        default="freq",
        help="Sort output by invocation frequency or correction count (default: freq)",
    )
    add_json_arg(stats_parser)

    scan_failures_parser = subparsers.add_parser(
        "scan-failures",
        help="Mine failed ll-* calls from interactive session logs and propose bug issues",
    )
    scan_failures_target = scan_failures_parser.add_mutually_exclusive_group(required=True)
    scan_failures_target.add_argument(
        "--project",
        type=Path,
        metavar="DIR",
        help="Working directory of the target project",
    )
    scan_failures_target.add_argument(
        "--all",
        action="store_true",
        help="Scan all projects with ll activity",
    )
    scan_failures_parser.add_argument(
        "--window-days",
        type=int,
        default=None,
        metavar="D",
        help="Only consider records within the last D calendar days",
    )
    scan_failures_parser.add_argument(
        "--capture",
        action="store_true",
        help="Create bug issue files for each failure cluster (one per tool+error signature)",
    )
    scan_failures_parser.add_argument(
        "--capture-foreign",
        action="store_true",
        help="Allow --capture to include failures from projects other than the current directory (only meaningful with --all)",
    )
    add_json_arg(scan_failures_parser)

    dead_skills_parser = subparsers.add_parser(
        "dead-skills",
        help="List catalog skills/commands with zero or low invocations across the corpus",
    )
    dead_skills_target = dead_skills_parser.add_mutually_exclusive_group(required=True)
    dead_skills_target.add_argument(
        "--project",
        type=Path,
        metavar="DIR",
        help="Working directory of the target project (also used as catalog root)",
    )
    dead_skills_target.add_argument(
        "--all",
        action="store_true",
        help="Aggregate across all projects; catalog loaded from current directory",
    )
    dead_skills_parser.add_argument(
        "--window-days",
        type=int,
        default=None,
        metavar="D",
        help="Only consider records within the last D calendar days",
    )
    dead_skills_parser.add_argument(
        "--threshold",
        type=int,
        default=3,
        metavar="N",
        help="Skills with invocations <= N are 'rarely' invoked (default: 3)",
    )
    add_json_arg(dead_skills_parser)

    diff_parser = subparsers.add_parser(
        "diff",
        help="Compare two sessions' ll-invocation behavior (skills, sequences, counts)",
    )
    diff_parser.add_argument(
        "session_a", metavar="SESSION_A", help="First session ID or JSONL file path"
    )
    diff_parser.add_argument(
        "session_b", metavar="SESSION_B", help="Second session ID or JSONL file path"
    )
    add_json_arg(diff_parser)

    eval_export_parser = subparsers.add_parser(
        "eval-export",
        help="Export eval fixtures from ll-harness session logs",
    )
    eval_export_parser.add_argument(
        "--project",
        type=Path,
        metavar="DIR",
        help="Project working directory (default: current directory)",
    )
    eval_export_parser.add_argument(
        "--skill",
        metavar="NAME",
        help="Filter by skill name",
    )
    eval_export_parser.add_argument(
        "--issue",
        metavar="ID",
        help="Filter by issue ID in session context",
    )
    eval_export_parser.add_argument(
        "--limit",
        type=int,
        default=0,
        metavar="N",
        help="Cap output records (0 = unlimited)",
    )
    eval_export_parser.add_argument(
        "--out",
        metavar="PATH",
        help="Write output to file (default: stdout)",
    )
    add_json_arg(eval_export_parser, help_text="JSON output instead of YAML (default: YAML)")

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

        if args.command == "scan-failures":
            return _cmd_scan_failures(args, logger)

        if args.command == "dead-skills":
            return _cmd_dead_skills(args, logger)

        if args.command == "diff":
            return _cmd_diff(args, logger)

        if args.command == "eval-export":
            return _cmd_eval_export(args)

        return 1
