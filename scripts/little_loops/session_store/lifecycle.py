"""Retention lifecycle and LCM session-compaction for the session store
(ENH-2890 split from session_store.py).

Covers the JSONL backfill/rebuild/compact/prune retention lifecycle
(``backfill``, ``backfill_incremental``, ``rebuild``, ``compact``, ``prune``,
``record_retirement``/``list_retirements``) plus LCM hierarchical
session-summary compaction (``compact_session``, ``compact_session_with_reasoning``
and their helpers). Depends on :mod:`little_loops.session_store.schema`
(``connect``, ``ensure_db``, ``SCHEMA_VERSION``),
:mod:`little_loops.session_store.backend` (``open_history``,
``translate_sqlite_errors`` -- VACUUM/retirement chokepoint routing, ENH-3526),
:mod:`little_loops.session_store.db` (``DEFAULT_DB_PATH``), and
:mod:`little_loops.session_store.writers` for the per-table ``_backfill_*``
helpers and raw_events pack/unpack helpers. The deferred (inside-function)
imports from ``little_loops.compaction.instant`` are preserved to break a
circular dependency: ``instant.py`` imports back from
``little_loops.session_store`` (``_call_llm_for_summary``) inside its own
function bodies, so neither module can import the other at module-load time.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import subprocess
import threading
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import little_loops.session_store as _pkg
from little_loops.host_runner import project_child_env, resolve_host
from little_loops.pii import HistorySanitizationError, sanitize_history_payload
from little_loops.session_store.backend import (
    HistoryError,
    connect_readonly,
    refuse_on_remote,
    translate_sqlite_errors,
)
from little_loops.session_store.db import DEFAULT_DB_PATH, resolve_history_target
from little_loops.session_store.schema import SCHEMA_VERSION
from little_loops.session_store.sessions import (
    SessionHandle,
    handles_from_paths,
    iter_events,
)
from little_loops.session_store.targets import HistoryTarget, LocalTarget
from little_loops.session_store.usage_proof import (
    RETENTION_LIMIT,
    retention_reasons,
)
from little_loops.session_store.usage_proof_scope import (
    UsageProofLimit,
    collect_usage_proof_scope,
    inspect_scope,
)
from little_loops.session_store.usage_replay import ReplayReport, release_safe_holds
from little_loops.session_store.usage_source_state import (
    REFUSAL_CODES,
    AcquisitionWitness,
    SourceScope,
    has_prior_semantic_success,
    pending_obligations,
    read_source_head,
    storage_available,
)
from little_loops.session_store.usage_source_tracking import (
    RETRYABLE_USAGE_REASONS,
    Attempt,
    account_physical_lines,
    begin_attempt,
    finalize_source_refresh,
    has_sticky_rejection,
    record_failure_only,
    record_rejections,
    record_replay_outcomes,
    resolve_cache_obligations,
    resolve_usage_obligations,
    retained_proof_is_clean,
    stage_raw_only_source,
    stage_source_acquisition,
    sticky_rejection_lines,
    verify_claude_prefix,
)
from little_loops.session_store.writers import (
    SkillReplaySurvivor,
    UsageReplayHolds,
    UsageSearchScope,
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
    _index,
    _iter_events,
    _now,
    _pack_payload,
    _parse_aware_ts,
    _reconcile_usage_search,
    _unpack_payload,
    host_layout_for,
    load_usage_replay_holds,
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
            env=project_child_env(inv),
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
            "(see LL_HOST_CLI / orchestration.host_cli).",
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

    Raw codex payloads (every subtype except the exec calls
    :class:`~little_loops.session_store.codex.CodexNormalizer` normalizes,
    ENH-3433) and kimi-code payloads carry no ``sessionId`` field of their
    own (ENH-3422 D3 — their id lives only in ``raw_events.session_id``,
    filled at ingest via ``handle.session_id``), so the cursor path also
    falls back to that column directly for any source the record-content
    pass above found nothing for.
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
    if isinstance(source, sqlite3.Cursor):
        for source_path, session_id in conn.execute(
            "SELECT DISTINCT source_path, session_id FROM raw_events WHERE session_id IS NOT NULL"
        ):
            if source_path in seen:
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                (str(session_id), source_path),
            )
            count += cur.rowcount
            seen.add(source_path)
    return count


_REMOTE_INSERT_CHUNK = 200
_REMOTE_RAW_INSERT = (
    "INSERT OR IGNORE INTO raw_events"
    "(ts, session_id, host, host_basis, source_path, line_no, ordinal, event_type,"
    " raw_line, parsed_json, usage_contract)"
    " SELECT ?, ?, ?, 'handle', ?, ?, ?, ?, ?, ?, ?"
    " WHERE NOT EXISTS (SELECT 1 FROM raw_events WHERE session_id IS ? AND line_no = ?)"
)


def _watermark_key(db: Path | str) -> str:
    """The ``meta`` key holding the ingestion watermark for the store *db* resolves to.

    SQLite keeps the single global ``last_raw_event_ts``. A shared remote store keeps one key
    per machine: a global key would let one machine's progress silently skip another
    machine's older, not-yet-ingested transcripts.
    """
    from little_loops.session_store.db import resolve_history_target
    from little_loops.session_store.libsql import machine_id
    from little_loops.session_store.targets import RemoteTarget

    if isinstance(resolve_history_target(db), RemoteTarget):
        return f"last_raw_event_ts:{machine_id()}"
    return "last_raw_event_ts"


def _backfill_raw_events(conn: sqlite3.Connection, handles: list[SessionHandle]) -> int:
    """Parse *handles* via ``iter_events`` and INSERT OR IGNORE one row per event.

    Idempotent via the ``(source_path, line_no)`` dedup index. ``event_type``
    is the event's own ``type`` (``"user"``, ``"assistant"``, ...) — one
    source event can feed multiple derived cache rows (e.g. an assistant
    event yields both an assistant_messages row and zero-or-more tool_events
    rows), so raw_events stores the event payload rather than a cache-table
    kind (ENH-2581).

    ``raw_events.host`` is each ``handle.host`` (BUG-3542), never the ambient
    host of the ingesting process, and ``host_basis='handle'`` marks the row as
    verified. ``ll-session backfill --host qwen`` (ENH-3166) still stamps qwen
    because ``handles_from_paths`` builds its handles with that host. Legacy
    rows keep their host and a NULL ``host_basis``; re-ingestion is
    ``INSERT OR IGNORE`` and never certifies them.

    ENH-3422 (D1-D6): every host is ingested through the single
    ``iter_events``/``_PARSERS`` dispatch instead of per-host ``HostLayout``
    branching. ``line_no`` comes from ``event.line_no`` (real file line
    number for per-line hosts; enumeration index for gemini/omp, matching
    prior behavior). ``session_id`` falls back to ``handle.session_id`` when
    the payload carries none (codex/kimi, D3). ``raw_line``/``parsed_json``
    are both the re-serialized, history-policy-sanitized ``event.payload`` (D6,
    ENH-3751) — no longer verbatim for per-line hosts. Sanitization runs once per
    event, under the handle's verified host and the event's type, before
    serialization, packing, or queuing a remote batch; metadata and usage
    qualification still come from the original event. A sanitizer failure
    propagates (``HistorySanitizationError``) and persists nothing further. ENH-3745:
    a failure is tagged with its source (``ll_failed_source``) so the public owner, after
    its full rollback, can persist a content-free diagnostic. Physical-line accounting of
    rejected lines is the owner's call (:func:`_account_ingested_sources`).
    """

    remote = not hasattr(conn, "create_function")
    count = 0
    pending: list[tuple[Any, ...]] = []

    def _flush() -> int:
        # Remote (FEAT-3535): one atomic batch per chunk instead of a round trip per event,
        # and dedup on (session_id, line_no) so a copied session file at another path is not
        # ingested twice (the (source_path, line_no) unique index cannot catch it).
        if not pending:
            return 0
        added = conn.executemany(_REMOTE_RAW_INSERT, pending).rowcount
        pending.clear()
        return int(added)

    for handle in handles:
        source_path = str(handle.path)
        try:
            count += _ingest_handle_events(conn, handle, remote, pending, _flush)
        except Exception as exc:
            exc.ll_failed_source = source_path  # type: ignore[attr-defined]
            raise
    if remote:
        count += _flush()
    return count


def _ingest_handle_events(
    conn: sqlite3.Connection,
    handle: SessionHandle,
    remote: bool,
    pending: list[tuple[Any, ...]],
    flush: Callable[[], int],
) -> int:
    """Insert one handle's sanitized events (the body of :func:`_backfill_raw_events`)."""
    from little_loops.session_store.claude_usage import claude_transcript_contract

    count = 0
    source_path = str(handle.path)
    for event in iter_events(handle):
        serialized = json.dumps(
            sanitize_history_payload(
                event.payload, host=handle.host, event_type=event.type or "unknown"
            ).payload
        )
        session_id = event.payload.get("sessionId") or handle.session_id
        usage_contract = claude_transcript_contract(
            event.payload, host=handle.host, host_basis="handle"
        )
        packed = _pack_payload(serialized)
        if remote:
            pending.append(
                (
                    event.timestamp,
                    session_id,
                    handle.host,
                    source_path,
                    event.line_no,
                    event.ordinal,
                    event.type or "unknown",
                    packed,
                    packed,
                    usage_contract,
                    session_id,
                    event.line_no,
                )
            )
            if len(pending) >= _REMOTE_INSERT_CHUNK:
                count += flush()
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO raw_events"
            "(ts, session_id, host, host_basis, source_path, line_no, ordinal, event_type,"
            " raw_line, parsed_json, usage_contract)"
            " VALUES(?, ?, ?, 'handle', ?, ?, ?, ?, ?, ?, ?)",
            (
                event.timestamp,
                session_id,
                handle.host,
                source_path,
                event.line_no,
                event.ordinal,
                event.type or "unknown",
                packed,
                packed,
                usage_contract,
            ),
        )
        count += cur.rowcount
    return count


_ACCOUNTED_HOSTS = frozenset({"claude-code", "codex"})


@dataclass(frozen=True)
class _IngestSnapshot:
    """What a raw-only ingestion saw before it wrote: prior row counts and source stats."""

    rows: dict[str, int]
    stats: dict[str, tuple[int, int, int, int] | None]


def _ingest_snapshot(conn: sqlite3.Connection, handles: list[SessionHandle]) -> _IngestSnapshot:
    """Snapshot pre-ingest row counts and file stats of line-oriented handles."""
    rows: dict[str, int] = {}
    stats: dict[str, tuple[int, int, int, int] | None] = {}
    if not hasattr(conn, "create_function"):  # remote stores have no physical-line semantics
        return _IngestSnapshot(rows, stats)
    for handle in handles:
        if handle.host not in _ACCOUNTED_HOSTS:
            continue
        key = str(handle.path)
        rows[key] = conn.execute(
            "SELECT COUNT(*) FROM raw_events WHERE source_path = ?", (key,)
        ).fetchone()[0]
        try:
            st = handle.path.stat()
            stats[key] = (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)
        except OSError:
            stats[key] = None
    return _IngestSnapshot(rows, stats)


def _stage_raw_only_acquisition(
    conn: sqlite3.Connection,
    handle: SessionHandle,
    accounting: Any,
    snapshot: _IngestSnapshot,
) -> None:
    """Stage the verified acquisition of a just-ingested, cleanly accounted source.

    Needs all of: canonical coverage (a pristine first ingest read the whole file from zero;
    a previously ingested *tracked* source must re-verify its whole retained prefix),
    verified native identity (one stored session equal to the handle's) and source
    stability (the file did not change while it was read). An untracked source with
    historical rows gains no head: headless raw never acquires fabricated lineage.
    """
    key = str(handle.path)
    before = snapshot.stats.get(key)
    if before is None:
        return
    try:
        final = handle.path.stat()
    except OSError:
        return
    if (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns) != before:
        return
    if final.st_size != accounting.offset:
        return
    sessions = {
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT session_id FROM raw_events WHERE source_path = ?", (key,)
        )
    }
    if sessions != {handle.session_id}:
        return
    pristine = snapshot.rows.get(key, 0) == 0
    tracked = read_source_head(conn, key) is not None
    if not pristine:
        if not tracked:
            return
        if handle.host == "claude-code":
            if not verify_claude_prefix(conn, handle.path, accounting.offset):
                return
        else:
            try:
                existing = {
                    row[0]
                    for row in conn.execute(
                        "SELECT line_no FROM raw_events WHERE source_path = ?", (key,)
                    )
                }
                _certify_codex_stored_source(conn, handle, handle.path, handle.session_id, existing)
            except RuntimeError:
                return
    try:
        with handle.path.open("rb") as stream:
            digest = _source_tail_digest(stream, accounting.offset)
    except OSError:
        return
    attempt = begin_attempt(conn, key, _USAGE_DERIVE_VERSION, host=handle.host)
    attempt = _with_verified_session(attempt, handle.host, handle.session_id)
    stage_raw_only_source(
        conn,
        attempt,
        accounting=accounting,
        witness=AcquisitionWitness(
            final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns, digest
        ),
        coverage_proved=True,
    )


def _account_ingested_source(
    conn: sqlite3.Connection, handle: SessionHandle, snapshot: _IngestSnapshot | None = None
) -> None:
    """Record a just-ingested source's rejected lines and stage its verified acquisition.

    Source-local evidence (ENH-3745/3770) alongside the successful inserts; the caller owns
    commit/rollback. Only line-oriented hosts have physical-line semantics; a missing or
    unreadable file simply records nothing.
    """
    if handle.host not in _ACCOUNTED_HOSTS or not storage_available(conn):
        return
    try:
        accounting = account_physical_lines(handle.path)
    except OSError:
        return
    if accounting.rejected:
        attempt = begin_attempt(conn, str(handle.path), _USAGE_DERIVE_VERSION, host=handle.host)
        if attempt is not None:
            record_rejections(conn, attempt, accounting)
        return
    if snapshot is not None and accounting.clean:
        _stage_raw_only_acquisition(conn, handle, accounting, snapshot)


