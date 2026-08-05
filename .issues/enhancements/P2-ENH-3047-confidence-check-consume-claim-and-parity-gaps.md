---
id: ENH-3047
title: 'confidence-check: consume unverified-claim and missing-parity gaps as Criterion
  4 deductions'
type: ENH
priority: P3
status: open
discovered_by: capture-issue
discovered_date: 2026-08-04
captured_at: '2026-08-04T20:47:11Z'
depends_on:
- FEAT-3048
relates_to:
- ENH-3045
- ENH-2946
- FEAT-2942
- BUG-3051
labels:
- skills
- issues
- gates
decision_needed: false
testable: true
confidence_score: 95
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# ENH-3047: Feed claim/parity gaps into confidence-check scoring

## Summary

`/ll:confidence-check` scored FEAT-2942 at **93 readiness / 76 outcome** while the issue
contained a false claim about its own core write path, a silent behavior regression, two
internal contradictions, and three undefined terms. Wire the FEAT-3048 claim gaps and the
ENH-3045 parity gap into the existing Phase 1.6 pre-fetch as explicit Criterion 4 deductions, so
the score reflects what the new gates find.

## Current Behavior

Criterion 4 ("Issue Well-Specified") checks for the **presence** of sections — acceptance
criteria, specific files to modify, scope boundaries, actionable steps
(`skills/confidence-check/SKILL.md` Phase 2). FEAT-2942 has all four, so it scores well
regardless of whether those sections are *correct*, *consistent*, or *sufficient*.

Criterion 3's detection bullet 5 is the one instruction that reaches correctness — *"Verify
claims in the issue against actual code"* — but it is the last sub-bullet of a type-specific
criterion with no CLI behind it, and it is the only prose-only gate in a skill where every other
check has one. Phase 1.6 already pre-fetches the Program Design gate, so the mechanism and the
slot both exist; there is simply nothing to fetch for claims or parity yet.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

- Phase 1.6's existing pre-fetch (`skills/confidence-check/SKILL.md`, `### Phase 1.6: Pre-Fetch Program Design Gate (ENH-2852)`, lines 132-150) is the concrete template this issue extends — it populates two shell variables from `ll-issues format-check {{issue_id}} --format json`: `PD_GAP` (raw reason string, `json.load(sys.stdin).get('program_design_nonspecific', [])` joined with `; `) and `PD_FAIL` (a separate pass/fail verdict from the dedicated `ll-issues check-design {{issue_id}}` exit code, not re-derived from JSON in the skill).
- **Superseded 2026-08-05 — ENH-3045 has since landed.** The original finding read: "the target keys ... do not exist anywhere in the current schema ... none of the three target keys are present." That is now false for one of the three. `missing_behavior_parity` is live in `FormatGaps` (`scripts/little_loops/issue_parser.py:259`), mirrored in `has_gaps` (`:280`) and `to_dict()` (`:301`), emitted by `cmd_format_check` (`scripts/little_loops/cli/issues/format_check.py:163`), and documented (`docs/reference/CLI.md:1900` and the JSON example at `:1950`; `docs/reference/API.md:878`). `FormatGaps` now has 16 `list[str]` fields, not 15. Only `stale_symbol_ref` and `stale_cli_flag` (FEAT-3048) remain absent from the schema.
- The "no precedent for defensively reading a not-yet-emitted key" concern therefore applies **only to the FEAT-3048 pair**, not to parity. For those two, `.get('stale_symbol_ref', [])` on a payload that lacks the key yields `[]`, which makes the claim deduction and its hard override inert — the same fail-open end state as the Program Design gate on an unstamped project, reached by a different route (schema-absent key vs. schema-present-but-empty). Stage 2 must not ship until FEAT-3048 lands, but stage 1 is unaffected: `missing_behavior_parity` is schema-present today.

## Expected Behavior

Phase 1.6 additionally pre-fetches, via `ll-issues format-check --format json`:

- missing behavior parity (`missing_behavior_parity` — **shipped by ENH-3045**, available today)
- unverified-claim count (`stale_symbol_ref` + `stale_cli_flag` — awaiting FEAT-3048)

