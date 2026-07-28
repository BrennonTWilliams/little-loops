"""Retention lifecycle and LCM session-compaction for the session store
(ENH-2890 split from session_store.py).

Covers the JSONL backfill/rebuild/compact/prune retention lifecycle
(``backfill``, ``backfill_incremental``, ``rebuild``, ``compact``, ``prune``,
``record_retirement``/``list_retirements``) plus LCM hierarchical
session-summary compaction (``compact_session``, ``compact_session_with_reasoning``
and their helpers). Depends on :mod:`little_loops.session_store.schema`
(``connect``, ``ensure_db``, ``_configure_connection``, ``SCHEMA_VERSION``),
:mod:`little_loops.session_store.db` (``DEFAULT_DB_PATH``), and
:mod:`little_loops.session_store.writers` for the per-table ``_backfill_*``
helpers and raw_events pack/unpack helpers. The deferred (inside-function)
imports from ``little_loops.compaction.instant`` are preserved to break a
circular dependency: ``instant.py`` imports back from
``little_loops.session_store`` (``_call_llm_for_summary``) inside its own
function bodies, so neither module can import the other at module-load time.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import subprocess
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import little_loops.session_store as _pkg
from little_loops.host_runner import resolve_host
from little_loops.session_store.db import DEFAULT_DB_PATH
from little_loops.session_store.schema import SCHEMA_VERSION, _configure_connection
from little_loops.session_store.writers import (
    _backfill_assistant_messages,
    _backfill_commit_events,
    _backfill_issues_and_snapshots,
    _backfill_learning_test_events,
    _backfill_loops,
    _backfill_messages,
    _backfill_prompt_opt,
    _backfill_skill_events,
    _backfill_snapshots,
    _backfill_subagent_runs,
    _backfill_tool_events,
    _backfill_usage_events,
    _iter_events,
    _now,
    _pack_payload,
    mine_corrections_from_messages,
)

if TYPE_CHECKING:
    from little_loops.config.features import CompactionConfig

logger = logging.getLogger(__name__)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate using the LCM convention: 4 characters per token."""
    return len(text) // 4