def _account_ingested_sources(
    conn: sqlite3.Connection,
    handles: list[SessionHandle],
    snapshot: _IngestSnapshot | None = None,
) -> None:
    """Record every ingested source's rejected lines in the caller's open transaction."""
    if not hasattr(conn, "create_function"):  # remote stores have no physical-line semantics
        return
    for handle in handles:
        _account_ingested_source(conn, handle, snapshot)


def _note_ingestion_failure(
    db: Path | str, exc: BaseException, paths: list[tuple[Path, str]]
) -> None:
    """After a public ingestion owner fully rolled back, persist a content-free diagnostic.

    *paths* are the ``(source, host)`` candidates of the failed call. A sanitizer refusal is
    attributed to the tagged source (``ll_failed_source``); a decode failure to every
    candidate whose physical accounting shows one -- including header acquisition that
    failed before any handle existed, with explicitly unknown session scope. Best effort:
    the original exception always propagates and failure to record never becomes success.
    """
    chain = [exc, exc.__cause__, exc.__context__]
    refused = next((e for e in chain if isinstance(e, HistorySanitizationError)), None)
    decode = any(isinstance(e, UnicodeDecodeError) for e in chain)
    if refused is None and not decode:
        return
    try:
        conn = _pkg.connect(db)
    except Exception:
        return
    try:
        targets: list[tuple[Path, str]] = []
        failed = getattr(exc, "ll_failed_source", None)
        if refused is not None:
            targets = [(p, h) for p, h in paths if str(p) == failed]
        else:
            targets = list(paths)
        attempts = [
            (path, begin_attempt(conn, str(path), _USAGE_DERIVE_VERSION, host=host))
            for path, host in targets
            if host in _ACCOUNTED_HOSTS
        ]
    finally:
        conn.close()
    for path, attempt in attempts:
        if refused is not None:
            record_failure_only(
                lambda: _pkg.connect(db),
                attempt,
                reason="sanitization_refused",
                refusal_code=_refusal_code(refused),
            )
            continue
        reason, line, offset = _first_rejected(path)
        if line is None:
            continue  # this candidate had no physical decode failure of its own
        record_failure_only(
            lambda: _pkg.connect(db),
            attempt,
            reason=reason,
            first_line_no=line,
            first_offset=offset,
        )


def backfill_raw_events(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    jsonl_files: list[Path] | None = None,
    handles: list[SessionHandle] | None = None,
    since_ts: float | None = None,
    host: str | None = None,
) -> int:
    """Parse session sources and INSERT OR IGNORE rows into raw_events.

    Idempotent via ``INSERT OR IGNORE`` on ``(source_path, line_no)``. Accepts
    either *jsonl_files* (widened internally via ``handles_from_paths``,
    ENH-3422 D4 — the codex CLI path has no project folder to glob, so it
    must pass *handles* directly) or *handles*; passing both raises
    ``ValueError``, passing neither ingests nothing. Filters by
    ``handle.updated_at`` >= *since_ts* when given (``None`` processes every
    provided source). Updates the ``last_raw_event_ts`` meta key on success —
    the single watermark that replaces ``last_backfill_ts`` /
    ``last_backfill_ts_assistant_messages`` / ``last_backfill_ts_skill_events``
    (ENH-2581). *host* names the host whose transcripts are ingested for the
    ``raw_events.host`` column (ENH-3166), and the host used to synthesize
    handles when widening *jsonl_files*; omitted, the ambient host is used.
    Returns the count of new rows inserted.
    """
    if jsonl_files is not None and handles is not None:
        raise ValueError("backfill_raw_events: pass jsonl_files or handles, not both")
    effective_host = host if host is not None else resolve_host().name
    if handles is None:
        try:
            handles = handles_from_paths(jsonl_files or [], effective_host)
        except UnicodeDecodeError as exc:
            # Path-to-handle/header acquisition failed before a handle or transaction exists.
            _note_ingestion_failure(db, exc, [(Path(p), effective_host) for p in jsonl_files or []])
            raise
    candidates = [(h.path, h.host) for h in handles]
    conn = _pkg.connect(db)
    try:
        filtered = (
            [h for h in handles if h.updated_at >= since_ts] if since_ts is not None else handles
        )
        snapshot = _ingest_snapshot(conn, filtered)
        count = _backfill_raw_events(conn, filtered)
        _account_ingested_sources(conn, filtered, snapshot)
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_watermark_key(db), _now()),
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        _note_ingestion_failure(db, exc, candidates)
        raise
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
    refuse_on_remote(db, "recompress")
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
        vac = _pkg.open_history(db_path)
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
# issue_snapshots/hook_events/harness_events/harness_admissions/prompt_opt_events
# — those have no raw_events-backed _backfill_* path (they're either
# live-write-only or sourced from .issues/.loops/git log, out of this issue's
# scope; see ENH-2581 management plan). Wiping them here with no re-derivation
# path would be unrecoverable data loss. hook_events and harness_events in
# particular have no transcript-JSONL source at all (ENH-2506, ENH-2739);
# harness_admissions (ENH-3406) is append-only audit data with the same
# no-source-to-replay-from property.
# prompt_opt_events does get JSONL-sourced enrichment (ENH-2498's
# _backfill_prompt_opt), but as a non-destructive UPDATE-only pass called
# separately below — it must NOT be added here or to _REBUILD_SEARCH_KINDS,
# since a wipe would destroy the live offer rows it enriches.
# usage_events is the one member that also receives live writes
# (record_usage_event, channel = 'live'); it is wiped only for replayable
# channels ('transcript', ENH-3532 'rollout') via _REBUILD_TABLE_PREDICATES
# (BUG-3530). run_id/state are NOT valid discriminators: replay derives run_id.
# summary_nodes likewise keeps ``kind = 'retention'`` rows (BUG-3715): compact()
# writes them deterministically and prune() then deletes their source raw_events,
# so replay can neither regenerate them nor would it ever write them. summary_spans
# stays fully wiped — retention nodes have no spans, and spans reference
# message_events ids that this rebuild replaces.
# tool_events and user_corrections are likewise mixed-origin (BUG-3761): the
# PostToolUse hook writes byte-bearing tool rows and the prompt hook writes
# corrections directly, with no raw event to replay. Replay always binds NULL
# bytes_in/bytes_out (``_backfill_tool_events``) and the reserved source
# 'backfill' (``mine_corrections_from_messages``), so those signals classify a
# row as replayable; everything else survives and is re-indexed in ``rebuild()``.
# skill_events is mixed-origin too (BUG-3766): the prompt hook and ``ll-action`` write
# live rows (the latter with completion fields) that replay cannot recreate. Unlike tools
# and corrections there is no writer-distinguishing signal in the row, so v61 added an
# ``origin`` column; only ``'transcript'`` rows are wiped.
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

_REBUILD_TABLE_PREDICATES = {
    # ENH-3770: ``rebuild`` never deletes committed usage observations. It compares every
    # retained request with them (guarded reconciliation) and only adds, qualifies or
    # demotes what it can prove; a row's identity, numbers, stored cost and timestamps
    # survive. The predicate matches no row, so the generic wipe loop skips the table.
    "usage_events": "0",
    "summary_nodes": "kind IS NOT 'retention'",
    "tool_events": "bytes_in IS NULL AND bytes_out IS NULL",
    "user_corrections": "source = 'backfill'",
    "skill_events": "origin IS 'transcript'",
}

_REBUILD_SEARCH_KINDS = ("tool", "message", "skill", "correction", "usage")

# Bump when a usage normalizer's meaning changes, even without a DDL migration.
# A mismatch causes one atomic replay of historical raw rows before tail work.
_USAGE_DERIVE_VERSION = "enh3651-v1"

# Bump when a non-usage ``rebuild()`` output or selection changes: parser/replay
# semantics, ``_REBUILD_TABLES`` or search-index derivation, corrections,
# summaries, or prompt-opt enrichment. Usage-only derivation changes bump
# ``_USAGE_DERIVE_VERSION`` instead (incremental path), never this constant.
# A mismatch makes every store rebuild once (a full wipe-and-replay); the
# SessionStart size gate (:func:`rebuild_disposition`) defers that replay on a
# large store. Compared with ``!=`` (an identifier, never ordered).
# ``test_enh3678_rebuild_derive_gate.py`` fails when the derivation changes without a bump.
REBUILD_DERIVE_VERSION = "bug3766-v1"

# Stores last rebuilt at or after this ``SCHEMA_VERSION`` but carrying no
# ``rebuild_derive_version`` stamp were derived under schema-58 semantics, which
# ``_FROZEN_LEGACY_DERIVE_VERSION`` names. A floor rather than ``== 58`` so a
# ``SCHEMA_VERSION`` bump that lands first does not force a rebuild.
_LEGACY_REBUILD_FLOOR = 58
# A frozen literal, NEVER an alias of ``REBUILD_DERIVE_VERSION``: an alias would
# move with every bump and mark unstamped legacy stores current under a newer
# derivation. Pinned by ``test_frozen_legacy_derive_version_literal``.
_FROZEN_LEGACY_DERIVE_VERSION = "enh3678-v1"

# Busy timeout for ``rebuild_needed``'s read-only open: well inside the 5 s
# SessionStart hook budget so a contended store maps to ``unknown`` instead of
# getting the hook killed before it spawns the incremental worker.
_REBUILD_NEEDED_TIMEOUT = 0.5


@dataclass(frozen=True)
class RebuildState:
    """Whether the derived tables need a ``rebuild()`` (see :func:`rebuild_needed`).

    ``reason`` is one of: ``derive_match``, ``legacy_floor`` (both ``current``);
    ``derive_mismatch``, ``legacy_below_floor``, ``no_stamp``, ``db_missing``
    (all ``stale``); ``read_error``, ``remote`` (both ``unknown``).
    """

    status: Literal["current", "stale", "unknown"]
    reason: str


def rebuild_needed(db: Path | str | HistoryTarget = DEFAULT_DB_PATH) -> RebuildState:
    """Decide whether *db* needs a ``rebuild()`` under the current derive version.

    Opens the store with the strict read-only ``connect_readonly`` (never creates or
    migrates, short busy timeout). ``unknown`` means the store could not be read (any
    open/query failure, a lock timeout) or is remote; callers must not rebuild on it.
    A missing DB or missing stamp is ``stale``.
    """
    try:
        target = resolve_history_target(db)
        if not isinstance(target, LocalTarget):
            return RebuildState("unknown", "remote")
        if not target.path.exists():
            return RebuildState("stale", "db_missing")
        conn = connect_readonly(target, timeout=_REBUILD_NEEDED_TIMEOUT)
        try:
            rows = dict(
                conn.execute(
                    "SELECT key, value FROM meta "
                    "WHERE key IN ('rebuild_derive_version', 'last_rebuild_version')"
                ).fetchall()
            )
        finally:
            conn.close()
    except Exception:
        return RebuildState("unknown", "read_error")

    stamped = rows.get("rebuild_derive_version")
    if stamped is not None and stamped != "":
        if isinstance(stamped, str):
            if stamped == REBUILD_DERIVE_VERSION:
                return RebuildState("current", "derive_match")
            return RebuildState("stale", "derive_mismatch")
        return RebuildState("stale", "legacy_below_floor")
    last = rows.get("last_rebuild_version")
    if last is None or last == "":
        return RebuildState("stale", "no_stamp")
    try:
        last_version = int(last)
    except (ValueError, TypeError):
        return RebuildState("stale", "legacy_below_floor")
    if last_version < _LEGACY_REBUILD_FLOOR:
        return RebuildState("stale", "legacy_below_floor")
    if _FROZEN_LEGACY_DERIVE_VERSION == REBUILD_DERIVE_VERSION:
        return RebuildState("current", "legacy_floor")
    return RebuildState("stale", "derive_mismatch")


# Largest stale store (main DB bytes + WAL bytes, filesystem sizes) whose replay the
# SessionStart hook's detached worker starts automatically; a larger one is
# ``pending`` until an explicit ``ll-session rebuild``. Bytes, main plus WAL: a
# conservative proxy that can overcount overwritten WAL frames or free pages.
# Calibrated offline (ENH-3698) on synthetic Claude stores replayed with
# ``rebuild(db, config=None)``: ~1 KiB and ~50 us per raw row, i.e. about 3 s at 60 MiB,
# 9 s at 180 MiB, 22 s at 450 MiB (linear). 64 MiB keeps replay near the 5 s
# operational target with ~1.5x margin. Not a duration guarantee -- CLI telemetry waits
# only 250 ms (ENH-3679), so even a short replay can drop concurrent events.
REBUILD_AUTO_MAX_BYTES = 2**26


@dataclass(frozen=True)
class RebuildDisposition:
    """Whether an automatic ``rebuild()`` may run (see :func:`rebuild_disposition`).

    ``state`` is the metadata verdict from :func:`rebuild_needed` (its ``reason`` is
    preserved for every outcome). ``size_bytes`` is main DB plus WAL bytes, ``0`` for a
    missing store, ``None`` when no probe ran or it failed. ``outcome``: ``auto``
    (stale, within :data:`REBUILD_AUTO_MAX_BYTES`), ``pending`` (stale, above it),
    ``none`` (current or unknown: nothing to rebuild or no basis to), ``unknown_size``
    (stale, but a size probe failed -- never treated as small).
    """

    state: RebuildState
    size_bytes: int | None
    outcome: Literal["auto", "pending", "none", "unknown_size"]


def _store_bytes(path: Path) -> int | None:
    """Main DB plus ``-wal`` bytes of *path* (a missing file counts 0), else ``None``.

    ``None`` means a probe failed with an ``OSError`` other than ``FileNotFoundError``.
    ``-shm`` is ignored: it is a shared-memory index, not committed data.
    """
    total = 0
    for candidate in (path, path.with_name(path.name + "-wal")):
        try:
            total += candidate.stat().st_size
        except FileNotFoundError:
            continue
        except OSError:
            return None
    return total