The two signals are deliberately wired to different mechanisms, because they carry different
weight:

- **Parity → soft deduction.** A missing `### Behavior Parity` subsection means the issue may
  have under-described what it replaces. That is a specification weakness; it caps Criterion 4
  but does not by itself make the issue unimplementable.
- **Claims → hard override.** A `stale_symbol_ref`/`stale_cli_flag` gap means the issue asserts
  something about the codebase that is not true. A false claim about the implementation surface
  is not a "well specified" issue at any score, so it forces `STOP — ADDRESS GAPS` regardless of
  aggregate, following the Learning Test / Program Design hard-override shape.

Both must fail open: when a gap key is absent from the payload (unarmed project, or FEAT-3048
not yet landed) the deduction and the override are inert, and the score is exactly what it is
today.

## Motivation

Without this, FEAT-3048 and ENH-3045 improve the *gates* while the *score* stays uncalibrated —
and the score is what `/ll:go-no-go`, `ll-auto`, and sprint selection actually consume. An issue
that fails a claim check should not read as 93% ready.

## Proposed Solution

Follow the existing Phase 1.6 pattern: one `format-check --format json` call, parsed into
counts, referenced by the rubric tables. `ENH-2946` already established that confidence-check
reads `format-check` output, so this is an extension of a live integration rather than a new
coupling.

Keep the deduction table in `rubric.md` (the skill already delegates all scoring tables there),
not in `SKILL.md` — that file is 405 lines against the 500-line cap.

**Dependency (revised 2026-08-05):** this issue was captured as hard-`blocked_by: [FEAT-3048]`
on the reasoning that "without it there is nothing to read." ENH-3045 has since landed, so
there *is* something to read: `missing_behavior_parity` is in the schema today. The edge is
therefore `depends_on: [FEAT-3048]`, not `blocked_by`, and the work splits into two stages:

- **Stage 1 (unblocked, ship now)** — parity pre-fetch + Criterion 4 deduction row + tests.
- **Stage 2 (on FEAT-3048)** — claim pre-fetch + Phase 3 hard override + tests.

Stage 1 is self-contained and leaves the claim path as an inert `.get(..., [])` read, so
stage 2 is a pure addition rather than a rework.

### Deduction Rows (resolves the open Option A row-authoring gap)

`/ll:decide-issue` settled the table *shape* (Option A — inline rows in Criterion 4's existing
`Finding | Score` table) but not the row *content*, which is what Option B's critique had
objected to ("would require inventing prose bands"). Resolved here so implementation does not
re-litigate it. Criterion 4's table becomes:

| Finding | Score |
|---------|-------|
| Clear acceptance criteria, specific files, defined scope; no parity or claim gaps | 20 |
| Most details present, 1-2 minor gaps fillable from context; no parity or claim gaps | 15 |
| Any `missing_behavior_parity` gap (cap — apply regardless of otherwise-higher row) | 10 |
| Key details missing but inferrable from codebase research | 10 |
| Any `stale_symbol_ref` / `stale_cli_flag` gap (also forces the Phase 3 hard override) | 0 |
| Vague requirements, significant guesswork needed | 0 |

The parity row is a **cap**, not an additive delta: it preserves the table's absolute-value
convention (the one Option A property Option B challenged) while still expressing a
count-driven signal. The claim row is scored 0 for internal consistency only — the Phase 3
hard override is what actually gates, so the point value is not load-bearing.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

**Option A**: Add deduction rows directly into the existing `### Criterion 4: Issue Well-Specified` `Finding | Score` table in `rubric.md` (absolute point value per row, same two-column shape as today). Mirrors the majority precedent — 5 of 6 rubric.md criterion tables use this shape.

