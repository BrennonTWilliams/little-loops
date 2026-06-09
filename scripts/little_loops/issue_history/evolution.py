"""Evolution trigger detectors for analyze-history (ENH-1911).

Queries history.db to surface recurring user corrections and skill bypasses
as quantified signals for harness self-improvement.
"""

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any

from little_loops.config.features import EvolutionConfig
from little_loops.history_reader import _stale_cutoff
from little_loops.issue_history.models import (
    RecurringFeedback,
    RecurringFeedbackAnalysis,
    SkillBypass,
    SkillBypassAnalysis,
)

logger = logging.getLogger(__name__)

_STALE_DAYS = 90  # Look back 90 days for evolution signals


def _open_db(db_path: Path) -> sqlite3.Connection | None:
    """Open *db_path* for read-only querying without running schema migrations.

    Uses a direct URI connection so the file is opened as-is.  This avoids the
    ``ensure_db`` migration path inside ``_connect_readonly``, which fails when
    the database was created by the test harness (tables already exist).
    Returns ``None`` when the file does not exist.
    """
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON")
        return conn
    except sqlite3.Error:
        logger.warning("evolution: could not open %s read-only", db_path, exc_info=True)
        return None


_MIN_BYPASS_KEYWORDS = 2  # Require >= 2 keyword tokens to reduce false positives


def _fingerprint(content: str) -> str:
    """Return a stable 16-char hex fingerprint for a correction content string."""
    return hashlib.sha256(content[:512].encode()).hexdigest()[:16]


def _load_memory_feedback(project_root: Path) -> dict[str, str]:
    """Load curated feedback topics and content from memory/feedback_* files."""
    result: dict[str, str] = {}
    memory_dir = project_root / "memory"
    if not memory_dir.is_dir():
        return result
    for f in sorted(memory_dir.glob("feedback_*.md")):
        try:
            content = f.read_text(encoding="utf-8")
            # Strip frontmatter
            if content.startswith("---"):
                end = content.find("---", 3)
                body = content[end + 3 :].strip() if end != -1 else content.strip()
            else:
                body = content.strip()
            result[f.stem] = body[:500]
        except OSError:
            pass
    return result


def _get_session_ids_for_content(conn: sqlite3.Connection, content: str, cutoff: str) -> list[str]:
    """Return distinct session IDs containing a correction matching content."""
    try:
        rows = conn.execute(
            "SELECT DISTINCT session_id FROM user_corrections "
            "WHERE content = ? AND ts >= ? LIMIT 10",
            (content, cutoff),
        ).fetchall()
        return [row["session_id"] for row in rows if row["session_id"]]
    except sqlite3.Error:
        return []


def detect_recurring_feedback(
    db_path: Path,
    config: EvolutionConfig,
    project_root: Path | None = None,
) -> RecurringFeedbackAnalysis:
    """Detect user corrections that have recurred >= config.feedback_min_recurrence times.

    Queries user_corrections grouped by content with a HAVING threshold filter,
    enriches each result with session IDs, and cross-references memory/feedback_*
    files for candidate_rule seeds.
    """
    conn = _open_db(db_path)
    if conn is None:
        return RecurringFeedbackAnalysis()

    try:
        cutoff = _stale_cutoff(_STALE_DAYS)
        threshold = config.feedback_min_recurrence

        try:
            rows = conn.execute(
                "SELECT content, COUNT(*) AS seen_count "
                "FROM user_corrections "
                "WHERE ts >= ? "
                "GROUP BY content "
                "HAVING seen_count >= ? "
                "ORDER BY seen_count DESC, MAX(ts) DESC "
                "LIMIT 50",
                (cutoff, threshold),
            ).fetchall()
        except sqlite3.Error:
            logger.warning("evolution: recurring feedback query failed", exc_info=True)
            return RecurringFeedbackAnalysis()

        memory_feedback = _load_memory_feedback(project_root) if project_root else {}

        # Load retirement fingerprints — fall back gracefully for old DBs missing the table.
        try:
            retired_rows = conn.execute(
                "SELECT topic_fingerprint, rule_id FROM correction_retirements"
            ).fetchall()
            retirements: dict[str, str] = {
                r["topic_fingerprint"]: (r["rule_id"] or "") for r in retired_rows
            }
        except sqlite3.OperationalError:
            retirements = {}

        feedbacks: list[RecurringFeedback] = []
        retired_count = 0
        for row in rows:
            content = row["content"] or ""
            count = row["seen_count"]
            fingerprint = _fingerprint(content)

            # Exclude clusters that have been addressed and retired.
            if fingerprint in retirements:
                retired_count += 1
                continue

            session_ids = _get_session_ids_for_content(conn, content, cutoff)

            # Match memory feedback files by shared keywords as candidate_rule seed
            candidate_rule = ""
            content_words = set(re.findall(r"[a-z]{3,}", content.lower()))
            for _mem_topic, mem_body in memory_feedback.items():
                topic_words = set(re.findall(r"[a-z]{3,}", _mem_topic.lower()))
                if topic_words & content_words:
                    candidate_rule = mem_body[:200]
                    break

            excerpt = content[:120] + "..." if len(content) > 120 else content
            feedbacks.append(
                RecurringFeedback(
                    topic=excerpt,
                    occurrence_count=count,
                    example_sessions=session_ids[:5],
                    example_content=[content[:200]],
                    candidate_rule=candidate_rule,
                    topic_fingerprint=fingerprint,
                )
            )

        rule_candidates = [f.candidate_rule for f in feedbacks if f.candidate_rule][:10]
        return RecurringFeedbackAnalysis(
            feedbacks=feedbacks,
            total_recurring_corrections=sum(f.occurrence_count for f in feedbacks),
            threshold_used=threshold,
            rule_candidates=rule_candidates,
            retired_count=retired_count,
        )
    finally:
        conn.close()