def rebuild_disposition(db: Path | str | HistoryTarget = DEFAULT_DB_PATH) -> RebuildDisposition:
    """Decide whether an automatic ``rebuild()`` of *db* may run.

    Resolves one target, asks :func:`rebuild_needed` about that exact target, and only
    for a stale local store measures its size with filesystem stats at the same
    resolved path. Report-only: never creates, migrates, checkpoints or queries rows,
    and never raises (a resolution/read failure is ``unknown``/``read_error``, a size
    probe failure ``unknown_size``). Remote, current and unknown stores are never
    stat'ed.
    """
    try:
        target = resolve_history_target(db)
        state = rebuild_needed(target)
    except Exception:
        return RebuildDisposition(RebuildState("unknown", "read_error"), None, "none")
    if state.status != "stale" or not isinstance(target, LocalTarget):
        return RebuildDisposition(state, None, "none")
    if state.reason == "db_missing":
        return RebuildDisposition(state, 0, "auto")
    size = _store_bytes(target.path)
    if size is None:
        return RebuildDisposition(state, None, "unknown_size")
    return RebuildDisposition(state, size, "auto" if size <= REBUILD_AUTO_MAX_BYTES else "pending")


def rebuild_compaction_enabled(config_path: Path | None) -> bool | None:
    """Whether ``ll-session rebuild`` would run LLM compaction, or ``None`` if unknown.

    Mirrors what the manual command loads: the raw project JSON at *config_path*, with no
    ``.ll/ll.local.md`` merge. ``None`` when there is no config path or the file cannot
    be read/parsed, so callers can word the caveat conservatively.
    """
    if config_path is None:
        return None
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        enabled = raw.get("history", {}).get("compaction", {}).get("enabled", False)
    except (OSError, ValueError, AttributeError):
        return None
    return bool(enabled)


def rebuild_pending_notice(state: RebuildState, compaction: bool | None) -> str:
    """One-line user-facing notice that an automatic rebuild was deferred for size.

    *state* selects the reason-specific wording (``derive_mismatch``: rows may be mixed;
    otherwise tables may be incomplete); *compaction* is :func:`rebuild_compaction_enabled`.
    """
    if state.reason == "derive_mismatch":
        stale = "historical and live-derived rows may be mixed"
    else:
        stale = "tables may be incomplete"
    if compaction is True:
        summaries = (
            "it clears leaf/condensed summaries and regenerates them with LLM "
            "summarization inside the same transaction (history.compaction is enabled)"
        )
    elif compaction is False:
        summaries = (
            "it clears leaf/condensed summaries without regenerating them "
            "(history.compaction is disabled)"
        )
    else:
        summaries = (
            "it clears leaf/condensed summaries and, if history.compaction is enabled, "
            "regenerates them with LLM summarization inside the same transaction"
        )
    return (
        "[little-loops] History rebuild deferred: the store is above the automatic-rebuild "
        "size limit, so derived tables (sessions, tool/skill events, corrections, "
        f"summaries, search) remain out of date ({stale}). Raw event ingestion and usage "
        "derivation continue; incremental backfill does not refresh the derived tables. "
        "Optional recovery: run `ll-session rebuild` with no other ll sessions active -- "
        f"it holds the write lock for the whole replay and {summaries}."
    )


def _usage_raw_cursor(
    conn: sqlite3.Connection, where: str = "", params: tuple = ()
) -> sqlite3.Cursor:
    """Return replay rows with identity metadata in deterministic source order."""
    return conn.execute(
        "SELECT raw_line, source_path, host, host_basis, event_type, ts, "
        "session_id, line_no, ordinal, usage_contract, id FROM raw_events "
        + where
        + " ORDER BY source_path, COALESCE(ordinal, line_no), line_no, id",
        params,
    )


_SQLITE_INT_MAX = 2**63 - 1


@dataclass(frozen=True)
class _CheckpointState:
    """Validated reading of the usage derive checkpoint (ENH-3745).

    ``status`` is ``valid`` (current-version, non-negative, sequence-consistent floor),
    ``absent`` (both keys missing), or one bounded failure: ``partial`` (one key
    missing), ``version_changed``, ``invalid`` (malformed value), ``contradictory``
    (floor above the allocation sequence) or ``sequence_unprovable`` (a positive floor
    with no usable allocation sequence). ``floor`` is set only when ``valid``.
    """

    status: str
    floor: int | None = None

    @property
    def valid(self) -> bool:
        return self.status == "valid"


def _checkpoint_int(value: object) -> int | None:
    """Strict non-negative signed-64-bit integer reading of a stored metadata value."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        number = value
    elif isinstance(value, str):
        if not (value.isascii() and value.isdigit()):
            return None
        number = int(value)
    else:
        return None
    return number if 0 <= number <= _SQLITE_INT_MAX else None


def _raw_event_sequence(conn: sqlite3.Connection) -> tuple[bool, int | None]:
    """``(table_readable, seq)`` for ``raw_events``'s allocation sequence (None = no usable row)."""
    try:
        row = conn.execute("SELECT seq FROM sqlite_sequence WHERE name = 'raw_events'").fetchone()
    except sqlite3.Error:
        return False, None
    if row is None:
        return True, None
    return True, _checkpoint_int(row[0])


def _read_usage_checkpoint(conn: sqlite3.Connection) -> _CheckpointState:
    """Classify the committed usage derive checkpoint without converting unchecked text.

    The version is compared before the raw ID is converted. The allocation sequence may
    only *reject* a floor (above it) or leave a positive floor unprovable; it never
    raises a floor or proves that anything was processed.
    """
    rows = dict(
        conn.execute(
            "SELECT key, value FROM meta WHERE key IN "
            "('usage_derive_version', 'usage_derive_raw_id')"
        ).fetchall()
    )
    has_version = "usage_derive_version" in rows
    has_raw_id = "usage_derive_raw_id" in rows
    if not has_version and not has_raw_id:
        return _CheckpointState("absent")
    if has_version != has_raw_id:
        return _CheckpointState("partial")
    if rows["usage_derive_version"] != _USAGE_DERIVE_VERSION:
        return _CheckpointState("version_changed")
    floor = _checkpoint_int(rows["usage_derive_raw_id"])
    if floor is None:
        return _CheckpointState("invalid")
    readable, seq = _raw_event_sequence(conn)
    if floor > 0:
        if not readable or seq is None:
            return _CheckpointState("sequence_unprovable")
        if floor > seq:
            return _CheckpointState("contradictory")
    return _CheckpointState("valid", floor)


def _usage_bootstrap_eligible(conn: sqlite3.Connection) -> bool:
    """Whether a store with no checkpoint is pristine enough for a first-enable replay.

    Requires no replay-derived (non-live) observations, no replay holds and no prior
    successful semantic boundary. Live-only observations and ingestion-only source
    tracking, pending or failure rows do not block it.
    """
    if conn.execute("SELECT 1 FROM usage_events WHERE channel IS NOT 'live' LIMIT 1").fetchone():
        return False
    if conn.execute("SELECT 1 FROM usage_replay_holds LIMIT 1").fetchone():
        return False
    return not has_prior_semantic_success(conn)


@dataclass(frozen=True)
class _DeriveDisposition:
    """Bounded outcome of one incremental derive (ENH-3745, ENH-3770).

    ``status`` is ``derived`` (the scan ran under valid or bootstrap proof) or
    ``skipped`` (checkpoint proof is missing or unusable; nothing was touched).
    ``reason`` is a bounded checkpoint status for a skip. ``scanned_bound`` is the raw ID
    through which retained rows were actually scanned (None when skipped); it certifies
    retained *scheduling* only, never source completion or a hold release.
    ``unresolved_sources`` are the scanned sources whose guarded replay left durable
    pending work in this transaction (committed with the scan advance). ``held_skipped``
    is kept for callers and is always empty: held sources are planned, not skipped.
    """

    status: str
    count: int = 0
    reason: str | None = None
    scanned_bound: int | None = None
    held_skipped: tuple[tuple[str, int, int], ...] = ()
    unresolved_sources: frozenset[str] = frozenset()


def _publish_usage_derive_checkpoint(
    conn: sqlite3.Connection, *, prior_floor: int | None, scanned_bound: int
) -> None:
    """Commit usage version and ``max(prior validated floor, scanned bound)`` with its rows.

    The caller supplies the validated floor and the bound it actually scanned; this never
    re-queries the surviving ``MAX(raw_events.id)``, so a pruned maximum cannot lower it.
    """
    floor = max(prior_floor or 0, scanned_bound)
    for key, value in (
        ("usage_derive_version", _USAGE_DERIVE_VERSION),
        ("usage_derive_raw_id", str(floor)),
    ):
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def _cache_pending_sources(conn: sqlite3.Connection) -> list[str]:
    """Sources with an outstanding parser-derived cache obligation."""
    if not storage_available(conn):
        return []
    return [
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT source_path FROM usage_source_pending "
            "WHERE raw_cache_pending = 1 AND kind = 'refresh' ORDER BY source_path"
        )
    ]


def _cache_coverage_accounted(conn: sqlite3.Connection, source: str) -> bool:
    """Whether every retained raw row of *source* was a recognizable record.

    The cache writers skip undecodable payloads silently, so an unreadable row is the one
    thing a replay cannot prove it consumed; any such row keeps the cache obligation.
    """
    for (raw_line,) in conn.execute(
        "SELECT raw_line FROM raw_events WHERE source_path = ?", (source,)
    ):
        try:
            payload = json.loads(_unpack_payload(raw_line))
        except (json.JSONDecodeError, TypeError, ValueError):
            return False
        if not isinstance(payload, dict):
            return False
    return True


def _set_usage_derive_checkpoint(
    conn: sqlite3.Connection,
    state: _CheckpointState | None = None,
    *,
    bootstrap: bool = True,
    report: ReplayReport | None = None,
) -> bool:
    """Persist the replay's unresolved scopes, then stamp the checkpoint under the safety rule.

    *state* is the checkpoint reading taken before the replay mutated anything. A valid
    floor is carried forward; an absent one is stamped only when *bootstrap* says the
    store was pristine. Missing/invalid/version-changed established proof stays untouched
    and returns False. Unresolved scopes of a full replay (*report*) commit with it, and a
    source whose replay was clean resolves its outstanding usage work (ENH-3770).
    """
    if report is not None:
        record_replay_outcomes(conn, _USAGE_DERIVE_VERSION, report.outcomes.values())
        incomplete = report.incomplete_sources
        # A full rebuild replayed every retained row, so any outstanding usage work whose
        # source ended clean is resolved -- even a source with no usage-bearing record.
        for source in sorted(set(_retry_sources(conn)) - incomplete):
            resolve_usage_obligations(conn, source)
        _release_held_sources(conn)
        # A full rebuild just replayed every retained raw row into the deterministic
        # parser-derived caches (``max_sessions`` limits only summary compaction), so the
        # cache component of a parser refresh is consumed -- unless a retained row could not
        # be accounted for at all.
        for source in _cache_pending_sources(conn):
            if _cache_coverage_accounted(conn, source):
                resolve_cache_obligations(conn, source)
    state = state if state is not None else _read_usage_checkpoint(conn)
    unusable = (state.status == "absent" and not bootstrap) or state.status not in {
        "valid",
        "absent",
    }
    if unusable:
        # A full rebuild replayed the whole retained population: it may repair an
        # established unusable checkpoint, but only under the complete repair contract and
        # only to the bound it actually scanned.
        bound = _checkpoint_repairable(conn, report) if report is not None else None
        if bound is None:
            return False
        _publish_usage_derive_checkpoint(conn, prior_floor=None, scanned_bound=bound)
        return True
    max_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM raw_events").fetchone()[0]
    _publish_usage_derive_checkpoint(conn, prior_floor=state.floor, scanned_bound=max_id)
    return True


def _usage_checkpoint_snapshot(
    conn: sqlite3.Connection,
) -> tuple[_CheckpointState, bool, ReplayReport]:
    """The checkpoint reading, bootstrap eligibility and a fresh replay report.

    Taken before a replay mutates usage; the report collects the replay's unresolved scopes.
    """
    state = _read_usage_checkpoint(conn)
    return state, state.status == "absent" and _usage_bootstrap_eligible(conn), ReplayReport()


_RETRY_SIGNATURE_KEY = "usage_retry_signature"


def _retry_sources(conn: sqlite3.Connection) -> list[str]:
    """Sources with an outstanding replay-resolvable usage obligation in the current generation."""
    if not storage_available(conn):
        return []
    marks = ", ".join("?" for _ in RETRYABLE_USAGE_REASONS)
    return [
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT p.source_path FROM usage_source_pending p "
            "JOIN usage_source_state s ON s.source_path = p.source_path "
            "AND s.generation_id = p.generation_id AND s.derive_version = p.derive_version "
            "WHERE p.usage_pending = 1 AND p.kind IN ('derive_gap', 'refresh') "
            f"AND p.reason IN ({marks}) ORDER BY p.source_path",
            sorted(RETRYABLE_USAGE_REASONS),
        )
    ]


def _retry_signature(conn: sqlite3.Connection, sources: list[str]) -> str:
    """Fingerprint of everything that could newly resolve an outstanding usage obligation.

    Covers the retained rows of the outstanding sources (content-sensitive), the committed
    observation population, the holds and the obligations themselves -- and nothing else, so
    it stays cheap and never scans unrelated history.
    """
    digest = hashlib.sha256()
    marks = ", ".join("?" for _ in sources)
    for row in conn.execute(
        "SELECT id, source_path, line_no, session_id, host, usage_contract, "
        f"LENGTH(CAST(raw_line AS BLOB)) FROM raw_events WHERE source_path IN ({marks}) "
        "ORDER BY id",
        sources,
    ):
        digest.update(repr(tuple(row)).encode("utf-8"))
    usage = conn.execute(
        "SELECT COUNT(*), COALESCE(MAX(id), 0), COALESCE(SUM(provenance = 'measured'), 0), "
        "TOTAL(input_tokens), TOTAL(output_tokens), TOTAL(cost_usd), "
        "COALESCE(SUM(observation_key IS NOT NULL), 0) FROM usage_events"
    ).fetchone()
    holds = conn.execute("SELECT COUNT(*) FROM usage_replay_holds").fetchone()[0]
    pending = conn.execute(
        "SELECT obligation_id, revision FROM usage_source_pending ORDER BY obligation_id"
    ).fetchall()
    digest.update(
        json.dumps([sources, list(usage), holds, [list(r) for r in pending]]).encode("utf-8")
    )
    return digest.hexdigest()