> **Selected:** Option A — evidence shows 8 of 9 Phase 2 scoring tables use this plain `Finding | Score` shape, and no downstream mechanism (Phase 3's hard-override reads independent shell variables, not a table) requires the alternative shape. See Decision Rationale below.

**Option B**: Add a separate modifier table (`Target Status | Score Modifier | Action`) applied "on top of" Criterion 4, mirroring the one existing gate-driven-modifier precedent: the "Learning Test Status Scoring (Criterion 1 Modifier)" table (`rubric.md` lines 161-172).

**Recommended**: Option B — the two new gap kinds are count/presence-based hard signals (a claim either references current code or it doesn't; a parity gap either exists or it doesn't), structurally closer to the Learning Test target's `missing`/`refuted` states than to Criterion 4's existing qualitative "how well specified is this issue" prose conditions. Folding counts into the absolute Finding/Score table would require inventing prose bands ("mostly clean but 1 stale ref = 15") that don't reflect the actual signal shape, whereas a modifier table keeps the count-driven deduction explicit and composable with the Phase 3 hard-override paragraph pattern already established for Program Design and Learning Test gates.

### Decision Rationale

_Added by `/ll:decide-issue` — 2026-08-04:_

**Selected: Option A** (add deduction rows directly into the existing Criterion 4 `Finding | Score`
table), overriding this section's inline "Recommended: Option B" note. Evidence-based scoring found
the status-driven analogy Option B's recommendation rests on does not hold up:

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A — inline Criterion 4 rows | 2 | 3 | 3 | 3 | **11/12** |
| B — separate modifier table | 1 | 1 | 3 | 2 | 7/12 |

**Key evidence:**
- 8 of 9 tables in `rubric.md` Phase 2 ("Readiness Scoring Tables") use the plain two-column
  `Finding | Score` shape; only the Learning Test table uses the three-column
  `Target Status | Score Modifier | Action` shape Option B proposes to mirror.
- The Learning Test modifier table is **status-driven** — a lookup over four discrete labels
  (`proven`/`stale`/`refuted`/`missing`) — not count-driven. A scalar claim/parity count is a
  materially different signal shape, weakening the analogy Option B's "Recommended" note relies on.
- The codebase's actual count-based-modifier precedent (Outcome Confidence's history-correction
  signal, `-0.1` per matched correction, capped at 5) is a formula applied directly to the score,
  not a three-column table — so even the closest true count-driven analog doesn't match Option B's
  proposed shape.
- SKILL.md Phase 3's hard-override mechanism (Learning Test and Program Design overrides) reads
  independently-computed shell variables (`PD_FAIL`, Learning Test target presence) regardless of
  which table shape backs the underlying score — Program Design has no modifier table at all and
  its override still works. No downstream mechanism requires Option B's separate-table structure.

## Scope Boundaries

**In scope:** Phase 1.6 pre-fetch of two existing/planned `format-check` gap keys, one Criterion 4
table revision in `rubric.md`, one Phase 3 hard-override paragraph in `SKILL.md`, the matching
test class, and regenerating the two adapter mirrors.

**Explicitly out of scope:**

- **Detecting** claim or parity gaps. FEAT-3048 and ENH-3045 own detection; this issue only
  consumes what `format-check` already emits. No changes to `issue_parser.py`,
  `check_format_gaps()`, or `FormatGaps`.
- A `check-claims`-style CLI subcommand — explicitly decided against (see Program Design §
  Signatures).
- Any change to the other four criteria, to the outcome-confidence scoring, or to the
  score-to-tier thresholds in `.ll/ll-config.json` (`commands.confidence_gate`).
- Re-scoring existing issues. Downward re-scoring is an intended *consequence* on next run, not
  a batch migration this issue performs.
- The Dependencies hard override — that is BUG-3051's scope, not this issue's, even though both
  edit the same Phase 3 block.

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — Phase 1.6 pre-fetch, Phase 3 recommendation
- `skills/confidence-check/rubric.md` — Criterion 4 deduction table
- `scripts/tests/test_confidence_check_skill.py` — scoring assertions for the deduction path

### Similar Patterns
- `ENH-2852` / `ENH-2967` — Program Design gate pre-fetch and its `check-design` CLI owner;
  the exact shape to copy for the pre-fetch (though **not** for CLI ownership — see Program
  Design § Signatures)
