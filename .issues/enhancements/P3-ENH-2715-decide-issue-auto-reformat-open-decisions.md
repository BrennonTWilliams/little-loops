---
id: ENH-2715
title: decide-issue --auto should reformat found-but-unstructured open decisions
status: done
captured_at: '2026-07-21T03:08:03Z'
completed_at: '2026-07-21T03:32:32Z'
discovered_date: 2026-07-21
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 21
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 25
---

# ENH-2715: decide-issue --auto should reformat found-but-unstructured open decisions

## Summary

When `/ll:decide-issue ISSUE_ID --auto` cannot find a properly formatted
decision (no `### Option A/B` blocks, no bold `**Option X**` labels, no
scoreable structure) it currently only reacts by invoking
`/ll:refine-issue ${ISSUE_ID} --auto` once (Phase 2.5, ENH-2443) to have
refine-issue *research and deposit new* options, then re-scans. If the issue
already contains open decisions expressed in unstructured prose — e.g. an
`## Open Questions` section with unresolved items, or ad-hoc "we could do X
or Y" language in the body — that content is only picked up by Phase 3b's
inline provisional-language scan for *locking in* a clear winner (Pattern
D). There is no path where decide-issue rewrites an existing informal
decision into the canonical `### Option A` / `### Option B` structure so it
can go through normal Phase 4–7 scoring.

## Current Behavior

`skills/decide-issue/SKILL.md` Phase 2.5 / Phase 3 / Phase 3b:
- `OPTIONS == 0` + `AUTO_MODE` → calls `/ll:refine-issue --auto` once to
  deposit new options via codebase research, then re-scans.
- If the re-scan still finds 0 structured options, falls through to Phase 3b,
  which only scans for a declarative recommendation marker to lock in a
  single winner (or leaves `decision_needed: true` for human review if no
  marker exists).