def _retry_candidates(conn: sqlite3.Connection, exclude: set[str]) -> list[str]:
    """Sources whose outstanding usage work should be replayed now (signature-gated).

    Independent of hold presence and of whether raw ``MAX`` moved. A signature of the inputs
    that could change the outcome (retained rows of the outstanding sources, committed
    observations, holds and the obligations themselves) skips a replay that cannot differ
    from the last one, so an unresolvable scope does not re-scan on every call.
    """
    sources = _retry_sources(conn)
    if not sources:
        return []
    signature = _retry_signature(conn, sources)
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (_RETRY_SIGNATURE_KEY,)).fetchone()
    if row is not None and row[0] == signature:
        return []
    return [s for s in sources if s not in exclude]


_REPAIR_SIGNATURE_KEY = "usage_repair_signature"


def _checkpoint_repairable(conn: sqlite3.Connection, report: ReplayReport) -> int | None:
    """The freshly scanned bound ``B`` when the whole-population repair contract holds.

    Called after one transaction replayed the *entire* retained raw population (so ``B`` is
    exactly what was scanned, never ``max(untrusted prior, B)``) and persisted its source
    outcomes. Requires a usable allocation-sequence check, no unresolved usage work of any
    generation at or below ``B``, no incomplete scanned scope, and a clean post-write proof
    for every scanned source. An empty retained set or a sequence-unprovable store cannot
    repair a discarded positive floor. The scan floor certifies retained scheduling only.
    """
    ready, sequence = _raw_event_sequence(conn)
    bound = conn.execute("SELECT COALESCE(MAX(id), 0) FROM raw_events").fetchone()[0]
    if not ready or sequence is None or bound <= 0 or bound > sequence:
        return None
    if _unlinked_unheld_usage(conn):
        return None
    if report.outcomes:
        return None
    if (
        storage_available(conn)
        and conn.execute(
            "SELECT 1 FROM usage_source_pending WHERE usage_pending = 1 LIMIT 1"
        ).fetchone()
    ):
        return None
    if not all(retained_proof_is_clean(conn, source) for source in sorted(report.scanned_sources)):
        return None
    return int(bound)


def _unlinked_unheld_usage(conn: sqlite3.Connection) -> bool:
    """Whether non-live observations exist with no source link and no covering population hold.

    Such a legacy population cannot be matched to retained candidates, so replaying the whole
    retained population beside it could count the same request twice.
    """
    return (
        conn.execute(
            "SELECT 1 FROM usage_events WHERE channel IS NOT 'live' AND source_raw_event_id IS NULL "
            "AND source_path IS NULL AND NOT EXISTS (SELECT 1 FROM usage_replay_holds h WHERE "
            "h.source_path IS NULL AND (h.host = '*' OR h.host IS usage_events.host) "
            "AND (h.channel = '*' OR h.channel IS usage_events.channel)) LIMIT 1"
        ).fetchone()
        is not None
    )


def _repair_signature(conn: sqlite3.Connection, state: _CheckpointState) -> str:
    """Fingerprint of what could newly make a failed whole-population repair succeed."""
    raw = conn.execute("SELECT COUNT(*), COALESCE(MAX(id), 0) FROM raw_events").fetchone()
    usage = conn.execute(
        "SELECT COUNT(*), COALESCE(MAX(id), 0), COALESCE(SUM(provenance = 'measured'), 0), "
        "TOTAL(input_tokens), TOTAL(output_tokens) FROM usage_events"
    ).fetchone()
    holds = conn.execute("SELECT COUNT(*) FROM usage_replay_holds").fetchone()[0]
    pending = (
        conn.execute(
            "SELECT obligation_id, revision FROM usage_source_pending ORDER BY obligation_id"
        ).fetchall()
        if storage_available(conn)
        else []
    )
    meta = conn.execute(
        "SELECT key, value FROM meta WHERE key IN ('usage_derive_version', 'usage_derive_raw_id') "
        "ORDER BY key"
    ).fetchall()
    payload = json.dumps(
        [
            state.status,
            list(raw),
            list(usage),
            holds,
            [list(r) for r in pending],
            [list(m) for m in meta],
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _recover_under_unusable_checkpoint(
    conn: sqlite3.Connection, state: _CheckpointState, attempt: Attempt | None
) -> _DeriveDisposition:
    """Source recovery plus guarded whole-population repair for an established store.

    Established absent, partial, version-changed, invalid, contradictory or
    sequence-unprovable metadata is never silently restamped. Outstanding source-scoped
    usage work may still be recovered under independently valid acquisition, generation and
    action proof, leaving the metadata and its skipped reason exactly as found. Only the
    complete repair -- one transaction replaying the entire retained population, a usable
    sequence check, nothing unresolved at or below the scanned bound and every proof clean --
    publishes, and then only the freshly scanned bound.
    """
    reason = f"checkpoint_{'missing' if state.status == 'absent' else state.status}"
    search_scope = UsageSearchScope()
    report = ReplayReport()
    count = 0
    retried = _retry_candidates(conn, exclude=set())
    if retried:
        search_scope.mark(*retried)
        count += _backfill_usage_events(
            conn,
            _usage_raw_cursor(
                conn,
                f"WHERE source_path IN ({', '.join('?' for _ in retried)})",
                tuple(sorted(retried)),
            ),
            search_scope=search_scope,
            report=report,
        )
        _reconcile_usage_search(conn, search_scope)
        record_replay_outcomes(
            conn, _USAGE_DERIVE_VERSION, report.outcomes.values(), attempt=attempt
        )
        for source in retried:
            if source not in report.incomplete_sources:
                resolve_usage_obligations(conn, source)
        _store_retry_signature(conn)
    signature = _repair_signature(conn, state)
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (_REPAIR_SIGNATURE_KEY,)).fetchone()
    if (row is not None and row[0] == signature) or _unlinked_unheld_usage(conn):
        # Unchanged since the last blocked attempt -- or an unlinked, unheld legacy
        # population that a whole-population replay could double count: no repair scan.
        return _DeriveDisposition("skipped", count, reason=reason)
    full = ReplayReport()
    search_all = UsageSearchScope()
    count += _backfill_usage_events(
        conn, _usage_raw_cursor(conn), search_scope=search_all, report=full
    )
    _reconcile_usage_search(conn, search_all)
    record_replay_outcomes(conn, _USAGE_DERIVE_VERSION, full.outcomes.values(), attempt=attempt)
    for source in sorted(set(_retry_sources(conn)) - full.incomplete_sources):
        resolve_usage_obligations(conn, source)
    bound = _checkpoint_repairable(conn, full)
    if bound is not None:
        _publish_usage_derive_checkpoint(conn, prior_floor=None, scanned_bound=bound)
        conn.execute("DELETE FROM meta WHERE key = ?", (_REPAIR_SIGNATURE_KEY,))
        return _DeriveDisposition(
            "derived", count, scanned_bound=bound, unresolved_sources=full.incomplete_sources
        )
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (_REPAIR_SIGNATURE_KEY, _repair_signature(conn, state)),
    )
    return _DeriveDisposition(
        "skipped", count, reason=reason, unresolved_sources=full.incomplete_sources
    )


_RELEASE_SIGNATURE_KEY = "usage_release_signature"


def _release_held_sources(conn: sqlite3.Connection) -> list[str]:
    """Lift exact-source holds whose whole covered population is proved reconstructible.

    Candidates are held sources that still retain raw rows (a source pruned whole has none
    to reconstruct from). Signature-gated like the outstanding-work retry, so an unchanged
    store never re-proves; the release itself commits with the transaction that proved it.
    """
    candidates = [
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT h.source_path FROM usage_replay_holds h "
            "WHERE h.source_path IS NOT NULL "
            "AND EXISTS (SELECT 1 FROM raw_events r WHERE r.source_path = h.source_path) "
            "ORDER BY h.source_path"
        )
    ]
    if not candidates:
        conn.execute("DELETE FROM meta WHERE key = ?", (_RELEASE_SIGNATURE_KEY,))
        return []
    signature = _retry_signature(conn, candidates)
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (_RELEASE_SIGNATURE_KEY,)).fetchone()
    if row is not None and row[0] == signature:
        return []
    released = release_safe_holds(conn, candidates)
    remaining = [c for c in candidates if c not in released]
    if remaining:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_RELEASE_SIGNATURE_KEY, _retry_signature(conn, remaining)),
        )
    else:
        conn.execute("DELETE FROM meta WHERE key = ?", (_RELEASE_SIGNATURE_KEY,))
    return released


def _store_retry_signature(conn: sqlite3.Connection) -> None:
    """Remember the post-retry state so an identical state is not replayed again."""
    sources = _retry_sources(conn)
    if not sources:
        conn.execute("DELETE FROM meta WHERE key = ?", (_RETRY_SIGNATURE_KEY,))
        return
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (_RETRY_SIGNATURE_KEY, _retry_signature(conn, sources)),
    )


def _derive_usage_incremental_disposition(
    conn: sqlite3.Connection, attempt: Attempt | None = None
) -> _DeriveDisposition:
    """Derive new replayable usage under an existing IMMEDIATE transaction.

    Validated same-version progress is never reset by a lower surviving raw maximum
    (retention). A pristine store with no checkpoint replays once without deleting
    anything. Missing, partial, malformed, contradictory or version-changed proof in an
    established store skips untouched and reports a bounded reason.

    ENH-3770: nothing is deleted. Every Codex source with appended rows is replayed whole
    (its turn state starts before the slice) and every other appended row is replayed, all
    through the guarded planner, which compares with committed observations before it
    prices or writes. Every incomplete scanned scope -- held or unheld -- is persisted as
    durable pending in this transaction, before the high-water advances, and outstanding
    usage work at or below the checkpoint is retried even when raw ``MAX`` is unchanged.
    """
    state = _read_usage_checkpoint(conn)
    max_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM raw_events").fetchone()[0]
    report = ReplayReport()
    if state.status == "absent":
        if not _usage_bootstrap_eligible(conn):
            return _recover_under_unusable_checkpoint(conn, state, attempt)
        count = _backfill_usage_events(conn, _usage_raw_cursor(conn), report=report)
        record_replay_outcomes(
            conn, _USAGE_DERIVE_VERSION, report.outcomes.values(), attempt=attempt
        )
        # Raw-only acquisition left a derive handoff per verified source: a pristine replay
        # that ended clean resolves it from the committed rows (no original-file access).
        for source in sorted(set(_retry_sources(conn)) - report.incomplete_sources):
            resolve_usage_obligations(conn, source)
        _publish_usage_derive_checkpoint(conn, prior_floor=None, scanned_bound=max_id)
        return _DeriveDisposition(
            "derived",
            count,
            scanned_bound=max_id,
            unresolved_sources=report.incomplete_sources,
        )
    if not state.valid:
        return _recover_under_unusable_checkpoint(conn, state, attempt)
    checkpoint = int(state.floor or 0)
    # ENH-3747: search evidence is reconciled once, from committed rows, for every source
    # this catch-up touched -- including zero-insert sources.
    search_scope = UsageSearchScope()
    # A Codex source with appended rows is replayed whole (its turn state starts before the
    # slice); a source with outstanding usage work at or below the checkpoint is replayed
    # whole too, so a slice replay never hides work it did not cover. Everything runs in ONE
    # guarded replay so conflicting new requests across sources are all recognized before
    # the first priced insert, independent of source order.
    full_sources: set[str] = set()
    if max_id > checkpoint:
        full_sources.update(
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT source_path FROM raw_events WHERE id > ? AND host = 'codex'",
                (checkpoint,),
            )
        )
    retried = _retry_candidates(conn, exclude=full_sources)
    full_sources.update(retried)
    count = 0
    if max_id > checkpoint or full_sources:
        clauses: list[str] = []
        params: list[Any] = []
        if max_id > checkpoint:
            clauses.append("id > ?")
            params.append(checkpoint)
        if full_sources:
            clauses.append(f"source_path IN ({', '.join('?' for _ in full_sources)})")
            params.extend(sorted(full_sources))
        search_scope.mark(*full_sources)
        count = _backfill_usage_events(
            conn,
            _usage_raw_cursor(conn, "WHERE " + " OR ".join(clauses), tuple(params)),
            search_scope=search_scope,
            report=report,
        )
    _reconcile_usage_search(conn, search_scope)
    record_replay_outcomes(conn, _USAGE_DERIVE_VERSION, report.outcomes.values(), attempt=attempt)
    for source in retried:
        if source not in report.incomplete_sources:
            resolve_usage_obligations(conn, source)
    if (
        retried
        or _retry_sources(conn)
        or conn.execute("SELECT 1 FROM meta WHERE key = ?", (_RETRY_SIGNATURE_KEY,)).fetchone()
    ):
        _store_retry_signature(conn)
    _release_held_sources(conn)
    if max_id > checkpoint:
        _publish_usage_derive_checkpoint(conn, prior_floor=checkpoint, scanned_bound=max_id)
        return _DeriveDisposition(
            "derived", count, scanned_bound=max_id, unresolved_sources=report.incomplete_sources
        )
    return _DeriveDisposition(
        "derived", count, scanned_bound=checkpoint, unresolved_sources=report.incomplete_sources
    )


