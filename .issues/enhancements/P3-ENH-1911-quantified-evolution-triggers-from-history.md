---
id: ENH-1911
title: Quantified evolution triggers from history (recurring feedback + skill bypass)
type: ENH
priority: P3
status: done
captured_at: '2026-06-03T20:59:38Z'
completed_at: '2026-06-09T00:28:49Z'
discovered_date: 2026-06-03
discovered_by: capture-issue
depends_on:
- ENH-1906
parent: EPIC-2027
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-1911: Quantified evolution triggers from history (recurring feedback + skill bypass)

## Summary

Extend `analyze-history` (and feed `improve-claude-md`) with quantified "evolution trigger"
signals modeled on `revfactory/harness`'s Phase 7: detect when the **same user correction has
recurred ≥N times** and when a user has **bypassed a skill/loop N times** (did the work
manually instead of invoking the matching skill). Both signals turn accreted history into
concrete, count-backed proposals for harness self-improvement (a CLAUDE.md rule, a sharper
skill description, or a new loop).

## Current Behavior

`analyze-history` surfaces recurring manual activity (`ManualPattern` / `ManualPatternAnalysis`) but does not quantify:
- How many times the same user correction has recurred across sessions
- How many times a user bypassed a registered skill or loop, doing the work manually instead

Corrections accumulate in `memory/feedback_*` files without recurrence counts; skill/loop bypasses go undetected.

## Expected Behavior

`analyze-history` gains an `## Evolution Triggers` section reporting:
- **Recurring feedback**: corrections clustered by topic, with occurrence counts, example session IDs, and a candidate permanent-rule proposal for any cluster meeting the configured threshold
- **Skill bypass**: skills/loops where the user performed the work manually instead of invoking them, with bypass counts and example sessions

`improve-claude-md` receives the ranked candidates annotated with recurrence counts to justify CLAUDE.md rule additions or skill-description tweaks. Both thresholds are configurable via `analysis.evolution.*` in `.ll/ll-config.json`.

## Motivation

little-loops already detects recurring *manual* activity — `ManualPattern` /
`ManualPatternAnalysis` (`scripts/little_loops/issue_history/models.py`) flags activities
across ≥2 issues and suggests automation. But it does **not** quantify two signals harness
makes load-bearing:
- **Recurring feedback**: the same correction given repeatedly. little-loops captures these
  ad hoc as `memory/feedback_*` files but never counts recurrence to justify a permanent rule.
- **Skill bypass**: the user repeatedly doing by hand what a skill/loop already does — a strong
  "the trigger isn't firing or the skill is too heavy" signal.

**Why:** "Same feedback ≥2 times" and "user bypassed the orchestrator" are exactly the
evolution triggers that keep a harness from drifting. little-loops has the raw material
(`.ll/history.db`, `memory/feedback_*`) but no counter that converts recurrence into action.
**How to apply:** This is a *detector + proposer*, not an auto-editor. It surfaces ranked,
count-backed candidates; applying a change stays with `improve-claude-md` / the user.

## Motivating Signal (from this conversation)

A review of harness's Phase 7 "Evolution Triggers" (fire on: same feedback type 2+ times,
repeated failure pattern, user bypasses orchestrator) highlighted that little-loops detects
recurring manual work but not recurring *feedback* or *bypass*.

## Implementation Steps

0. **Coordinate with ENH-1906 retention policy.** Ensure correction-shaped `message_events`
   rows are either (a) excluded from pruning until recurrence analysis has run, or (b) rolled
   up into FEAT-1712 summaries with topic + occurrence-count preserved. If the roll-up format
   does not preserve topic-level recurrence counts, request a
   `recurrence_exempt_tables: [user_corrections, message_events]` override in the retention
   config before pruning is enabled.

1. **Define models** in `scripts/little_loops/issue_history/models.py` (after `ManualPatternAnalysis` at line 391). Add four dataclasses following the `ManualPattern`/`ManualPatternAnalysis` field conventions (required positional first, then `occurrence_count: int = 0`, `list[str]` fields with `field(default_factory=list)`, string fields defaulting to `""`; `to_dict()` with slice caps):
   - `RecurringFeedback(topic, occurrence_count, example_sessions, example_content, candidate_rule)`
   - `RecurringFeedbackAnalysis(feedbacks, total_recurring_corrections, threshold_used, rule_candidates)`
   - `SkillBypass(skill_name, bypass_count, example_sessions, evidence, suggested_improvement)`
   - `SkillBypassAnalysis(bypasses, total_bypassed_invocations, threshold_used, improvement_suggestions)`
   Also add two optional fields to `HistoryAnalysis` (after line 672): `recurring_feedback_analysis: RecurringFeedbackAnalysis | None = None` and `skill_bypass_analysis: SkillBypassAnalysis | None = None`.