- Neither path reformats an existing informal decision (e.g. bullet points
  under `## Open Questions`, or inline "Option A vs Option B" prose that
  doesn't match Patterns 1–4) into the structured template so it can be
  scored normally.

## Expected Behavior

After the existing `refine-issue --auto` deposit attempt is exhausted
(`DEPOSIT_ATTEMPTED = true`) and a re-scan still yields `OPTIONS == 0`,
decide-issue should check the issue body for open decisions expressed in
unstructured form (unresolved `## Open Questions` items, informal
alternative-listing prose elsewhere in the body) and, if found, rewrite them
in-place into the canonical `### Option A` / `### Option B` structure under
`## Proposed Solution` before falling through to Phase 3b. This lets a
decision that already exists in the issue — just not in scoreable form — get
picked up by normal Phase 4–7 scoring instead of dead-ending at
`NO_ACTIONABLE_DECISIONS` or staying stuck on `decision_needed: true`.

## Motivation

Today, an issue author who jots down alternatives informally (a quick "could
do X or Y" note, or an `## Open Questions` list without the lettered-option
structure) gets no benefit from `--auto` decision-making even though the
substance of a decision is already written down — automation only helps if
the prose happens to match Patterns 1–4 or contains an explicit
recommendation marker. Reformatting existing content is lower-risk than
depositing brand-new options (no new research/investigation needed) and
should be tried before conceding to `NO_ACTIONABLE_DECISIONS` or leaving
`decision_needed: true` on issues that could be resolved with the
information already present.

## Proposed Solution

Both options reuse the same detection surface: genuinely unresolved items in
`## Open Questions` (per `_OPEN_QUESTION_SIGNAL_RE` /
`_RESOLVED_QUESTION_MARKER_RE`, `scripts/little_loops/issue_parser.py:374-420`,
already exposed via `count_open_questions_in_sections()`) or prose naming 2+
concrete alternatives without a Pattern-4 bullet backing them (the exact
shape Phase 3b's Provisional Pattern D already recognizes but currently
requires to already exist as a bullet — `skills/decide-issue/SKILL.md:242-249`,
"Requirement: the referent must exist as a Pattern-4 bullet option"). The
reformat target is the same `**Option A**`/`**Option B**` bold-label
template refine-issue's "Decision-Point Formatting" rule already produces
(`commands/refine-issue.md:284-303`; ENH-2607), so no `issue_parser.py`
regex changes are needed — Pattern 2 already matches it.

**Option A**: Add a new **Phase 3c: Reformat Informal Decisions** step,
inserted after the Phase 2.5 deposit-retry is exhausted
(`DEPOSIT_ATTEMPTED = true`) and Phase 3's re-scan still yields
`OPTIONS == 0`, but *before* Phase 3b's provisional scan runs. Phase 3c scans
unresolved Open-Questions items and non-bullet prose for a 2+-alternative
shape, rewrites them in place as `### Option A` / `### Option B` headers
under `## Proposed Solution`, then re-runs the Phase 3 extraction. If the
re-scan now finds `OPTIONS >= 2`, proceed directly to Phase 4 full
evidence-based scoring instead of Phase 3b's lock-in-only path. If no
2+-alternative shape is found, fall through unchanged to Phase 3b exactly as
today.

> **Selected:** Option B — mirrors the completed ENH-2607 precedent (extend an
> existing enrichment rule in place) and reuses Phase 3b's existing
> `_phase_text()` test-slice convention; avoids duplicating Phase 2.5's
> re-scan/re-branch machinery in a new phase.

**Option B**: Extend Phase 3b's existing Resolution Logic
(`skills/decide-issue/SKILL.md:253-277`) in place, rather than adding a new
phase. When the Provisional Pattern A-D scan identifies a **Clear winner**
whose alternatives are NOT already Pattern-4 bullets (today this case is
simply unreachable for Pattern D, since its Requirement demands an existing
bullet — lines 247-248), or when unresolved Open-Questions items name 2+
concrete alternatives, first materialize the named alternatives as
`**Option A**`/`**Option B**` blocks (reusing the ENH-2607 template
verbatim) in the same edit that would otherwise just add the
`> **Selected:**` callout, then continue straight to Phase 4 scoring instead
of the current short-circuit-to-Phase-8 exit. Ambiguous matches keep today's
behavior unchanged (leave `decision_needed: true`, no reformat, no write).

**Recommended**: Option B — it reuses Phase 3b's already-designated home for
informal-decision handling instead of introducing a second re-entry point
into Phase 3/4 (Option A's phase would need its own copy of the re-scan
logic Phase 2.5 already has). It also mirrors how ENH-2607 fixed the
production side: extend an existing enrichment rule in place rather than
add a parallel step. The over-triggering risk is bounded by reusing Pattern
D's existing "2+ named alternatives with a stated preference" match
criteria — the same guard already proven not to over-fire on the Pattern-4
bullet-list case (`skills/decide-issue/SKILL.md:181`,
"Auto-mode bullet-list handling").

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **No existing implementation or test coverage for this gap.** Neither
  `ll-issues check-decidable` (`scripts/little_loops/cli/issues/check_decidable.py:19-45`)
  nor the newer `ll-issues check-open-questions`
  (`scripts/little_loops/cli/issues/check_open_questions.py:40-72`, ENH-2446)
  reimplements Pattern D or a "reformat" pass — both only count/gate, never
  rewrite. `check-open-questions` composes `count_unresolved_options()` and
  `count_open_questions_in_sections()` (`issue_parser.py:352-436`) and is
  already the coverage-aware probe FSM callers chain ahead of
  `check-decidable` (`rn-remediate.yaml:292`, `autodev.yaml:238` —
  `check-open-questions || check-decidable`), so it is the natural
  post-condition check for whichever option lands here: after a reformat,
  `check-open-questions` should flip from `OPEN_QUESTIONS_REMAIN` to exit 0
  (or `check-decidable` should flip from `OPTIONS_MISSING` to `Decidable`).
- **Why Phase 3b can't just be widened without care**: Phase 3b's two exits
  (Clear winner → lock in + skip Phase 4-7; Ambiguous/none → leave
  `decision_needed: true` + skip Phase 4-7) both currently skip evidence
  scoring entirely (`skills/decide-issue/SKILL.md:259-277`). A reformat step
  needs a *third* exit — "reformatted, now score it" — that the current
  control flow has no branch for; Phase 3b as written only ever proceeds to
  Phase 7-or-8 tail states, never back into Phase 3/4.
- **Precedent for the reuse-vs-new-phase tradeoff**: `commands/refine-issue.md`'s
  "Decision-Point Formatting" rule (lines 284-303, added by ENH-2607) is the
  closest existing analogue — it already converts "Two viable resolutions:
  (a)... or (b)... Recommendation: X" prose into the same
  `**Option A**`/`**Recommended**` block shape this issue targets, but only
  for refine-issue's own freshly-written research findings, not pre-existing
  issue prose or `## Open Questions` items. That scope boundary
  (`commands/refine-issue.md:299-303`, "does not rewrite pre-existing
  human-authored prose it didn't write") is explicitly why ENH-2715 can't be
  satisfied by refine-issue alone and needs a decide-issue-side fix.
- **Test convention for this class of change**: neither `decide-issue` nor
  `refine-issue` markdown prose is exercised by a live LLM in the automated
  suite — coverage is structural presence-assertion tests that slice the
  skill/command file between two heading anchors and assert marker
  substrings, e.g. `TestPattern4BulletOptions.test_auto_mode_bullet_guardrail_documented`
  and `TestPattern3bDeclarativeRecommendation`
  (`scripts/tests/test_decide_issue_skill.py:316-351, 545-582`) and
  `TestOptionCountDetectionInCommand.test_decision_point_formatting_rule_documented`
  (`scripts/tests/test_refine_issue_command.py:84-96`). Whichever option is
  implemented should follow this same pattern: a new test method asserting
  the new rule's marker text is present within the relevant phase's text
  span, not an LLM-invoking test.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-20.

**Selected**: Option B — Extend Phase 3b's existing Resolution Logic in place

**Reasoning**: Option B directly mirrors the completed ENH-2607 precedent
(extending `refine-issue.md`'s existing "Decision-Point Formatting" rule in
place rather than adding a parallel phase) and reuses Phase 3b's shared
`_phase_text()` test-slice helper already used by 3 of 4 Phase-3b test
classes. Option A's own evidence gathering confirmed the issue's own
Codebase Research Findings: a new Phase 3c would need "its own copy of the
re-scan logic Phase 2.5 already has," duplicating control flow rather than
reusing it. Both options require the same net-new work (materializing
prose into `**Option A**`/`**Option B**` blocks — no existing Python utility
does this), so the tie-breaker is architectural consistency, which favors
Option B.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|--------------|------|-------|
| Option A (new Phase 3c) | 2/3 | 1/3 | 3/3 | 2/3 | 8/12 |
| Option B (extend Phase 3b) | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |

**Key evidence**:
- Option A: Follows the codebase's established lettered-sub-phase convention
  (`3b`, `2b`, `4b`, `4c` already exist in `decide-issue`, `capture-issue`,
  `audit-issue-conflicts`), but the issue's own findings and the evidence
  agent both confirm it duplicates Phase 2.5's already-built
  act-then-rescan-then-branch machinery in a new, parallel construct.
- Option B: Reuses the exact `_phase_text()` slice-boundary test helper
  used by `TestPhase3bInlineProvisionalScan` and
  `TestPattern3bDeclarativeRecommendation`, and follows the same
  extend-in-place shape ENH-2607 already proved out on the refine-issue
  side. Its cost is adding a genuine third exit to Phase 3b's currently
  strictly-terminal two-branch shape and relaxing Pattern D's
  bullet-existence Requirement — a real but contained structural change
  scoped to one section.

## Integration Map

### Files to Modify
- `skills/decide-issue/SKILL.md` — Phase 3b Resolution Logic
  (lines 253-277), and/or a new Phase 3c depending on the selected option
  above.
- `scripts/tests/test_decide_issue_skill.py` — new structural
  presence-assertion test method(s), following the existing
  `TestPhase3bInlineProvisionalScan` / `TestPattern3bDeclarativeRecommendation`
  class conventions (lines 219-274, 545-582).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/check_decidable.py:19-45`
  (`cmd_check_decidable`) — deterministic FSM companion to
  `--validate-only`; a successful reformat should flip its verdict from
  `OPTIONS_MISSING` to `Decidable` on re-check.
- `scripts/little_loops/cli/issues/check_open_questions.py:40-72`
  (`cmd_check_open_questions`, ENH-2446) — coverage-aware probe combining
  `count_unresolved_options()` and `count_open_questions_in_sections()`;
  should flip from `OPEN_QUESTIONS_REMAIN` to exit 0 after a successful
  reformat clears the underlying Open-Questions items.
- `scripts/little_loops/loops/rn-remediate.yaml:292` and
  `scripts/little_loops/loops/autodev.yaml:238` — both chain
  `check-open-questions || check-decidable` ahead of invoking
  `/ll:decide-issue` / `/ll:refine-issue --auto`; no FSM changes are
  expected since these loops already gate on the same two CLIs, but the
  gate's pass/fail behavior will change once decide-issue can resolve more
  issues without a `/ll:refine-issue` deposit round-trip.

### Similar Patterns
- `commands/refine-issue.md:284-303` ("Decision-Point Formatting (Auto Mode
  only)") — the production-side precedent for converting named-alternative
  prose into `**Option A**`/`**Recommended**` blocks; this issue is the
  consumption-side counterpart (see ENH-2607, its completed twin).
- `skills/decide-issue/SKILL.md:181` ("Auto-mode bullet-list handling") —
  the exact false-positive guard shape (downgrade to a safer path rather
  than block outright) that any new reformat logic must match to avoid
  over-eager auto-scoring.

### Tests
- `scripts/tests/test_decide_issue_skill.py` — existing structural test
  classes for Phase 3/3b (`TestPhase3bInlineProvisionalScan`,
  `TestPhase3bResolvedFilter`, `TestPattern4BulletOptions`,
  `TestPattern3bDeclarativeRecommendation`) are the direct precedent for how
  new coverage should be written — no LLM invocation, only marker-text
  presence assertions within a sliced phase span.
- `scripts/tests/test_ll_issues_check_open_questions.py` and
  `scripts/tests/test_issue_parser_unresolved.py` — unit tests for the
  deterministic Python functions (`count_open_questions_in_sections`,
  `count_unresolved_options`) this feature's detection logic would build on
  or need to stay in parity with.

## Impact

- **Priority**: P3 — quality-of-life improvement to an existing auto-mode
  gap; not blocking, no data loss or regression risk.
- **Effort**: Medium — touches `skills/decide-issue/SKILL.md` Phase 2.5/3b
  logic and likely needs new test coverage in the decide-issue test suite.
- **Risk**: Low-medium — must not over-trigger and rewrite issue prose that
  wasn't actually meant as a decision list (same class of risk the Phase 3
  "Auto-mode bullet-list handling" guard was added to avoid).

## Session Log
- `/ll:manage-issue` - 2026-07-21T03:32:26 - `78f5de87-41ac-413f-b350-15c80a20c5e2.jsonl`
- `/ll:ready-issue` - 2026-07-21T03:26:24 - `28f90485-c101-4e9e-992a-207631fabdb6.jsonl`
- `/ll:decide-issue` - 2026-07-21T03:23:27 - `5ee3a927-b3a9-448d-9c46-360f02d776dc.jsonl`
- `/ll:refine-issue` - 2026-07-21T03:18:37 - `c292b3d1-1d24-45ed-9b15-dc634c923e2c.jsonl`
- `/ll:capture-issue` - 2026-07-21T03:08:03Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/58687b43-4209-4796-b24a-1505ad6b098f.jsonl`

---

## Status

- [ ] Not started