def _derive_usage_incremental_conn(conn: sqlite3.Connection) -> int:
    """Count-only view of :func:`_derive_usage_incremental_disposition`."""
    return _derive_usage_incremental_disposition(conn).count


def backfill_usage_incremental(db: Path | str = DEFAULT_DB_PATH) -> int:
    """Catch up replayable usage observations without rebuilding other caches."""
    refuse_on_remote(db, "backfill_usage_incremental")
    conn = _pkg.connect(db)
    try:
        conn.execute("BEGIN IMMEDIATE")
        disposition = _derive_usage_incremental_disposition(conn)
        conn.commit()
        return disposition.count
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _source_tail_digest(handle: Any, offset: int) -> str:
    """Hash a bounded boundary witness without rereading an entire transcript."""
    handle.seek(max(0, offset - 64))
    return hashlib.sha256(handle.read(min(offset, 64))).hexdigest()


def _certify_codex_stored_source(
    conn: sqlite3.Connection,
    handle: SessionHandle,
    path: Path,
    session_id: str,
    preexisting: set[int],
    *,
    prior_lines: int = 0,
    exempt_lines: frozenset[int] = frozenset(),
) -> None:
    """Raise unless every stored row of *path* canonically matches the current rollout parse.

    Lines present before the refresh may be legacy plaintext: they certify by canonical
    comparison. Lines the refresh inserted must be the literal sanitized payload.
    """
    from little_loops.session_store.claude_usage import claude_transcript_contract
    from little_loops.session_store.usage_refresh import (
        _canonical_payload,
        _payload_equal,
        _stored_payloads,
    )

    stored = {
        row[0]: row[1:]
        for row in conn.execute(
            "SELECT line_no, session_id, host, host_basis, event_type, ts, "
            "ordinal, usage_contract, CAST(raw_line AS BLOB), CAST(parsed_json AS BLOB), "
            "typeof(raw_line), typeof(parsed_json) "
            "FROM raw_events WHERE source_path = ?",
            (str(path),),
        )
    }
    seen: set[int] = set()
    for event in iter_events(handle):
        if event.line_no is None:
            raise RuntimeError("Codex parser omitted a source line number")
        expected = (
            event.payload.get("sessionId") or session_id,
            "codex",
            "handle",
            event.type or "unknown",
            event.timestamp,
            event.ordinal,
            claude_transcript_contract(event.payload, host="codex", host_basis="handle"),
        )
        row = stored.get(event.line_no)
        if row is None or row[:7] != expected:
            raise RuntimeError("Codex stored source differs from current rollout")
        if (
            event.line_no <= prior_lines
            and event.line_no not in preexisting
            and event.line_no not in exempt_lines
        ):
            # Restored from the native source during this refresh: it proves nothing about
            # the retained prior prefix.
            raise RuntimeError("Codex retained prefix was not intact before this refresh")
        columns = _stored_payloads(row[7], row[9], row[8], row[10])
        sanitized = _canonical_payload(
            event.payload, host="codex", event_type=event.type or "unknown"
        )
        if event.line_no in preexisting:
            columns = tuple(  # type: ignore[assignment]
                _canonical_payload(column, host=str(row[1]), event_type=str(row[3]))
                for column in columns
            )
        if not all(_payload_equal(column, sanitized) for column in columns):
            raise RuntimeError("Codex stored source differs from current rollout")
        seen.add(event.line_no)
    if seen != stored.keys():
        raise RuntimeError("Codex stored source has unmatched rollout rows")


def _refusal_code(exc: BaseException) -> str:
    code = getattr(exc, "reason", None)
    return code if code in REFUSAL_CODES else "invalid_payload"


def _first_rejected(path: Path) -> tuple[str, int | None, int | None]:
    """``(reason, first_line, first_offset)`` of the first physically rejected line, if any."""
    try:
        accounting = account_physical_lines(path)
    except OSError:
        return "decode_failure", None, None
    if not accounting.rejected:
        return "decode_failure", None, None
    first = min(accounting.rejected, key=lambda r: r.first_offset)
    return first.reason, first.first_line_no, first.first_offset


def _codex_failure_diagnostic(
    db: Path | str, attempt: Attempt | None, path: Path, exc: BaseException
) -> None:
    """After a full rollback, persist a content-free failure for a Codex refresh (best effort)."""
    chain = [exc, exc.__cause__, exc.__context__]
    if any(isinstance(e, HistorySanitizationError) for e in chain):
        refused = next(e for e in chain if isinstance(e, HistorySanitizationError))
        record_failure_only(
            lambda: _pkg.connect(db),
            attempt,
            reason="sanitization_refused",
            refusal_code=_refusal_code(refused),
        )
    elif any(isinstance(e, UnicodeDecodeError | json.JSONDecodeError) for e in chain):
        reason, line, offset = _first_rejected(path)
        record_failure_only(
            lambda: _pkg.connect(db),
            attempt,
            reason=reason,
            first_line_no=line,
            first_offset=offset,
        )


def _refresh_status(base: str, result: Any) -> dict[str, int | str]:
    """Overlay a truthful incomplete marker on an otherwise complete refresh status."""
    if base == "complete" and result.reason not in _BENIGN_FINALIZE_REASONS:
        return {"status": "incomplete", "reason": str(result.reason)}
    return {"status": base}


# Finalize outcomes that leave the legacy public fallback intact: nothing negative was found.
_BENIGN_FINALIZE_REASONS = frozenset({None, "acquisition_unprovable", "storage_unavailable"})