def _summarize_block(
    messages: list[str],
    budget: int,
    *,
    model: str | None = None,
    timeout: int = 60,
) -> str:
    """Summarize block_text to fit within budget tokens, with convergence guarantee.

    LCM Algorithm 3 three-level escalation:

    1. **Level 1**: Normal LLM summary (preserve details), target = budget.
       Accepted only if ``_estimate_tokens(result) < _estimate_tokens(input)``.
    2. **Level 2**: Aggressive bullet-point LLM summary at ``budget // 2``.
       Triggered when level-1 output is not smaller than input.
    3. **Level 3**: Deterministic truncation — ``min(budget * 4, 2048)`` characters.
       Guaranteed to produce output ≤ input by construction.
    Escalations are logged at WARNING level for operator visibility.
    """

    block_text = "\n---\n".join(messages)

    est_input = _estimate_tokens(block_text)

    # Short-circuit: for very small inputs an LLM summary cannot be meaningfully
    # smaller than the input — skip directly to deterministic truncation.
    if est_input < 25:
        return block_text[: min(budget * 4, 2048)]

    # -- Level 1: normal prose summary -------------------------------------------------
    level1_prompt = (
        "Summarize these session messages concisely (2-3 paragraphs), capturing key "
        "topics, decisions, and outcomes. Target approximately "
        f"{budget} tokens:\n\n" + block_text
    )
    result = _call_llm_for_summary(level1_prompt, model=model, timeout=timeout)
    if result and _estimate_tokens(result) < est_input:
        return result

    # -- Level 2: aggressive bullet-point summary at half budget -----------------------
    if result:
        logger.warning(
            "_summarize_block: level-1 summary not smaller than input "
            "(est_output=%d >= est_input=%d); escalating to level 2",
            _estimate_tokens(result),
            est_input,
        )
    else:
        logger.warning("_summarize_block: level-1 LLM call failed; escalating to level 2")
    level2_budget = max(budget // 2, 64)
    level2_prompt = (
        "Summarize these session messages as a compact bullet list. Be extremely terse: "
        "one line per key point, no preamble or commentary. Target approximately "
        f"{level2_budget} tokens:\n\n" + block_text
    )
    result = _call_llm_for_summary(level2_prompt, model=model, timeout=timeout)
    if result and _estimate_tokens(result) < est_input:
        return result

    # -- Level 3: deterministic truncation (guaranteed convergence) --------------------
    if result:
        logger.warning(
            "_summarize_block: level-2 summary not smaller than input "
            "(est_output=%d >= est_input=%d); escalating to level 3",
            _estimate_tokens(result),
            est_input,
        )
    else:
        logger.warning("_summarize_block: level-2 LLM call failed; escalating to level 3")
    # Truncation: min(budget * 4, 2048) chars. The 2048 cap (~512 tokens at 4 chars/token)
    # follows the LCM paper's level-3 constant, providing a strict convergence guarantee.
    max_chars = min(budget * 4, 2048)
    return block_text[:max_chars]


def _call_llm_for_summary(
    prompt: str,
    *,
    model: str | None = None,
    timeout: int = 60,
) -> str | None:
    """Call the host LLM for a summary and extract the prose ``result`` field.

    Returns the extracted prose string on success, or ``None`` if the LLM call
    failed or produced an unparseable response (allowing escalation logic to
    fall through to the next level).
    """

    try:
        inv = resolve_host().build_blocking_json(prompt=prompt, model=model)
        proc = subprocess.run(
            [inv.binary, *inv.args],
            env={**os.environ, **inv.env},
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.warning("_call_llm_for_summary: LLM call timed out after %ds", timeout)
        return None
    except FileNotFoundError:
        logger.error(
            "_call_llm_for_summary: %s CLI not found. Install the active host CLI "
            "(see LL_HOST_CLI).",
            inv.binary,
        )
        return None

    if proc.returncode != 0:
        stderr_preview = proc.stderr.strip()[:200] if proc.stderr else "(no stderr)"
        logger.error(
            "_call_llm_for_summary: %s CLI returned exit code %d (stderr: %s)",
            inv.binary,
            proc.returncode,
            stderr_preview,
        )
        return None

    if not proc.stdout.strip():
        stderr_info = proc.stderr.strip()[:200] if proc.stderr else ""
        logger.error(
            "_call_llm_for_summary: %s CLI returned empty stdout on exit 0"
            + (f" (stderr: {stderr_info})" if stderr_info else "")
        )
        return None

    # Parse the JSON envelope and extract the 'result' field — see
    # evaluate_llm_structured() at fsm/evaluators.py:832-880 for the
    # canonical envelope-parsing pattern.
    try:
        stdout = proc.stdout.strip()
        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError:
            # Try JSONL: take the last non-empty line
            lines = [line for line in stdout.split("\n") if line.strip()]
            if not lines:
                raise
            envelope = json.loads(lines[-1])

        # Check for structured-output retry exhaustion or legacy is_error
        if envelope.get("subtype") == "error_max_structured_output_retries":
            logger.error(
                "_call_llm_for_summary: %s CLI could not produce valid output after retries",
                inv.binary,
            )
            return None
        if envelope.get("is_error", False):
            err_text = str(envelope.get("result", "") or "")[:200]
            logger.error(
                "_call_llm_for_summary: %s CLI reported error: %s",
                inv.binary,
                err_text,
            )
            return None

        # Extract the result field (plain prose; no --json-schema here)
        result = envelope.get("result", "")
        if not result:
            logger.error(
                "_call_llm_for_summary: empty result field in %s CLI response",
                inv.binary,
            )
            return None
        return str(result)

    except (json.JSONDecodeError, TypeError, ValueError) as e:
        raw_preview = proc.stdout[:300] if proc.stdout else "(empty)"
        logger.error(
            "_call_llm_for_summary: failed to parse LLM response: %s (raw: %s)",
            e,
            raw_preview,
        )
        return None


def _compact_session_conn(
    conn: sqlite3.Connection,
    session_id: str,
    budget: int = 4096,
    *,
    model: str | None = None,
    timeout: int = 60,
) -> int:
    """Compact one session using an existing connection. Returns new leaf node count.

    Greedy single-pass block grouping: token estimate ``len(s) // 4``. Each block
    gets one ``leaf`` summary_node; if the session accumulates ≥ 2 leaves a single
    ``condensed`` node is inserted (or silently skipped if one already exists via
    ``INSERT OR IGNORE`` + ``idx_summary_nodes_condensed_dedup``). Leaf dedup is
    handled by ``idx_summary_nodes_leaf_dedup`` on ``(session_id, ts_start, ts_end)``.
    """
    rows = conn.execute(
        "SELECT id, ts, content FROM message_events WHERE session_id = ? ORDER BY ts, id",
        (session_id,),
    ).fetchall()

    if not rows:
        return 0

    # Greedy block accumulation
    blocks: list[list[tuple[int, str, str]]] = []
    current: list[tuple[int, str, str]] = []
    current_tokens = 0

    for row in rows:
        msg_id, ts, content = row[0], row[1], row[2] or ""
        tok = _estimate_tokens(content)
        if current_tokens + tok > budget and current:
            blocks.append(current)
            current = [(msg_id, ts, content)]
            current_tokens = tok
        else:
            current.append((msg_id, ts, content))
            current_tokens += tok
    if current:
        blocks.append(current)

    now = _now()
    new_leaves = 0

    for block in blocks:
        ts_start = block[0][1]
        ts_end = block[-1][1]
        msg_ids = [r[0] for r in block]
        contents = [r[2] for r in block]

        summary = _summarize_block(contents, budget, model=model, timeout=timeout)
        cursor = conn.execute(
            "INSERT OR IGNORE INTO summary_nodes"
            "(kind, content, tokens, session_id, ts_start, ts_end, created_at)"
            " VALUES('leaf', ?, ?, ?, ?, ?, ?)",
            (summary, _estimate_tokens(summary), session_id, ts_start, ts_end, now),
        )
        if cursor.rowcount:
            leaf_id = cursor.lastrowid
            conn.executemany(
                "INSERT OR IGNORE INTO summary_spans(summary_id, message_event_id) VALUES(?, ?)",
                [(leaf_id, mid) for mid in msg_ids],
            )
            new_leaves += 1

    # Condensed node: one per session, summarises all leaves.
    all_leaves = conn.execute(
        "SELECT id, content FROM summary_nodes"
        " WHERE kind='leaf' AND session_id=? ORDER BY ts_start",
        (session_id,),
    ).fetchall()

    if len(all_leaves) >= 2:
        leaf_summaries = [r[1] for r in all_leaves]
        condensed_text = _summarize_block(leaf_summaries, budget, model=model, timeout=timeout)
        cursor = conn.execute(
            "INSERT OR IGNORE INTO summary_nodes"
            "(kind, content, tokens, session_id, ts_start, ts_end, created_at)"
            " VALUES('condensed', ?, ?, ?, NULL, NULL, ?)",
            (condensed_text, _estimate_tokens(condensed_text), session_id, now),
        )
        if cursor.rowcount:
            condensed_id = cursor.lastrowid
            conn.execute(
                "UPDATE summary_nodes SET parent_id = ?"
                " WHERE session_id = ? AND kind = 'leaf' AND parent_id IS NULL",
                (condensed_id, session_id),
            )

    return new_leaves


def _compact_session_conn_with_reasoning(
    conn: sqlite3.Connection,
    session_id: str,
    budget: int = 4096,
    *,
    model: str | None = None,
    timeout: int = 60,
) -> tuple[str | None, list[int]]:
    """Compute an assistant-inclusive summary for one session (FEAT-2747).

    Sibling of ``_compact_session_conn`` that joins ``message_events`` and
    ``assistant_messages`` (role-tagged ``UNION ALL``, ordered by ts/id) instead
    of reading ``message_events`` alone, so the assistant's derived reasoning is
    part of what gets summarized. Reuses the same greedy token-budget block
    grouping and ``_summarize_block`` escalation as ``_compact_session_conn``.

    Unlike ``_compact_session_conn``, this does not write to ``summary_nodes``/
    ``summary_spans`` — it returns the computed summary directly. Persisting
    would collide with ``idx_summary_nodes_condensed_dedup``
    (``UNIQUE(session_id) WHERE kind='condensed'`` — one condensed node per
    session, no discriminator for which function produced it), corrupting
    whichever of the two functions ran second for a given session. The caller
    (a single FSM prompt-state invocation, FEAT-2711) needs a summary value to
    carry forward, not a durable DAG node.

    Returns ``(None, [])`` if the session has no rows in either table.
    Returns ``(summary_text, message_event_ids)`` otherwise, where
    ``message_event_ids`` covers only the ``message_events``-sourced rows
    (matching ``CompactResult.compacted_messages``'s existing
    ``message_events``-only semantics).
    """
    rows = conn.execute(
        "SELECT id, ts, content, 'user' AS role FROM message_events WHERE session_id = ?"
        " UNION ALL"
        " SELECT id, ts, content, 'assistant' AS role FROM assistant_messages"
        " WHERE session_id = ?"
        " ORDER BY ts, id",
        (session_id, session_id),
    ).fetchall()

    if not rows:
        return None, []

    # Greedy block accumulation (mirrors _compact_session_conn).
    blocks: list[list[tuple[int, str, str, str]]] = []
    current: list[tuple[int, str, str, str]] = []
    current_tokens = 0

    for row in rows:
        msg_id, ts, content, role = row[0], row[1], row[2] or "", row[3]
        tok = _estimate_tokens(content)
        if current_tokens + tok > budget and current:
            blocks.append(current)
            current = [(msg_id, ts, content, role)]
            current_tokens = tok
        else:
            current.append((msg_id, ts, content, role))
            current_tokens += tok
    if current:
        blocks.append(current)

    message_event_ids = [r[0] for r in rows if r[3] == "user"]

    leaf_summaries = [
        _summarize_block([r[2] for r in block], budget, model=model, timeout=timeout)
        for block in blocks
    ]

    if len(leaf_summaries) >= 2:
        summary_text = _summarize_block(leaf_summaries, budget, model=model, timeout=timeout)
    else:
        summary_text = leaf_summaries[0]

    return summary_text, message_event_ids


def compact_session_with_reasoning(
    session_id: str,
    db: Path | str = DEFAULT_DB_PATH,
    *,
    config: dict | None = None,
) -> tuple[str | None, list[int]]:
    """Public entry point for assistant-inclusive compaction (FEAT-2747).

    Mirrors ``compact_session()``'s ``CompactionConfig`` resolution and
    ``connect``/``try``/``finally`` lifecycle. Unlike ``compact_session()``,
    this is a pure compute-and-return call — no rows are inserted, so there is
    nothing to ``commit()``.
    """
    from little_loops.config.features import CompactionConfig

    raw = config.get("history", {}).get("compaction", {}) if config else {}
    compact_cfg = CompactionConfig.from_dict(raw)
    conn = _pkg.connect(db)
    try:
        return _compact_session_conn_with_reasoning(
            conn,
            session_id,
            budget=compact_cfg.budget_tokens,
            model=compact_cfg.model,
            timeout=compact_cfg.timeout,
        )
    finally:
        conn.close()


def _maybe_soft_threshold_summary(
    conn: sqlite3.Connection,
    session_id: str,
    db: Path | str,
    compact_cfg: CompactionConfig,
) -> threading.Thread | None:
    """Fire a background 6-section summary once the soft token threshold is crossed (FEAT-2598).

    Gated on ``CompactionConfig.enabled`` — summarization is the opt-in LLM-cost
    path (unlike the always-on structural eviction pass in
    ``compaction.instant.evict_sink_and_window``, applied here to bound the
    summarizer's input). Updates the session's existing per-session condensed
    ``summary_nodes`` row (``kind='condensed'``, ``level=0``) in place — no new
    node kind, no schema change, and no change to
    ``history_reader.condensed_nodes_for_issue()``'s query semantics.

    Does not touch ``_compact_session_conn``'s purely-additive contract: this
    function only ever reads ``message_events`` and writes to ``summary_nodes``
    from a background thread using its own connection (sqlite3 connections are
    not thread-safe across threads).
    """
    if not compact_cfg.enabled:
        return None

    from little_loops.compaction.instant import SOFT_THRESHOLD_TOKENS, evict_sink_and_window

    rows = conn.execute(
        "SELECT content FROM message_events WHERE session_id = ? ORDER BY ts, id",
        (session_id,),
    ).fetchall()
    if not rows:
        return None

    contents = [r[0] or "" for r in rows]
    if sum(_estimate_tokens(c) for c in contents) < SOFT_THRESHOLD_TOKENS:
        return None

    bounded = evict_sink_and_window([{"role": "user", "content": c} for c in contents])
    bounded_contents = [m["content"] for m in bounded]

    def _run() -> None:
        from little_loops.compaction.instant import summarize_6_section

        summary_text = summarize_6_section(
            bounded_contents, model=compact_cfg.model, timeout=compact_cfg.timeout
        )
        thread_conn = _pkg.connect(db)
        try:
            existing = thread_conn.execute(
                "SELECT id FROM summary_nodes"
                " WHERE session_id = ? AND kind = 'condensed' AND level = 0",
                (session_id,),
            ).fetchone()
            tokens = _estimate_tokens(summary_text)
            if existing:
                thread_conn.execute(
                    "UPDATE summary_nodes SET content = ?, tokens = ? WHERE id = ?",
                    (summary_text, tokens, existing[0]),
                )
            else:
                thread_conn.execute(
                    "INSERT OR IGNORE INTO summary_nodes"
                    "(kind, content, tokens, session_id, ts_start, ts_end, created_at, level)"
                    " VALUES('condensed', ?, ?, ?, NULL, NULL, ?, 0)",
                    (summary_text, tokens, session_id, _now()),
                )
            thread_conn.commit()
        finally:
            thread_conn.close()

    thread = threading.Thread(target=_run, name=f"compact-6section-{session_id}", daemon=True)
    thread.start()
    return thread


def _compact_sessions(
    conn: sqlite3.Connection,
    config: dict | None = None,
    max_sessions: int | None = None,
    db: Path | str = DEFAULT_DB_PATH,
) -> int:
    """Compact all sessions in the sessions table; returns total new leaf nodes created.

    Gated by ``history.compaction.enabled`` (default ``false``). Skips silently when
    disabled so backfill() callers that omit config are unaffected.

    When ``cross_session_enabled`` is True (default), runs a recursive cross-session
    condensation pass after per-session compaction: existing condensed nodes are
    grouped level-by-level by token budget, summarised, and inserted as higher-order
    condensed nodes (``session_id=NULL``, ``level=1+``) until exactly one project-root
    summary node remains (ENH-1954).

    Args:
        max_sessions: When set, caps the number of sessions compacted in this run
            (useful for incremental first-time backfills on large databases).
        db: Path passed through to the soft-threshold background summarizer
            (FEAT-2598), which needs its own connection to the same database.
    """
    from little_loops.config.features import CompactionConfig

    raw = config.get("history", {}).get("compaction", {}) if config else {}
    compact_cfg = CompactionConfig.from_dict(raw)
    if not compact_cfg.enabled:
        return 0

    rows = conn.execute("SELECT session_id FROM sessions ORDER BY started_at DESC").fetchall()
    if max_sessions is not None:
        rows = rows[:max_sessions]
    total = 0
    for row in rows:
        total += _compact_session_conn(
            conn,
            row[0],
            budget=compact_cfg.budget_tokens,
            model=compact_cfg.model,
            timeout=compact_cfg.timeout,
        )
        _maybe_soft_threshold_summary(conn, row[0], db, compact_cfg)

    # -- Cross-session condensation (ENH-1954) ---------------------------------
    if not compact_cfg.cross_session_enabled:
        return total

    now = _now()
    level = 1
    max_level = compact_cfg.max_level  # None = unlimited

    while True:
        # Collect condensed nodes at the current level.
        # Level 0 = per-session condensed; level 1+ = cross-session.
        condensed = conn.execute(
            "SELECT id, content, tokens, session_id FROM summary_nodes"
            " WHERE kind='condensed' AND level = ?"
            " ORDER BY id",
            (level - 1,),
        ).fetchall()

        if len(condensed) <= 1:
            break  # nothing to roll up, or already at root

        # Group by token budget — same greedy algorithm as _compact_session_conn
        groups: list[list[tuple[int, str, int, str | None]]] = []
        current: list[tuple[int, str, int, str | None]] = []
        current_tokens = 0

        for row in condensed:
            node_id, content, tokens, sess_id = (
                row[0],
                row[1],
                row[2] or 0,
                row[3],
            )
            if current_tokens + tokens > compact_cfg.budget_tokens and current:
                groups.append(current)
                current = [(node_id, content, tokens, sess_id)]
                current_tokens = tokens
            else:
                current.append((node_id, content, tokens, sess_id))
                current_tokens += tokens
        if current:
            groups.append(current)

        for group in groups:
            member_ids = [g[0] for g in group]
            contents = [g[1] for g in group]

            summary = _summarize_block(
                contents,
                compact_cfg.budget_tokens,
                model=compact_cfg.model,
                timeout=compact_cfg.timeout,
            )

            # Compute ts_start/ts_end for the dedup index.
            # Level-1 members are per-session condensed nodes (session_id NOT NULL
            # but ts_start=NULL). Query leaf descendants via session_id to get
            # real timestamps. Level-2+ members already have ts_start/ts_end set.
            if level == 1:
                sess_ids = [g[3] for g in group if g[3] is not None]
                if sess_ids:
                    ph = ",".join(["?"] * len(sess_ids))
                    ts_row = conn.execute(
                        f"SELECT MIN(ts_start), MAX(ts_end) FROM summary_nodes"
                        f" WHERE kind='leaf' AND session_id IN ({ph})",
                        sess_ids,
                    ).fetchone()
                    ts_start = ts_row[0] if ts_row else None
                    ts_end = ts_row[1] if ts_row else None
                else:
                    ts_start, ts_end = None, None
            else:
                ph = ",".join(["?"] * len(member_ids))
                ts_row = conn.execute(
                    f"SELECT MIN(ts_start), MAX(ts_end) FROM summary_nodes WHERE id IN ({ph})",
                    member_ids,
                ).fetchone()
                ts_start = ts_row[0] if ts_row else None
                ts_end = ts_row[1] if ts_row else None

            cursor = conn.execute(
                "INSERT OR IGNORE INTO summary_nodes"
                "(kind, content, tokens, session_id, ts_start, ts_end, created_at, level)"
                " VALUES('condensed', ?, ?, NULL, ?, ?, ?, ?)",
                (summary, _estimate_tokens(summary), ts_start, ts_end, now, level),
            )
            if cursor.rowcount:
                parent_id: int | None = cursor.lastrowid
            else:
                # Node already exists (idempotent re-run) — look up its id
                existing = conn.execute(
                    "SELECT id FROM summary_nodes"
                    " WHERE kind='condensed' AND session_id IS NULL"
                    " AND level = ? AND ts_start = ? AND ts_end = ?",
                    (level, ts_start, ts_end),
                ).fetchone()
                parent_id = existing[0] if existing else None

            if parent_id is not None:
                ph = ",".join(["?"] * len(member_ids))
                conn.execute(
                    f"UPDATE summary_nodes SET parent_id = ?"
                    f" WHERE id IN ({ph}) AND parent_id IS NULL",
                    [parent_id] + member_ids,
                )

        # Depth-limit check
        if max_level is not None and level >= max_level:
            break

        level += 1

    return total


def compact_session(
    session_id: str,
    db: Path | str = DEFAULT_DB_PATH,
    *,
    config: dict | None = None,
) -> int:
    """Summarize message_events for one session into summary_nodes and summary_spans.

    Idempotent: repeated calls do not create duplicate nodes (INSERT OR IGNORE +
    partial unique indexes). Uses LCM Algorithm 3 three-level escalation (level 1:
    normal LLM summary → level 2: aggressive bullet-point LLM summary → level 3:
    deterministic truncation) so a leaf node is always produced. Returns the count
    of new leaf nodes created.
    """
    from little_loops.config.features import CompactionConfig

    raw = config.get("history", {}).get("compaction", {}) if config else {}
    compact_cfg = CompactionConfig.from_dict(raw)
    conn = _pkg.connect(db)
    try:
        result = _compact_session_conn(
            conn,
            session_id,
            budget=compact_cfg.budget_tokens,
            model=compact_cfg.model,
            timeout=compact_cfg.timeout,
        )
        conn.commit()
        _maybe_soft_threshold_summary(conn, session_id, db, compact_cfg)
    finally:
        conn.close()
    return result


def _backfill_sessions(conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor) -> int:
    """Seed ``sessions`` table by mapping each JSONL file to its session_id.

    Reads just enough of each source to extract the first ``sessionId`` value,
    then inserts one row per unique source. ``INSERT OR IGNORE`` + PRIMARY KEY
    makes repeated calls idempotent (ENH-1710). *source* accepts either JSONL
    files or a raw_events cursor — see :func:`_iter_events`. Unlike the legacy
    per-file loop this no longer short-circuits to the next physical file on
    the first hit (the cursor path has no file boundary), instead skipping
    further parse attempts for a source once its session_id is known.
    """
    count = 0
    seen: set[str] = set()
    for line, source_label in _iter_events(source):
        if source_label in seen:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        session_id = record.get("sessionId")
        if session_id:
            cur = conn.execute(
                "INSERT OR IGNORE INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                (str(session_id), source_label),
            )
            count += cur.rowcount
            seen.add(source_label)
    return count


def _mtime(path: Path) -> float:
    """Return file modification time as a Unix float, or 0.0 if inaccessible."""
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _backfill_raw_events(conn: sqlite3.Connection, jsonl_files: list[Path]) -> int:
    """Parse *jsonl_files* and INSERT OR IGNORE one row per line into raw_events.

    Idempotent via the ``(source_path, line_no)`` dedup index. ``event_type``
    is the record's own ``type`` field (``"user"``, ``"assistant"``, ...) —
    one JSONL line can feed multiple derived cache rows (e.g. an assistant
    line yields both an assistant_messages row and zero-or-more tool_events
    rows), so raw_events stores the source line verbatim rather than a
    cache-table kind (ENH-2581).
    """
    host = resolve_host().name
    count = 0
    for jsonl_file in jsonl_files:
        try:
            handle = jsonl_file.open(encoding="utf-8")
        except OSError:
            continue
        source_path = str(jsonl_file)
        with handle:
            for line_no, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                cur = conn.execute(
                    "INSERT OR IGNORE INTO raw_events"
                    "(ts, session_id, host, source_path, line_no, event_type, raw_line, parsed_json)"
                    " VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(record.get("timestamp") or ""),
                        record.get("sessionId"),
                        host,
                        source_path,
                        line_no,
                        str(record.get("type") or "unknown"),
                        _pack_payload(line),
                        _pack_payload(json.dumps(record)),
                    ),
                )
                count += cur.rowcount
    return count


def backfill_raw_events(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    jsonl_files: list[Path],
    since_ts: float | None = None,
) -> int:
    """Parse JSONL files and INSERT OR IGNORE rows into raw_events.

    Idempotent via ``INSERT OR IGNORE`` on ``(source_path, line_no)``. Filters
    *jsonl_files* by mtime >= *since_ts* when given (``None`` processes every
    provided file). Updates the ``last_raw_event_ts`` meta key on success —
    the single watermark that replaces ``last_backfill_ts`` /
    ``last_backfill_ts_assistant_messages`` / ``last_backfill_ts_skill_events``
    (ENH-2581). Returns the count of new rows inserted.
    """
    conn = _pkg.connect(db)
    try:
        filtered = (
            [f for f in jsonl_files if _mtime(f) >= since_ts]
            if since_ts is not None
            else jsonl_files
        )
        count = _backfill_raw_events(conn, filtered)
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('last_raw_event_ts', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_now(),),
        )
        conn.commit()
    finally:
        conn.close()
    return count