2. **Implement `detect_recurring_feedback()`** in new `scripts/little_loops/issue_history/evolution.py`. Reuse `_query_recurring_corrections()` pattern from `history_reader.py:869` (`GROUP BY content`, `COUNT(*) AS seen_count`) over `user_corrections`; filter by `seen_count >= threshold` (from `EvolutionConfig.feedback_min_recurrence`). Enrich each row with `session_id` list via a secondary query. Use `_connect_readonly()` + `_stale_cutoff()` from `history_reader.py`. Also scan `memory/feedback_*` files for curated signal (topic as filename stem, content as `candidate_rule` seed).

3. **Implement `detect_skill_bypass()`** in `evolution.py`. Enumerate registered skills using the `_load_skill_descriptions()` + `_extract_keywords()` / `_match_phrasing()` pattern from `cli/verify_triggers.py`. For each session, check whether correction-shaped `message_events` content matches a skill's keywords but no `skill_events.skill_name` row for that skill exists in the same session window. Count per-skill bypass sessions; surface those meeting `EvolutionConfig.bypass_min_count`. Start conservative (require ≥2 keyword tokens to match, not just 1) to reduce false positives per Open Question #1.

4. **Wire into orchestrator** at `scripts/little_loops/issue_history/analysis.py` after line 134 (after `detect_manual_patterns`). Call both detectors, thread `EvolutionConfig` thresholds from `HistoryConfig.evolution`, assign to `HistoryAnalysis.recurring_feedback_analysis` and `skill_bypass_analysis`. `calculate_analysis()` signature does not yet accept `db_path` — add it as an optional `Path | None = None` parameter defaulting to `session_store.DEFAULT_DB_PATH`.

5. **Add report sections** to `scripts/little_loops/issue_history/formatting.py`. In `format_analysis_markdown()` (after line 883) and `format_analysis_text()` (after line 362), add an `## Evolution Triggers` section guarded by `if analysis.recurring_feedback_analysis or analysis.skill_bypass_analysis:`. Render two subsections: `### Recurring Corrections` (table: Topic | Count | Example Sessions | Candidate Rule) and `### Skill Bypasses` (table: Skill | Bypass Count | Example Sessions | Suggested Improvement).

6. **Export from `__init__.py`**: add `RecurringFeedback`, `RecurringFeedbackAnalysis`, `SkillBypass`, `SkillBypassAnalysis` at both the import block (lines 103–104) and `__all__` (lines 150–151). Add `detect_recurring_feedback`, `detect_skill_bypass` from the new `evolution` module.

7. **Update skill files**: `skills/analyze-history/SKILL.md` — document `## Evolution Triggers` output format. `skills/improve-claude-md/SKILL.md` and `algorithm.md` — document consumption of `RecurringFeedbackAnalysis.rule_candidates` and `SkillBypassAnalysis.improvement_suggestions` as additional input signals.

8. **Tests**: new `scripts/tests/test_evolution_triggers.py` with `TestDetectRecurringFeedback` and `TestDetectSkillBypass` classes following `TestDetectManualPatterns` structure in `test_issue_history_quality.py` (empty-input early-return, threshold filtering, session grouping). Extend `test_issue_history_advanced_analytics.py` with model `to_dict()` round-trip tests. Extend `test_issue_history_formatting.py` with Evolution Triggers markdown section tests.

9. **Config**: `config-schema.json` already has `analysis.evolution.*` keys (lines 1549–1565); `EvolutionConfig` in `config/features.py` already exists. Verify thresholds are passed through `calculate_analysis()` → detector calls — no new schema work needed.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `scripts/little_loops/cli/history.py:main_history()` — In the `analyze` branch (lines 256–289), compute and pass `db_path` to `calculate_analysis()` using the `DEFAULT_DB_PATH` / `resolve_history_db` pattern already used in the `summary` and `sessions` branches. This threads the `db_path` parameter added in Step 4 through to the new detectors.
11. Update `scripts/tests/test_cli_history.py` — Add test verifying the `analyze` branch resolves and passes `db_path` correctly to the mocked `calculate_analysis`; follow the existing mock pattern in that file.

## API/Interface

- `analyze-history` report gains an `## Evolution Triggers` section (rendered by `formatting.py:format_analysis_markdown()` after the Manual Pattern Analysis section).
- Four new dataclasses in `scripts/little_loops/issue_history/models.py` (after `ManualPatternAnalysis` at line 391):