def _refresh_codex_usage_source(db: Path | str, source: Path) -> dict[str, int | str]:
    """Replay a complete native rollout and commit new usage with a source boundary.

    Codex's on-disk parser also normalizes shell tool pairs across records, so
    the detached worker reparses the source while inserting only new line
    positions. This preserves the existing raw-event contract until its
    stateful normalizer has a durable tail cursor of its own.
    """
    path = source.expanduser().resolve()
    conn = _pkg.connect(db)
    attempt: Attempt | None = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        attempt = begin_attempt(conn, str(path), _USAGE_DERIVE_VERSION, host="codex")
        with path.open("rb") as handle:
            initial = path.stat()
            if initial.st_size == 0:
                conn.rollback()
                return {"raw_events": 0, "usage_events": 0, "status": "empty"}
            handle.seek(-1, 2)
            if handle.read(1) != b"\n":
                conn.rollback()
                return {"raw_events": 0, "usage_events": 0, "status": "partial"}
            cursor = conn.execute(
                "SELECT session_id, device, inode, committed_offset, tail_sha256, host, "
                "source_mtime_ns, status, derived_raw_event_id, committed_line_no "
                "FROM usage_source_cursors WHERE source_path = ?",
                (str(path),),
            ).fetchone()
            if cursor and (
                cursor[5] != "codex"
                or (initial.st_dev, initial.st_ino) != (cursor[1], cursor[2])
                or initial.st_size < cursor[3]
                or _source_tail_digest(handle, int(cursor[3])) != cursor[4]
            ):
                conn.execute(
                    "UPDATE usage_source_cursors SET status = 'source_changed', updated_at = ? "
                    "WHERE source_path = ?",
                    (_now(), str(path)),
                )
                conn.commit()
                raise RuntimeError("Codex rollout rotated, truncated, or overwritten")
            if cursor and (initial.st_size, initial.st_mtime_ns) == (cursor[3], cursor[6]):
                # Unchanged bytes cannot waive semantic recovery: report pending, failure
                # or version/checkpoint state truthfully, and never publish new proof here.
                state = _read_usage_checkpoint(conn)
                negative = _freshness_negative_evidence(conn, str(path))
                derived_mark = _checkpoint_int(cursor[8])
                conn.rollback()
                if cursor[7] != "complete":
                    reason = "cursor_incomplete"
                elif negative is not None:
                    reason = negative[1]
                elif not state.valid:
                    reason = f"checkpoint_{state.status}"
                elif derived_mark is None or int(state.floor or 0) < derived_mark:
                    reason = "derive_pending"
                else:
                    return {"raw_events": 0, "usage_events": 0, "status": "complete"}
                return {
                    "raw_events": 0,
                    "usage_events": 0,
                    "status": "incomplete",
                    "reason": reason,
                }
            handle.seek(0)
            try:
                header = json.loads(handle.readline())
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError("Codex rollout has no valid native header") from exc
            header_payload = header.get("payload") if isinstance(header, dict) else None
            native_id = header_payload.get("id") if isinstance(header_payload, dict) else None
            if (
                not isinstance(header, dict)
                or header.get("type") != "session_meta"
                or not isinstance(native_id, str)
                or not native_id
            ):
                raise RuntimeError("Codex rollout has no verified thread ID")
            handle.seek(0)
            line_count = sum(1 for _ in handle)

        handles = handles_from_paths([path], "codex")
        if not handles:
            raise RuntimeError("Codex rollout vanished before refresh")
        session_id = handles[0].session_id
        if session_id != native_id:
            raise RuntimeError("Codex rollout thread ID disagrees with source handle")
        if cursor and cursor[0] != session_id:
            raise RuntimeError("Codex rollout thread identity changed")
        # Lines present before this call may be legacy plaintext: they certify by
        # canonical comparison. Lines inserted below must be the literal sanitized
        # payload, or canonicalizing the stored side would mask a missed insert seam.
        preexisting = {
            row[0]
            for row in conn.execute(
                "SELECT line_no FROM raw_events WHERE source_path = ?", (str(path),)
            )
        }
        inserted = _backfill_raw_events(conn, handles)

        # First enablement may encounter rows ingested by SessionStart before
        # the source cursor existed. Certify the stored source against the
        # current parser output before publishing a fresh boundary. A later refresh
        # extends semantic coverage only if the same certification still holds; a
        # failure there leaves the older boundary and pending completion instead.
        prefix_proved = True
        if cursor is None:
            _certify_codex_stored_source(conn, handles[0], path, session_id, preexisting)
        else:
            try:
                _certify_codex_stored_source(
                    conn,
                    handles[0],
                    path,
                    session_id,
                    preexisting,
                    prior_lines=int(cursor[9] or 0),
                    exempt_lines=sticky_rejection_lines(conn, str(path)),
                )
            except RuntimeError:
                prefix_proved = False

        accounting = account_physical_lines(path)
        with path.open("rb") as handle:
            final = path.stat()
            if (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns) != (
                initial.st_dev,
                initial.st_ino,
                initial.st_size,
                initial.st_mtime_ns,
            ):
                raise RuntimeError("Codex rollout changed during refresh")
            digest = _source_tail_digest(handle, final.st_size)
        # ENH-3770: the verified native header is actual acquisition evidence of host and
        # session; stage the verified acquisition before reconciliation needs it.
        attempt = _with_verified_session(attempt, "codex", session_id)
        stage_source_acquisition(
            conn,
            attempt,
            accounting=accounting,
            witness=AcquisitionWitness(
                final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns, digest
            ),
            coverage_proved=prefix_proved,
        )
        disposition = _derive_usage_incremental_disposition(conn, attempt)
        source_max_id = conn.execute(
            "SELECT COALESCE(MAX(id), 0) FROM raw_events WHERE source_path = ?",
            (str(path),),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO usage_source_cursors(source_path, host, session_id, device, inode, "
            "committed_offset, committed_line_no, tail_sha256, source_mtime_ns, "
            "derived_raw_event_id, status, updated_at) "
            "VALUES(?, 'codex', ?, ?, ?, ?, ?, ?, ?, ?, 'complete', ?) "
            "ON CONFLICT(source_path) DO UPDATE SET "
            "session_id = excluded.session_id, device = excluded.device, inode = excluded.inode, "
            "committed_offset = excluded.committed_offset, "
            "committed_line_no = excluded.committed_line_no, "
            "tail_sha256 = excluded.tail_sha256, "
            "source_mtime_ns = excluded.source_mtime_ns, "
            "derived_raw_event_id = excluded.derived_raw_event_id, "
            "status = excluded.status, updated_at = excluded.updated_at",
            (
                str(path),
                session_id,
                final.st_dev,
                final.st_ino,
                final.st_size,
                line_count,
                digest,
                final.st_mtime_ns,
                source_max_id,
                _now(),
            ),
        )
        outcome = finalize_source_refresh(
            conn,
            attempt,
            accounting=accounting,
            witness=AcquisitionWitness(
                final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns, digest
            ),
            coverage_proved=prefix_proved,
            derive_status=disposition.status,
            derive_reason=disposition.reason,
            held_skipped=disposition.held_skipped,
            source_max_raw_id=source_max_id,
            now=_now(),
            reacquired_from_zero=True,
        )
        conn.commit()
        return {
            "raw_events": inserted,
            "usage_events": disposition.count,
            **_refresh_status("complete", outcome),
        }
    except Exception as exc:
        conn.rollback()
        _codex_failure_diagnostic(db, attempt, path, exc)
        raise
    finally:
        conn.close()


def _with_verified_session(
    attempt: Attempt | None, host: str, session_id: str | None
) -> Attempt | None:
    """*attempt* with host/session set from actual acquisition evidence (never guessed)."""
    if attempt is None:
        return None
    scope = attempt.scope
    return Attempt(
        SourceScope(
            scope.source_path,
            scope.generation_id,
            scope.derive_version,
            host,
            session_id or scope.session_id,
        ),
        attempt.head_revision,
    )


def refresh_usage_source(
    db: Path | str, source: Path, *, host: str = "claude-code"
) -> dict[str, int | str]:
    """Ingest a verified current source and derive its usage atomically.

    Claude consumes only appended, newline-terminated records. Codex
    reparses its rollout to preserve stateful tool normalization, but inserts
    only new line positions. A partial tail is not certified. A changed
    inode or overwritten boundary refuses reuse of physical line numbers.
    The returned ``status`` is ``incomplete`` (with a bounded ``reason``) when ingestion
    advanced but derivation, acquisition or source proof did not complete.
    """
    if host not in {"claude-code", "codex"}:
        raise ValueError(f"refresh_usage_source: unverified trigger host {host!r}")
    refuse_on_remote(db, "refresh_usage_source")
    if host == "codex":
        return _refresh_codex_usage_source(db, source)
    from little_loops.session_store.claude_usage import claude_transcript_contract

    path = source.expanduser().resolve()
    conn = _pkg.connect(db)
    attempt: Attempt | None = None
    refusal_line: int | None = None
    refusal_offset: int | None = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        attempt = begin_attempt(conn, str(path), _USAGE_DERIVE_VERSION, host=host)
        cursor = conn.execute(
            "SELECT session_id, device, inode, committed_offset, committed_line_no, "
            "tail_sha256 FROM usage_source_cursors WHERE source_path = ?",
            (str(path),),
        ).fetchone()
        preexisting_rows = (
            conn.execute(
                "SELECT 1 FROM raw_events WHERE source_path = ? LIMIT 1", (str(path),)
            ).fetchone()
            is not None
        )
        native_session_seen: str | None = None
        with path.open("rb") as handle:
            initial = path.stat()
            offset = int(cursor[3]) if cursor else 0
            line_no = int(cursor[4]) if cursor else 0
            started_at_zero = offset == 0
            ingest_from = offset
            if cursor and (
                initial.st_dev != cursor[1]
                or initial.st_ino != cursor[2]
                or initial.st_size < offset
                or _source_tail_digest(handle, offset) != cursor[5]
            ):
                conn.execute(
                    "UPDATE usage_source_cursors SET status = 'source_changed', updated_at = ? "
                    "WHERE source_path = ?",
                    (_now(), str(path)),
                )
                conn.commit()
                raise RuntimeError("source rotated, truncated, or overwritten")
            session_id = cursor[0] if cursor else path.stem
            retained_before = frozenset(
                r[0]
                for r in conn.execute(
                    "SELECT line_no FROM raw_events WHERE source_path = ?", (str(path),)
                )
            )
            prior_line_no = line_no
            exempt_lines = sticky_rejection_lines(conn, str(path))
            if cursor and has_sticky_rejection(conn, str(path)):
                # Full re-acquisition from zero: a repaired gap can only be proven by
                # comparing every retained position (INSERT OR IGNORE keeps existing rows).
                offset = line_no = ingest_from = 0
                started_at_zero = True
            handle.seek(offset)
            inserted = 0
            partial = False
            while True:
                line_start = handle.tell()
                raw_line = handle.readline()
                if not raw_line:
                    break
                if not raw_line.endswith(b"\n"):
                    partial = True
                    break
                offset = handle.tell()
                line_no += 1
                try:
                    record = json.loads(raw_line)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if not isinstance(record, dict):
                    continue
                native_session = record.get("sessionId")
                if isinstance(native_session, str) and native_session:
                    session_id = native_session
                    native_session_seen = native_session
                refusal_line, refusal_offset = line_no, line_start
                packed = _pack_payload(
                    json.dumps(
                        sanitize_history_payload(
                            record,
                            host="claude-code",
                            event_type=str(record.get("type") or "unknown"),
                        ).payload
                    )
                )
                refusal_line = refusal_offset = None
                contract = claude_transcript_contract(
                    record, host="claude-code", host_basis="handle"
                )
                cur = conn.execute(
                    "INSERT OR IGNORE INTO raw_events"
                    "(ts, session_id, host, host_basis, source_path, line_no, event_type, "
                    "raw_line, parsed_json, usage_contract) "
                    "VALUES(?, ?, 'claude-code', 'handle', ?, ?, ?, ?, ?, ?)",
                    (
                        record.get("timestamp") or "",
                        session_id,
                        str(path),
                        line_no,
                        str(record.get("type") or "unknown"),
                        packed,
                        packed,
                        contract,
                    ),
                )
                inserted += cur.rowcount
            final = path.stat()
            if final.st_dev != initial.st_dev or final.st_ino != initial.st_ino:
                raise RuntimeError("source changed during refresh")
            status = "partial" if partial else "complete"
            if final.st_size > offset and not partial:
                status = "pending_append"
            digest = _source_tail_digest(handle, offset)

        accounting = account_physical_lines(path, limit=offset if not partial else None)
        # Zero-origin coverage: a pristine first read of the whole prefix, or a full
        # re-acquisition from zero that canonically matches every retained position.
        coverage = (started_at_zero and not preexisting_rows) or verify_claude_prefix(
            conn,
            path,
            accounting.offset,
            retained_before=retained_before,
            prior_line_no=prior_line_no,
            exempt_lines=exempt_lines,
        )
        # ENH-3770: only a native sessionId seen during acquisition verifies the session, and
        # the verified acquisition scope/head is staged *before* reconciliation needs
        # generation authority; finalization below reuses it and publishes from post-write
        # proof. Staging alone is acquisition evidence, never completion.
        attempt = _with_verified_session(attempt, host, native_session_seen)
        stage_source_acquisition(
            conn,
            attempt,
            accounting=accounting,
            witness=AcquisitionWitness(
                final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns, digest
            ),
            coverage_proved=coverage,
        )
        disposition = _derive_usage_incremental_disposition(conn, attempt)
        source_max_id = conn.execute(
            "SELECT COALESCE(MAX(id), 0) FROM raw_events WHERE source_path = ?",
            (str(path),),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO usage_source_cursors(source_path, host, session_id, device, inode, "
            "committed_offset, committed_line_no, tail_sha256, source_mtime_ns, "
            "derived_raw_event_id, status, updated_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(source_path) DO UPDATE SET "
            "host = excluded.host, session_id = excluded.session_id, "
            "device = excluded.device, inode = excluded.inode, "
            "committed_offset = excluded.committed_offset, "
            "committed_line_no = excluded.committed_line_no, "
            "tail_sha256 = excluded.tail_sha256, "
            "source_mtime_ns = excluded.source_mtime_ns, "
            "derived_raw_event_id = excluded.derived_raw_event_id, "
            "status = excluded.status, updated_at = excluded.updated_at",
            (
                str(path),
                host,
                session_id,
                final.st_dev,
                final.st_ino,
                offset,
                line_no,
                digest,
                final.st_mtime_ns,
                source_max_id,
                status,
                _now(),
            ),
        )
        outcome = finalize_source_refresh(
            conn,
            attempt,
            accounting=accounting,
            witness=AcquisitionWitness(
                final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns, digest
            ),
            coverage_proved=coverage,
            derive_status=disposition.status,
            derive_reason=disposition.reason,
            held_skipped=disposition.held_skipped,
            source_max_raw_id=source_max_id,
            now=_now(),
            ingest_from=ingest_from,
            reacquired_from_zero=ingest_from == 0,
        )
        conn.commit()
        return {
            "raw_events": inserted,
            "usage_events": disposition.count,
            **_refresh_status(status, outcome),
        }
    except Exception as exc:
        conn.rollback()
        if isinstance(exc, HistorySanitizationError):
            # Whole-call rollback stands; a separate guarded failure-only transaction
            # records only the bounded reason and first refused position.
            record_failure_only(
                lambda: _pkg.connect(db),
                attempt,
                reason="sanitization_refused",
                refusal_code=_refusal_code(exc),
                first_line_no=refusal_line,
                first_offset=refusal_offset,
            )
        raise
    finally:
        conn.close()


def _snapshot_ready(conn: sqlite3.Connection) -> bool:
    """Whether *conn* is an active pinned read transaction with ``query_only`` enabled."""
    try:
        return bool(conn.in_transaction) and conn.execute("PRAGMA query_only").fetchone()[0] == 1
    except sqlite3.Error:
        return False


def _freshness_negative_evidence(conn: sqlite3.Connection, source: str) -> tuple[str, str] | None:
    """``(status, reason)`` from durable semantic tracking that overrides legacy trust.

    Reads the source head and its pending obligations. A tracked source that is not
    cleanly complete never falls back to the legacy cursor comparison. ``None`` means no
    semantic tracking exists, so only the legacy comparison applies.
    """
    head = read_source_head(conn, source)
    pending = pending_obligations(conn, source)
    if head is None and not pending:
        return None
    for ob in pending:
        if ob.kind in {"acquisition_failure", "native_conflict"}:
            return "unknown", ob.reason
    for ob in pending:
        if ob.kind == "partial_tail":
            return "unknown", "partial_tail"
    if any(ob.usage_pending for ob in pending):
        return "stale", "derive_pending"
    if head is None or head.status == "pending":
        return "stale", "derive_pending"
    if head.status == "unprovable":
        return "unknown", head.reason or "invalid_state"
    return None


def usage_source_freshness(
    db: Path | str, source: Path, *, conn: sqlite3.Connection | None = None
) -> dict[str, int | str | None]:
    """Classify a selected local source against its committed derive boundary.

    Reads only cursor/source-state metadata, file stat, and a bounded boundary/tail
    witness; it never parses usage or advances the store. ``unknown`` is used whenever
    the source cannot be compared safely (missing, rotation, partial write, invalid
    metadata). With *conn*, the caller's already-active pinned read transaction
    (``PRAGMA query_only = 1``) supplies every database read and is never opened, committed,
    rolled back or closed here; an inactive or writable connection yields
    ``unknown/read_snapshot_unavailable``. Without it, one owned read transaction is begun
    before the first database read and released afterwards.
    """
    path = source.expanduser().resolve()
    owned: sqlite3.Connection | None = None
    try:
        if conn is None:
            owned = connect_readonly(db)
            owned.execute("BEGIN")
            read = owned
        else:
            if not _snapshot_ready(conn):
                return {
                    "status": "unknown",
                    "reason": "read_snapshot_unavailable",
                    "as_of_offset": None,
                }
            read = conn
        cursor = read.execute(
            "SELECT device, inode, committed_offset, tail_sha256, source_mtime_ns, "
            "derived_raw_event_id, status, updated_at FROM usage_source_cursors "
            "WHERE source_path = ?",
            (str(path),),
        ).fetchone()
        checkpoint = _read_usage_checkpoint(read)
        negative = _freshness_negative_evidence(read, str(path))
        head = read_source_head(read, str(path))
    except Exception:
        return {"status": "unknown", "reason": "store_unavailable", "as_of_offset": None}
    finally:
        if owned is not None:
            owned.close()
    if cursor is None:
        if negative is not None:
            return {
                "status": negative[0],
                "reason": negative[1],
                "as_of": None,
                "as_of_offset": None,
            }
        return {"status": "unknown", "reason": "source_untracked", "as_of_offset": None}
    offset = _checkpoint_int(cursor[2])
    derived = _checkpoint_int(cursor[5])
    if (
        offset is None
        or derived is None
        or not all(_checkpoint_int(cursor[i]) is not None for i in (0, 1))
        or not isinstance(cursor[3], str)
        or _checkpoint_int(cursor[4]) is None
    ):
        return {"status": "unknown", "reason": "cursor_invalid", "as_of_offset": None}
    base: dict[str, int | str | None] = {"as_of_offset": offset, "as_of": cursor[7]}
    if head is not None:
        # Semantic tracking exists: the older successful boundary, never ingestion state,
        # is the as-of fact. An unproved boundary stays unknown.
        successful = head.successful
        base = {
            "as_of_offset": successful.offset if successful else None,
            "as_of": successful.at if successful else None,
        }
    try:
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            stat = path.stat()
            if (opened.st_dev, opened.st_ino) != (stat.st_dev, stat.st_ino):
                return {**base, "status": "unknown", "reason": "source_changed"}
            if (stat.st_dev, stat.st_ino) != (cursor[0], cursor[1]) or stat.st_size < offset:
                return {**base, "status": "unknown", "reason": "source_changed"}
            if _source_tail_digest(handle, offset) != cursor[3] or cursor[6] == "source_changed":
                return {**base, "status": "unknown", "reason": "source_changed"}
            if stat.st_size > offset:
                handle.seek(-1, 2)
                complete = handle.read(1) == b"\n"
                return {
                    **base,
                    "status": "stale" if complete else "unknown",
                    "reason": "new_append" if complete else "partial_tail",
                }
            after = path.stat()
            if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
                opened.st_mtime_ns,
            ):
                return {**base, "status": "unknown", "reason": "source_changed"}
    except OSError:
        return {**base, "status": "unknown", "reason": "source_unreadable"}
    if negative is not None:
        return {**base, "status": negative[0], "reason": negative[1]}
    if cursor[6] != "complete" or stat.st_mtime_ns != cursor[4]:
        return {**base, "status": "unknown", "reason": "source_changed"}
    if checkpoint.status in {"absent", "version_changed"}:
        return {**base, "status": "stale", "reason": "normalizer_changed"}
    if not checkpoint.valid:
        return {**base, "status": "unknown", "reason": "checkpoint_invalid"}
    if int(checkpoint.floor or 0) < derived:
        return {**base, "status": "stale", "reason": "derive_pending"}
    return {**base, "status": "fresh", "reason": None}


def _is_transcript_anchor(anchor: object, skill_name: str) -> bool:
    """True for a replay-style skill search anchor: a ``.jsonl`` source path."""
    return (
        isinstance(anchor, str)
        and anchor != skill_name
        and ("/" in anchor or "\\" in anchor)
        and anchor.endswith(".jsonl")
    )


def _classify_legacy_skill_origins(conn: sqlite3.Connection) -> None:
    """Stamp every NULL-origin ``skill_events`` row with a provenance (BUG-3766).

    Runs inside ``rebuild()``'s transaction, before anything is deleted, so it reads the
    *original* skill search entries and a failed rebuild rolls it back. Explicit origins
    are never touched. For each NULL-origin row: any completion field (including zero)
    proves a skill host (``'skill_host'``); otherwise ``'transcript'`` only when its
    ``(session, ts, name)`` group holds exactly one base row and exactly one search entry
    whose anchor is a ``.jsonl`` source path; everything else — name-only anchors,
    duplicates, conflicts, missing evidence — is ``'legacy'`` and survives forever.
    """
    rows = conn.execute(
        "SELECT id, ts, session_id, skill_name, exit_code, success, duration_ms "
        "FROM skill_events WHERE origin IS NULL"
    ).fetchall()
    if not rows:
        return
    keyed: dict[tuple[str, str, object], int] = {}
    for _id, ts, sid, name, *_rest in rows:
        key = (str(sid) if sid else "", ts, name)
        keyed[key] = keyed.get(key, 0) + 1
    # One pass over the FTS table (kind/ref/anchor/ts are UNINDEXED): tally only the
    # entries that can match a NULL-origin row's group.
    anchors: dict[tuple[str, str, object], list[object]] = {}
    for ref, ts, content, anchor in conn.execute(
        "SELECT ref, ts, content, anchor FROM search_index WHERE kind = 'skill'"
    ):
        key = (ref, ts, content)
        if key in keyed:
            anchors.setdefault(key, []).append(anchor)
    updates: list[tuple[str, int]] = []
    for row_id, ts, sid, name, exit_code, success, duration_ms in rows:
        if exit_code is not None or success is not None or duration_ms is not None:
            origin = "skill_host"
        else:
            key = (str(sid) if sid else "", ts, name)
            found = anchors.get(key, [])
            origin = (
                "transcript"
                if keyed[key] == 1
                and len(found) == 1
                and isinstance(name, str)
                and name
                and _is_transcript_anchor(found[0], name)
                else "legacy"
            )
        updates.append((origin, row_id))
    conn.executemany("UPDATE skill_events SET origin = ? WHERE id = ?", updates)


def _reindex_skill_survivors(conn: sqlite3.Connection) -> list[SkillReplaySurvivor]:
    """Re-index surviving ``skill_events`` rows and return their eligible hook twins.

    Uses the live writers' own search arguments. Eligible survivors (``prompt_hook``,
    no completion fields, non-empty session/name, string args, tz-aware timestamp) may
    each suppress one replay twin in ``_backfill_skill_events``; skill hosts, legacy and
    unknown origins never do.
    """
    survivors: list[SkillReplaySurvivor] = []
    for row_id, ts, sid, name, args, origin, exit_code, success, duration_ms in conn.execute(
        "SELECT id, ts, session_id, skill_name, args, origin, exit_code, success, duration_ms "
        "FROM skill_events ORDER BY id"
    ).fetchall():
        _index(conn, content=name or "", kind="skill", ref=sid or "", anchor=name or "", ts=ts)
        if origin != "prompt_hook" or not sid or not name or not isinstance(args, str):
            continue
        if exit_code is not None or success is not None or duration_ms is not None:
            continue
        parsed = _parse_aware_ts(ts)
        if parsed is not None:
            survivors.append(SkillReplaySurvivor(row_id, str(sid), name, args, parsed))
    return survivors


def _stamp_rebuild_derive_version(conn: sqlite3.Connection) -> None:
    """Record the derive version in the caller's open transaction (not a derivation)."""
    conn.execute(
        "INSERT INTO meta(key, value) VALUES('rebuild_derive_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (REBUILD_DERIVE_VERSION,),
    )


def rebuild(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    config: dict | None = None,
    max_sessions: int | None = None,
) -> dict[str, int]:
    """Wipe and re-derive the JSONL-sourced cache tables from ``raw_events``.

    Wipes ``_REBUILD_TABLES`` plus the ``search_index`` rows for
    ``_REBUILD_SEARCH_KINDS`` (except rows ``_REBUILD_TABLE_PREDICATES`` preserves:
    ``channel = 'live'`` usage events, ``kind = 'retention'`` summary nodes,
    byte-bearing hook tool rows, non-``backfill`` corrections and every
    non-``transcript`` ``skill_events`` row, none of which can be replayed from
    ``raw_events``; surviving rows are re-indexed and their replay twins suppressed), then re-derives them by replaying every
    ``raw_events`` row through the same ``_backfill_*`` parsers the legacy
    JSONL path uses (via :func:`_iter_events`). Idempotent — safe to call
    repeatedly. On success, updates the ``last_rebuild_version`` meta key to
    ``SCHEMA_VERSION`` and stamps ``rebuild_derive_version`` with
    ``REBUILD_DERIVE_VERSION`` (what :func:`rebuild_needed` gates on), in the same
    transaction as the derived rows.

    Leaf/condensed summary nodes and all ``summary_spans`` are wiped and
    regenerated only when ``config`` enables history compaction; with ``config``
    omitted they are cleared and not regenerated. The whole replay runs in one
    ``BEGIN IMMEDIATE`` transaction, so an enabled config can make host
    summarization calls while the write lock is held.

    Issue/loop/commit/cli/file/test_run tables are outside ``raw_events``'s
    scope for this issue (ENH-2581) and are left untouched.
    """
    refuse_on_remote(db, "rebuild")
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
        conn.execute("BEGIN IMMEDIATE")
        usage_checkpoint, usage_bootstrap, usage_report = _usage_checkpoint_snapshot(conn)
        # BUG-3766: provenance must be settled from the original search entries
        # before the wipe below deletes them.
        _classify_legacy_skill_origins(conn)
        for table in _REBUILD_TABLES:
            where = _REBUILD_TABLE_PREDICATES.get(table)
            conn.execute(f"DELETE FROM {table}" + (f" WHERE {where}" if where else ""))
        placeholders = ",".join(["?"] * len(_REBUILD_SEARCH_KINDS))
        conn.execute(
            f"DELETE FROM search_index WHERE kind IN ({placeholders})",
            _REBUILD_SEARCH_KINDS,
        )

        # BUG-3761: surviving live tool/correction rows lost their search entries to
        # the blanket delete above; re-index them with the writers' own arguments.
        # The Counter lets replay skip transcript twins of surviving live tool rows
        # (matched on key, not ts: the hook stamps _now(), replay copies the transcript).
        live_tools: Counter[tuple[str | None, str, str]] = Counter()
        for tool_ts, tool_sid, tool_name, args_hash, agent_type in conn.execute(
            "SELECT ts, session_id, tool_name, args_hash, agent_type FROM tool_events ORDER BY id"
        ).fetchall():
            live_tools[(tool_sid, tool_name, args_hash)] += 1
            _index(
                conn,
                content=f"{tool_name} {agent_type or ''}".strip(),
                kind="tool",
                ref=tool_name,
                anchor=str(tool_sid or ""),
                ts=tool_ts,
            )
        for corr_ts, corr_sid, corr_content, corr_source in conn.execute(
            "SELECT ts, session_id, content, source FROM user_corrections ORDER BY id"
        ).fetchall():
            _index(
                conn,
                content=corr_content,
                kind="correction",
                ref=corr_sid or "",
                anchor=corr_source,
                ts=corr_ts,
            )

        # BUG-3766: likewise for surviving skill rows (live hook / skill-host / legacy);
        # eligible hook rows let replay skip their transcript twins.
        live_skills = _reindex_skill_survivors(conn)

        def _raw_events_cursor(*, usage_order: bool = False) -> sqlite3.Cursor:
            ordering = (
                "source_path, COALESCE(ordinal, line_no), line_no, id" if usage_order else "id"
            )
            return conn.execute(
                "SELECT raw_line, source_path, host, host_basis, event_type, ts, "
                f"session_id, line_no, ordinal, usage_contract, id "
                f"FROM raw_events ORDER BY {ordering}"
            )

        # sessions first: assistant_messages/backfill order elsewhere relies on
        # the sessions table already being populated (ENH-1710).
        counts["sessions"] = _backfill_sessions(conn, _raw_events_cursor())
        counts["tools"] = _backfill_tool_events(conn, _raw_events_cursor(), skip_live=live_tools)
        counts["messages"] = _backfill_messages(conn, _raw_events_cursor())
        counts["assistant_messages"] = _backfill_assistant_messages(conn, _raw_events_cursor())
        counts["skill_events"] = _backfill_skill_events(
            conn, _raw_events_cursor(), skip_live=live_skills
        )
        counts["usage_events"] = _backfill_usage_events(
            conn, _raw_events_cursor(usage_order=True), reindex_all=True, report=usage_report
        )
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
        _stamp_rebuild_derive_version(conn)
        _set_usage_derive_checkpoint(
            conn, usage_checkpoint, bootstrap=usage_bootstrap, report=usage_report
        )
        conn.commit()
    except Exception:
        # A failed replay must not expose a partially replaced rollout set.
        conn.rollback()
        raise
    finally:
        conn.close()
    return counts


def backfill_snapshots(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    issues_dir: Path | None = None,
) -> int:
    """Hydrate ``issue_snapshots`` from all ``.md`` files under *issues_dir*.

    Idempotent via ``INSERT OR IGNORE`` on the ``(issue_num, transition)`` dedup
    index — type-blind by design, so a suppressed insert whose stored row
    belongs to a different issue id can indicate a genuine number-reuse
    collision (BUG-3006) rather than an idempotent retype no-op; this backfill
    path stays quiet by default. Also indexes each snapshot in ``search_index``
    with ``kind="snapshot"``.
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
    handles: list[SessionHandle] | None = None,
    config: dict | None = None,
    max_sessions: int | None = None,
    repo_root: Path | None = None,
    registry_dir: Path | None = None,
    sessions_root: Path | None = None,
    host: str | None = None,
    also_rebuild: bool = False,
) -> dict[str, int]:
    """Populate the database from existing on-disk sources.

    Reads issue-file frontmatter, FSM loop-state JSON, git commit history
    (ENH-2458; only when *repo_root* is given and contains ``.git``), the
    Learning Test Registry (ENH-2466; only when *registry_dir* is given and is
    a directory), and nested subagent transcripts (ENH-2505; only when
    *sessions_root* is given and is a directory) directly. When *host* is
    given, the subagent-transcript walk uses that host's layout descriptor
    (ENH-3165 — qwen nests ``subagents/<session-id>/`` with ``.meta.json``
    sidecars); omitted, the Claude shape is preserved verbatim. Session
    sources (*jsonl_files*, widened via ``handles_from_paths``, or *handles*
    directly — ENH-3422 D4; passing both raises ``ValueError``) are ingested
    into ``raw_events`` only (ENH-2581) — the JSONL-derived cache tables
    (``tool_events``, ``message_events``, ``assistant_messages``,
    ``skill_events``, ``sessions``) are **not** populated here; call
    :func:`rebuild` (or pass ``also_rebuild=True`` to do both in one call) to
    materialize them from ``raw_events``.

    Returns a per-kind count of rows inserted/derived. Sources that are
    absent are skipped silently.
    """
    refuse_on_remote(db, "backfill")
    if jsonl_files is not None and handles is not None:
        raise ValueError("backfill: pass jsonl_files or handles, not both")
    issues_dir = issues_dir if issues_dir is not None else Path(".issues")
    loops_dir = loops_dir if loops_dir is not None else Path(".loops")
    if registry_dir is None:
        registry_dir = Path(".ll") / "learning-tests"
    conn = _pkg.connect(db)
    header_failure: tuple[BaseException, list[tuple[Path, str]]] | None = None
    raw_candidates: list[tuple[Path, str]] = []
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
        if jsonl_files or handles:
            effective_host = host if host is not None else resolve_host().name
            if handles is not None:
                raw_handles = handles
            else:
                try:
                    raw_handles = handles_from_paths(jsonl_files or [], effective_host)
                except UnicodeDecodeError as exc:
                    header_failure = (exc, [(Path(p), effective_host) for p in jsonl_files or []])
                    raise
            raw_candidates = [(h.path, h.host) for h in raw_handles]
            raw_snapshot = _ingest_snapshot(conn, raw_handles)
            counts["raw_events"] = _backfill_raw_events(conn, raw_handles)
            _account_ingested_sources(conn, raw_handles, raw_snapshot)
        if registry_dir.is_dir():
            counts["learning_tests"] = _backfill_learning_test_events(conn, registry_dir)
        if sessions_root is not None and sessions_root.is_dir():
            layout = host_layout_for(host) if host else None
            counts["subagent_runs"] = _backfill_subagent_runs(conn, sessions_root, layout=layout)
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('last_raw_event_ts', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_now(),),
        )
        conn.commit()
    except Exception as exc:
        # Roll back every uncommitted write on this connection (issues, snapshots, loops,
        # git, raw events): a sanitizer failure publishes no watermark and no rebuild. Only
        # then may a separate guarded transaction record the content-free diagnostic.
        conn.rollback()
        if header_failure is not None:
            _note_ingestion_failure(db, header_failure[0], header_failure[1])
        else:
            _note_ingestion_failure(db, exc, raw_candidates)
        raise
    finally:
        conn.close()

    if also_rebuild:
        counts.update(rebuild(db, config=config, max_sessions=max_sessions))

    return counts


def backfill_incremental(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    jsonl_files: list[Path] | None = None,
    handles: list[SessionHandle] | None = None,
    since_ts: float | None = None,
    config: dict | None = None,
    also_rebuild: bool = False,
    host: str | None = None,
) -> dict[str, int]:
    """Ingest session sources modified after *since_ts* into ``raw_events``.

    Thin wrapper over :func:`backfill_raw_events` (ENH-2581): ingest only.
    The three legacy per-table watermarks (``last_backfill_ts``,
    ``last_backfill_ts_assistant_messages``, ``last_backfill_ts_skill_events``)
    collapse to the single ``last_raw_event_ts`` key maintained by
    :func:`backfill_raw_events`. Accepts either *jsonl_files* or *handles*
    (ENH-3422 D4; both given raises ``ValueError``, validated by the
    delegate).

    If *since_ts* is ``None``, reads ``last_raw_event_ts`` from the ``meta``
    table (defaults to 0.0 — all sources — when the key is absent or NULL).

    Pass ``also_rebuild=True`` to materialize the JSONL-derived cache tables
    from ``raw_events`` afterward in the same call — used by the
    ``SessionStart`` hook worker when :func:`rebuild_needed` reports ``stale`` (the
    derivation changed; see ``cli/backfill_worker.py --rebuild``).

    Issues and loop-state JSON are NOT backfilled here; this variant is
    ingest-only and designed for low-latency background use in session hooks.
    *host* names the host whose transcripts are ingested for the
    ``raw_events.host`` column (ENH-3166); omitted, the ambient host is used.
    Errors are not suppressed — the caller (the hook worker) handles them;
    ``HistorySanitizationError`` carries a content-free reason code only and
    leaves the watermark unchanged.
    """
    if also_rebuild:
        refuse_on_remote(db, "rebuild")
    if since_ts is None:
        conn = _pkg.connect(db)
        try:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = ?", (_watermark_key(db),)
            ).fetchone()
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

    raw_count = backfill_raw_events(
        db, jsonl_files=jsonl_files, handles=handles, since_ts=since_ts, host=host
    )
    counts: dict[str, int] = {"raw_events": raw_count}
    if also_rebuild:
        counts.update(rebuild(db, config=config))
    return counts


def compact(
    db: Path | str = DEFAULT_DB_PATH,
    *,
    config: dict | None = None,
    and_prune: bool = False,
) -> dict[str, Any]:
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
    count, held-row count (``retained_rows``) and ``retention_reasons`` into the
    return value.
    """
    refuse_on_remote(db, "compact")
    from little_loops.config.features import RetentionConfig

    raw = (config or {}).get("analytics", {}).get("retention", {})
    retention_cfg = RetentionConfig.from_dict(raw)
    result: dict[str, Any] = {
        "compacted_rows": 0,
        "summary_nodes": 0,
        "pruned_rows": 0,
        "retained_rows": 0,
        "retention_reasons": [],
    }

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
        result["retained_rows"] = prune_result.get("retained", {}).get("raw_events", 0)
        result["retention_reasons"] = list(prune_result.get("retention_reasons", []))

    return result


# Reasons a compacted, aged raw row is kept by prune's whole-source usage rule.
# ``usage_derive_unverified``: the derive checkpoint is missing, malformed, negative
# or from another normalizer version. ``usage_derive_pending``: the checkpoint lags
# the source's newest row. ``usage_replay_context_required``: part of the source is
# still recent or uncompacted, or retained usage depends on context another source
# would lose. Semantic veto (ENH-3744): ``usage_derive_gap`` (a recognized candidate
# has no committed representation), ``usage_proof_unprovable`` (identity, grain,
# order or retained input cannot be proved) and ``usage_proof_limit`` (the proof scope
# crossed a private size bound).
_RETENTION_UNVERIFIED = "usage_derive_unverified"
_RETENTION_PENDING = "usage_derive_pending"
_RETENTION_CONTEXT = "usage_replay_context_required"
_RETENTION_LIMIT = RETENTION_LIMIT
# ENH-3745: an unresolved source-recovery obligation (acquisition failure, native conflict,
# refresh, held-source derive gap, or an outstanding raw-cache component) needs the raw rows.
_RETENTION_RECOVERY = "source_recovery_pending"


def _valid_usage_checkpoint(conn: sqlite3.Connection) -> int | None:
    """Return the validated current-version usage derive floor, or None if unproven."""
    return _read_usage_checkpoint(conn).floor


@dataclass
class _PruneOverlay:
    """Effects of earlier planned source deletions a dry run has not performed.

    A real run sees them in the database; a dry run carries them here so later sources
    plan against the same evidence and counts/reasons match an actual prune.
    """

    deleted: set[str] = field(default_factory=set)
    markers: set[str] = field(default_factory=set)


def _eligible_sources(conn: sqlite3.Connection, cutoff_str: str) -> list[str]:
    """Sources holding at least one aged compacted raw row, in deterministic order."""
    return [
        row[0]
        for row in conn.execute(
            "SELECT source_path FROM raw_events GROUP BY source_path "
            "HAVING SUM(CASE WHEN ts < ? AND compacted = 1 THEN 1 ELSE 0 END) > 0 "
            "ORDER BY source_path",
            (cutoff_str,),
        )
    ]


def _source_has_linked_usage(conn: sqlite3.Connection, source_path: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM usage_events WHERE channel IS NOT 'live' AND source_path = ? "
            "UNION SELECT 1 FROM usage_events u JOIN raw_events r ON r.id = u.source_raw_event_id "
            "WHERE u.channel IS NOT 'live' AND r.source_path = ? LIMIT 1",
            (source_path, source_path),
        ).fetchone()
        is not None
    )