def recompress_raw_events(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    batch_size: int = 2000,
) -> dict[str, Any]:
    """Rewrite legacy uncompressed ``raw_events`` payloads as compressed BLOBs.

    New rows are written compressed by :func:`_backfill_raw_events`; this backfills
    the one-time conversion of pre-existing TEXT rows. Runs in short per-batch
    transactions (not one giant lock) so it does not freeze the interactive hook
    write path, then ``VACUUM`` reclaims the freed pages. Idempotent and resumable
    via ``typeof(...) = 'text'`` — already-compressed rows are BLOBs and skipped.

    Returns ``{"recompressed": int, "size_before_mb": float, "size_after_mb": float}``.
    """
    db_path = _pkg.ensure_db(db)  # unified env→config→default resolution + schema (ENH-2623)
    size_before = db_path.stat().st_size if db_path.exists() else 0
    conn = _pkg.connect(db_path)
    recompressed = 0
    try:
        while True:
            rows = conn.execute(
                "SELECT id, raw_line, parsed_json FROM raw_events "
                "WHERE typeof(raw_line) = 'text' OR typeof(parsed_json) = 'text' "
                "LIMIT ?",
                (batch_size,),
            ).fetchall()
            if not rows:
                break
            conn.execute("BEGIN")
            for row in rows:
                raw_line = row["raw_line"]
                parsed_json = row["parsed_json"]
                packed_raw = raw_line if isinstance(raw_line, bytes) else _pack_payload(raw_line)
                packed_parsed = (
                    parsed_json if isinstance(parsed_json, bytes) else _pack_payload(parsed_json)
                )
                conn.execute(
                    "UPDATE raw_events SET raw_line = ?, parsed_json = ? WHERE id = ?",
                    (packed_raw, packed_parsed, row["id"]),
                )
            conn.commit()
            recompressed += len(rows)
    finally:
        conn.close()
    if recompressed:
        vac = sqlite3.connect(str(db_path))
        try:
            vac.execute("VACUUM")
        finally:
            vac.close()
    size_after = db_path.stat().st_size if db_path.exists() else 0
    return {
        "recompressed": recompressed,
        "size_before_mb": round(size_before / 1_000_000, 1),
        "size_after_mb": round(size_after / 1_000_000, 1),
    }