```python
@dataclass
class RecurringFeedback:
    topic: str                                          # content excerpt or cluster key
    occurrence_count: int = 0
    example_sessions: list[str] = field(default_factory=list)  # capped at 5
    example_content: list[str] = field(default_factory=list)   # capped at 3
    candidate_rule: str = ""                           # proposed CLAUDE.md rule text

@dataclass
class RecurringFeedbackAnalysis:
    feedbacks: list[RecurringFeedback] = field(default_factory=list)
    total_recurring_corrections: int = 0
    threshold_used: int = 2
    rule_candidates: list[str] = field(default_factory=list)   # capped at 10

@dataclass
class SkillBypass:
    skill_name: str                                    # skill that was bypassed
    bypass_count: int = 0
    example_sessions: list[str] = field(default_factory=list)  # capped at 5
    evidence: list[str] = field(default_factory=list)          # user message snippets, capped at 3
    suggested_improvement: str = ""                  # sharper trigger or lighter skill suggestion

@dataclass
class SkillBypassAnalysis:
    bypasses: list[SkillBypass] = field(default_factory=list)
    total_bypassed_invocations: int = 0
    threshold_used: int = 2
    improvement_suggestions: list[str] = field(default_factory=list)  # capped at 10
```

- Two new optional fields on `HistoryAnalysis` (after `cross_cutting_analysis` at line 672):
  `recurring_feedback_analysis: RecurringFeedbackAnalysis | None = None`
  `skill_bypass_analysis: SkillBypassAnalysis | None = None`
- Config: `analysis.evolution.feedback_min_recurrence` (default 2), `analysis.evolution.bypass_min_count` (default 2) — **already in `config-schema.json` and `EvolutionConfig`**.

## Scope Boundaries

- **Out of scope**: auto-applying corrections to CLAUDE.md or skill descriptions — detector + proposer only; applying a change stays with `improve-claude-md` / the user
- **Out of scope**: cross-project bypass tracking — operates only on this project's `.ll/history.db`
- **Out of scope**: inferring feedback from code review diffs, PR comments, or external tools — only session history and `memory/feedback_*`
- **Out of scope**: real-time per-session trigger reporting — batch analysis only, invoked explicitly
- **EPIC-1707 boundary**: This issue is `relates_to` (not a child of) EPIC-1707 because it
  serves batch harness-evolution analysis rather than runtime agent context injection. It
  reads from the same `.ll/history.db` but targets different consumers (`analyze-history` /
  `improve-claude-md`) and produces *proposals for human review* rather than *injected context
  for agent decisions*. The recurrence detection it builds may contribute evidence toward
  EPIC-1707's success metric ("measurable reduction in repeated user_corrections") but is
  tracked and evaluated separately.

## Open Questions

1. **Bypass detection precision.** Matching "user did X manually that skill Y covers" is fuzzy;
   risk of false positives. Start conservative (high-confidence keyword/file-signature matches)
   and report counts, not auto-actions.
2. **Feedback clustering.** Reuse the FTS5 / topic-excerpt machinery (`ll-history`,
   `ll-history-context`) or cluster `memory/feedback_*` directly? Probably both: memory files
   are the curated signal, history.db the raw recurrence evidence.
3. **Cross-session identity.** Recurrence must span sessions; lean on `.ll/history.db` as the
   durable store rather than single-session transcripts.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_history/models.py` — add `RecurringFeedback`, `RecurringFeedbackAnalysis`, `SkillBypass`, `SkillBypassAnalysis` dataclasses after `ManualPatternAnalysis` (line 391); add two new `| None` fields to `HistoryAnalysis` after line 672
- `scripts/little_loops/issue_history/analysis.py` — wire new detectors in `calculate_analysis()` after the `detect_manual_patterns` call at line 134; pass `EvolutionConfig` thresholds
- `scripts/little_loops/issue_history/formatting.py` — add `## Evolution Triggers` rendering in `format_analysis_markdown()` after line 883 and `format_analysis_text()` after line 362, following the `ManualPatternAnalysis` guard pattern (`if analysis.recurring_feedback_analysis:`)
- `scripts/little_loops/issue_history/__init__.py` — add 4 new model names at both the import block (lines 103–104) and `__all__` (lines 150–151); add new detector functions
- `skills/analyze-history/SKILL.md` — add the `## Evolution Triggers` report section
- `skills/improve-claude-md/SKILL.md` — consume the ranked candidates
- `skills/improve-claude-md/algorithm.md` — update algorithm to accept evolution trigger proposals as input
- `scripts/little_loops/cli/history.py` — update `main_history()` analyze branch to compute and pass `db_path` to `calculate_analysis()`, using the `DEFAULT_DB_PATH` pattern already established in the `summary` and `sessions` branches [Wiring pass finding]