def _supplier_protected(
    conn: sqlite3.Connection,
    supplier: str | None,
    host: str | None,
    channel: str | None,
    holds: UsageReplayHolds,
    cutoff_str: str,
    overlay: _PruneOverlay,
) -> bool:
    """Whether a represented candidate's actual observation supplier stays protected.

    Protection follows the observation's stored ``source_path`` (or the host/channel
    population when attribution is absent), never an observation ID or raw pointer.
    """
    if holds.holds(supplier, host, channel):
        return True
    if supplier is None:
        return False
    sql = "SELECT 1 FROM raw_events WHERE source_path = ?"
    params: tuple[str, ...] = (supplier,)
    if supplier in overlay.deleted:
        sql += " AND NOT (ts < ? AND compacted = 1)"
        params = (supplier, cutoff_str)
    sql += " LIMIT 1"
    return conn.execute(sql, params).fetchone() is not None


def _semantic_veto(
    conn: sqlite3.Connection, source_path: str, cutoff_str: str, overlay: _PruneOverlay
) -> set[str]:
    """Reasons the retained candidates of *source_path* forbid deleting its raw rows.

    Evaluates the source's logical usage candidates against committed observations
    **before** anything is deleted. The checkpoint and age/compaction gates stay
    necessary conditions; this only adds a veto and never derives, prices, promotes
    or releases a hold. Empty means the proof imposes no objection.
    """
    try:
        scope = collect_usage_proof_scope(
            conn, source_path, deleted_sources=overlay.deleted, cutoff=cutoff_str
        )
    except UsageProofLimit:
        return {_RETENTION_LIMIT}
    proofs = list(inspect_scope(scope))
    reasons = set(retention_reasons(proofs))
    if reasons:
        return reasons
    holds = load_usage_replay_holds(conn)
    holds = UsageReplayHolds(holds.sources | frozenset(overlay.markers), holds.populations)
    for proof in proofs:
        if proof.correspondence != "represented":
            continue
        for supplier in proof.supplier_sources:
            if supplier == source_path:
                continue
            if not _supplier_protected(
                conn, supplier, proof.host, proof.channel, holds, cutoff_str, overlay
            ):
                return {_RETENTION_CONTEXT}
    return set()