# Cache tables re-derived from raw_events by rebuild(). Deliberately excludes
# cli_events/file_events/test_run_events/issue_events/loop_events/commit_events/
# issue_snapshots/hook_events/harness_events/prompt_opt_events — those have no
# raw_events-backed _backfill_* path (they're either live-write-only or
# sourced from .issues/.loops/git log, out of this issue's scope; see
# ENH-2581 management plan). Wiping them here with no re-derivation path
# would be unrecoverable data loss. hook_events and harness_events in
# particular have no transcript-JSONL source at all (ENH-2506, ENH-2739).
# prompt_opt_events does get JSONL-sourced enrichment (ENH-2498's
# _backfill_prompt_opt), but as a non-destructive UPDATE-only pass called
# separately below — it must NOT be added here or to _REBUILD_SEARCH_KINDS,
# since a wipe would destroy the live offer rows it enriches.
_REBUILD_TABLES = (
    "tool_events",
    "message_events",
    "assistant_messages",
    "skill_events",
    "sessions",
    "user_corrections",
    "summary_nodes",
    "summary_spans",
    "usage_events",
)

_REBUILD_SEARCH_KINDS = ("tool", "message", "skill", "correction", "usage")


def rebuild(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    config: dict | None = None,
    max_sessions: int | None = None,
) -> dict[str, int]:
    """Wipe and re-derive the JSONL-sourced cache tables from ``raw_events``.

    Wipes ``_REBUILD_TABLES`` plus the ``search_index`` rows for
    ``_REBUILD_SEARCH_KINDS``, then re-derives them by replaying every
    ``raw_events`` row through the same ``_backfill_*`` parsers the legacy
    JSONL path uses (via :func:`_iter_events`). Idempotent — safe to call
    repeatedly. Updates the ``last_rebuild_version`` meta key to
    ``SCHEMA_VERSION`` on success.

    Issue/loop/commit/cli/file/test_run tables are outside ``raw_events``'s
    scope for this issue (ENH-2581) and are left untouched.
    """
    conn = _pkg.connect(db)
    counts: dict[str, int] = {
        "sessions": 0,
        "tools": 0,
        "messages": 0,
        "assistant_messages": 0,
        "skill_events": 0,
        "corrections": 0,
        "summaries": 0,
        "usage_events": 0,
        "prompt_opt_events": 0,
    }
    try:
        for table in _REBUILD_TABLES:
            conn.execute(f"DELETE FROM {table}")
        placeholders = ",".join(["?"] * len(_REBUILD_SEARCH_KINDS))
        conn.execute(
            f"DELETE FROM search_index WHERE kind IN ({placeholders})",
            _REBUILD_SEARCH_KINDS,
        )

        def _raw_events_cursor() -> sqlite3.Cursor:
            return conn.execute("SELECT raw_line, source_path FROM raw_events ORDER BY id")

        # sessions first: assistant_messages/backfill order elsewhere relies on
        # the sessions table already being populated (ENH-1710).
        counts["sessions"] = _backfill_sessions(conn, _raw_events_cursor())
        counts["tools"] = _backfill_tool_events(conn, _raw_events_cursor())
        counts["messages"] = _backfill_messages(conn, _raw_events_cursor())
        counts["assistant_messages"] = _backfill_assistant_messages(conn, _raw_events_cursor())
        counts["skill_events"] = _backfill_skill_events(conn, _raw_events_cursor())
        counts["usage_events"] = _backfill_usage_events(conn, _raw_events_cursor())
        counts["corrections"] = mine_corrections_from_messages(conn, config)
        counts["summaries"] = _compact_sessions(conn, config, max_sessions=max_sessions, db=db)
        # Non-destructive UPDATE-only enrichment — deliberately not part of
        # the DELETE-then-replay loop above (see _REBUILD_TABLES comment).
        counts["prompt_opt_events"] = _backfill_prompt_opt(conn, _raw_events_cursor())

        conn.execute(
            "INSERT INTO meta(key, value) VALUES('last_rebuild_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()
    finally:
        conn.close()
    return counts


def backfill_snapshots(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    issues_dir: Path | None = None,
) -> int:
    """Hydrate ``issue_snapshots`` from all ``.md`` files under *issues_dir*.

    Idempotent via ``INSERT OR IGNORE`` on the ``(issue_id, transition)`` dedup
    index.  Also indexes each snapshot in ``search_index`` with ``kind="snapshot"``.
    Returns the number of rows inserted (0 when *issues_dir* is absent or empty).
    """
    issues_dir = issues_dir if issues_dir is not None else Path(".issues")
    if not issues_dir.is_dir():
        return 0
    conn = _pkg.connect(db)
    try:
        count = _backfill_snapshots(conn, issues_dir)
        conn.commit()
    finally:
        conn.close()
    return count


def backfill(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    issues_dir: Path | None = None,
    loops_dir: Path | None = None,
    jsonl_files: list[Path] | None = None,
    config: dict | None = None,
    max_sessions: int | None = None,
    repo_root: Path | None = None,
    registry_dir: Path | None = None,
    sessions_root: Path | None = None,
    also_rebuild: bool = False,
) -> dict[str, int]:
    """Populate the database from existing on-disk sources.

    Reads issue-file frontmatter, FSM loop-state JSON, git commit history
    (ENH-2458; only when *repo_root* is given and contains ``.git``), the
    Learning Test Registry (ENH-2466; only when *registry_dir* is given and is
    a directory), and nested subagent transcripts (ENH-2505; only when
    *sessions_root* is given and is a directory) directly. Session JSONL lines
    are ingested into ``raw_events`` only (ENH-2581) — the JSONL-derived cache
    tables (``tool_events``, ``message_events``, ``assistant_messages``,
    ``skill_events``, ``sessions``) are **not** populated here; call
    :func:`rebuild` (or pass ``also_rebuild=True`` to do both in one call) to
    materialize them from ``raw_events``.

    Returns a per-kind count of rows inserted/derived. Sources that are
    absent are skipped silently.
    """
    issues_dir = issues_dir if issues_dir is not None else Path(".issues")
    loops_dir = loops_dir if loops_dir is not None else Path(".loops")
    if registry_dir is None:
        registry_dir = Path(".ll") / "learning-tests"
    conn = _pkg.connect(db)
    counts: dict[str, int] = {
        "issues": 0,
        "loops": 0,
        "snapshots": 0,
        "commits": 0,
        "raw_events": 0,
        "learning_tests": 0,
        "subagent_runs": 0,
    }
    try:
        if issues_dir.is_dir():
            counts["issues"], counts["snapshots"] = _backfill_issues_and_snapshots(conn, issues_dir)
        if loops_dir.is_dir():
            counts["loops"] = _backfill_loops(conn, loops_dir)
        if repo_root is not None and (repo_root / ".git").exists():
            counts["commits"] = _backfill_commit_events(conn, repo_root)
        if jsonl_files:
            counts["raw_events"] = _backfill_raw_events(conn, jsonl_files)
        if registry_dir.is_dir():
            counts["learning_tests"] = _backfill_learning_test_events(conn, registry_dir)
        if sessions_root is not None and sessions_root.is_dir():
            counts["subagent_runs"] = _backfill_subagent_runs(conn, sessions_root)
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('last_raw_event_ts', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_now(),),
        )
        conn.commit()
    finally:
        conn.close()

    if also_rebuild:
        counts.update(rebuild(db, config=config, max_sessions=max_sessions))

    return counts