### New Files
- `scripts/little_loops/issue_history/evolution.py` — new dedicated module (parallel to `quality.py`) for `detect_recurring_feedback()` and `detect_skill_bypass()` detector functions; separate from `quality.py` because these query history.db directly rather than scanning issue file text

### Similar Patterns

#### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/issue_history/models.py:366` — `ManualPattern` dataclass (exact field template: required positional `pattern_type`/`pattern_description`, then `occurrence_count: int = 0`, `list[str]` fields with `field(default_factory=list)`, string fields defaulting to `""`; `to_dict()` caps lists at 10/5 with slice)
- `scripts/little_loops/issue_history/quality.py:272` — `detect_manual_patterns()` (full detector pattern: early-return on empty input, module-level config dict, per-issue content scan, sort descending by count, build suggestions list filtered by threshold ≥ 2)
- `scripts/little_loops/history_reader.py:869` — `_query_recurring_corrections()` — **directly reusable**: already `GROUP BY content` with `COUNT(*) AS seen_count` over `user_corrections`; just needs threshold filter and session-ID enrichment
- `scripts/little_loops/history_reader.py:196` — `find_user_corrections()` — `LIKE %topic%` fuzzy search over `user_corrections` (30-day stale filter by default)
- `scripts/little_loops/history_reader.py` — `_connect_readonly()` / `_stale_cutoff()` — standard read-only DB connection + stale cutoff helpers; all detector functions must use this pattern
- `scripts/little_loops/cli/verify_triggers.py` — `_load_skill_descriptions()`, `_extract_keywords()`, `_match_phrasing()`, `STOPWORDS` — skill registry enumeration + keyword tokenization primitives needed for bypass detection
- `scripts/little_loops/issue_history/quality.py` — `detect_config_gaps()` — shows how to enumerate skills from `project_root / "skills"` when DB-level enumeration is not enough
- `scripts/little_loops/session_store.py:142` — `is_correction()` — three-regex correction classifier used by `mine_corrections_from_messages()`; `user_corrections` table is the pre-aggregated result

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_history/__init__.py` — exports `ManualPattern`/`ManualPatternAnalysis`; must export new `RecurringFeedback`/`SkillBypass` models
- `skills/analyze-history/SKILL.md` — consumes `ManualPatternAnalysis` output; must consume new evolution trigger models
- `scripts/little_loops/config/features.py` — `EvolutionConfig` dataclass **already exists** with `feedback_min_recurrence: int = 2` and `bypass_min_count: int = 2`; `HistoryConfig.evolution` already wired; verify thresholds are threaded into `calculate_analysis()` call sites

### Tests
- `scripts/tests/test_issue_history_advanced_analytics.py` — extend with `RecurringFeedback`/`SkillBypass` model tests
- `scripts/tests/test_issue_history_analysis.py` — extend with evolution-trigger analysis integration tests (follow call-site pattern at `analysis.py:134`)
- `scripts/tests/test_issue_history_formatting.py` — extend with `## Evolution Triggers` markdown section rendering tests
- `scripts/tests/test_evolution_triggers.py` (new) — detector logic unit tests; follow `TestDetectManualPatterns` class structure in `test_issue_history_quality.py` (empty-input early-return, threshold filtering, cluster dedup, bypass matching)
- `scripts/tests/test_config.py` — `TestHistoryConfig.test_evolution_defaults()` **already exists**; no changes needed for config defaults
- `scripts/tests/test_cli_history.py` — tests `main_history()` subcommands with mocked `calculate_analysis`; add test verifying the `analyze` branch correctly resolves and passes `db_path` [Wiring pass finding]

### Documentation
- `docs/reference/API.md` — update `little_loops.issue_history.models` section with new models
- `docs/reference/CONFIGURATION.md` — document `analysis.evolution.*` config keys
- `skills/analyze-history/SKILL.md` — document the `## Evolution Triggers` report section and output format

### Configuration
- `config-schema.json` — `analysis.evolution.feedback_min_recurrence` and `analysis.evolution.bypass_min_count` **already added** at lines 1549–1565 (ENH-1911 attribution); no schema changes needed
- `EvolutionConfig` dataclass in `scripts/little_loops/config/features.py` **already exists** with correct defaults; verify it is passed into detector calls in `analysis.py`