- `ENH-2946` — confidence-check already consuming `format-check` output

### Coordination: BUG-3051 edit collision

`BUG-3051` (P2, unblocked) adds a **Dependencies Hard Override** to the same `SKILL.md` Phase 3
paragraph block this issue's claim override targets (`skills/confidence-check/SKILL.md` lines
~300-306, immediately after the Learning Test and Program Design overrides). The two changes are
independent in behavior but collide textually.

Whichever lands second rebases onto the other's Phase 3 text; do not resolve by reverting either
override. If BUG-3051 lands first it will also correctly re-gate *this* issue's own
confidence-check run, which is the desired self-consistency.

### Documentation

_Wiring pass added by `/ll:wire-issue`; corrected 2026-08-05:_
- `docs/reference/CLI.md` — the original wiring note claimed the gap-class enumeration
  (~line 1872) and JSON example payload (~line 1942) "do not list `missing_behavior_parity`
  today." **That is no longer true**: ENH-3045 added it at `CLI.md:1872` (in the sixteen-class
  enumeration), `:1900` (its own description paragraph), and `:1950` (the JSON example), plus
  `docs/reference/API.md:862`/`:878`. Stage 1 needs no CLI.md change.
- The note stands only for stage 2: `stale_symbol_ref`/`stale_cli_flag` are FEAT-3048's
  obligation to document, but Phase 1.6 is the first consumer that breaks if that update is
  skipped [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_confidence_check_skill.py` — no existing test class covers Phase 1.6 or
  Criterion 4 (existing classes cover Phase 4/4.5/4.6, Criterion D, Criterion A, learning-test
  prefetch, VERDICT_JSON); follow the `TestConfidenceCheckLearningTestPrefetch` structural-slice
  pattern — slice `### Phase 1.6:` and the Criterion 4 table via `content.index`/`content.find`,
  then assert the new gap-field names and deduction-point language appear in the sliced text
  [Agent 3 finding]. Confidence-check's Phase 1.6 bash logic is untested by pytest today — the
  Program Design gate precedent (PD_GAP/PD_FAIL) only tests the underlying CLI predicate
  (`test_ll_issues_check_design.py`), never the SKILL.md prose itself, so this file gets a new
  test class rather than an update to an existing one.

### Adapter Mirrors

_Wiring pass added by `/ll:wire-issue`:_
- `.kimi-code/skills/confidence-check/SKILL.md` and `.gemini/skills/confidence-check/SKILL.md`
  are git-tracked, generated mirrors of `skills/confidence-check/SKILL.md` (produced by
  `ll-adapt --host <host> --apply`, marked `# generated by ll-adapt`). Editing Phase 1.6/Phase 3
  in the source without regenerating both mirrors leaves them drifted [Agent 2 finding].

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

### Conventions in Force

- Rubric deduction tables are one `###`-level table per criterion/gate, `Finding | Score` (absolute point value), not a delta — evidence: 5 of 6 tables in `skills/confidence-check/rubric.md` "Phase 2 — Readiness Scoring Tables" (lines 176-252), including the existing `### Criterion 4: Issue Well-Specified` table this issue targets (lines 236-243).
- One documented exception exists: gate-driven modifiers use a different `Target Status | Score Modifier | Action` shape, signed delta applied "on top of" the base criterion rather than folded into its Finding/Score rows — evidence: "Learning Test Status Scoring (Criterion 1 Modifier)" table, `rubric.md` lines 161-172.
- Phase 3 hard overrides are named bolded paragraphs ("**X Hard Override**") placed before score summation, gated on a Phase-1.6-set variable being non-empty/non-zero, forcing `STOP — ADDRESS GAPS` "regardless of aggregate score" — evidence: Learning Test Hard Override and Program Design Hard Override, `skills/confidence-check/SKILL.md` "Phase 3: Score and Recommend" lines 300-306. This is the pattern the issue's Expected Behavior cites for "nonzero unverified-claim count as a readiness blocker."
- `format-check --format json` keys are referenced two ways in this codebase, both established: inline bash/python extraction into shell variables (confidence-check's Phase 1.6), and pure markdown prose naming the key plus its non-empty/nonzero condition with no code shown (`commands/refine-issue.md` Step 6.7, lines 781-831, for `prose_dep_drift`/`stale_prose_dep`/`program_design_nonspecific`/`superseded_marker_count`/`duplicate_findings_block`).
- `check_design.py`'s `cmd_check_design` is the CLI-owner precedent named in this issue's "Similar Patterns" — its docstring states it is the "single CLI owner of the `design_gate_failed()` predicate, replacing the three independent inline `python3 -c "..."` blocks in autodev.yaml that each re-derived the same boolean from raw `format-check --format json` output," and that it "fails open (exit 0) on projects that haven't armed the ... gate, mirroring `check_format_gaps()`'s existing fail-open behavior."

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

### Types

- `FormatGaps` (`scripts/little_loops/issue_parser.py:237`) — the dataclass all `format-check` JSON/text consumers key off; **16** `list[str]` gap-kind fields as of ENH-3045, each mirrored in `has_gaps` and `to_dict()` (`:301`). `missing_behavior_parity` is present at `:259` and needs no schema work. Stage 2 presupposes FEAT-3048 adds `stale_symbol_ref` and `stale_cli_flag` as two more `list[str]` fields on this same dataclass. _(Corrected 2026-08-05 — the original finding said all three keys were absent.)_
- `PD_GAP: str` / `PD_FAIL: str` — the two shell-variable shapes Phase 1.6 currently populates from `format-check`/`check-design` output (`skills/confidence-check/SKILL.md:132-150`): a joined reason-string (`PD_GAP`, from a `list[str]` JSON key) and a separate pass/fail verdict (`PD_FAIL`, `""` or `"yes"`, from a dedicated CLI's exit code rather than re-derived from JSON).

### Signatures

- `program_design_gate_active(issue_path: Path, content: str) -> bool`

  `scripts/little_loops/issues/program_design.py:415` — the activation-gating pattern (unstamped project / grandfathered / `*_not_applicable: true` frontmatter all return `False`) that the Program Design gate uses to fail open; a parity/claim equivalent, if the CLI layer needs one, would follow this same shape.
- `cmd_format_check() -> None`

  `scripts/little_loops/cli/issues/format_check.py:165` — the existing JSON-serialization entry point (`gaps.to_dict()` via `check_format_gaps()`) that would need the new `FormatGaps` fields threaded through before Phase 1.6 has anything new to parse.
- `cmd_check_design` — sole CLI owner of the `design_gate_failed()` boolean predicate (`scripts/little_loops/cli/issues/check_design.py`).

  **Decision (2026-08-05): no `check-claims` CLI. Derive both booleans inline.** Research left
  this open; resolving it here so implementation does not stall. `cmd_check_design` exists
  because `design_gate_failed()` is a three-way OR (non-specific / missing / empty) that was
  being re-derived inline in three separate `python3 -c` blocks in `autodev.yaml` — its own
  docstring names de-duplicating those three call sites as the reason. Neither new signal has
  that shape: each is a single `len(gaps[key]) > 0` test with exactly one consumer (Phase 1.6).
  A dedicated CLI would add a subcommand, its docs, and its tests to own one non-empty check.
  Revisit only if a second consumer appears — at which point the `check-design` precedent
  applies for real.

### Call Path

`skills/confidence-check/SKILL.md` Phase 1.6 bash block -> `ll-issues format-check --format json` -> `cmd_format_check()` (`format_check.py:165`) -> `check_format_gaps()` (`issue_parser.py`) -> `FormatGaps.to_dict()` (`issue_parser.py:281`) -> parsed via inline `python -c` in the SKILL.md bash block -> stored in a shell variable -> read by `rubric.md`'s Criterion 4 table and/or `SKILL.md` Phase 3's hard-override paragraph.

## Implementation Steps

### Stage 1 — parity deduction (unblocked, ship now)

1. Extend the Phase 1.6 bash block to populate `PARITY_GAP` from
   `ll-issues format-check {{issue_id}} --format json`, joining
   `.get('missing_behavior_parity', [])` with `; ` — same extraction shape as the existing
   `PD_GAP` line, including the `2>/dev/null || true` fail-open tail.
2. Revise the Criterion 4 table in `rubric.md` to the six rows specified in Proposed Solution §
   Deduction Rows, including the parity cap row.
3. Add the new test class to `scripts/tests/test_confidence_check_skill.py` (structural slice,
   per the wiring note below).
4. Regenerate both adapter mirrors.

### Stage 2 — claim hard override (on FEAT-3048)

5. Extend Phase 1.6 to populate `CLAIM_GAP` from `stale_symbol_ref` + `stale_cli_flag`, derived
   inline — no new CLI (see Program Design § Signatures).
6. Add the **Unverified Claim Hard Override** paragraph to `SKILL.md` Phase 3, following the
   Program Design override's shape: non-empty `CLAIM_GAP` forces `STOP — ADDRESS GAPS`
   regardless of aggregate score, with the reason strings reproduced verbatim under **Gaps to
   Address**. Rebase onto BUG-3051's Dependencies override if that landed first.
7. Extend the test class to cover the override and the claim rows.
8. Confirm FEAT-3048 documented the two new keys in `docs/reference/CLI.md`; file a follow-up
   against FEAT-3048 if not.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add a new test class to `scripts/tests/test_confidence_check_skill.py` covering Phase 1.6's
  new gap-field parsing and Criterion 4's new deduction rows, following the
  `TestConfidenceCheckLearningTestPrefetch` structural-slice pattern
- Regenerate the generated adapter mirrors — `ll-adapt --host kimi-code --apply` and
  `ll-adapt --host gemini --apply` — after editing `skills/confidence-check/SKILL.md`, so
  `.kimi-code/skills/confidence-check/SKILL.md` and `.gemini/skills/confidence-check/SKILL.md`
  stay in sync
- Update `docs/reference/CLI.md`'s `format-check --format json` gap-class enumeration and JSON
  example to include the new gap keys once they exist — **stage 2 / FEAT-3048 only**; ENH-3045
  already did this for `missing_behavior_parity`

## Acceptance Criteria

1. A `format-check --format json` payload with a non-empty `missing_behavior_parity` list caps
   that issue's Criterion 4 score at 10.
2. A payload with **no** `missing_behavior_parity`, `stale_symbol_ref`, or `stale_cli_flag` key
   at all — the pre-FEAT-3048 and unarmed-project cases — produces scoring identical to today's
   behavior. Both new pre-fetch variables come back empty, both new rows are unreachable; no
   error, no stderr, no score change. This is the fail-open requirement, and it is testable
   independently of FEAT-3048.
3. (Stage 2) A non-empty `stale_symbol_ref` or `stale_cli_flag` list forces `STOP — ADDRESS
   GAPS` regardless of aggregate readiness score, and the offending reason strings appear
   verbatim under **Gaps to Address**.
4. `scripts/tests/test_confidence_check_skill.py` gains a test class asserting that the sliced
   `### Phase 1.6:` block names `missing_behavior_parity` and that the sliced Criterion 4 table
   contains the parity cap row; `python -m pytest scripts/tests/` exits 0.
5. `.kimi-code/skills/confidence-check/SKILL.md` and `.gemini/skills/confidence-check/SKILL.md`
   match a fresh `ll-adapt --host <host> --apply` run — no drift.
6. `skills/confidence-check/SKILL.md` stays under the 500-line cap enforced by `ll-verify-skills`
   (405 lines today; stages 1 and 2 together add roughly 15).
7. **End-to-end validation fixture.** Re-running `/ll:confidence-check` on an issue that
   `format-check` reports a `missing_behavior_parity` gap for scores it at or below 85 readiness
   — under this repo's `commands.confidence_gate` threshold, i.e. no longer auto-passing.
   Record which issue was used.

   _Note (2026-08-05): the Summary's motivating example, FEAT-2942, is **not** a valid fixture
   for stage 1 — `ll-issues format-check FEAT-2942` reports only a `testable` gap, no parity
   gap. Its defects (false claim about its own write path, contradictions, undefined terms) are
   claim-class, so FEAT-2942 validates **stage 2**, not stage 1. It is still 93/76 today, so it
   remains a live stage-2 fixture._

## Impact

- **Priority**: P3 — stage 1 is unblocked as of ENH-3045; stage 2 waits on FEAT-3048
- **Effort**: Low — prompt/rubric wiring on an existing pre-fetch
- **Risk**: Low — scoring change only; re-scores some existing issues downward (intended)
- **Blast radius (measured 2026-08-05)**: 10 of 170 active issues (6%) currently carry a
  `missing_behavior_parity` gap, so the stage-1 cap re-scores a modest slice rather than the
  whole backlog. This measurement is what justifies setting the cap at 10 rather than a
  softer 15 — re-measure if it has grown substantially before implementing.

## Related Key Documentation

- `.claude/CLAUDE.md` — confidence gate thresholds in `.ll/ll-config.json`
  (`commands.confidence_gate`: readiness 85, outcome 65)
- `docs/reference/COMMANDS.md` — `/ll:confidence-check`

## Status

**Open** | Created: 2026-08-04 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-04_

> **Stale as of 2026-08-05 — re-run before implementing.** Three of the four recorded concerns
> have since been addressed: the hard blocker was downgraded to `depends_on` (ENH-3045 landed,
> making stage 1 startable), the open `check-claims` CLI decision was resolved (no new CLI), and
> the missing Scope Boundaries section was added. The 75 readiness score below predates all
> three and understates current readiness.

**Readiness Score**: 75/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 68/100 → MODERATE

### Concerns
- Hard blocker `FEAT-3048` is still `status: open` — this issue's own text states "without it there is nothing to read," so Dependencies Satisfied scored 0/20 despite the other four criteria scoring near-perfect (75 total masks a real cannot-start-yet state; treat as blocked, not merely cautioned, until FEAT-3048 lands).
- `format-check` flags a missing "Scope Boundaries" section (Criterion 4, −5).
- Program Design's own research left one implementation decision open: whether claim/parity verification needs a dedicated `check-claims`-style CLI owner (mirroring `cmd_check_design`) or should stay inline like `PD_FAIL` today — noted as "unresolved by research and is an implementation decision."

### Outcome Risk Factors
- Moderate breadth (6 touch sites: SKILL.md, rubric.md, test file, CLI.md docs, two generated adapter mirrors) with local-logic depth in the Phase 1.6 bash parsing extension — not mechanical-only.
- Test coverage for the new path can only be structurally slice-tested (SKILL.md prose) until FEAT-3048's gap kinds actually exist in `FormatGaps`; true integration coverage is deferred by the same blocker as above.

## Session Log
- `/ll:confidence-check` - 2026-08-05T02:22:34 - `20781823-2973-4b25-9054-bebe6629d257.jsonl`
- `/ll:confidence-check` - 2026-08-05T01:56:50 - `6569bf0b-4efa-4bb9-8b85-a0e909af608e.jsonl`
- `/ll:wire-issue` - 2026-08-05T01:49:15 - `2c309fa5-8c43-401a-82fc-22975e2f2e35.jsonl`
- `/ll:decide-issue` - 2026-08-05T01:40:16 - `f80f4891-ce9f-494e-aa23-5cc25bc1524e.jsonl`
- `/ll:refine-issue` - 2026-08-05T01:31:24 - `42ca0c4a-7282-4fbe-9b00-3b9e16ffcd31.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-05T00:25:09 - `b9710cb8-1d2b-4d04-8cf1-ad93d3cfccb7.jsonl`
- `/ll:capture-issue` - 2026-08-04T20:50:28 - `2a9240a9-e6df-4ed5-ad2a-73a280bc7d8b.jsonl`