def backfill_incremental(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    jsonl_files: list[Path],
    since_ts: float | None = None,
    config: dict | None = None,
    also_rebuild: bool = False,
) -> dict[str, int]:
    """Ingest JSONL files modified after *since_ts* into ``raw_events``.

    Thin wrapper over :func:`backfill_raw_events` (ENH-2581): ingest only.
    The three legacy per-table watermarks (``last_backfill_ts``,
    ``last_backfill_ts_assistant_messages``, ``last_backfill_ts_skill_events``)
    collapse to the single ``last_raw_event_ts`` key maintained by
    :func:`backfill_raw_events`.

    If *since_ts* is ``None``, reads ``last_raw_event_ts`` from the ``meta``
    table (defaults to 0.0 — all files — when the key is absent or NULL).

    Pass ``also_rebuild=True`` to materialize the JSONL-derived cache tables
    from ``raw_events`` afterward in the same call — used by the
    ``SessionStart`` hook worker when ``SCHEMA_VERSION`` has changed (see
    ``cli/backfill_worker.py --rebuild``).

    Issues and loop-state JSON are NOT backfilled here; this variant is
    JSONL-only and designed for low-latency background use in session hooks.
    Errors are not suppressed — the caller (session hook) catches them and
    logs a warning.
    """
    if since_ts is None:
        conn = _pkg.connect(db)
        try:
            row = conn.execute("SELECT value FROM meta WHERE key = 'last_raw_event_ts'").fetchone()
        finally:
            conn.close()
        raw = row[0] if (row and row[0]) else None
        if raw:
            try:
                since_ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
            except ValueError:
                since_ts = 0.0
        else:
            since_ts = 0.0

    raw_count = backfill_raw_events(db, jsonl_files=jsonl_files, since_ts=since_ts)
    counts: dict[str, int] = {"raw_events": raw_count}
    if also_rebuild:
        counts.update(rebuild(db, config=config))
    return counts