def _source_recovery_pending(conn: sqlite3.Connection, source_path: str) -> bool:
    """Whether *source_path* has an unresolved usage or raw-cache recovery obligation."""
    return any(
        ob.usage_pending or ob.raw_cache_pending for ob in pending_obligations(conn, source_path)
    )


def _plan_raw_prune(
    conn: sqlite3.Connection,
    cutoff_str: str,
    *,
    sources: list[str] | None = None,
    overlay: _PruneOverlay | None = None,
) -> tuple[list[str], list[str], int, int, set[str]]:
    """Decide which compacted, aged raw rows prune may delete (BUG-3736, ENH-3744).

    Must run inside the transaction that deletes, so the derive checkpoint and
    source state it proves cannot change before commit. A source that may carry
    replay-derived usage (it has linked non-live usage, or the derive checkpoint
    does not cover it) is deleted whole or held whole: payload keys, raw pointers
    and token equality are never used as proof of replayability. A source the
    checkpoint would allow deleting is additionally vetoed when the semantic proof
    finds a candidate with no committed representation or one it cannot prove.
    *sources* limits planning to those sources (prune plans and commits one source per
    transaction); *overlay* carries a dry run's earlier planned deletions. Returns
    ``(delete_sources, marker_sources, deletable_rows, held_rows, reasons)`` where
    ``delete_sources`` are the sources whose aged compacted rows are removed and
    ``marker_sources`` is the subset of those that carry usage and need a hold marker.
    """
    checkpoint = _valid_usage_checkpoint(conn)
    overlay = overlay if overlay is not None else _PruneOverlay()
    delete_sources: list[str] = []
    marker_sources: list[str] = []
    deletable = held = 0
    reasons: set[str] = set()
    for source_path in sources if sources is not None else _eligible_sources(conn, cutoff_str):
        total, eligible, max_id = conn.execute(
            "SELECT COUNT(*), SUM(CASE WHEN ts < ? AND compacted = 1 THEN 1 ELSE 0 END), "
            "MAX(id) FROM raw_events WHERE source_path = ?",
            (cutoff_str, source_path),
        ).fetchone()
        if not eligible:
            continue
        if _source_recovery_pending(conn, source_path):
            # An unresolved acquisition/conflict/refresh/derive obligation still needs this
            # source's raw rows as evidence. Prune never acknowledges or deletes it.
            held += eligible
            reasons.add(_RETENTION_RECOVERY)
            continue
        capable = (
            checkpoint is None or max_id > checkpoint or _source_has_linked_usage(conn, source_path)
        )
        if not capable or (checkpoint is not None and eligible == total and max_id <= checkpoint):
            veto = _semantic_veto(conn, source_path, cutoff_str, overlay)
            if veto:
                held += eligible
                reasons |= veto
                continue
            delete_sources.append(source_path)
            deletable += eligible
            overlay.deleted.add(source_path)
            if capable:
                marker_sources.append(source_path)
                overlay.markers.add(source_path)
        else:
            held += eligible
            if checkpoint is None:
                reasons.add(_RETENTION_UNVERIFIED)
            elif max_id > checkpoint:
                reasons.add(_RETENTION_PENDING)
            else:
                reasons.add(_RETENTION_CONTEXT)
    return delete_sources, marker_sources, deletable, held, reasons


_PARTIAL_PRUNE_NOTE = (
    "history prune stopped at one source; earlier sources may already be committed. "
    "Re-running prune is safe."
)


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

    Usage-bearing sources are never deleted in part (BUG-3736). A source that
    carries, or may yet carry, replay-derived usage is deleted only when every row
    is old, compacted and at or below a valid current-version usage derive
    checkpoint; otherwise the whole source is retained. Deleting such a source
    writes a ``usage_replay_holds`` marker in the same transaction, so a later
    rebuild or catch-up leaves its retained usage alone. A checkpoint alone never
    proves the usage was captured (ENH-3744): a source whose recognized logical
    candidates lack a compatible committed observation, or whose correspondence cannot
    be proved, keeps its raw rows.

    Each source is planned, protected and deleted in its own ``BEGIN IMMEDIATE``
    transaction, re-reading every cross-source witness after earlier commits. A failure
    rolls back only the failing source, stops further deletion and re-raises; sources
    already committed stay committed and re-running is safe. A dry run reads one
    snapshot, writes nothing, and carries earlier planned deletions in memory so its
    counts and reasons match an actual prune absent concurrent changes.

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
        - ``retained`` (dict[str, int]): ``{"raw_events": count}`` of aged compacted rows
          kept by the whole-source usage rule, each counted once
        - ``retention_reasons`` (list[str]): sorted subset of ``usage_derive_unverified``,
          ``usage_derive_pending``, ``usage_replay_context_required``, ``usage_derive_gap``,
          ``usage_proof_unprovable`` and ``usage_proof_limit``
        - ``vacuumed`` (bool): whether VACUUM ran (always False in dry_run)
    """
    refuse_on_remote(db, "prune")
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
        "retained": {"raw_events": 0},
        "retention_reasons": [],
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

        deleted_count = held_count = 0
        reasons: set[str] = set()
        if dry_run:
            # One consistent read snapshot; earlier planned deletions live in the overlay.
            overlay = _PruneOverlay()
            conn.execute("BEGIN")
            try:
                for source_path in _eligible_sources(conn, cutoff_str):
                    _, _, deleted, held, source_reasons = _plan_raw_prune(
                        conn, cutoff_str, sources=[source_path], overlay=overlay
                    )
                    deleted_count += deleted
                    held_count += held
                    reasons |= source_reasons
            finally:
                conn.rollback()
        else:
            for source_path in _eligible_sources(conn, cutoff_str):
                # Take the write lock before reading derive/source proof so a concurrent
                # derive or refresh cannot invalidate it before this source commits.
                conn.execute("BEGIN IMMEDIATE")
                try:
                    delete_sources, marker_sources, deleted, held, source_reasons = _plan_raw_prune(
                        conn, cutoff_str, sources=[source_path]
                    )
                    now = _now()
                    conn.executemany(
                        "INSERT OR IGNORE INTO usage_replay_holds"
                        "(source_path, host, channel, reason, created_at) "
                        "VALUES(?, '*', '*', 'pruned_whole_source', ?)",
                        [(marker, now) for marker in marker_sources],
                    )
                    conn.executemany(
                        "DELETE FROM raw_events WHERE source_path = ? AND ts < ? AND compacted = 1",
                        [(delete, cutoff_str) for delete in delete_sources],
                    )
                    conn.commit()
                except BaseException as exc:
                    conn.rollback()
                    exc.add_note(_PARTIAL_PRUNE_NOTE)
                    raise
                deleted_count += deleted
                held_count += held
                reasons |= source_reasons

        result["deleted"] = {"raw_events": deleted_count}
        result["retained"] = {"raw_events": held_count}
        result["retention_reasons"] = sorted(reasons)
        result["pruned"] = True
    finally:
        conn.close()

    # VACUUM outside the original connection to avoid transaction conflicts
    if result["pruned"] and not dry_run:
        try:
            with translate_sqlite_errors():
                vac_conn = _pkg.open_history(db_path)
                vac_conn.isolation_level = None
                try:
                    vac_conn.execute("VACUUM")
                    result["vacuumed"] = True
                finally:
                    vac_conn.close()
        except HistoryError as exc:
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
    conn = _pkg.open_history(db)
    try:
        with translate_sqlite_errors():
            rows = conn.execute(
                "SELECT topic_fingerprint, rule_id, addressed_at, session_id"
                " FROM correction_retirements ORDER BY addressed_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]
    except HistoryError:
        return []
    finally:
        conn.close()