def _load_skill_keywords(project_root: Path) -> dict[str, set[str]]:
    """Load keyword sets for all registered skills."""
    from little_loops.cli.verify_triggers import _extract_keywords, _load_skill_descriptions

    skills_dir = project_root / "skills"
    descriptions = _load_skill_descriptions(skills_dir)
    return {name: _extract_keywords(desc) for name, (desc, _path) in descriptions.items()}


def _tokenize_content(text: str) -> set[str]:
    """Tokenize message content for keyword matching."""
    from little_loops.cli.verify_triggers import _tokenize

    return _tokenize(text[:512])


def detect_skill_bypass(
    db_path: Path,
    config: EvolutionConfig,
    project_root: Path | None = None,
) -> SkillBypassAnalysis:
    """Detect sessions where user manually performed work a skill covers.

    Compares message_events content against skill keyword sets. A bypass is counted
    when >= _MIN_BYPASS_KEYWORDS keyword tokens match AND no skill_events row for
    that skill exists in the same session. Conservative threshold reduces false positives.
    """
    if project_root is None:
        return SkillBypassAnalysis()

    conn = _open_db(db_path)
    if conn is None:
        return SkillBypassAnalysis()

    try:
        cutoff = _stale_cutoff(_STALE_DAYS)
        threshold = config.bypass_min_count

        skill_keywords = _load_skill_keywords(project_root)
        if not skill_keywords:
            return SkillBypassAnalysis()

        try:
            messages = conn.execute(
                "SELECT session_id, content FROM message_events WHERE ts >= ? LIMIT 5000",
                (cutoff,),
            ).fetchall()

            skill_rows = conn.execute(
                "SELECT skill_name, session_id FROM skill_events WHERE ts >= ?",
                (cutoff,),
            ).fetchall()
        except sqlite3.Error:
            logger.warning("evolution: skill bypass query failed", exc_info=True)
            return SkillBypassAnalysis()

        # Build invocation map: skill_name -> set of session_ids where skill WAS invoked
        skill_invocations: dict[str, set[str]] = {}
        for row in skill_rows:
            skill_name = row["skill_name"]
            session_id = row["session_id"]
            if skill_name and session_id:
                skill_invocations.setdefault(skill_name, set()).add(session_id)

        # Per-skill bypass accumulators
        bypass_data: dict[str, dict[str, Any]] = {
            name: {"count": 0, "sessions": [], "evidence": []} for name in skill_keywords
        }
        # Dedupe: only count each (skill, session) pair once
        seen_pairs: dict[str, set[str]] = {name: set() for name in skill_keywords}

        for msg in messages:
            session_id = msg["session_id"]
            content = msg["content"] or ""
            if not session_id or not content:
                continue

            tokens = _tokenize_content(content)
            if not tokens:
                continue

            for skill_name, keywords in skill_keywords.items():
                if session_id in seen_pairs[skill_name]:
                    continue
                # Require >= _MIN_BYPASS_KEYWORDS matching tokens (conservative)
                if len(tokens & keywords) < _MIN_BYPASS_KEYWORDS:
                    continue
                # Check if skill was invoked in this session
                if session_id in skill_invocations.get(skill_name, set()):
                    continue
                # Bypass detected
                seen_pairs[skill_name].add(session_id)
                data = bypass_data[skill_name]
                data["count"] += 1
                if len(data["sessions"]) < 5:
                    data["sessions"].append(session_id)
                if len(data["evidence"]) < 3:
                    data["evidence"].append(content[:150])

        bypasses: list[SkillBypass] = []
        for skill_name, data in bypass_data.items():
            if data["count"] >= threshold:
                bypasses.append(
                    SkillBypass(
                        skill_name=skill_name,
                        bypass_count=data["count"],
                        example_sessions=data["sessions"],
                        evidence=data["evidence"],
                        suggested_improvement=(
                            f"Review trigger keywords for '{skill_name}' — "
                            f"users are doing this manually {data['count']}x"
                        ),
                    )
                )

        bypasses.sort(key=lambda b: -b.bypass_count)
        suggestions = [
            f"Sharpen trigger for '{b.skill_name}' (bypassed {b.bypass_count}x)" for b in bypasses
        ][:10]

        return SkillBypassAnalysis(
            bypasses=bypasses,
            total_bypassed_invocations=sum(b.bypass_count for b in bypasses),
            threshold_used=threshold,
            improvement_suggestions=suggestions,
        )
    finally:
        conn.close()
