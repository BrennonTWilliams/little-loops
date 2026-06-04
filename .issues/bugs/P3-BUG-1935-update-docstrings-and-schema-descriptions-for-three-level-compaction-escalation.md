---
id: BUG-1935
title: Update docstrings and schema descriptions for three-level compaction escalation
type: BUG
priority: P3
status: done
testable: false
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
size: Large
confidence_score: 100
outcome_confidence: 71
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 10
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

## Current Behavior

Docstrings, migration comments, and schema descriptions across multiple files describe the old binary fallback model for compaction — an LLM summary that either succeeds or falls back to deterministic truncation. No intermediate escalation level is documented. Specifically:

- `compact_session()` docstring: "On LLM failure, falls back to deterministic truncation"
- v10 migration comment: "LLM-generated (or truncation-fallback) summaries"
- `CompactionConfig` docstring: "LLM summaries (or truncation fallbacks)"
- `config-schema.json` compaction description: no mention of escalation levels
- `config-schema.json` timeout description: "On timeout, falls back to deterministic truncation"
- `docs/ARCHITECTURE.md` v10 schema table: "LLM-generated (or truncation-fallback)"

The canonical `_summarize_block()` docstring at `session_store.py:1045` was updated in BUG-1934 to correctly describe all three levels — all other locations still carry the stale binary framing.

## Expected Behavior

All documentation, comments, and schema descriptions should accurately describe the three-level LCM Algorithm 3 escalation chain implemented by `_summarize_block()`:

1. **Level 1**: Normal LLM summary (preserve details), accepted only if output < input
2. **Level 2**: Aggressive bullet-point LLM summary at `budget // 2`, triggered when level 1 output is not smaller than input
3. **Level 3**: Deterministic truncation (`min(budget * 4, 2048)` chars), guaranteed convergence

The canonical source at `session_store.py:1045` (`_summarize_block()` docstring) serves as the language template for all other locations.

## Steps to Reproduce

1. Read the `compact_session()` docstring at `scripts/little_loops/session_store.py:1344` — observe it references binary "LLM failure → truncation" fallback with no intermediate level 2
2. Read the v10 migration comment at `scripts/little_loops/session_store.py:305` — observe "LLM-generated (or truncation-fallback)" language
3. Read the `CompactionConfig` dataclass docstring at `scripts/little_loops/config/features.py:721` — observe "LLM summaries (or truncation fallbacks)"
4. Read the `compaction` object description at `config-schema.json:1509` — observe no mention of three-level escalation or convergence guarantee
5. Read the `timeout` description at `config-schema.json:1529` — observe "falls back to deterministic truncation" with no mention of intermediate levels
6. Read the v10 schema table row at `docs/ARCHITECTURE.md:562` — observe "LLM-generated (or truncation-fallback)"
7. Compare each location against the canonical `_summarize_block()` docstring at `session_store.py:1045` — observe the canonical source correctly describes all three levels while all other locations do not

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py:1344` — `compact_session()` docstring: stale binary fallback language ("On LLM failure, falls back to deterministic truncation")
- `scripts/little_loops/session_store.py:305` — v10 migration comment: "LLM-generated (or truncation-fallback) summaries"
- `scripts/little_loops/config/features.py:721` — `CompactionConfig` dataclass docstring: "LLM summaries (or truncation fallbacks)" *(found during codebase research)*
- `config-schema.json:1509` — `compaction` object description: no mention of three-level escalation
- `config-schema.json:1529` — `timeout` description: "On timeout, falls back to deterministic truncation"
- `docs/ARCHITECTURE.md:562` — v10 schema table entry: "LLM-generated (or truncation-fallback)" *(found during codebase research)*

### Source of Truth
- `session_store.py:1045` — `_summarize_block()` docstring: already correctly describes all three levels (was updated in BUG-1934). Serves as the canonical language for all other updates.

### Tests
- `scripts/tests/test_session_store.py:1878` — `TestSummarizeBlock` class: tests level-1 accept, level-2 escalation, level-3 truncation
- `scripts/tests/test_session_store.py:1627` — `TestCompactSession` class: integration tests for `compact_session()`

### Dependent Files (No Changes Needed)
- `scripts/little_loops/config/core.py:664` — serializes `CompactionConfig` values; unaffected by docstring changes
- Config schema consumers are unaffected by description-only changes

## Root Cause

- **File**: Multiple files (see Integration Map above)
- **Anchor**: Six locations across four files
- **Cause**: BUG-1934 implemented three-level LCM Algorithm 3 escalation in `_summarize_block()` and updated that function's docstring, but left five other locations describing the old binary fallback model (LLM success or truncation, with no intermediate level 2). The `config-schema.json` compaction object description never mentioned escalation at all. These stale references now misrepresent the actual behavior:
  1. **Level 1**: Normal LLM summary (preserve details), accepted only if output < input
  2. **Level 2**: Aggressive bullet-point LLM summary at `budget // 2`, triggered when level 1 output is not smaller than input
  3. **Level 3**: Deterministic truncation (`min(budget * 4, 2048)` chars), guaranteed convergence

## Implementation Steps

1. **Update `compact_session()` docstring** (`session_store.py:1344`): Change "On LLM failure, falls back to deterministic truncation so a leaf node is always produced" to describe the three-level chain (level 1 → level 2 aggressive → level 3 truncation). Use language from the canonical `_summarize_block()` docstring.

