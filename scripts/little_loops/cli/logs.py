"""ll-logs: Discover, extract, analyze ll-relevant log entries across every registered host."""

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
from datetime import UTC, date, datetime, timedelta
from datetime import time as dt_time
from pathlib import Path
from typing import TYPE_CHECKING

from little_loops.analytics.association import compute_lift, compute_pmi
from little_loops.cli.loop.info import (  # private symbol: cross-module coupling; verify signature on upgrade
    _format_history_event,
)
from little_loops.cli.output import configure_output, print_json, table, use_color_enabled
from little_loops.cli_args import (
    add_corpus_target_args,
    add_host_arg,
    add_json_arg,
    add_window_args,
)
from little_loops.config import BRConfig
from little_loops.fsm.loop_paths import get_builtin_loops_dir
from little_loops.logger import Logger
from little_loops.session_store import (
    DEFAULT_DB_PATH,
    REGISTERED_HOSTS,
    SessionHandle,
    cli_event_context,
    detect_sessions,
    explain_no_sessions,
    iter_events,
    list_workspaces,
    resolve_history_db,
)
from little_loops.user_messages import _resolve_host

if TYPE_CHECKING:
    from little_loops.fsm.validation import ValidationError

_COMMAND_NAME_RE = re.compile(r"<command-name>/ll:")
BRIDGE_MARKER = "Bridged from `commands/"

# Archive run folder naming: <YYYY-MM-DDTHHMMSS>-<loop-name>
_HISTORY_RUN_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{6})-(.+)$")


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


def _workspace_has_ll_activity(handles: list[SessionHandle]) -> bool:
    """Early-exit walk over parsed events across every handle for one workspace.

    Replaces the old file-glob-based ``_has_ll_activity``: normalization to
    Claude shape (qwen/gemini/omp) and envelope/payload splitting (Codex) now
    happen inside ``iter_events`` itself, so this just applies
    ``_is_ll_relevant`` to each event's payload.
    """
    for handle in handles:
        if handle.is_agent:
            continue
        for event in iter_events(handle):
            if _is_ll_relevant(event.payload):
                return True
    return False


def _discover_workspace_handles(
    logger: Logger, *, host: str | None, existing_only: bool = False
) -> dict[Path, list[SessionHandle]]:
    """The handles-returning core behind ``--all`` discovery (ENH-3430).

    Iterates **per host, not per workspace with ``host=None``** —
    ``detect_sessions(ws, host)`` is called at most once per ``(workspace,
    host)`` pair, never with ``host=None`` (that would probe every registered
    host for every candidate workspace). Dedupes on resolved cwd but *merges*
    handles across hosts under the deduped key, so a workspace recorded under
    two hosts keeps both hosts' handles rather than only the first-seen
    host's. The ll-activity filter is evaluated once per deduped workspace
    against the full merged handle set, so a workspace survives if *any*
    host's handles show activity (e.g. Claude Code activity keeps a workspace
    whose Codex handles alone contribute zero events).

    ``existing_only`` mirrors ``discover_all_projects``'s historical
    contract: ``False`` (default) logs a debug line for a decoded path that
    no longer exists on disk; ``True`` skips it silently.
    """
    hosts = (host,) if host is not None else REGISTERED_HOSTS

    decoded_by_key: dict[str, Path] = {}
    handles_by_key: dict[str, list[SessionHandle]] = {}

    for one_host in hosts:
        for workspace in list_workspaces(one_host, existing_only=False):
            if not workspace.exists():
                if not existing_only:
                    logger.debug(f"Decoded path does not exist: {workspace}")
                continue
            key = str(workspace.resolve())
            found = detect_sessions(workspace, one_host, include_agents=False)
            decoded_by_key.setdefault(key, workspace)
            handles_by_key.setdefault(key, []).extend(found)

    results: dict[Path, list[SessionHandle]] = {}
    for key, handles in handles_by_key.items():
        if not _workspace_has_ll_activity(handles):
            continue
        results[decoded_by_key[key]] = handles
    return results


def discover_all_projects(
    logger: Logger, *, host: str | None = None, existing_only: bool = False
) -> list[Path]:
    """Discover all workspaces with ll activity for the given host.

    Args:
        logger: Logger instance for diagnostics.
        host: Host identifier to restrict discovery to. ``None`` unions every
            registered host (callers resolve ``--host``/``LL_HOOK_HOST`` via
            ``_resolve_host`` before calling this).
        existing_only: When True, silently skip paths that don't exist on disk
            (no debug message). Useful for scripted consumers that want clean
            stderr as well as clean stdout.

    Returns:
        Sorted list of decoded absolute paths for workspaces with ll activity.
    """
    return sorted(
        _discover_workspace_handles(logger, host=host, existing_only=existing_only).keys()
    )


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
    handles: list[SessionHandle],
    *,
    cutoff: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, list[InvocationEvent]]:
    """Extract per-session ordered ll-invocation event streams from session handles.

    Walks each handle's parsed events via ``iter_events`` (per-host
    normalization to Claude shape, where one exists, already applied),
    filters to records with an ll invocation signal, and returns a dict
    mapping session id to a timestamp-sorted list of ``InvocationEvent``.

    Args:
        handles: Session handles to walk (already host/agent filtered by the caller).
        cutoff: If set, exclude records with timestamps before this datetime.
        until: If set, exclude records with timestamps after this datetime.

    Returns:
        Dict of ``{session_id: [InvocationEvent, ...]}`` with events sorted by timestamp.
    """
    events_by_session: dict[str, list[InvocationEvent]] = {}
    if not handles:
        return events_by_session

    all_events: list[InvocationEvent] = []

    for handle in handles:
        for event in iter_events(handle):
            record = event.payload
            tool_name = _extract_tool_name(record)
            if tool_name is None:
                continue

            ts = record.get("timestamp", "")
            sid = record.get("sessionId") or handle.session_id

            evt = InvocationEvent(tool_name=tool_name, timestamp=ts, session_id=sid)
            all_events.append(evt)

    # Apply wall-clock cutoff/until filters
    if cutoff is not None:
        all_events = [e for e in all_events if _parse_iso_timestamp(e.timestamp) >= cutoff]
    if until is not None:
        all_events = [e for e in all_events if _parse_iso_timestamp(e.timestamp) <= until]

    # Bucket by session and sort
    for evt in all_events:
        events_by_session.setdefault(evt.session_id, []).append(evt)

    for session_id in events_by_session:
        events_by_session[session_id].sort(key=lambda e: e.timestamp)

    return events_by_session


@dataclass
class _InvocationSignal:
    """Raw ll invocation signal extracted from a JSONL record.

    Shared by ``_extract_tool_name`` and ``_extract_eval_invocation`` — single
    source of truth for the three-signal detection logic.
    """

    tool_name: str  # matched skill/tool name, e.g. "scan-codebase" or "ll-issues"
    runner: str  # signal source: "queue-operation" | "user" | "bash"
    input_context: str  # raw matched text (full cmd for bash; user/queue text otherwise)


def _detect_ll_signal(record: dict) -> _InvocationSignal | None:
    """Extract the ll invocation signal from a JSONL record.

    Detects three signal types:
    (a) queue-operation enqueue with ``/ll:<name>`` → tool_name=name, runner=queue-operation
    (b) user records with ``<command-name>/ll:<name>`` → tool_name=name, runner=user
    (c) assistant Bash tool-use invoking ``ll-<tool>`` → tool_name=match, runner=bash

    ``input_context`` holds the raw matched text used by eval-export consumers.
    Returns ``None`` for records carrying no ll invocation signal.
    """
    record_type = record.get("type")

    # (a) queue-operation enqueue
    if record_type == "queue-operation" and record.get("operation") == "enqueue":
        content = record.get("content", "")
        if isinstance(content, str) and content.startswith("/ll:"):
            m = _QUEUE_SKILL_RE.match(content)
            if m:
                return _InvocationSignal(m.group(1), "queue-operation", content)

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
                return _InvocationSignal(name, "user", text)

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
                        return _InvocationSignal(m.group(1), "bash", cmd)

    return None


def _extract_tool_name(record: dict) -> str | None:
    """Extract the ll tool/skill name from a JSONL record."""
    sig = _detect_ll_signal(record)
    return sig.tool_name if sig else None


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


def _resolve_window(args: argparse.Namespace) -> tuple[datetime | None, datetime | None]:
    """Resolve --window-days/--since/--until into a UTC-aware (cutoff, until) pair.

    ``--since``/``--window-days`` are mutually exclusive (enforced by argparse);
    ``--until`` composes with either, so a closed date range works. Built as
    UTC-aware datetimes (not calendar dates) since every call site filters
    against ``_parse_iso_timestamp()`` results, which are UTC-aware.
    """
    since = getattr(args, "since", None)
    until_raw = getattr(args, "until", None)
    window_days = getattr(args, "window_days", None)

    if since is not None:
        cutoff = datetime.combine(date.fromisoformat(since), dt_time.min, tzinfo=UTC)
    elif window_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=window_days)
    else:
        cutoff = None

    until = (
        datetime.combine(date.fromisoformat(until_raw), dt_time.max, tzinfo=UTC)
        if until_raw is not None
        else None
    )

    if cutoff is not None and until is not None and cutoff > until:
        print("error: --since is later than --until", file=sys.stderr)
        sys.exit(2)

    return cutoff, until