## Impact

- **Priority**: P3 — Enhances harness self-improvement loop; no existing P0–P2 blockers
- **Effort**: Medium — New detector models (~2 dataclasses), FTS5 query additions, report section in two skills, config schema update
- **Risk**: Low — Additive only; no existing behavior changes; proposal-only output
- **Breaking Change**: No

## Labels

`enhancement`, `history`, `analyze-history`, `improve-claude-md`, `evolution`

## Provenance

Surfaced while reviewing `https://github.com/revfactory/harness`. Its Phase 7 fires
self-improvement on quantified triggers (same feedback 2+ times, repeated failure, user
bypasses orchestrator). This issue ports the *signal detection*; little-loops keeps its more
rigorous "propose, don't auto-grade" stance for the action side.


## Verification Notes

**Verdict**: VALID — 2026-06-05T21:00:23

- Issue describes a planned feature/enhancement that has not yet been implemented
- Referenced files and directories verified to exist (where applicable)
- No claims about current code behavior are contradicted by the codebase
- Dependency references are valid (no broken refs, missing backlinks, or cycles)

## Resolution

**Completed**: 2026-06-09T00:28:49Z

### Changes Made

- **New**: `scripts/little_loops/issue_history/evolution.py` — `detect_recurring_feedback()` and `detect_skill_bypass()` detector functions; queries `user_corrections` (HAVING threshold) and `message_events`/`skill_events` respectively
- **Modified**: `scripts/little_loops/issue_history/models.py` — 4 new dataclasses (`RecurringFeedback`, `RecurringFeedbackAnalysis`, `SkillBypass`, `SkillBypassAnalysis`); 2 new optional fields on `HistoryAnalysis`; updated `to_dict()`
- **Modified**: `scripts/little_loops/issue_history/analysis.py` — `db_path` param added to `calculate_analysis()`; detectors wired in after `detect_manual_patterns`
- **Modified**: `scripts/little_loops/issue_history/formatting.py` — `## Evolution Triggers` section in both `format_analysis_text()` and `format_analysis_markdown()`
- **Modified**: `scripts/little_loops/issue_history/__init__.py` — exports 4 new models + 2 new detector functions
- **Modified**: `scripts/little_loops/cli/history.py` — analyze branch now computes and passes `db_path` to `calculate_analysis()`
- **New**: `scripts/tests/test_evolution_triggers.py` — 16 tests for both detectors
- **Modified**: `scripts/tests/test_issue_history_advanced_analytics.py` — `TestRecurringFeedbackModels` (8 to_dict tests)
- **Modified**: `scripts/tests/test_issue_history_formatting.py` — `TestFormatAnalysisEvolutionTriggers` (6 rendering tests)
- **Modified**: `scripts/tests/test_cli_history.py` — `TestHistoryAnalyzeDbPath` (1 db_path pass-through test)
- **Modified**: `skills/analyze-history/SKILL.md`, `skills/improve-claude-md/SKILL.md`, `skills/improve-claude-md/algorithm.md` — Evolution Triggers documentation

### Test Results
10,967 passed, 0 failed (full suite)

## Session Log
- `/ll:manage-issue` - 2026-06-09T00:28:49Z - `6bf7df7e-536f-4f48-955c-a913a8e9db1c.jsonl`
- `/ll:ready-issue` - 2026-06-08T23:56:02 - `1520ba81-91be-4451-819b-6559090539e9.jsonl`
- `/ll:confidence-check` - 2026-06-08T00:00:00Z - `ea56c0b1-effd-4835-ba99-baf5e5634136.jsonl`
- `/ll:confidence-check` - 2026-06-08T00:00:00Z - `7b77c952-e0f3-4d17-9910-f90fb3b15400.jsonl`
- `/ll:wire-issue` - 2026-06-08T23:59:00 - `7fa034e8-b10d-497f-82ed-c69aea9b71df.jsonl`
- `/ll:refine-issue` - 2026-06-08T23:24:10 - `7fa034e8-b10d-497f-82ed-c69aea9b71df.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T04:34:19 - `e1e6b264-2dd0-4d92-92be-102681aa7fbc.jsonl`
- `/ll:format-issue` - 2026-06-03T21:05:33 - `b833547d-130c-42f1-b9a5-75900748b2de.jsonl`
- `/ll:capture-issue` - 2026-06-03T20:59:38Z - `b4fa1e68-4a59-49bd-949a-5a5b7533509f.jsonl`

---

## Status

**Open** | Created: 2026-06-03 | Priority: P3