def compact(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    config: dict | None = None,
    and_prune: bool = False,
) -> dict[str, int]:
    """Sweep old ``raw_events`` rows into per-session retention summaries.

    Reads ``analytics.retention.raw_event_max_age_days`` (default 90) from
    *config*. Groups eligible (uncompacted, past-cutoff) ``raw_events`` rows by
    ``session_id`` and inserts one ``kind='retention'`` ``summary_nodes`` row
    per session — a deterministic one-liner; this lifecycle path makes no
    host-CLI call, unlike the LLM-backed ``history.compaction`` feature
    (:func:`_compact_sessions`, which uses ``kind='condensed'`` — a distinct
    kind so the two features' dedup indexes never collide). Marks the swept
    rows ``compacted=1`` with ``summary_node_id`` set so :func:`prune` can
    delete them safely later. Idempotent via
    ``idx_summary_nodes_retention_dedup``.

    If *and_prune*, calls :func:`prune` afterward and folds its deleted-row
    count into the return value.
    """
    from little_loops.config.features import RetentionConfig

    raw = (config or {}).get("analytics", {}).get("retention", {})
    retention_cfg = RetentionConfig.from_dict(raw)
    result: dict[str, int] = {"compacted_rows": 0, "summary_nodes": 0, "pruned_rows": 0}

    if retention_cfg.raw_event_max_age_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=retention_cfg.raw_event_max_age_days)
        cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

        conn = _pkg.connect(db)
        try:
            rows = conn.execute(
                "SELECT id, ts, session_id FROM raw_events"
                " WHERE ts < ? AND compacted = 0 ORDER BY session_id, ts",
                (cutoff_str,),
            ).fetchall()

            by_session: dict[str | None, list[sqlite3.Row]] = {}
            for row in rows:
                by_session.setdefault(row["session_id"], []).append(row)

            now = _now()
            for session_id, session_rows in by_session.items():
                ts_start = session_rows[0]["ts"]
                ts_end = session_rows[-1]["ts"]
                summary = (
                    f"Compacted {len(session_rows)} raw event(s) for session "
                    f"{session_id or '(unknown)'} between {ts_start} and {ts_end}."
                )
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO summary_nodes"
                    "(kind, content, tokens, session_id, ts_start, ts_end, created_at)"
                    " VALUES('retention', ?, ?, ?, ?, ?, ?)",
                    (summary, _estimate_tokens(summary), session_id, ts_start, ts_end, now),
                )
                if cursor.rowcount:
                    summary_node_id = cursor.lastrowid
                    result["summary_nodes"] += 1
                else:
                    existing = conn.execute(
                        "SELECT id FROM summary_nodes"
                        " WHERE kind='retention' AND session_id IS ?"
                        " AND ts_start = ? AND ts_end = ?",
                        (session_id, ts_start, ts_end),
                    ).fetchone()
                    summary_node_id = existing[0] if existing else None

                ids = [r["id"] for r in session_rows]
                placeholders = ",".join(["?"] * len(ids))
                conn.execute(
                    f"UPDATE raw_events SET compacted = 1, summary_node_id = ?"
                    f" WHERE id IN ({placeholders})",
                    [summary_node_id, *ids],
                )
                result["compacted_rows"] += len(ids)

            conn.commit()
        finally:
            conn.close()

    if and_prune:
        prune_result = prune(db, config=config)
        result["pruned_rows"] = sum(prune_result.get("deleted", {}).values())

    return result


