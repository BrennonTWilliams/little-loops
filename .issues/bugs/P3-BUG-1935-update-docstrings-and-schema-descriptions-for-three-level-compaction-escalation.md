---
id: BUG-1935
title: Update docstrings and schema descriptions for three-level compaction escalation
type: BUG
priority: P3
status: open
parent: BUG-1928
relates_to:
- EPIC-1707
- FEAT-1712
labels:
- bug
- history
- session-store
- context-management
- documentation
size: Small
---

# BUG-1935: Update docstrings and schema descriptions for three-level compaction escalation

## Summary

After the core three-level escalation fix (BUG-1934), several docstrings, migration comments, and config-schema descriptions still describe the old binary fallback (LLM → truncation). Update them to reflect the actual three-level chain: level 1 (preserve-details) → level 2 (aggressive/bullet-point at T/2) → level 3 (deterministic truncation).

## Parent Issue

Decomposed from BUG-1928: Summarizer skips LCM Algorithm 3 convergence check and level-2 escalation

## Scope

This child covers documentation, comment, and schema description updates only. The code change and tests are in BUG-1934.

### Covers Parent Steps

Steps 7, 8, 9, 16 from BUG-1928 Implementation Steps.

## Implementation Steps

1. **Update `compact_session()` docstring** (`session_store.py:1174`): Change "On LLM failure, falls back to deterministic truncation so a leaf node is always produced" to describe the three-level chain (level 1 → level 2 aggressive → level 3 truncation).

2. **Update v10 migration comment** (`session_store.py:303-305`): Broaden "LLM-generated (or truncation-fallback) summaries" to reflect the three-level escalation. Minor; only if wording feels misleading.

3. **Update `config-schema.json:1529` timeout description**: Change "On timeout, falls back to deterministic truncation" to "On timeout, escalation proceeds through remaining levels, ultimately to deterministic truncation."

4. **Update `config-schema.json:1507-1509` compaction object description**: Broaden to mention three-level escalation and convergence guarantee, consistent with the updated timeout (line 1529) and budget_tokens (line 1519) descriptions.

## Files to Modify

- `scripts/little_loops/session_store.py` — docstring at line 1174, migration comment at line 303-305
- `config-schema.json` — timeout description at line 1529, compaction object description at lines 1507-1509

## Acceptance Criteria

- `compact_session()` docstring accurately describes the three-level escalation chain
- `config-schema.json` timeout and compaction descriptions match the implemented behavior
- No code changes — documentation only

## Impact

**Who benefits**: Developers and operators reading docs to understand compaction behavior. **Severity**: P3 — documentation accuracy for an opt-in feature.

## Session Log

- `/ll:issue-size-review` - 2026-06-04T08:56:00Z - `f4ca78cf-649f-4e81-a544-c9b72f755584.jsonl`