@dataclass
class Edge:
    """A transition edge within an n-gram chain."""

    from_: str
    to: str
    freq: float
    pmi: float | None = None
    lift: float | None = None


@dataclass
class ChainResult:
    """An n-gram chain with occurrence count and per-edge transition frequencies."""

    chain: list[str]
    count: int
    edges: list[Edge]
    pmi: float | None = None
    lift: float | None = None

    def to_dict(self) -> dict:
        edges_out = []
        for e in self.edges:
            ed: dict = {"from": e.from_, "to": e.to, "freq": e.freq}
            if e.pmi is not None:
                ed["pmi"] = e.pmi
            if e.lift is not None:
                ed["lift"] = e.lift
            edges_out.append(ed)
        result: dict = {"chain": self.chain, "count": self.count, "edges": edges_out}
        if self.pmi is not None:
            result["pmi"] = self.pmi
        if self.lift is not None:
            result["lift"] = self.lift
        return result


def _count_ngrams(
    events_by_session: dict[str, list[InvocationEvent]],
    min_len: int = 2,
) -> tuple[Counter, Counter]:
    """Count n-grams and unigrams across per-session event streams.

    Args:
        events_by_session: Per-session ordered event streams.
        min_len: Minimum n-gram length (window size).

    Returns:
        Tuple of (ngram_counter, unigram_counter).
        ngram_counter maps ``(tool_1, tool_2, ...)`` tuples to occurrence counts.
        unigram_counter maps individual tool names to occurrence counts.
    """
    counter: Counter = Counter()
    unigram_counter: Counter = Counter()
    for events in events_by_session.values():
        names = [e.tool_name for e in events]
        for name in names:
            unigram_counter[name] += 1
        for n in range(min_len, len(names) + 1):
            for i in range(len(names) - n + 1):
                ngram = tuple(names[i : i + n])
                counter[ngram] += 1
    return counter, unigram_counter


def _build_chain_results(
    counter: Counter,
    unigram_counter: Counter | None = None,
    min_count: int = 1,
    top: int | None = None,
) -> list[ChainResult]:
    """Build ranked ``ChainResult`` list from n-gram counter.

    Args:
        counter: n-gram counter from ``_count_ngrams``.
        unigram_counter: Unigram counter from ``_count_ngrams``. When provided,
            PMI and lift scores are attached to each edge and chain result.
        min_count: Minimum occurrence count to include.
        top: If set, limit to top N chains by frequency.

    Returns:
        List of ``ChainResult`` sorted by count descending.
    """
    all_transitions: Counter = Counter()
    out_degree: Counter = Counter()
    for ngram_key, count in counter.items():
        for i in range(len(ngram_key) - 1):
            pair = (ngram_key[i], ngram_key[i + 1])
            all_transitions[pair] += count
            out_degree[ngram_key[i]] += count

    total_unigrams = sum(unigram_counter.values()) if unigram_counter else 0

    results: list[ChainResult] = []
    for ngram, count in counter.most_common():
        if count < min_count:
            continue
        edges = _compute_edges(
            ngram, all_transitions, out_degree, unigram_counter, total_unigrams, counter
        )

        chain_pmi: float | None = None
        chain_lift: float | None = None
        if edges and all(e.lift is not None for e in edges):
            chain_lift = min(e.lift for e in edges if e.lift is not None)  # type: ignore[type-var]
            chain_pmi = min(e.pmi for e in edges if e.pmi is not None)  # type: ignore[type-var]

        results.append(
            ChainResult(chain=list(ngram), count=count, edges=edges, pmi=chain_pmi, lift=chain_lift)
        )

    if top is not None:
        results = results[:top]

    return results


def _compute_edges(
    ngram: tuple[str, ...],
    all_transitions: Counter,
    out_degree: Counter,
    unigram_counter: Counter | None = None,
    total_unigrams: int = 0,
    ngram_counter: Counter | None = None,
) -> list[Edge]:
    """Compute per-edge transition frequencies and PMI/lift for an n-gram chain.

    For each adjacent pair ``(from, to)`` in the chain, computes the frequency
    as the proportion of times ``from → to`` appears out of all transitions
    originating from ``from`` across the entire corpus.  When ``unigram_counter``
    and ``ngram_counter`` are provided, also computes PMI and lift for each edge
    using the raw bigram count from ``ngram_counter`` (not the overcounted
    ``all_transitions`` which accumulates across all n-gram lengths).
    """
    edges: list[Edge] = []
    for i in range(len(ngram) - 1):
        from_ = ngram[i]
        to = ngram[i + 1]
        pair = (from_, to)
        total_out = out_degree.get(from_, 0)
        freq = all_transitions.get(pair, 0) / total_out if total_out > 0 else 0.0

        edge_pmi: float | None = None
        edge_lift: float | None = None
        if unigram_counter and total_unigrams > 0 and ngram_counter is not None:
            # Use the raw bigram count (not all_transitions which overcounts from longer n-grams)
            count_ab = ngram_counter.get(pair, 0)
            count_a = unigram_counter.get(from_, 0)
            count_b = unigram_counter.get(to, 0)
            if count_ab > 0 and count_a > 0 and count_b > 0:
                edge_lift = round(compute_lift(count_ab, count_a, count_b, total_unigrams), 4)
                edge_pmi = round(compute_pmi(count_ab, count_a, count_b, total_unigrams), 4)

        edges.append(Edge(from_=from_, to=to, freq=round(freq, 4), pmi=edge_pmi, lift=edge_lift))

    return edges


def _detect_project_handles(
    cwd_path: Path, host: str | None, logger: Logger
) -> list[SessionHandle] | None:
    """Detect non-agent session handles for a single ``--project`` target.

    Detects with ``include_agents=True`` first so "the project has sessions,
    but only agent-* ones" (empty non-agent result, existing behavior) is
    distinguished from "no sessions at all for this cwd" (error, exit 1) —
    detecting straight to ``include_agents=False`` would conflate the two.
    Returns ``None`` (having already logged the error) for the latter case.
    """
    all_handles = detect_sessions(cwd_path, host, include_agents=True)
    if not all_handles:
        _cause, reason = explain_no_sessions(cwd_path, host=host, include_agents=True)
        print(f"No sessions found for: {cwd_path}", file=sys.stderr)
        print(reason, file=sys.stderr)
        print("Or pass --project to point at the correct workspace.", file=sys.stderr)
        return None
    return [h for h in all_handles if not h.is_agent]


def _collect_sequences(
    args: argparse.Namespace,
    logger: Logger,
    *,
    handles: list[SessionHandle],
) -> list[ChainResult]:
    """Extract ranked n-gram chains of ll invocations from session handles.

    Extracted from ``_cmd_sequences`` (Decisions #7): event extraction +
    ``_count_ngrams`` + ``_build_chain_results``; printing stays in
    ``_cmd_sequences``. Discovery happens once in the caller and is passed in
    via *handles* (ENH-3430) — this function never re-detects sessions.
    """
    cutoff, until = _resolve_window(args)
    all_events = _extract_ll_event_streams(handles, cutoff=cutoff, until=until)

    # Count n-grams
    counter, unigram_counter = _count_ngrams(all_events, min_len=args.min_len)
    return _build_chain_results(counter, unigram_counter, min_count=args.min_count, top=args.top)