def prune(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    config: dict | None = None,
    dry_run: bool = False,
) -> dict:
    """Delete compacted ``raw_events`` rows older than max-age, then VACUUM.

    Operates on ``raw_events`` only (ENH-2581): rows must already be marked
    ``compacted=1`` by :func:`compact` before ``prune()`` will delete them.
    ``prune()`` never mutates ``search_index`` or the cache tables —
    :func:`rebuild` owns re-deriving those. ``cli_events``/``file_events``/
    ``test_run_events`` are outside ``raw_events``'s scope for this issue and
    are no longer pruned by this path.

    Both dual gates must be exceeded before any rows are deleted:
    - ``min_project_age_days``: project age (MIN(started_at) from sessions table)
    - ``min_db_size_mb``: DB file size on disk

    Args:
        db: Path to the history database.
        config: Project config dict (reads ``analytics.retention``). ``None`` uses defaults.
        dry_run: Count rows that would be deleted without deleting them.

    Returns:
        dict with keys:
        - ``pruned`` (bool): whether pruning ran (gates met and rows eligible)
        - ``gate_unmet`` (list[str]): human-readable reason for each unmet gate
        - ``project_age_days`` (int): measured project age
        - ``db_size_mb`` (float): DB file size in MB
        - ``deleted`` (dict[str, int]): ``{"raw_events": count}`` (actual or projected)
        - ``vacuumed`` (bool): whether VACUUM ran (always False in dry_run)
    """
    from little_loops.config.features import RetentionConfig

    raw = (config or {}).get("analytics", {}).get("retention", {})
    retention_cfg = RetentionConfig.from_dict(raw)

    db_path = Path(db)
    result: dict = {
        "pruned": False,
        "gate_unmet": [],
        "project_age_days": 0,
        "db_size_mb": 0.0,
        "deleted": {},
        "vacuumed": False,
    }

    conn = _pkg.connect(db)
    try:
        # Gate 1: project age — MIN(started_at) from sessions
        row = conn.execute("SELECT MIN(started_at) FROM sessions").fetchone()
        oldest_ts = row[0] if row and row[0] else None
        if oldest_ts:
            try:
                oldest_dt = datetime.fromisoformat(oldest_ts.replace("Z", "+00:00"))
                project_age_days = (datetime.now(UTC) - oldest_dt).days
            except ValueError:
                project_age_days = 0
        else:
            project_age_days = 0
        result["project_age_days"] = project_age_days

        # Gate 2: DB file size
        db_size_mb = db_path.stat().st_size / (1024 * 1024) if db_path.exists() else 0.0
        result["db_size_mb"] = round(db_size_mb, 2)

        # Evaluate gates
        gates_unmet: list[str] = []
        if project_age_days < retention_cfg.min_project_age_days:
            gates_unmet.append(
                f"project age {project_age_days}d < {retention_cfg.min_project_age_days}d"
            )
        if db_size_mb < retention_cfg.min_db_size_mb:
            gates_unmet.append(f"db size {db_size_mb:.1f}MB < {retention_cfg.min_db_size_mb}MB")
        result["gate_unmet"] = gates_unmet

        if gates_unmet:
            return result

        if retention_cfg.raw_event_max_age_days is None:
            result["pruned"] = True
            return result

        cutoff = datetime.now(UTC) - timedelta(days=retention_cfg.raw_event_max_age_days)
        cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

        count_row = conn.execute(
            "SELECT COUNT(*) FROM raw_events WHERE ts < ? AND compacted = 1", (cutoff_str,)
        ).fetchone()
        deleted_count = count_row[0] if count_row else 0
        if not dry_run and deleted_count > 0:
            conn.execute("DELETE FROM raw_events WHERE ts < ? AND compacted = 1", (cutoff_str,))

        result["deleted"] = {"raw_events": deleted_count}
        result["pruned"] = True

        if not dry_run:
            conn.commit()
    finally:
        conn.close()

    # VACUUM outside the original connection to avoid transaction conflicts
    if result["pruned"] and not dry_run:
        try:
            vac_conn = sqlite3.connect(str(db_path))
            _configure_connection(vac_conn)
            vac_conn.isolation_level = None
            try:
                vac_conn.execute("VACUUM")
                result["vacuumed"] = True
            finally:
                vac_conn.close()
        except sqlite3.Error as exc:
            logger.warning("prune: VACUUM failed: %s", exc)

    return result


