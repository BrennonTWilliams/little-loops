---
id: ENH-2046
title: "Evolution-trigger consumer + correction retirement (close the detect\u2192\
  propose\u2192persist loop)"
type: ENH
priority: P3
status: done
captured_at: '2026-06-09T00:00:00Z'
completed_at: '2026-06-09T19:31:12Z'
discovered_date: '2026-06-09'
discovered_by: capture-issue
parent: EPIC-2027
relates_to:
- ENH-1911
- FEAT-949
- FEAT-948
- ENH-1831
labels:
- history
- evolution
- improve-claude-md
- decisions
- harness
- self-improve
confidence_score: 92
outcome_confidence: 76
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 18
decision_needed: false
---

# ENH-2046: Evolution-trigger consumer + correction retirement

## Summary

Close the last mile of EPIC-2027's `detect → quantify → propose` pipeline.

## Motivation

ENH-1911's Evolution Triggers output is useful for inspection but dead-ends at copy-paste — corrections keep resurfacing as candidates even after they've been acted on, diluting the real open signal with already-addressed topics. Every `analyze-history` run requires manual deduplication against rules the user already wrote. The consumer + retirement piece makes the pipeline actually actionable: ranked candidates become persisted rules under human review, addressed clusters stop reappearing, and the recurrence-gated signal stays clean for future runs. Without it, the self-improvement loop is observational only.
ENH-1911 (done) already detects recurring corrections and skill bypasses and
surfaces them as ranked, count-backed candidates in the `## Evolution Triggers`
section of `analyze-history` output. What is still missing is the **consumer**
that turns those candidates into a persisted rule under human review, plus a
**retirement** mechanism so an addressed correction stops re-surfacing forever.

This is the little-loops analog of squid's Self-Improve skill — but built on our
recurrence-gated signal (≥ `feedback_min_recurrence`, default 2, across sessions)
rather than squid's single-session transcript scan, which is noisier. It also
targets `decisions.yaml` (required rules → synced to `ll.local.md`) as the
primary sink, keeping `CLAUDE.md` edits in `improve-claude-md`'s existing lane.

This issue promotes two of EPIC-2027's listed **"Potential Future Children"**
into concrete scope, and adds the retirement piece the EPIC does not yet name.

## Current Behavior

The pipeline from "correction in conversation" to "recurring-feedback analysis"
is complete and working:

1. **Capture** — `user_prompt_submit` hook detects corrections (patterns in
   `scripts/little_loops/session_store.py`) → `user_corrections` table in
   `.ll/history.db`. Gated by `analytics.capture.corrections`.
2. **Analyze** — `analyze-history` → `detect_recurring_feedback()` /
   `detect_skill_bypass()` (`scripts/little_loops/issue_history/evolution.py`)
   group by topic and count recurrence.
3. **Propose** — ENH-1911 renders an `## Evolution Triggers` section with
   ranked **Candidate Rule** text
   (`scripts/little_loops/issue_history/formatting.py`).

But:

- **No consumer.** `improve-claude-md` *can* ingest Evolution Triggers output as
  rule candidates, but there is no command that chains analyze → dedup against
  existing rules → approve → persist. The user copies candidate text by hand.
- **No retirement.** Once a candidate becomes a rule, nothing marks the
  underlying correction cluster as "addressed." The same topic keeps surfacing
  in every future `analyze-history` run, indistinguishable from an open signal.
- **No dedup against `decisions.yaml`.** Candidates are not cross-checked against
  rules that already exist, so already-ruled topics reappear as fresh proposals.

## Expected Behavior

A consumer path that preserves EPIC-2027's hard stance — *nothing is
auto-applied; output is always a human-reviewed proposal* — plus retirement:

1. **Consumer (orchestration).** A way to take ENH-1911's ranked candidates and,
   for each, propose persistence as either a `decisions.yaml` required rule
   (preferred, via `ll-issues decisions add`, carrying the recurrence count and
   example sessions as provenance) or a `CLAUDE.md` edit (delegated to
   `improve-claude-md`). Each proposal requires explicit approval before write.
2. **Dedup.** Before proposing, cross-check each candidate topic against existing
   `decisions.yaml` rules and current `CLAUDE.md` content; suppress or annotate
   candidates already covered.