def _cmd_sequences(args: argparse.Namespace, logger: Logger) -> int:
    """Extract n-grams of ll invocations from session logs."""
    host = _resolve_host(getattr(args, "host", None))
    if args.project:
        handles = _detect_project_handles(args.project, host, logger)
        if handles is None:
            return 1
    else:
        handles = [h for hs in _discover_workspace_handles(logger, host=host).values() for h in hs]

    results = _collect_sequences(args, logger, handles=handles)

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
    """Extract ll-relevant records to logs/<slug>/<session-id>.jsonl."""
    host = _resolve_host(getattr(args, "host", None))
    if args.project:
        cwd_path: Path = args.project
        handles = _detect_project_handles(cwd_path, host, logger)
        if handles is None:
            return 1
    else:
        handles = [h for hs in _discover_workspace_handles(logger, host=host).values() for h in hs]

    by_cwd: dict[Path, list[SessionHandle]] = defaultdict(list)
    for h in handles:
        by_cwd[h.cwd].append(h)

    rows: list[dict] = []
    skipped: list[str] = []
    matched_before_filter = 0

    for cwd_path, cwd_handles in by_cwd.items():
        slug = cwd_path.resolve().name
        buckets: dict[str, list[dict]] = {}

        for handle in cwd_handles:
            # iter_events() swallows an unreadable file silently (no
            # exception, no yield); probe openability directly first so an
            # unreadable session is still reported in `skipped` (BUG-2489-
            # adjacent contract test_extract_unreadable_file_reported locks).
            try:
                with open(handle.path, encoding="utf-8"):
                    pass
            except OSError:
                skipped.append(str(handle.path))
                continue
            for event in iter_events(handle):
                record = event.payload
                if _is_ll_relevant(record):
                    session_id = record.get("sessionId") or handle.session_id
                    buckets.setdefault(session_id, []).append(record)

        matched_before_filter += sum(len(records) for records in buckets.values())

        if args.cmd:
            filtered: dict[str, list[dict]] = {}
            for session_id, records in buckets.items():
                matching = [r for r in records if _cmd_matches(r, args.cmd)]
                if matching:
                    filtered[session_id] = matching
            buckets = filtered

        if not buckets:
            continue

        out_base = Path.cwd() / "logs" / slug
        for session_id, records in buckets.items():
            out_file = out_base / f"{session_id}.jsonl"
            out_file.parent.mkdir(parents=True, exist_ok=True)
            with open(out_file, "w", encoding="utf-8") as f:
                for record in records:
                    f.write(json.dumps(record) + "\n")

        rows.append(
            {
                "project": str(cwd_path),
                "slug": slug,
                "out_dir": str(out_base),
                "sessions": len(buckets),
                "records": sum(len(records) for records in buckets.values()),
            }
        )

    generate_index(Path.cwd() / "logs")

    total_sessions = sum(row["sessions"] for row in rows)
    total_records = sum(row["records"] for row in rows)
    zero_match = bool(args.cmd) and matched_before_filter > 0 and total_records == 0

    if args.json:
        print_json(
            {
                "projects": rows,
                "totals": {
                    "projects": len(rows),
                    "sessions": total_sessions,
                    "records": total_records,
                },
                "skipped": skipped,
                "cmd_filter": args.cmd,
                "zero_match": zero_match,
            }
        )
        return 0

    if zero_match:
        print(f"No records matched --cmd {args.cmd!r}")
    elif not rows:
        print("No ll-relevant records found; nothing extracted.")
    else:
        for row in rows:
            print(
                f"{row['slug']:<15} {row['sessions']:>3,} sessions, "
                f"{row['records']:>6,} records -> {row['out_dir']}/"
            )
        summary = (
            f"{len(rows)} project{'s' if len(rows) != 1 else ''}, "
            f"{total_sessions} session{'s' if total_sessions != 1 else ''}, "
            f"{total_records:,} record{'s' if total_records != 1 else ''} written"
        )
        if skipped:
            summary += (
                f"; {len(skipped)} file{'s' if len(skipped) != 1 else ''} unreadable (skipped)"
            )
        print(summary)

    if skipped and (zero_match or not rows):
        print(f"{len(skipped)} file{'s' if len(skipped) != 1 else ''} unreadable (skipped)")

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
    until: datetime | None = None,
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
        if until is not None:
            skill_rows = [r for r in skill_rows if _parse_iso_timestamp(r["ts"] or "") <= until]

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
        host = _resolve_host(getattr(args, "host", None))
        decoded_paths = discover_all_projects(logger, host=host)
        db_paths = [p / ".ll" / "history.db" for p in decoded_paths]
        catalog_root = Path.cwd()

    cutoff, until = _resolve_window(args)

    merged: dict[str, int] = defaultdict(int)
    for db_path in db_paths:
        result = _aggregate_skill_stats(db_path, cutoff=cutoff, until=until)
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
    sort_key = getattr(args, "sort", "tier")
    if sort_key == "name":
        ordered_names = sorted(catalog_names)
    else:
        ordered_names = sorted(
            catalog_names,
            key=lambda n: (0 if merged.get(n, 0) == 0 else 1, merged.get(n, 0), n),
        )

    rows = []
    for name in ordered_names:
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
class _LoopRunRecord:
    """Single archived loop run record, used by loop-fleet aggregation."""

    loop_name: str
    project_path: Path
    run_folder: str
    final_state: str
    iterations: int
    outcome: (
        str  # converged / failed / error / max-steps / stalled / interrupted / signal / no_route
    )
    ts: str
    attribution: str  # builtin / custom / shadowed (Decisions #10)


@dataclass
class _LoopFleetAggregate:
    """Per-loop-name aggregate over a list of ``_LoopRunRecord`` (FEAT-2379).

    Produced by ``_aggregate_fleet_runs()``; consumed by the ``loop-fleet``
    table branch (which shortens ``projects`` to ``.name`` for display), the
    ``_flag_loops`` flagging rule, and the fleet-review JSON sidecar.
    """

    loop_name: str
    attribution: str
    runs: int
    converged: int
    success_pct: int
    median_iterations: float
    top_outcome: str
    outcomes: dict[str, int]  # full outcome Counter, not just the top one
    projects: list[Path]  # absolute paths, deduplicated, sorted
    runs_by_project: dict[str, int]  # str(abs path) -> run count