def record_retirement(
    db: Path | str = DEFAULT_DB_PATH,
    topic_fingerprint: str = "",
    rule_id: str = "",
    session_id: str = "",
) -> None:
    """Mark a recurring-correction cluster as addressed.

    Uses INSERT OR REPLACE so a second call for the same fingerprint updates
    the record rather than duplicating it.  ``rule_id`` should be the
    ``decisions.yaml`` entry ID (e.g. ``BEHAVIOR-001``) or ``"claude-md"``
    when the rule was written directly into CLAUDE.md.
    """
    if not topic_fingerprint:
        return
    conn = _pkg.connect(db)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO correction_retirements"
            "(topic_fingerprint, rule_id, addressed_at, session_id) VALUES (?, ?, ?, ?)",
            (topic_fingerprint, rule_id or None, _now(), session_id or None),
        )
        conn.commit()
    finally:
        conn.close()


def list_retirements(
    db: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Return all correction retirement records, newest first.

    Returns an empty list when the DB does not exist or the
    ``correction_retirements`` table has not yet been created.
    """
    db_path = Path(db)
    if not db_path.exists():
        return []
    conn = _pkg.connect(db)
    try:
        rows = conn.execute(
            "SELECT topic_fingerprint, rule_id, addressed_at, session_id"
            " FROM correction_retirements ORDER BY addressed_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