2. **Update v10 migration comment** (`session_store.py:305`): Broaden "LLM-generated (or truncation-fallback) summaries" to mention three-level LCM Algorithm 3 escalation. The "at two levels" phrase refers to DAG node kinds (leaf/condensed), not escalation levels — keep that part unchanged.

3. **Update `config-schema.json:1529` timeout description**: Change "On timeout, falls back to deterministic truncation" to "On timeout, escalation proceeds through remaining levels, ultimately to deterministic truncation."

4. **Update `config-schema.json:1509` compaction object description**: Broaden to mention three-level LCM Algorithm 3 pipeline and convergence guarantee, consistent with the updated timeout and budget_tokens descriptions.

5. **Update `CompactionConfig` docstring** (`config/features.py:721`): Change "LLM summaries (or truncation fallbacks)" to describe the three-level LCM Algorithm 3 escalation chain (normal → aggressive bullet-point → deterministic truncation). Found during codebase research — this dataclass docstring has the same stale binary fallback language.

6. **Update `docs/ARCHITECTURE.md:562` v10 schema table row**: Change "LLM-generated (or truncation-fallback) summaries" to reflect the three-level escalation. Found during codebase research — the architecture documentation carried the same stale binary framing.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Fix already applied**: Commit `65fa9ebd` (`fix(docs): update docstrings and schema descriptions for three-level compaction escalation`) applied all six docstring/comment/schema updates. All locations now carry three-level LCM Algorithm 3 language derived from the canonical `_summarize_block()` docstring at `session_store.py:1046`.
- **No remaining stale references**: A comprehensive search for binary-fallback language (`"LLM failure → truncation"`, `"truncation-fallback"`, `"two-level"`) across `scripts/`, `docs/`, and `config-schema.json` returned zero remaining stale locations.
- **Internal helpers correctly defer**: `_compact_session_conn()` at `session_store.py:1226` and `_compact_sessions()` at `session_store.py:1315` do not repeat escalation language — they correctly delegate to `_summarize_block()`. No update needed.
- **Additional test coverage found** (beyond what the issue listed):
  - `scripts/tests/test_history_reader.py:667-685` — `_make_db_with_compact_session()` helper
  - `scripts/tests/test_history_reader.py:779-800` — `_make_db_with_two_leaves()` helper for condensed node tests
  - `scripts/tests/test_ll_session.py:534-550` — `compact_session` usage in session tests
  - `scripts/tests/test_config.py:2770-2784` — `test_compaction_defaults()` and `test_compaction_override()`
  - `scripts/tests/test_config_schema.py:302-317` — `test_history_compaction_in_schema()`
- **Test-to-level mapping**: `TestSummarizeBlock` methods map 1:1 to the three escalation levels:
  - `test_level_1_accepts_smaller_summary` → "Accepted only if output < input"
  - `test_level_1_escalates_when_summary_not_smaller` → "Triggered when level-1 output is not smaller than input"
  - `test_level_2_accepts_smaller_summary` → Level 2 acceptance + fall-through to level 3 when level 2 also fails
  - `test_level_3_truncation_when_llm_fails` / `_when_timeout` / `_when_nonzero_returncode` → "Guaranteed to produce output"

## Acceptance Criteria

- `compact_session()` docstring accurately describes the three-level LCM Algorithm 3 escalation chain
- v10 migration comment reflects three-level escalation (not binary "LLM or truncation")
- `config-schema.json` timeout description explains escalation through remaining levels
- `config-schema.json` compaction object description mentions three-level pipeline and convergence guarantee
- `CompactionConfig` docstring in `features.py` describes three-level escalation instead of binary fallback
- `docs/ARCHITECTURE.md` v10 schema table entry reflects three-level escalation
- No code changes — documentation only

## Impact

**Who benefits**: Developers and operators reading docs to understand compaction behavior. **Severity**: P3 — documentation accuracy for an opt-in feature.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-04_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- **Enumeration without verification grep**: 6 change sites across 4 files are manually enumerated. Without a `grep` command to verify completeness, any missed site goes undetected until a reader notices. The mechanical nature of the changes mitigates this (all sites receive the same conceptual substitution).
- **No automated docstring-validation tests**: Documentation-only changes have no test harness validating their accuracy against behavior. Mitigation: the canonical source (`_summarize_block()` docstring at line 1045) was already updated in BUG-1934, so all other sites are derivations of verified language.

## Session Log
- `/ll:refine-issue` - 2026-06-04T13:17:25 - `41fac8c3-64a6-405b-836b-b471d0afef3e.jsonl`
- `/ll:format-issue` - 2026-06-04T13:09:20 - `82856f60-632c-4be7-8861-3cb93a5f2d7a.jsonl`
- `/ll:wire-issue` - 2026-06-04T08:16:35 - `7798db91-aacc-4ddc-bf44-1ff88b579450.jsonl`
- `/ll:refine-issue` - 2026-06-04T08:08:55 - `6096ff71-e430-4583-8b43-9df0c253ad76.jsonl`

- `/ll:issue-size-review` - 2026-06-04T08:56:00Z - `f4ca78cf-649f-4e81-a544-c9b72f755584.jsonl`
- `/ll:confidence-check` - 2026-06-04T10:19:00Z - `1d79c2a4-aa6d-44b7-b6ad-5d8c5f8d0c97.jsonl`