3. **Retirement.** When a candidate is accepted and persisted, mark the
   corresponding correction cluster as addressed (e.g. an `addressed_at` /
   linked-rule record keyed by the cluster's topic identity) so
   `detect_recurring_feedback()` excludes it (or flags it "already ruled") on
   subsequent runs. Addressing must be reversible/auditable.

Placement is a design choice for refinement: a thin new entry point
(e.g. `/ll:self-improve`) versus extending `improve-claude-md` with a
consume-and-persist mode. EPIC-2027 also lists an optional periodic FSM loop that
runs the full pipeline and files candidate-rule issues when thresholds cross —
out of scope here, tracked separately.

## Proposed Solution

**Option A (preferred): Extend `improve-claude-md` with a consume-and-persist mode**

> **Selected:** Option A — `improve-claude-md` already documents an ENH-1911 Evolution Trigger intake section and the `--dry-run` flag pattern is a direct template for `--consume-triggers`; formalizes existing design intent without creating a hand-authored thin-wrapper skill with no precedent.

Add a `--consume-triggers` flag that reads `analyze-history` Evolution Triggers output, deduplicates against `decisions.yaml` + `CLAUDE.md`, prompts per candidate for approval, calls `ll-issues decisions add` on acceptance, and writes an `addressed_at` retirement record keyed by cluster topic fingerprint into `history.db`.

**Option B: New `/ll:self-improve` skill entry point**

A thin wrapper that calls `analyze-history` then enters the consume-and-persist flow. Separates concerns from `improve-claude-md`'s CLAUDE.md-edit lane.

**Retirement schema**: New `correction_retirements` table in `history.db` — columns: `topic_fingerprint TEXT`, `rule_id TEXT`, `addressed_at TEXT`, `session_id TEXT`. `detect_recurring_feedback()` filters rows whose `topic_fingerprint` has an entry, or annotates them as `"already ruled: <rule_id>"`.

**Dedup**: Before proposing each candidate, cross-check its topic text against `ll-issues decisions list` output and a `grep` of `CLAUDE.md`; suppress if already covered, annotate if partially overlapping.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-09.

**Selected**: Option A — Extend `improve-claude-md` with a consume-and-persist mode

**Reasoning**: Option A wins because `improve-claude-md` already documents an "Evolution Trigger Inputs (ENH-1911)" intake section (lines 179–186) that anticipates exactly this consume path — extending with `--consume-triggers` formalizes existing design intent rather than creating a new skill. Option B would require a hand-authored thin-wrapper skill with no precedent in the codebase (all 30 `ll-*` thin-wrapper stubs are auto-generated Codex bridge artifacts), and would introduce dual-ownership ambiguity with `improve-claude-md`'s own documented ENH-1911 intake.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — Extend `improve-claude-md` | 2/3 | 2/3 | 2/3 | 2/3 | 8/12 |
| Option B — New `/ll:self-improve` skill | 1/3 | 1/3 | 2/3 | 2/3 | 6/12 |

**Key evidence**:
- Option A: `skills/improve-claude-md/SKILL.md` lines 179–186 document the ENH-1911 intake point; `--dry-run` flag-parsing is a direct template; `ll-issues decisions add` is established across 5+ call sites
- Option B: All 30 thin-wrapper `ll-*` skills are auto-generated Codex stubs, not functional orchestrators; no hand-authored precedent for chaining sibling skills; creates dual-ownership ambiguity with `improve-claude-md`'s existing ENH-1911 section

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_history/evolution.py` — add retirement filter to `detect_recurring_feedback()` and `detect_skill_bypass()`
- `scripts/little_loops/issue_history/formatting.py` — annotate already-ruled candidates in Evolution Triggers output
- `scripts/little_loops/session_store.py` — add `correction_retirements` table schema
- `skills/improve-claude-md/SKILL.md` or new `skills/self-improve/SKILL.md` — consumer entry point

### Dependent Files (Callers/Importers)
- `scripts/little_loops/hooks/` — session_start reads `history.db`; retirement table is additive, no hook changes expected
- `.ll/decisions.yaml` — sink for persisted rules (written via `ll-issues decisions add`)
- `.ll/ll.local.md` — rules synced here via `ll-issues decisions sync`

### Similar Patterns
- `skills/improve-claude-md/SKILL.md` — existing human-approval-required pattern to extend or parallel
- `ll-issues decisions add` — existing rule persistence CLI to reuse

### Tests
- `scripts/tests/test_builtin_loops.py` — check for related evolution/history coverage
- New test file or additions: consume→propose→approve→persist happy path, dedup suppression of already-ruled topic, retirement excluding addressed cluster from next detection run

### Documentation
- `docs/reference/API.md` — update `evolution.py` section if `detect_recurring_feedback()` signature changes

### Configuration
- N/A — no new config keys required (retirement table is internal to `history.db`)

## Implementation Steps

1. Add `correction_retirements` table to `session_store.py` schema and migration
2. Update `detect_recurring_feedback()` in `evolution.py` to filter/annotate retired cluster fingerprints
3. Add dedup check against `decisions.yaml` and `CLAUDE.md` before candidate proposal
4. Build consumer path (Option A or B above) with per-candidate approval loop → `ll-issues decisions add` → retirement write
5. Add tests covering happy path, dedup suppression, and retirement exclusion from next detection run
6. Update `docs/reference/API.md` if public API signatures change

## Acceptance Criteria

- [ ] A documented path consumes ENH-1911's ranked Evolution Triggers candidates
      and, per candidate, proposes persistence to `decisions.yaml` (preferred) or
      `CLAUDE.md`, with recurrence count + example sessions carried as provenance.
- [ ] No write occurs without explicit human approval (consistent with
      EPIC-2027's "never an auto-edit" constraint).
- [ ] Candidates are deduplicated against existing `decisions.yaml` rules and
      current `CLAUDE.md` content before being proposed.
- [ ] Accepting a candidate marks its correction cluster addressed such that a
      subsequent `analyze-history` run no longer surfaces it as an open candidate
      (or clearly labels it "already ruled").
- [ ] Retirement is recorded durably (survives across sessions) and is auditable
      / reversible.
- [ ] Tests cover: consume→propose→approve→persist happy path, dedup suppression
      of an already-ruled topic, and retirement excluding an addressed cluster
      from the next detection run.

## Scope Boundaries

- The optional periodic FSM loop that auto-files candidate-rule issues
  (EPIC-2027 "Potential Future Children" #3) — separate issue.
- A composite "harness drift score" metric (EPIC-2027) — separate issue.
- Changing the detection thresholds or correction-capture patterns (owned by
  ENH-1911 / ENH-1887 / ENH-1915).

## Impact

- **Priority**: P3 — Closes last-mile of EPIC-2027 pipeline; high value but non-blocking since existing pipeline is already useful for inspection
- **Effort**: Medium — Additive: new DB table + migration, filter logic in `evolution.py`, consumer skill/command, and test suite
- **Risk**: Low — Purely additive; no changes to existing capture, analyze, or hook paths
- **Breaking Change**: No

## Labels

history, evolution, improve-claude-md, decisions, harness, self-improve

## Status

open

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-09_

**Readiness Score**: 88/100 → PROCEED
**Outcome Confidence**: 70/100 → MODERATE

### Outcome Risk Factors
- **Option A or B** is noted as a preference but not formally resolved — "Placement is a design choice for refinement" leaves the consumer's file location open. Resolve before starting: decide whether `improve-claude-md` gets `--consume-triggers` (Option A) or a new `skills/self-improve/` directory is created (Option B).
- Moderate integration breadth (4 files across 3 subsystems) with a new DB migration (v13) — ensure migration is additive-only and version bump is consistent with the `v12 = ENH-1953` chain in `session_store.py`.

## Resolution

Implemented Option A (extend `improve-claude-md` with `--consume-triggers`). Changes:

1. **`session_store.py`** (v13 migration): Added `correction_retirements` table + unique index on `topic_fingerprint`. Added `record_retirement()` and `list_retirements()` public API. Updated `SCHEMA_VERSION` to 13.
2. **`models.py`**: Added `topic_fingerprint: str = ""` to `RecurringFeedback`; added `retired_count: int = 0` to `RecurringFeedbackAnalysis`.
3. **`evolution.py`**: Added `_fingerprint()` (sha256[:16]); `detect_recurring_feedback()` now loads retirement records read-only and excludes retired clusters from feedbacks.
4. **`formatting.py`**: Shows "(N cluster(s) excluded — already retired)" in both text and markdown Evolution Triggers output when `retired_count > 0`.
5. **`skills/improve-claude-md/SKILL.md`**: Added `--consume-triggers` flag with full CT-0 through CT-4 pipeline (get candidates → dedup → per-candidate approval → persist + retire → report).
6. **Tests**: New `test_correction_retirement.py` (7 tests) + `TestRetirementFilter` class in `test_evolution_triggers.py` (4 tests) + `TestSchemaV13` in `test_session_store.py` (3 tests). All 14 new tests pass; no regressions.
7. **`docs/reference/API.md`**: Added `little_loops.session_store` section documenting `record_retirement`, `list_retirements`, and the new table schema.

## Session Log
- `/ll:manage-issue` - 2026-06-09T19:31:12Z - `manage-issue`
- `/ll:ready-issue` - 2026-06-09T19:06:37 - `8aca788a-9ad4-4e75-9627-965a245e9941.jsonl`
- `/ll:decide-issue` - 2026-06-09T19:01:31 - `83da4906-b091-4fe3-9c50-4affc7023b72.jsonl`
- `/ll:confidence-check` - 2026-06-09T00:00:00Z - `04f82d31-35d7-47a9-8197-770bb00e881a.jsonl`
- `/ll:confidence-check` - 2026-06-09T20:00:00Z - `93086ece-d0ce-481b-be8b-66aa82f38523.jsonl`
- `/ll:format-issue` - 2026-06-09T18:45:01 - `04f82d31-35d7-47a9-8197-770bb00e881a.jsonl`

- Captured - 2026-06-09 - from squid-plugin evaluation; promotes two EPIC-2027
  "Potential Future Children" into concrete scope and adds correction retirement.