def _aggregate_fleet_runs(runs: list[_LoopRunRecord]) -> list[_LoopFleetAggregate]:
    """Aggregate loop runs into per-``(loop_name, attribution)`` fleet aggregates.

    Extracted from the human-table branch of ``_cmd_loop_fleet`` (Decisions
    #7). Grouping by ``(loop_name, attribution)`` rather than ``loop_name``
    alone means a built-in loop that also runs as a shadowed copy elsewhere
    (Decisions #10) yields two aggregates instead of one row with an
    arbitrary attribution and a merged ``success_pct``. ``top_outcome`` uses a
    deterministic tie-break (count descending, then outcome name ascending) —
    NOT ``Counter.most_common(1)``, whose tie-break depends on insertion
    order (itself dependent on filesystem ``iterdir()`` order).
    """
    import statistics as _statistics

    by_key: dict[tuple[str, str], list[_LoopRunRecord]] = defaultdict(list)
    for r in runs:
        by_key[(r.loop_name, r.attribution)].append(r)

    aggregates: list[_LoopFleetAggregate] = []
    for (loop_name, attribution), group in by_key.items():
        total = len(group)
        converged = sum(1 for r in group if r.outcome == "converged")
        success_pct = int(round(converged / total * 100)) if total else 0
        iterations = [r.iterations for r in group]
        med_iter = _statistics.median(iterations) if iterations else 0.0
        outcome_counts = Counter(r.outcome for r in group)
        top_outcome = sorted(outcome_counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        runs_by_project: dict[str, int] = defaultdict(int)
        for r in group:
            runs_by_project[str(r.project_path)] += 1
        projects = sorted({r.project_path for r in group}, key=str)
        aggregates.append(
            _LoopFleetAggregate(
                loop_name=loop_name,
                attribution=attribution,
                runs=total,
                converged=converged,
                success_pct=success_pct,
                median_iterations=med_iter,
                top_outcome=top_outcome,
                outcomes=dict(outcome_counts),
                projects=projects,
                runs_by_project=dict(runs_by_project),
            )
        )

    aggregates.sort(key=lambda a: (a.loop_name, a.attribution))
    return aggregates


_FLAG_OUTCOMES: frozenset[str] = frozenset({"error", "max-steps", "stalled", "failed", "no_route"})


def is_flagged(
    runs: int, success_pct: int, top_outcome: str, *, threshold: int, min_runs: int
) -> bool:
    """The fleet-review flagging rule on one loop's aggregate numbers.

    Flag iff ``runs >= min_runs`` AND (``success_pct < threshold`` OR
    ``top_outcome in _FLAG_OUTCOMES``). ``interrupted``/``signal`` are
    deliberately excluded from ``_FLAG_OUTCOMES`` (operator/infra exits, not
    loop-logic failures) but still count against ``success_pct`` since that
    is simply ``converged / runs`` (Decisions #2). ``no_route`` is included
    (ENH-3471/ENH-3482): a missing route declaration is a loop-authoring
    failure, not an operator/infra exit.

    Attribution is NOT checked here: callers that hold in-memory aggregates
    (``_flag_loops``) filter to ``builtin`` themselves, and the JSON sidecar's
    ``loops`` dict is already builtin-only. Public so the
    ``fleet-loop-improve`` meta-loop (``little_loops.fleet_improve``) applies
    the identical rule to a sidecar instead of re-deriving it.
    """
    if runs < min_runs:
        return False
    return success_pct < threshold or top_outcome in _FLAG_OUTCOMES


def _flag_loops(
    aggs: list[_LoopFleetAggregate], *, threshold: int, min_runs: int
) -> list[_LoopFleetAggregate]:
    """Return the ``builtin``-attribution aggregates that fail ``is_flagged``."""
    return [
        a
        for a in aggs
        if a.attribution == "builtin"
        and is_flagged(a.runs, a.success_pct, a.top_outcome, threshold=threshold, min_runs=min_runs)
    ]


@dataclass
class _FailureCluster:
    """Aggregated failure cluster keyed on (cwd_path, tool_name, normalized_sig)."""

    tool_name: str
    normalized_sig: str
    count: int
    sample_error: str
    session_ids: list[str]
    cwd_path: Path = field(default_factory=lambda: Path("."))
    skill_counts: dict[str | None, int] = field(default_factory=dict)
    skill_sessions: dict[str | None, list[str]] = field(default_factory=dict)


@dataclass
class _RawCluster:
    """Mutable accumulator for a (cwd_path, tool_name, normalized_sig) key while streaming."""

    count: int
    sample_error: str
    session_ids: list[str]
    latest_ts: str
    skill_counts: dict[str | None, int] = field(default_factory=dict)
    skill_sessions: dict[str | None, list[str]] = field(default_factory=dict)


def _collect_failure_clusters(
    args: argparse.Namespace,
    logger: Logger,
    *,
    handles: list[SessionHandle],
) -> list[_FailureCluster]:
    """Mine and cluster failed ll-* Bash calls from session handles.

    Extracted from ``_cmd_scan_failures`` (Decisions #7): everything through
    the skill-filter/limit steps. ``--capture`` and printing stay in the
    caller. Discovery happens once in the caller and is passed in via
    *handles* (ENH-3430) — this function never re-detects sessions.
    """
    from little_loops.issue_lifecycle import FailureType, classify_failure

    _cli_allowlist = _load_cli_allowlist(Path.cwd())

    # raw_clusters maps (cwd_path, tool_name, normalized_sig) -> _RawCluster
    raw_clusters: dict[tuple[Path, str, str], _RawCluster] = {}

    for handle in handles:
        _cwd_path = handle.cwd
        # pending maps tool_use_id -> (ll_tool_name, timestamp, enclosing_skill)
        pending: dict[str, tuple[str, str, str | None]] = {}
        # current_skill tracks the enclosing skill as records stream by (reset per handle)
        current_skill: str | None = None

        for event in iter_events(handle):
            record = event.payload
            record_type = record.get("type")
            ts = record.get("timestamp", "")
            session_id = record.get("sessionId") or handle.session_id

            if record_type == "assistant":
                message = record.get("message", {})
                content = message.get("content", [])
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use":
                        continue
                    if block.get("name") == "Skill":
                        skill_input = block.get("input", {}).get("skill", "")
                        if skill_input:
                            current_skill = skill_input.removeprefix("ll:")
                        continue
                    if block.get("name") != "Bash":
                        continue
                    cmd = block.get("input", {}).get("command", "")
                    m = _LL_BASH_RE.search(cmd)
                    if not m:
                        continue
                    tool_name = m.group(1)
                    # Skip tokens that are not real ll CLIs (e.g. sample-a, sample-b)
                    if _cli_allowlist and tool_name not in _cli_allowlist:
                        continue
                    block_id = block.get("id", "")
                    if block_id:
                        pending[block_id] = (tool_name, ts, current_skill)

            elif record_type == "user":
                message = record.get("message", {})
                content = message.get("content", [])
                if isinstance(content, str):
                    # Real user turn (not a tool_result carrier): re-derive
                    # current_skill from a <command-name> marker, resetting
                    # to None on no match (e.g. /clear, /model).
                    m2 = _COMMAND_NAME_SKILL_RE.search(content)
                    if m2:
                        name = m2.group(1)
                        if name.endswith("</command-name>"):
                            name = name[: -len("</command-name>")]
                        current_skill = name
                    else:
                        current_skill = None
                    continue
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
                    tool_name, _invoke_ts, skill = pending.pop(tool_use_id)

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
                    if failure_type in (
                        FailureType.TRANSIENT,
                        FailureType.NON_RECOVERABLE,
                        FailureType.INFRA_RETRY,
                    ):
                        continue

                    normalized_sig = _normalize_error_sig(error_text)
                    key = (_cwd_path, tool_name, normalized_sig)

                    if key in raw_clusters:
                        rc = raw_clusters[key]
                        if session_id not in rc.session_ids:
                            rc.session_ids.append(session_id)
                        rc.count += 1
                        rc.latest_ts = ts
                    else:
                        rc = _RawCluster(
                            count=1,
                            sample_error=error_text[:500],
                            session_ids=[session_id],
                            latest_ts=ts,
                        )
                        raw_clusters[key] = rc

                    rc.skill_counts[skill] = rc.skill_counts.get(skill, 0) + 1
                    skill_sids = rc.skill_sessions.setdefault(skill, [])
                    if session_id not in skill_sids:
                        skill_sids.append(session_id)

    # Apply wall-clock cutoff/until filters
    cutoff, until = _resolve_window(args)
    if cutoff is not None:
        raw_clusters = {
            k: v for k, v in raw_clusters.items() if _parse_iso_timestamp(v.latest_ts) >= cutoff
        }
    if until is not None:
        raw_clusters = {
            k: v for k, v in raw_clusters.items() if _parse_iso_timestamp(v.latest_ts) <= until
        }

    # Drop content-free clusters (bare "Exit code N" with no error body)
    raw_clusters = {
        k: v for k, v in raw_clusters.items() if not _is_content_free_error(v.sample_error)
    }

    clusters: list[_FailureCluster] = [
        _FailureCluster(
            tool_name=k[1],
            normalized_sig=k[2],
            count=v.count,
            sample_error=v.sample_error,
            session_ids=v.session_ids,
            cwd_path=k[0],
            skill_counts=v.skill_counts,
            skill_sessions=v.skill_sessions,
        )
        for k, v in raw_clusters.items()
    ]

    skill_filter = getattr(args, "skill", None)
    if skill_filter:
        normalized_filter = skill_filter.removeprefix("ll:")
        reprojected: list[_FailureCluster] = []
        for c in clusters:
            if normalized_filter not in c.skill_counts:
                continue
            c.count = c.skill_counts[normalized_filter]
            c.session_ids = c.skill_sessions.get(normalized_filter, [])
            reprojected.append(c)
        clusters = reprojected

    clusters.sort(key=lambda c: c.count, reverse=True)

    limit = getattr(args, "limit", 0) or 0
    if limit:
        clusters = clusters[:limit]

    return clusters


def _cmd_scan_failures(args: argparse.Namespace, logger: Logger) -> int:
    """Mine failed ll-* Bash calls from interactive session logs."""
    host = _resolve_host(getattr(args, "host", None))
    if args.project:
        handles = _detect_project_handles(args.project, host, logger)
        if handles is None:
            return 1
    else:
        handles = [h for hs in _discover_workspace_handles(logger, host=host).values() for h in hs]

    clusters = _collect_failure_clusters(args, logger, handles=handles)

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
                    "skills": sorted(s for s in c.skill_counts if s is not None),
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
        db_paths = [args.project / ".ll" / "history.db"]
    else:
        host = _resolve_host(getattr(args, "host", None))
        decoded_paths = discover_all_projects(logger, host=host)
        db_paths = [p / ".ll" / "history.db" for p in decoded_paths]

    cutoff, until = _resolve_window(args)

    merged: dict[str, dict[str, int]] = defaultdict(lambda: {"invocations": 0, "corrections": 0})
    found_any_db = False
    for db_path in db_paths:
        result = _aggregate_skill_stats(db_path, cutoff=cutoff, until=until)
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
            }
            for skill, counts in ranked
        ]
        print_json(rows_json)
        return 0

    headers = ["Skill", "Invocations", "Corrections", "Corr%"]
    rows = []
    for skill, counts in ranked:
        inv = counts["invocations"]
        corr = counts["corrections"]
        corr_pct = f"{corr / inv * 100:.1f}%" if inv > 0 else "0.0%"
        rows.append([skill, str(inv), str(corr), corr_pct])

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

    Delegates signal detection to ``_detect_ll_signal`` and wraps the result
    in an ``_EvalInvocation`` with ``session_id`` and ``timestamp`` from the
    record.  Runner mapping: queue-operation/user → "skill"; bash → "cmd"
    (target becomes the full command; input_context is "").

    Returns None for records that carry no ll invocation signal.
    """
    sig = _detect_ll_signal(record)
    if sig is None:
        return None
    sid = record.get("sessionId", "")
    ts = record.get("timestamp", "")
    if sig.runner == "bash":
        return _EvalInvocation("cmd", sig.input_context, sid, ts, "")
    return _EvalInvocation("skill", sig.tool_name, sid, ts, sig.input_context)


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
        # ENH-3415: no session-log signal for --samples exists today (this
        # fixture format never captured exit_code/semantic/timeout from the
        # log either), so this is always None on export; carried through so
        # a fixture that does set it round-trips instead of silently
        # dropping the flag on replay.
        "samples": None,
        # ENH-3462: no session-log signal exists for any of these either
        # (same rationale as `samples` above) -- always None/[] on export,
        # carried through so a fixture that does set them round-trips.
        "evidence": None,
        "require_artifact": None,
        "forbid_path": None,
        "expect_no_git_changes": None,
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
    if fixture.get("samples") is not None:
        argv.extend(["--samples", str(fixture["samples"])])
    for evidence_channel in fixture.get("evidence") or []:
        argv.extend(["--evidence", str(evidence_channel)])
    for path in fixture.get("require_artifact") or []:
        argv.extend(["--require-artifact", str(path)])
    for path in fixture.get("forbid_path") or []:
        argv.extend(["--forbid-path", str(path)])
    if fixture.get("expect_no_git_changes"):
        argv.append("--expect-no-git-changes")
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
    host = _resolve_host(getattr(args, "host", None))
    all_handles = detect_sessions(cwd_path, host, include_agents=True)
    if not all_handles:
        _cause, reason = explain_no_sessions(cwd_path, host=host, include_agents=True)
        print(f"No sessions found for: {cwd_path}", file=sys.stderr)
        print(reason, file=sys.stderr)
        return 1
    handles = [h for h in all_handles if not h.is_agent]
    db_path = resolve_history_db(cwd_path / ".ll" / "history.db")

    # Single pass over every handle's events: collect raw invocations +
    # per-session error flags together (avoids the double-parse the decision
    # warns against).
    invocations: list[_EvalInvocation] = []
    session_has_error: dict[str, bool] = {}
    for handle in handles:
        for event in iter_events(handle):
            record = event.payload
            sid = record.get("sessionId") or handle.session_id
            if _record_has_error(record):
                if sid:
                    session_has_error[sid] = True
            inv = _extract_eval_invocation(record)
            if inv is not None:
                if not inv.session_id:
                    inv = _EvalInvocation(
                        inv.runner, inv.target, sid, inv.timestamp, inv.input_context
                    )
                invocations.append(inv)

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


def _builtin_loop_paths() -> dict[str, Path]:
    """Return {stem: path} for every runnable built-in loop, recursively (Decisions #8).

    Rooted at ``get_builtin_loops_dir()`` (not a private ``logs.py``-local
    constant) so nested ``oracles/*`` built-ins resolve — ``resolve_loop_path``
    only checks the top level and must NOT be used for this. ``lib/`` fragments
    are excluded (not standalone runnable loops).
    """
    base = get_builtin_loops_dir()
    if not base.exists():
        return {}
    paths: dict[str, Path] = {}
    for yaml_file in sorted(base.rglob("*.yaml")):
        if "lib" in yaml_file.relative_to(base).parts:
            continue
        paths[yaml_file.stem] = yaml_file
    return paths


def _get_builtin_loop_names() -> frozenset[str]:
    """Return stem names of all runnable built-in loops in the package (excludes lib/ fragments)."""
    return frozenset(_builtin_loop_paths())


def _derive_loop_outcome(event: dict) -> str:
    """Derive an outcome category from a loop_complete event dict."""
    if event.get("terminated_by") == "no_route":
        # ENH-3482: decision-step failure (no valid transition, before_route
        # veto, evaluator/route raise) is a loop-authoring bug, not a runtime
        # crash. Must be checked before the `"error" in event` fallback below
        # since _finish() always passes error= for this abort too.
        return "no_route"
    if "error" in event:
        return "error"
    terminated_by = event.get("terminated_by", "")
    if terminated_by in ("max_steps", "max_iterations_reached"):
        return "max-steps"
    if terminated_by == "cycle_detected":
        return "stalled"
    if terminated_by in ("interrupted", "handoff", "timeout", "user_stopped"):
        # ENH-2522: user_stopped is a clean interrupt (cleaner than interrupted;
        # bucket with the other "non-failure" interruption causes).
        return "interrupted"
    if terminated_by == "system_signal":
        # ENH-2522: kernel/SIGKILL/OOM is its own signal bucket.
        return "signal"
    if terminated_by == "workdir_vanished":
        # BUG-3375: belt-and-suspenders — the `"error" in event` branch above
        # already catches this since _finish always passes error= for this
        # abort. An infra loss is not a loop-logic failure and must not
        # inflate the "failed" bucket in fleet rollups.
        return "error"
    final_state = event.get("final_state", "")
    if any(kw in final_state for kw in ("fail", "error", "abort")):
        return "failed"
    return "converged"


def _parse_terminal_event(events_file: Path) -> dict | None:
    """Read events.jsonl and return the loop_complete event, or None if absent."""
    try:
        with open(events_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if record.get("event") == "loop_complete":
                        return record
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return None


def _in_window(ts: str, cutoff: datetime | None, until: datetime | None) -> bool:
    """Return True if *ts* falls within [cutoff, until] (FEAT-2379).

    Mirrors the exact inline guard ``_collect_loop_runs`` has always applied:
    an **empty** ``ts`` string passes any window (preserved quirk, not a bug
    fix). Shared by ``_collect_loop_runs`` and ``fleet-review``'s in-memory
    window filter so the two definitions cannot drift (Program Design).
    """
    if not ts:
        return True
    if cutoff is not None and _parse_iso_timestamp(ts) < cutoff:
        return False
    if until is not None and _parse_iso_timestamp(ts) > until:
        return False
    return True


def _collect_loop_runs(
    project_path: Path,
    builtin_names: frozenset[str],
    *,
    loop_filter: str | None = None,
    cutoff: datetime | None = None,
    until: datetime | None = None,
) -> list[_LoopRunRecord]:
    """Collect archived loop runs from a project's .loops/.history/ directory.

    Attribution is ``"builtin"`` when *loop_name* is in *builtin_names*,
    ``"custom"`` otherwise, EXCEPT: when the project carries its own
    ``.loops/<loop_name>.yaml`` or ``.loops/<loop_name>.fsm.yaml`` copy of a
    built-in name, attribution is ``"shadowed"`` instead — that project's runs
    executed its own modified copy, not this repo's built-in (Decisions #10).
    The shadow-stem set is built once per project (a handful of ``exists()``
    calls over ``builtin_names``), before the ``iterdir()`` loop, not per run.
    """
    history_dir = project_path / ".loops" / ".history"
    if not history_dir.exists():
        return []

    local_loops_dir = project_path / ".loops"
    shadow_stems: set[str] = set()
    if local_loops_dir.is_dir():
        for name in builtin_names:
            if (local_loops_dir / f"{name}.yaml").exists() or (
                local_loops_dir / f"{name}.fsm.yaml"
            ).exists():
                shadow_stems.add(name)

    def _attribution_for(loop_name: str) -> str:
        if loop_name in shadow_stems:
            return "shadowed"
        return "builtin" if loop_name in builtin_names else "custom"

    records: list[_LoopRunRecord] = []
    visited: set[Path] = set()

    for run_dir in history_dir.iterdir():
        if not run_dir.is_dir():
            continue

        m = _HISTORY_RUN_RE.match(run_dir.name)
        if m:
            # Flat layout: <run_id>-<loop_name>/events.jsonl
            loop_name = m.group(2)
            events_file = run_dir / "events.jsonl"
            if not events_file.exists():
                continue
            visited.add(run_dir)
            if loop_filter and loop_name != loop_filter:
                continue
            terminal = _parse_terminal_event(events_file)
            if terminal is None:
                continue
            ts = terminal.get("ts", "")
            if not _in_window(ts, cutoff, until):
                continue
            records.append(
                _LoopRunRecord(
                    loop_name=loop_name,
                    project_path=project_path,
                    run_folder=run_dir.name,
                    final_state=terminal.get("final_state", "unknown"),
                    iterations=terminal.get("iterations", 0),
                    outcome=_derive_loop_outcome(terminal),
                    ts=ts,
                    attribution=_attribution_for(loop_name),
                )
            )
        else:
            # Legacy nested layout: <loop_name>/<run_id>/events.jsonl
            loop_name = run_dir.name
            if loop_filter and loop_name != loop_filter:
                continue
            if run_dir in visited:
                continue
            for run_subdir in run_dir.iterdir():
                if not run_subdir.is_dir():
                    continue
                events_file = run_subdir / "events.jsonl"
                if not events_file.exists():
                    continue
                terminal = _parse_terminal_event(events_file)
                if terminal is None:
                    continue
                ts = terminal.get("ts", "")
                if not _in_window(ts, cutoff, until):
                    continue
                records.append(
                    _LoopRunRecord(
                        loop_name=loop_name,
                        project_path=project_path,
                        run_folder=f"{loop_name}/{run_subdir.name}",
                        final_state=terminal.get("final_state", "unknown"),
                        iterations=terminal.get("iterations", 0),
                        outcome=_derive_loop_outcome(terminal),
                        ts=ts,
                        attribution=_attribution_for(loop_name),
                    )
                )

    return records


def _cmd_loop_fleet(args: argparse.Namespace, logger: Logger) -> int:
    """Aggregate cross-project loop-run outcomes for built-in loop improvement."""
    builtin_names = _get_builtin_loop_names()
    cutoff, until = _resolve_window(args)
    loop_filter: str | None = getattr(args, "loop", None)

    if args.project:
        projects = [Path(args.project)]
    else:
        host = _resolve_host(getattr(args, "host", None))
        projects = discover_all_projects(logger, host=host, existing_only=args.existing_only)

    all_runs: list[_LoopRunRecord] = []
    for proj in projects:
        all_runs.extend(
            _collect_loop_runs(
                proj, builtin_names, loop_filter=loop_filter, cutoff=cutoff, until=until
            )
        )

    if not all_runs:
        if args.json:
            print_json([])
        else:
            print("No loop-fleet runs found.")
        return 0

    if args.json:
        limit = getattr(args, "limit", 0) or 0
        sorted_runs = sorted(all_runs, key=lambda r: r.ts, reverse=True)
        if limit:
            sorted_runs = sorted_runs[:limit]
        print_json(
            [
                {
                    "loop_name": r.loop_name,
                    "project": str(r.project_path),
                    "run_folder": r.run_folder,
                    "final_state": r.final_state,
                    "iterations": r.iterations,
                    "outcome": r.outcome,
                    "ts": r.ts,
                    "attribution": r.attribution,
                }
                for r in sorted_runs
            ]
        )
        return 0

    # Aggregate per (loop name, attribution) for the human-readable table
    # (Decisions #7: _aggregate_fleet_runs, not an inline loop-name-only groupby).
    aggs = _aggregate_fleet_runs(all_runs)

    sort_key = getattr(args, "sort", "success")
    if sort_key == "name":
        aggs.sort(key=lambda a: a.loop_name)
    else:
        aggs.sort(key=lambda a: (a.success_pct, a.loop_name))  # worst first, tie-break name

    rows = [
        [
            a.loop_name,
            a.attribution,
            str(a.runs),
            f"{a.success_pct}%",
            f"{a.median_iterations:.1f}",
            a.top_outcome,
            (
                ", ".join(sorted(p.name for p in a.projects)[:3])
                + ("…" if len(a.projects) > 3 else "")
            ),
        ]
        for a in aggs
    ]

    print(table(["Loop", "Type", "Runs", "Success%", "Med-Iter", "Top Outcome", "Projects"], rows))
    return 0


def _validate_builtin_loop(
    name: str, *, orchestration_request_path: str | None
) -> tuple[bool, list[ValidationError]]:
    """Validate a built-in loop by name via ``load_and_validate()`` (Decisions #8).

    Thin wrapper over ``_builtin_loop_paths()[name]`` +
    ``load_and_validate(path, raise_on_error=False, orchestration_request_path=...)``.
    Does NOT use ``resolve_loop_path`` (top-level only; misses nested
    ``oracles/*`` built-ins) or ``cmd_validate`` (prints instead of
    returning). An unknown name, ``ValueError``, ``yaml.YAMLError``, or
    ``OSError`` becomes a single synthetic error ``ValidationError``,
    mirroring ``cmd_validate``'s ``--json`` branch. ``valid`` is
    ``not any(v.severity is ValidationSeverity.ERROR for v in violations)``.
    """
    import yaml

    from little_loops.fsm.validation import ValidationError, ValidationSeverity, load_and_validate

    path = _builtin_loop_paths().get(name)
    if path is None:
        violations: list[ValidationError] = [
            ValidationError(
                message=f"Unknown built-in loop: {name}",
                path="<root>",
                severity=ValidationSeverity.ERROR,
            )
        ]
        return False, violations

    try:
        _fsm, violations = load_and_validate(
            path,
            raise_on_error=False,
            orchestration_request_path=orchestration_request_path,
        )
    except (ValueError, yaml.YAMLError, OSError) as e:
        violations = [
            ValidationError(
                message=str(e),
                path="<root>",
                severity=ValidationSeverity.ERROR,
            )
        ]
        return False, violations

    valid = not any(v.severity is ValidationSeverity.ERROR for v in violations)
    return valid, violations


def _build_fleet_sidecar(
    *,
    generated: datetime,
    window_days: int | None,
    since: datetime | None,
    until: datetime | None,
    projects: list[Path],
    excluded: list[Path],
    aggs: list[_LoopFleetAggregate],
    shadowed: dict[str, dict[str, int]],
) -> dict:
    """Build the fleet-review JSON sidecar dict (Decisions #4).

    ``loops`` holds only ``builtin``-attribution aggregates; ``shadowed`` is a
    separate informational dict. ``Path`` values are stringified.
    """
    loops: dict[str, dict] = {}
    for a in aggs:
        if a.attribution != "builtin":
            continue
        loops[a.loop_name] = {
            "runs": a.runs,
            "converged": a.converged,
            "success_pct": a.success_pct,
            "top_outcome": a.top_outcome,
            "outcomes": a.outcomes,
            "projects": [str(p) for p in a.projects],
            "runs_by_project": a.runs_by_project,
        }
    return {
        "generated": generated.isoformat(),
        "window_days": window_days,
        "since": since.isoformat() if since is not None else None,
        "until": until.isoformat() if until is not None else None,
        "projects_scanned": [str(p) for p in projects],
        "excluded_projects": [str(p) for p in excluded],
        "loops": loops,
        "shadowed": shadowed,
    }


def _load_prior_baseline(
    diagnostics_dir: Path, *, exclude: Path | None
) -> tuple[Path, dict] | None:
    """Return ``(path, data)`` for the lexically-newest prior sidecar, or None.

    Sidecars are named ``fleet-review-<YYYYMMDDTHHMMSSZ>.json`` — the UTC
    stamp format sorts correctly lexically. Always skips *exclude* (the
    sidecar this run is about to write), so a same-day second run baselines
    against the first, never itself (Decisions #4).
    """
    if not diagnostics_dir.exists():
        return None
    candidates = sorted(diagnostics_dir.glob("fleet-review-*.json"))
    if exclude is not None:
        exclude_resolved = exclude.resolve()
        candidates = [c for c in candidates if c.resolve() != exclude_resolved]
    if not candidates:
        return None
    newest = candidates[-1]
    try:
        data = json.loads(newest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return newest, data


def _write_baseline(
    path: Path,
    aggs: list[_LoopFleetAggregate],
    *,
    window_days: int | None,
    since: datetime | None,
    until: datetime | None,
    projects: list[Path],
    excluded: list[Path],
    shadowed: dict[str, dict[str, int]] | None = None,
) -> None:
    """Write the JSON sidecar baseline for this fleet-review run (Decisions #4)."""
    data = _build_fleet_sidecar(
        generated=datetime.now(UTC),
        window_days=window_days,
        since=since,
        until=until,
        projects=projects,
        excluded=excluded,
        aggs=aggs,
        shadowed=shadowed or {},
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a minimal GitHub-flavored-markdown pipe table."""
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def _comparability_warning(prior: dict, current: dict) -> str | None:
    """Return a warning string when prior/current sidecar run populations differ (Decisions #4).

    Covers ``window_days``/``since``/``until`` (the window) AND
    ``excluded_projects``/``projects_scanned`` (the run population) — a delta
    between an excluded and a non-excluded run is meaningless and must not
    render silently.
    """
    mismatched = [f for f in ("window_days", "since", "until") if prior.get(f) != current.get(f)]
    if sorted(prior.get("excluded_projects", [])) != sorted(current.get("excluded_projects", [])):
        mismatched.append("excluded_projects")
    if sorted(prior.get("projects_scanned", [])) != sorted(current.get("projects_scanned", [])):
        mismatched.append("projects_scanned")
    if not mismatched:
        return None
    return (
        f"prior baseline differs in: {', '.join(mismatched)} — the delta below may not "
        "be meaningful"
    )


def _render_fleet_review_report(
    *,
    generated: datetime,
    window_days: int | None,
    since: datetime | None,
    until: datetime | None,
    projects: list[Path],
    excluded: list[Path],
    aggs: list[_LoopFleetAggregate],
    flagged: list[_LoopFleetAggregate],
    validations: dict[str, tuple[bool, list[ValidationError]]],
    zero_run: list[str],
    shadowed: dict[str, dict[str, int]],
    clusters: list[_FailureCluster] | None,
    sequences: list[ChainResult] | None,
    appendix_top: int,
    no_appendices: bool,
    prior: tuple[Path, dict] | None,
    sidecar: dict,
) -> str:
    """Render the fleet-review markdown report (Program Design → Types → Report)."""
    lines: list[str] = [f"# Fleet loop review — {generated.strftime('%Y-%m-%d %H:%M:%S UTC')}", ""]

    # --- Summary ---
    lines.append("## Summary")
    lines.append("")
    if window_days is not None:
        lines.append(f"- Window: last {window_days} day(s)")
    elif since is not None or until is not None:
        since_str = since.isoformat() if since is not None else "(none)"
        until_str = until.isoformat() if until is not None else "(none)"
        lines.append(f"- Window: since {since_str} until {until_str}")
    else:
        lines.append("- Window: all-time")
    lines.append(f"- Projects scanned: {len(projects)} (excluded: {len(excluded)})")
    lines.append(f"- Builtin runs in window: {sum(a.runs for a in aggs)}")
    if prior is None:
        lines.append("- Prior baseline: none")
    else:
        prior_path, prior_data = prior
        lines.append(f"- Prior baseline: {prior_path}")
        warning = _comparability_warning(prior_data, sidecar)
        if warning:
            lines.append(f"- **Comparability warning**: {warning}")
    lines.append("")

    # --- Flagged loops ---
    lines.append("## Flagged loops")
    lines.append("")
    if not flagged:
        lines.append("No loops flagged.")
        lines.append("")
    else:
        headers = ["Loop", "Runs", "Success%", "Top Outcome", "Outcomes", "Runs by project"]
        rows = []
        for a in flagged:
            outcomes_str = ", ".join(f"{k}:{v}" for k, v in sorted(a.outcomes.items()))
            by_proj = ", ".join(f"{p}:{n}" for p, n in sorted(a.runs_by_project.items()))
            rows.append(
                [
                    a.loop_name,
                    str(a.runs),
                    f"{a.success_pct}%",
                    a.top_outcome,
                    outcomes_str,
                    by_proj,
                ]
            )
        lines.append(_md_table(headers, rows))
        lines.append("")
        for a in flagged:
            lines.append(f"### {a.loop_name}")
            lines.append("")
            valid, violations = validations.get(a.loop_name, (True, []))
            lines.append(f"Validation: {'valid' if valid else 'INVALID'}")
            for v in violations:
                lines.append(f"- [{v.severity.value.upper()}] {v.path}: {v.message}")
            for proj in sorted(a.projects, key=str):
                lines.append(f"- `cd {proj} && ll-loop diagnose-evaluators {a.loop_name}`")
            lines.append("")

    # --- Delta vs baseline ---
    lines.append("## Delta vs baseline")
    lines.append("")
    if prior is None:
        lines.append("no prior baseline")
        lines.append("")
    else:
        _prior_path, prior_data = prior
        prior_loops: dict = prior_data.get("loops", {})
        current_loops = {a.loop_name: a for a in aggs if a.attribution == "builtin"}
        all_names = sorted(set(prior_loops) | set(current_loops))
        outcome_keys = sorted(_FLAG_OUTCOMES)
        headers = ["Loop", "Success% (prior→now, Δ)", "Δruns", "Δconverged"] + [
            f"Δ{o}" for o in outcome_keys
        ]
        rows = []
        for name in all_names:
            cur = current_loops.get(name)
            prev = prior_loops.get(name)
            if prev is None:
                rows.append([name, "new"] + [""] * (len(headers) - 2))
                continue
            if cur is None:
                rows.append([name, "dropped out of window"] + [""] * (len(headers) - 2))
                continue

            def _signed(n: int) -> str:
                return f"+{n}" if n >= 0 else str(n)

            d_success = cur.success_pct - prev.get("success_pct", 0)
            d_runs = cur.runs - prev.get("runs", 0)
            d_converged = cur.converged - prev.get("converged", 0)
            prev_outcomes = prev.get("outcomes", {})
            row = [
                name,
                f"{prev.get('success_pct', 0)}% → {cur.success_pct}% ({_signed(d_success)})",
                _signed(d_runs),
                _signed(d_converged),
            ]
            for o in outcome_keys:
                row.append(_signed(cur.outcomes.get(o, 0) - prev_outcomes.get(o, 0)))
            rows.append(row)
        lines.append(_md_table(headers, rows))
        lines.append("")

    # --- Zero-run built-ins ---
    lines.append("## Zero-run built-ins")
    lines.append("")
    if not zero_run:
        lines.append("None.")
    else:
        for name in zero_run:
            lines.append(f"- {name}")
    lines.append("")

    # --- Shadowed built-ins ---
    lines.append("## Shadowed built-ins")
    lines.append("")
    if not shadowed:
        lines.append("None.")
    else:
        headers = ["Loop", "Project", "Runs"]
        rows = []
        for loop_name in sorted(shadowed):
            for shadow_project, count in sorted(shadowed[loop_name].items()):
                rows.append([loop_name, shadow_project, str(count)])
        lines.append(_md_table(headers, rows))
    lines.append("")

    # --- Appendices (skipped under --no-appendices) ---
    if not no_appendices:
        lines.append("## Appendix: scan-failures clusters")
        lines.append("")
        cluster_rows = clusters or []
        if appendix_top:
            cluster_rows = cluster_rows[:appendix_top]
        if not cluster_rows:
            lines.append("No failure clusters.")
        else:
            headers = ["Tool", "Count", "Project", "Signature"]
            rows = [
                [c.tool_name, str(c.count), str(c.cwd_path), c.normalized_sig] for c in cluster_rows
            ]
            lines.append(_md_table(headers, rows))
        lines.append("")

        lines.append("## Appendix: sequences")
        lines.append("")
        seq_rows = sequences or []
        if appendix_top:
            seq_rows = seq_rows[:appendix_top]
        if not seq_rows:
            lines.append("No sequences.")
        else:
            headers = ["Chain", "Count"]
            rows = [[" → ".join(r.chain), str(r.count)] for r in seq_rows]
            lines.append(_md_table(headers, rows))
        lines.append("")

    # --- Reviewed, not fixed (empty; filled by hand) ---
    lines.append("## Reviewed, not fixed")
    lines.append("")

    return "\n".join(lines) + "\n"


def _cmd_fleet_review(args: argparse.Namespace, logger: Logger) -> int:
    """Harvest fleet-wide built-in loop outcomes, flag unhealthy loops, and write a
    dated diagnostic report plus a JSON baseline sidecar (FEAT-2379).

    See the Call Path in the issue's Program Design section: discover projects
    minus ``--exclude-project`` -> unwindowed ``_collect_loop_runs`` per
    project -> zero-run derivation -> in-memory ``_in_window`` filter ->
    ``_aggregate_fleet_runs`` over ``builtin`` records (``shadowed`` tallied
    separately) -> ``_flag_loops`` -> ``_validate_builtin_loop`` per flagged
    loop -> appendix collectors (unless ``--no-appendices``) ->
    ``_load_prior_baseline`` -> render report + ``_write_baseline``.
    ``--json`` prints the sidecar and writes no files at all.
    """
    builtin_names = _get_builtin_loop_names()
    host = _resolve_host(getattr(args, "host", None))

    if args.project:
        # Absolute paths throughout (Decisions #4/#9): the sidecar and report's
        # `cd <project> && ...` lines must be copy-pasteable.
        discovered = [Path(args.project).resolve()]
        project_handles: dict[Path, list[SessionHandle]] = {
            discovered[0]: detect_sessions(discovered[0], host, include_agents=False)
        }
    else:
        # Reuse the same handles for the appendix collectors below instead of
        # a second discovery pass (discover_all_projects's own path-only
        # signature would force a re-detect that parses every session twice).
        project_handles = _discover_workspace_handles(
            logger, host=host, existing_only=args.existing_only
        )
        discovered = sorted(project_handles.keys())

    exclude_raw = getattr(args, "exclude_project", None) or []
    excluded_resolved = {Path(p).resolve() for p in exclude_raw}
    projects = [p for p in discovered if p.resolve() not in excluded_resolved]
    excluded = [p for p in discovered if p.resolve() in excluded_resolved]

    # Unwindowed harvest — zero-run derivation and shadow attribution both
    # need the full (unfiltered-by-window) picture (Decisions #2, #10).
    unwindowed_runs: list[_LoopRunRecord] = []
    for proj in projects:
        unwindowed_runs.extend(_collect_loop_runs(proj, builtin_names))

    cutoff, until = _resolve_window(args)
    windowed_runs = [r for r in unwindowed_runs if _in_window(r.ts, cutoff, until)]

    builtin_seen_unwindowed = {r.loop_name for r in unwindowed_runs if r.attribution == "builtin"}
    zero_run = sorted(builtin_names - builtin_seen_unwindowed)

    builtin_runs = [r for r in windowed_runs if r.attribution == "builtin"]
    shadowed_runs = [r for r in windowed_runs if r.attribution == "shadowed"]

    aggs = _aggregate_fleet_runs(builtin_runs)

    shadowed_tally: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in shadowed_runs:
        shadowed_tally[r.loop_name][str(r.project_path)] += 1
    shadowed_tally = {k: dict(v) for k, v in shadowed_tally.items()}

    window_days = getattr(args, "window_days", None)

    if args.json:
        sidecar = _build_fleet_sidecar(
            generated=datetime.now(UTC),
            window_days=window_days,
            since=cutoff,
            until=until,
            projects=projects,
            excluded=excluded,
            aggs=aggs,
            shadowed=shadowed_tally,
        )
        print_json(sidecar)
        return 0

    flagged = _flag_loops(aggs, threshold=args.threshold, min_runs=args.min_runs)

    orchestration_request_path = BRConfig(Path.cwd()).orchestration.request_path
    validations: dict[str, tuple[bool, list[ValidationError]]] = {}
    for a in flagged:
        validations[a.loop_name] = _validate_builtin_loop(
            a.loop_name, orchestration_request_path=orchestration_request_path
        )

    clusters: list[_FailureCluster] | None = None
    sequences_result: list[ChainResult] | None = None
    if not args.no_appendices:
        appendix_top_param = None if args.appendix_top == 0 else args.appendix_top
        appendix_ns = argparse.Namespace(
            project=None,
            window_days=window_days,
            since=getattr(args, "since", None),
            until=getattr(args, "until", None),
            skill=None,
            limit=args.appendix_top,
            min_len=2,
            min_count=1,
            top=appendix_top_param,
        )
        appendix_handles = [h for p in projects for h in project_handles.get(p, [])]
        clusters = _collect_failure_clusters(appendix_ns, logger, handles=appendix_handles)
        sequences_result = _collect_sequences(appendix_ns, logger, handles=appendix_handles)

    generated = datetime.now(UTC)
    stamp = generated.strftime("%Y%m%dT%H%M%SZ")
    diagnostics_dir = Path.cwd() / ".loops" / "diagnostics"
    md_path = diagnostics_dir / f"fleet-review-{stamp}.md"
    json_path = diagnostics_dir / f"fleet-review-{stamp}.json"

    prior = _load_prior_baseline(diagnostics_dir, exclude=json_path)

    sidecar = _build_fleet_sidecar(
        generated=generated,
        window_days=window_days,
        since=cutoff,
        until=until,
        projects=projects,
        excluded=excluded,
        aggs=aggs,
        shadowed=shadowed_tally,
    )

    report = _render_fleet_review_report(
        generated=generated,
        window_days=window_days,
        since=cutoff,
        until=until,
        projects=projects,
        excluded=excluded,
        aggs=aggs,
        flagged=flagged,
        validations=validations,
        zero_run=zero_run,
        shadowed=shadowed_tally,
        clusters=clusters,
        sequences=sequences_result,
        appendix_top=args.appendix_top,
        no_appendices=args.no_appendices,
        prior=prior,
        sidecar=sidecar,
    )

    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    md_path.write_text(report, encoding="utf-8")
    _write_baseline(
        json_path,
        aggs,
        window_days=window_days,
        since=cutoff,
        until=until,
        projects=projects,
        excluded=excluded,
        shadowed=shadowed_tally,
    )

    logger.success(f"Wrote {md_path}")
    print(str(md_path))
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
    discover_parser.add_argument(
        "--existing-only",
        action="store_true",
        default=False,
        help="Only emit paths that currently exist on disk; suppress all diagnostic output.",
    )
    add_host_arg(discover_parser)

    tail_parser = subparsers.add_parser(
        "tail",
        help="Stream live events from an active loop session",
    )
    tail_parser.add_argument("--loop", required=True, metavar="NAME", help="Loop name to tail")
    tail_parser.add_argument(
        "--project", type=Path, metavar="DIR", help="Project root to tail loops from (default: CWD)"
    )

    extract_parser = subparsers.add_parser(
        "extract",
        help="Extract ll-relevant JSONL records to logs/<slug>/<session-id>.jsonl",
    )
    add_corpus_target_args(extract_parser, all_help="Extract all projects with ll activity")
    extract_parser.add_argument(
        "--cmd",
        metavar="TOOL",
        help="Filter to records containing this ll- tool name (e.g. ll-history)",
    )
    add_json_arg(extract_parser)
    add_host_arg(extract_parser)

    sequences_parser = subparsers.add_parser(
        "sequences",
        help="Extract tool-chain n-grams of ll invocations from JSONL logs",
    )
    add_corpus_target_args(sequences_parser, all_help="Analyze all projects with ll activity")
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
    add_window_args(sequences_parser)
    add_json_arg(sequences_parser)
    add_host_arg(sequences_parser)

    stats_parser = subparsers.add_parser(
        "stats",
        help="Aggregate skill invocation frequency and correction rate from history.db",
    )
    add_corpus_target_args(stats_parser, all_help="Aggregate across all projects with ll activity")
    add_window_args(stats_parser)
    stats_parser.add_argument(
        "--sort",
        choices=["freq", "corrections"],
        default="freq",
        help="Sort output by invocation frequency or correction count (default: freq)",
    )
    add_json_arg(stats_parser)
    add_host_arg(stats_parser)

    scan_failures_parser = subparsers.add_parser(
        "scan-failures",
        help="Mine failed ll-* calls from interactive session logs and propose bug issues",
    )
    add_corpus_target_args(scan_failures_parser, all_help="Scan all projects with ll activity")
    add_window_args(scan_failures_parser)
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
    scan_failures_parser.add_argument(
        "--limit",
        type=int,
        default=0,
        metavar="N",
        help="Cap output to top N clusters by count (0 = unlimited)",
    )
    scan_failures_parser.add_argument(
        "--skill",
        metavar="NAME",
        default=None,
        help=(
            "Limit reported clusters to ll-* CLI failures that occurred while NAME "
            "was the enclosing skill (via a <command-name> marker or a Skill tool_use "
            "block); does NOT filter failures of NAME's own Read/Edit/Grep calls, "
            "which this subcommand never sees. The 'll:' prefix is optional on "
            "either side. Attribution is heuristic: a tool call issued after a "
            "skill's turn completes but before the next user message may be "
            "mis-attributed to that skill."
        ),
    )
    add_json_arg(scan_failures_parser)
    add_host_arg(scan_failures_parser)

    dead_skills_parser = subparsers.add_parser(
        "dead-skills",
        help="List catalog skills/commands with zero or low invocations across the corpus",
    )
    add_corpus_target_args(
        dead_skills_parser,
        project_help="Working directory of the target project (also used as catalog root)",
        all_help="Aggregate across all projects; catalog loaded from current directory",
    )
    add_window_args(dead_skills_parser)
    dead_skills_parser.add_argument(
        "--threshold",
        type=int,
        default=3,
        metavar="N",
        help="Skills with invocations <= N are 'rarely' invoked (default: 3)",
    )
    dead_skills_parser.add_argument(
        "--sort",
        choices=["tier", "name"],
        default="tier",
        help="Sort by tier (never before rarely) then count, or alphabetically (default: tier)",
    )
    add_json_arg(dead_skills_parser)
    add_host_arg(dead_skills_parser)

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
    add_host_arg(eval_export_parser)

    loop_fleet_parser = subparsers.add_parser(
        "loop-fleet",
        help="Aggregate cross-project loop-run outcomes for built-in loop improvement",
    )
    add_corpus_target_args(
        loop_fleet_parser, all_help="Aggregate across all projects with ll activity"
    )
    loop_fleet_parser.add_argument(
        "--loop",
        metavar="NAME",
        help="Filter to a specific loop name",
    )
    add_window_args(loop_fleet_parser, noun="runs")
    loop_fleet_parser.add_argument(
        "--existing-only",
        action="store_true",
        default=False,
        help="Skip projects that no longer exist on disk (passed to discover; only meaningful with --all)",
    )
    loop_fleet_parser.add_argument(
        "--sort",
        choices=["success", "name"],
        default="success",
        help="Sort by success rate ascending (worst first) or alphabetically (default: success)",
    )
    loop_fleet_parser.add_argument(
        "--limit",
        type=int,
        default=0,
        metavar="N",
        help="Cap --json output to N most recent runs (0 = unlimited)",
    )
    add_json_arg(loop_fleet_parser)
    add_host_arg(loop_fleet_parser)

    fleet_review_parser = subparsers.add_parser(
        "fleet-review",
        help=(
            "Harvest fleet-wide built-in loop outcomes, flag unhealthy loops, and write a "
            "dated diagnostic report + JSON baseline sidecar"
        ),
    )
    add_corpus_target_args(
        fleet_review_parser, all_help="Harvest across all projects with ll activity"
    )
    fleet_review_parser.add_argument(
        "--exclude-project",
        action="append",
        type=Path,
        default=[],
        metavar="DIR",
        dest="exclude_project",
        help=(
            "Exclude a project from the harvest (repeatable; both sides resolved before "
            "comparison, e.g. --exclude-project .)"
        ),
    )
    add_window_args(fleet_review_parser, noun="runs")
    fleet_review_parser.add_argument(
        "--existing-only",
        action="store_true",
        default=False,
        help="Skip projects that no longer exist on disk (only meaningful with --all)",
    )
    fleet_review_parser.add_argument(
        "--threshold",
        type=int,
        default=50,
        metavar="N",
        help="Flag a built-in loop when success%% is below N (default: 50)",
    )
    fleet_review_parser.add_argument(
        "--min-runs",
        type=int,
        default=3,
        metavar="N",
        help="Minimum runs required before a loop can be flagged (default: 3)",
    )
    fleet_review_parser.add_argument(
        "--appendix-top",
        type=int,
        default=20,
        metavar="N",
        help="Cap each appendix to the top N rows (0 = unlimited; default: 20)",
    )
    fleet_review_parser.add_argument(
        "--no-appendices",
        action="store_true",
        default=False,
        help="Skip the scan-failures/sequences appendices entirely (faster re-measure runs)",
    )
    add_json_arg(
        fleet_review_parser,
        help_text="Print the JSON baseline sidecar to stdout and write no files",
    )
    add_host_arg(fleet_review_parser)

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
            host = _resolve_host(getattr(args, "host", None))
            projects = discover_all_projects(logger, host=host, existing_only=args.existing_only)
            if args.json:
                print_json({"paths": [str(p) for p in projects]})
            else:
                for path in projects:
                    print(path)
            return 0

        if args.command == "tail":
            project_root = args.project if args.project else Path.cwd()
            config = BRConfig(project_root)
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

        if args.command == "loop-fleet":
            return _cmd_loop_fleet(args, logger)

        if args.command == "fleet-review":
            return _cmd_fleet_review(args, logger)

        return 1
