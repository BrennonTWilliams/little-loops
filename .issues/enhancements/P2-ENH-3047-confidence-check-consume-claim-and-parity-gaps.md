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
verify_verdict: VALID
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
ENH-3045 parity gap into a new Phase 1.8 pre-fetch as explicit Criterion 4 deductions, so
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

- Phase 1.6's existing pre-fetch (`skills/confidence-check/SKILL.md`, `### Phase 1.6: Pre-Fetch Program Design Gate (ENH-2852)`, lines 132-150) is the concrete template this issue **copies into a new Phase 1.8 block** (not extends — see Integration Map § Coordination) — it populates two shell variables from `ll-issues format-check {{issue_id}} --format json`: `PD_GAP` (raw reason string, `json.load(sys.stdin).get('program_design_nonspecific', [])` joined with `; `) and `PD_FAIL` (a separate pass/fail verdict from the dedicated `ll-issues check-design {{issue_id}}` exit code, not re-derived from JSON in the skill).
- **Superseded 2026-08-05 — ENH-3045 has since landed.** The original finding read: "the target keys ... do not exist anywhere in the current schema ... none of the three target keys are present." That is now false for one of the three. `missing_behavior_parity` is live in `FormatGaps` (`scripts/little_loops/issue_parser.py:259`), mirrored in `has_gaps` (`:280`) and `to_dict()` (`:301`), emitted by `cmd_format_check` (`scripts/little_loops/cli/issues/format_check.py:163`), and documented (`docs/reference/CLI.md:1900` and the JSON example at `:1950`; `docs/reference/API.md:878`). `FormatGaps` now has 16 `list[str]` fields, not 15. Only `stale_symbol_ref` and `stale_cli_flag` (FEAT-3048) remain absent from the schema.
- The "no precedent for defensively reading a not-yet-emitted key" concern therefore applies **only to the FEAT-3048 pair**, not to parity. For those two, `.get('stale_symbol_ref', [])` on a payload that lacks the key yields `[]`, which makes the claim deduction and its hard override inert — the same fail-open end state as the Program Design gate on an unstamped project, reached by a different route (schema-absent key vs. schema-present-but-empty). Stage 2 must not ship until FEAT-3048 lands, but stage 1 is unaffected: `missing_behavior_parity` is schema-present today.

## Expected Behavior

A new Phase 1.8 block pre-fetches, via `ll-issues format-check --format json` (see Integration
Map § Coordination — Phase 1.7's separate-block shape is the precedent, not a Phase 1.6
extension):

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

Follow the existing Phase 1.6/1.7 pattern in a new Phase 1.8 block: one `format-check --format json` call, parsed into
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

The parity row is a **ceiling, never a floor**: it lowers an otherwise-higher row to 10 and never
raises a lower one (an issue that would score 0 on "vague requirements" still scores 0 with a
parity gap). It preserves the table's absolute-value convention (the one Option A property Option B challenged) while still expressing a
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

**In scope:** a new Phase 1.8 pre-fetch of two existing/planned `format-check` gap keys, one Criterion 4
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
- `skills/confidence-check/SKILL.md` — new Phase 1.8 pre-fetch block, Phase 3 recommendation
  (four overrides live at `:336-340` as of BUG-3051; 441 lines total)
- `skills/confidence-check/rubric.md` — Criterion 4 deduction table
- `scripts/tests/test_confidence_check_skill.py` — scoring assertions for the deduction path

### Similar Patterns
- `ENH-2852` / `ENH-2967` — Program Design gate pre-fetch and its `check-design` CLI owner;
  the exact shape to copy for the pre-fetch (though **not** for CLI ownership — see Program
  Design § Signatures)
- `ENH-2946` — confidence-check already consuming `format-check` output

### Coordination: BUG-3051 (landed 2026-08-05 — resolved)

`BUG-3051` **has landed** (commit `5cfaf967`). The anticipated edit collision is resolved in its
favor: this issue is the one that rebases. Concretely, as of that commit:

- Phase 3 now carries **four** overrides at `skills/confidence-check/SKILL.md:336-340` (Learning
  Test, Program Design, Dependencies) — not lines ~300-306 as originally written. Stage 2's
  **Unverified Claim Hard Override** appends after the Dependencies override.
- **Precedent change (important).** BUG-3051 did *not* extend Phase 1.6. It added a distinct
  `### Phase 1.7: Pre-Fetch Dependencies Gate (BUG-3051)` block with its own variables
  (`DEP_FAIL`, `DEP_ROWS`). That is the shape this issue now follows: a new
  `### Phase 1.8: Pre-Fetch Claim and Parity Gaps (ENH-3047)` block, **not** an extension of
  Phase 1.6. Phase 1.6 is titled "Pre-Fetch Program Design Gate (ENH-2852)"; adding parity/claim
  variables inside it mislabels the block and makes the structural-slice test ambiguous.

### Documentation

_Wiring pass added by `/ll:wire-issue`; corrected 2026-08-05:_
- `docs/reference/CLI.md` — the original wiring note claimed the gap-class enumeration
  (~line 1872) and JSON example payload (~line 1942) "do not list `missing_behavior_parity`
  today." **That is no longer true**: ENH-3045 added it at `CLI.md:1872` (in the sixteen-class
  enumeration), `:1900` (its own description paragraph), and `:1950` (the JSON example), plus
  `docs/reference/API.md:862`/`:878`. Stage 1 needs no CLI.md change.
- The note stands only for stage 2: `stale_symbol_ref`/`stale_cli_flag` are FEAT-3048's
  obligation to document, but Phase 1.8 is the first consumer that breaks if that update is
  skipped [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_confidence_check_skill.py` — no existing test class covers Phase 1.6/1.8 or
  Criterion 4; **BUG-3051 added the closest precedent**, `TestConfidenceCheckDependenciesPrefetch`
  (`:432`) plus `TestConfidenceCheckRubricDependenciesOverride` (`:489`) — copy that pair's shape
  rather than the older `TestConfidenceCheckLearningTestPrefetch` (`:368`). Slice
  `### Phase 1.8:` and the Criterion 4 table via `content.index`/`content.find`,
  then assert the new gap-field names and deduction-point language appear in the sliced text
  [Agent 3 finding]. Confidence-check's Phase 1.6 bash logic is untested by pytest today — the
  Program Design gate precedent (PD_GAP/PD_FAIL) only tests the underlying CLI predicate
  (`test_ll_issues_check_design.py`), never the SKILL.md prose itself, so this file gets a new
  test class rather than an update to an existing one.
- `scripts/tests/test_skill_size_checker.py::TestSkillLineLimit::test_all_skills_within_limit` —
  the concrete pytest gate behind Acceptance Criterion 6's "500-line cap enforced by
  `ll-verify-skills`" claim, not previously named anywhere in this issue. It globs `skills/*/SKILL.md`
  only (not `rubric.md`, which has no line-count gate). `skills/confidence-check/SKILL.md` is
  **442 lines today, not 441** (off-by-one in AC6's count) — leaving ~58 lines of headroom before
  Phase 1.8 (stage 1) plus the Unverified Claim Hard Override paragraph (stage 2) would need to
  trip this gate [Agent 3 finding, pattern-finder pass].

### Adapter Mirrors

_Wiring pass added by `/ll:wire-issue`:_
- `.kimi-code/skills/confidence-check/SKILL.md` and `.gemini/skills/confidence-check/SKILL.md`
  are git-tracked, generated mirrors of `skills/confidence-check/SKILL.md` (produced by
  `ll-adapt --host <host> --apply`, marked `# generated by ll-adapt`). Editing Phase 1.8/Phase 3
  in the source without regenerating both mirrors leaves them drifted [Agent 2 finding].

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

- `docs/reference/CLI.md`'s `--format json` JSON example now sits at `:1966`, not `:1950` as previously cited above (the `:1950` line now falls inside an unrelated `superseded_marker_count` paragraph) — the enumeration (`:1872`) and description-paragraph (`:1900`) citations are still accurate.
- Adapter mirror drift is broader than "missing Phase 1.7 content": `.gemini/skills/confidence-check/SKILL.md`'s frontmatter `allowed-tools` list (lines 6-14) is also missing `Bash(ll-issues:*)`, which the source added specifically for Phase 1.7's `ll-issues show`/`ll-issues format-check` calls (BUG-3051). The same gap is expected in `.kimi-code/skills/confidence-check/SKILL.md` by the same regeneration lag. A plain content-only regen must also pick up this permission-list change, not just the new phase text.
- No general mirror-staleness test exists to catch this class of drift today — the only committed parity test (`scripts/tests/test_wiring_skills_and_commands.py:345-372`, `test_wire_issue_skill_mirror_matches_source`) is scoped to `wire-issue` only; `confidence-check` has no equivalent `CONFIDENCE_CHECK_SKILL_MIRRORS` parametrization. `ENH-2968` (open) proposes a general `test_adapt_mirror_staleness.py` but the output-root seam it needs doesn't exist yet in `adapters/core.py`. This issue's Acceptance Criterion 5 (manual `ll-adapt --host <host> --apply` + diff check) is therefore the only enforcement mechanism until ENH-2968 lands.

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

- Correction to the "Conventions in Force" bullet above citing "Phase 3: Score and Recommend" lines 300-306 for the Learning Test/Program Design overrides — that range predates the current file (it disagrees with this section's own corrected Integration Map citation of `:336-340`). Current lines: `### Phase 3:` header at `:334`, Learning Test Hard Override at `:336`, Program Design Hard Override at `:338`, Dependencies Hard Override at `:340`.

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

- **Pre-fetch block internal shape (pattern-finder, new detail).** Phase 1.6/1.7 blocks in `SKILL.md` share more structure than just the `PD_GAP`/`DEP_FAIL`-style variables already noted above: each external `ll-issues ...` call is *individually* wrapped in `2>/dev/null || true` (not once for the whole block) — `SKILL.md:138-140`, `:162`, `:170`. Phase 1.7's inline JSON-extraction lines carry an explicit `<!-- ll-prose-ok: mirrors the pre-existing PD_GAP idiom (SKILL.md Phase 1.6) ... -->` comment naming the precedent it copies (`SKILL.md:161`, `:169`) — Phase 1.8 should carry the same self-documenting annotation. Both blocks close with prose (not just code) covering three things: what the variable means, when it is empty/inert, and an explicit "do not re-derive/re-judge yourself, the CLI is the source of truth" instruction (`SKILL.md:143-151`, `:179-184`).
- **Phase 3 override paragraph template (pattern-finder, new detail).** Each hard-override paragraph follows: condition ("if Phase 1.N set X to ...") → consequence ("`STOP — ADDRESS GAPS` regardless of aggregate score") → what to list under **Gaps to Address** → remedy sentence → inert-condition sentence. Learning Test's override (`SKILL.md:336`) is terser and skips the last two parts; Program Design (`:338`) and Dependencies (`:340`) both have all four, and Dependencies additionally closes by tying back to its Criterion's existing 0-20 scoring ("This is additive to Criterion 5's existing 0-20 scoring, which is unchanged for the non-blocking case") — the Unverified Claim override (stage 2) should follow the fuller four-part template, not the terser Learning Test one.
- **Test-class convention (pattern-finder, new detail beyond the existing Tests § pointer to `TestConfidenceCheckDependenciesPrefetch`).** The codebase keeps a SKILL.md-phase test class and a rubric.md-override test class separate rather than combined (`test_confidence_check_skill.py:432`, `:489`). Both use a private `_phase_text(self, heading)` helper, but the slice boundary differs by file: SKILL.md slicing stops at the next `\n###` heading (`:435-440`, matching `TestConfidenceCheckPhase4CLI._phase_text` at `:15-20`), while the rubric.md override test slices from the Criterion heading to the next `\n---` divider instead (`:493-496`) — using the SKILL.md-style `\n###` boundary on rubric.md would silently include unrelated Criterion sections. Every individual `test_*` assertion message across both classes ends with the issue ID in parens, e.g. `"... (BUG-3051)"` (`:445`, `:451`, `:457`, `:463`, `:469`, `:477`, `:485`, `:498`).
- **Rubric/SKILL pairing convention (pattern-finder, new detail).** Criterion 5's rubric table (`rubric.md:245-252`) is immediately followed, with no divider, by a `**Dependencies Hard Override** (BUG-3051):` paragraph inside the same `### Criterion 5` section (`rubric.md:254-259`) that cross-references "see SKILL.md Phase 3" rather than duplicating the STOP instruction in full — this is the second rubric.md precedent (alongside the Program Design § Signatures note already in this issue) for where stage 2's Criterion 4 override language could live if a rubric-side pointer is wanted.

### Conventions in Force

- Rubric deduction tables are one `###`-level table per criterion/gate, `Finding | Score` (absolute point value), not a delta — evidence: 5 of 6 tables in `skills/confidence-check/rubric.md` "Phase 2 — Readiness Scoring Tables" (lines 176-252), including the existing `### Criterion 4: Issue Well-Specified` table this issue targets (lines 236-243).
- One documented exception exists: gate-driven modifiers use a different `Target Status | Score Modifier | Action` shape, signed delta applied "on top of" the base criterion rather than folded into its Finding/Score rows — evidence: "Learning Test Status Scoring (Criterion 1 Modifier)" table, `rubric.md` lines 161-172.
- Phase 3 hard overrides are named bolded paragraphs ("**X Hard Override**") placed before score summation, gated on a Phase-1.6-set variable being non-empty/non-zero, forcing `STOP — ADDRESS GAPS` "regardless of aggregate score" — evidence: Learning Test Hard Override and Program Design Hard Override, `skills/confidence-check/SKILL.md` "Phase 3: Score and Recommend" lines 300-306. This is the pattern the issue's Expected Behavior cites for "nonzero unverified-claim count as a readiness blocker."
- `format-check --format json` keys are referenced two ways in this codebase, both established: inline bash/python extraction into shell variables (confidence-check's Phase 1.6), and pure markdown prose naming the key plus its non-empty/nonzero condition with no code shown (`commands/refine-issue.md` Step 6.7, lines 781-831, for `prose_dep_drift`/`stale_prose_dep`/`program_design_nonspecific`/`superseded_marker_count`/`duplicate_findings_block`).
- `check_design.py`'s `cmd_check_design` is the CLI-owner precedent named in this issue's "Similar Patterns" — its docstring states it is the "single CLI owner of the `design_gate_failed()` predicate, replacing the three independent inline `python3 -c "..."` blocks in autodev.yaml that each re-derived the same boolean from raw `format-check --format json` output," and that it "fails open (exit 0) on projects that haven't armed the ... gate, mirroring `check_format_gaps()`'s existing fail-open behavior."

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

- **Line-citation corrections (re-verified 2026-08-05, post ENH-3046/BUG-3059):** `FormatGaps` (`scripts/little_loops/issue_parser.py:236`) now has **18** `list[str]` gap-kind fields, not 16 — `soft_dep_hard_edge` (ENH-3046) and `malformed_dep_id` (BUG-3059) landed after this issue's Types section was written. `stale_symbol_ref`/`stale_cli_flag` remain correctly absent. The `missing_behavior_parity` mention in `has_gaps` is at `issue_parser.py:282` (not `:280`); its `to_dict()` entry is at `:305` (not `:301`, which is now the unrelated `stale_file_ref` entry). `docs/reference/CLI.md:1872` itself now says "eighteen classes."
- `cmd_format_check`'s actual location is `scripts/little_loops/cli/issues/format_check.py:178` — both prior citations in this issue (`:163`, `:165`) are stale.
- Additional rubric.md precedent for the table-shape decision (does not change the already-decided Option A): Criterion 5 (`rubric.md:245-259`) already pairs a plain two-column base table (`:249-252`) with a named "**Dependencies Hard Override** (BUG-3051)" prose paragraph directly beneath it in the same `### Criterion N` section (`:254-259`) — a second precedent, alongside SKILL.md's Phase 3 override paragraphs, for where Criterion 4's own override language could live if stage 2 needs a rubric-side pointer.

### Types

- `FormatGaps` (`scripts/little_loops/issue_parser.py:237`) — the dataclass all `format-check` JSON/text consumers key off; **16** `list[str]` gap-kind fields as of ENH-3045, each mirrored in `has_gaps` and `to_dict()` (`:301`). `missing_behavior_parity` is present at `:259` and needs no schema work. Stage 2 presupposes FEAT-3048 adds `stale_symbol_ref` and `stale_cli_flag` as two more `list[str]` fields on this same dataclass. _(Corrected 2026-08-05 — the original finding said all three keys were absent.)_
- `PD_GAP: str` / `PD_FAIL: str` — the two shell-variable shapes Phase 1.6 currently populates from `format-check`/`check-design` output (`skills/confidence-check/SKILL.md:132-150`): a joined reason-string (`PD_GAP`, from a `list[str]` JSON key) and a separate pass/fail verdict (`PD_FAIL`, `""` or `"yes"`, from a dedicated CLI's exit code rather than re-derived from JSON).

### Signatures

- `program_design_gate_active(issue_path: Path, content: str) -> bool`

  `scripts/little_loops/issues/program_design.py:415` — the activation-gating pattern (unstamped project / grandfathered / `*_not_applicable: true` frontmatter all return `False`) that the Program Design gate uses to fail open; a parity/claim equivalent, if the CLI layer needs one, would follow this same shape.
- `cmd_format_check() -> None`

  `scripts/little_loops/cli/issues/format_check.py:165` — the existing JSON-serialization entry point (`gaps.to_dict()` via `check_format_gaps()`) that would need the new `FormatGaps` fields threaded through before Phase 1.8 has anything new to parse (stage 2 only — parity is already threaded).
- `cmd_check_design` — sole CLI owner of the `design_gate_failed()` boolean predicate (`scripts/little_loops/cli/issues/check_design.py`).

  **Decision (2026-08-05): no `check-claims` CLI. Derive both booleans inline.** Research left
  this open; resolving it here so implementation does not stall. `cmd_check_design` exists
  because `design_gate_failed()` is a three-way OR (non-specific / missing / empty) that was
  being re-derived inline in three separate `python3 -c` blocks in `autodev.yaml` — its own
  docstring names de-duplicating those three call sites as the reason. Neither new signal has
  that shape: each is a single `len(gaps[key]) > 0` test with exactly one consumer (Phase 1.8).
  A dedicated CLI would add a subcommand, its docs, and its tests to own one non-empty check.
  Revisit only if a second consumer appears — at which point the `check-design` precedent
  applies for real.

### Call Path

`skills/confidence-check/SKILL.md` Phase 1.8 bash block -> `ll-issues format-check --format json` -> `cmd_format_check()` (`format_check.py:165`) -> `check_format_gaps()` (`issue_parser.py`) -> `FormatGaps.to_dict()` (`issue_parser.py:281`) -> parsed via inline `python -c` in the SKILL.md bash block -> stored in a shell variable -> read by `rubric.md`'s Criterion 4 table and/or `SKILL.md` Phase 3's hard-override paragraph.

## Implementation Steps

### Stage 1 — parity deduction (unblocked, ship now)

1. Add a new `### Phase 1.8: Pre-Fetch Claim and Parity Gaps (ENH-3047)` block to `SKILL.md`,
   immediately after Phase 1.7, populating `PARITY_GAP` from
   `ll-issues format-check {{issue_id}} --format json`, joining
   `.get('missing_behavior_parity', [])` with `; ` — same extraction shape as the existing
   `PD_GAP` line, including the `2>/dev/null || true` fail-open tail. Do **not** extend Phase
   1.6 (see Integration Map § Coordination).
2. Revise the Criterion 4 table in `rubric.md` to the six rows specified in Proposed Solution §
   Deduction Rows, including the parity cap row.
3. Add the new test class to `scripts/tests/test_confidence_check_skill.py` (structural slice,
   per the wiring note below).
4. Regenerate both adapter mirrors.

### Stage 2 — claim hard override (on FEAT-3048)

5. Extend Phase 1.8 to populate `CLAIM_GAP` from `stale_symbol_ref` + `stale_cli_flag`, derived
   inline — no new CLI (see Program Design § Signatures).
6. Add the **Unverified Claim Hard Override** paragraph to `SKILL.md` Phase 3 **after** the
   Dependencies Hard Override (`SKILL.md:340`, landed), following the Program Design override's
   shape: non-empty `CLAIM_GAP` forces `STOP — ADDRESS GAPS` regardless of aggregate score, with
   the reason strings reproduced verbatim under **Gaps to Address**.
7. Extend the test class to cover the override and the claim rows.
8. Confirm FEAT-3048 documented the two new keys in `docs/reference/CLI.md`; file a follow-up
   against FEAT-3048 if not.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add a new test class to `scripts/tests/test_confidence_check_skill.py` covering Phase 1.8's
  gap-field parsing and Criterion 4's new deduction rows, following the
  `TestConfidenceCheckDependenciesPrefetch` structural-slice pattern (BUG-3051)
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
2. Fail-open, in the two distinct shapes it actually takes:
   - **Present-but-empty** (parity): `missing_behavior_parity` is schema-present today and can
     never be absent, so its fail-open case is an empty list. `PARITY_GAP` comes back empty, the
     cap row is unreachable, scoring is identical to today.
   - **Absent key** (claims, pre-FEAT-3048): `.get('stale_symbol_ref', [])` /
     `.get('stale_cli_flag', [])` on a payload lacking both keys yields `[]`. `CLAIM_GAP` comes
     back empty, the claim row and the Phase 3 override are inert.

   Neither case produces an error, stderr output, or a score change. Both are testable
   independently of FEAT-3048.
3. (Stage 2) A non-empty `stale_symbol_ref` or `stale_cli_flag` list forces `STOP — ADDRESS
   GAPS` regardless of aggregate readiness score, and the offending reason strings appear
   verbatim under **Gaps to Address**.
4. `scripts/tests/test_confidence_check_skill.py` gains a test class asserting that the sliced
   `### Phase 1.8:` block names `missing_behavior_parity` and that the sliced Criterion 4 table
   contains the parity cap row; `python -m pytest scripts/tests/` exits 0.
5. `.kimi-code/skills/confidence-check/SKILL.md` and `.gemini/skills/confidence-check/SKILL.md`
   match a fresh `ll-adapt --host <host> --apply` run — no drift.

   _Note (2026-08-05): both mirrors are **already drifted** — neither contains BUG-3051's Phase
   1.7. The regen this issue performs will therefore also carry BUG-3051's content into the
   mirrors. That is correct, but expect a larger mirror diff than this issue's own edits._
6. `skills/confidence-check/SKILL.md` stays under the 500-line cap enforced by `ll-verify-skills`
   (**441** lines today after BUG-3051; stages 1 and 2 together add roughly 15, landing near
   456 — the margin is thinner than the original 405-line estimate assumed, so keep the Phase
   1.8 prose tight and push any explanatory detail to `rubric.md`)
   > ⚠ Superseded — actual count is 442, not 441 [wire-issue].
7. **End-to-end validation fixture.** Re-running `/ll:confidence-check` on an issue with a
   `missing_behavior_parity` gap reports **Criterion 4 = 10** and reproduces the parity reason
   string under **Gaps to Address**. Record which issue was used.

   _Rewritten 2026-08-05 — the original wording ("scores at or below 85 readiness") is
   unfalsifiable with the only available fixture. Re-measured blast radius: **1 of 65 swept
   active issues (1.5%)**, not 10 of 170 (6%) — the sole issue carrying a parity gap is
   `FEAT-2787` (`missing_behavior_parity: ['scripts/little_loops/adapters/omp.py']`), and it
   already scores **56 readiness**, so the ≤85 assertion passes whether or not the cap fires.
   The criterion-level assertion above is the one with signal. If a fixture that would otherwise
   score >85 is wanted, construct a synthetic issue rather than hunting the backlog._

   _Note (2026-08-05): the Summary's motivating example, FEAT-2942, is **not** a valid fixture
   for stage 1 — `ll-issues format-check FEAT-2942` reports only a `testable` gap, no parity
   gap. Its defects (false claim about its own write path, contradictions, undefined terms) are
   claim-class, so FEAT-2942 validates **stage 2**, not stage 1. It is still 93/76 today, so it
   remains a live stage-2 fixture._

## Impact

- **Priority**: P3 — stage 1 is unblocked as of ENH-3045; stage 2 waits on FEAT-3048
- **Effort**: Low — prompt/rubric wiring on an existing pre-fetch
- **Risk**: Low — scoring change only; re-scores some existing issues downward (intended)
- **Blast radius (re-measured 2026-08-05 via `ll-issues format-check --all --format json`)**:
  **1 of 65 swept active issues (1.5%)** carries a `missing_behavior_parity` gap — `FEAT-2787`.
  This supersedes the earlier "10 of 170 (6%)" figure. The stage-1 cap is therefore close to
  inert against today's backlog; it is a forward-looking gate on newly written issues, not a
  re-scoring event. The cap value (10 vs. a softer 15) has almost no empirical consequence
  today, so keep 10 for the stricter default rather than re-litigating it.

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
- `/ll:confidence-check` - 2026-08-05T06:33:49 - `3f582821-770b-4d5b-a2a2-2dc16d0483b5.jsonl`
- `/ll:verify-issues` - 2026-08-05T06:31:11 - `5ceed56d-d650-4654-ab0d-8a7ea09a822f.jsonl`
- `/ll:wire-issue` - 2026-08-05T06:28:08 - `a6e5f56c-0e65-481a-b5ae-a4af5a727e15.jsonl`
- `/ll:refine-issue` - 2026-08-05T06:18:46 - `70f16d46-5a12-4806-91f5-71e162c23783.jsonl`
- `/ll:confidence-check` - 2026-08-05T06:15:32 - `38d8f4ce-76bd-4df4-9666-cadc0bc921cf.jsonl`
- `/ll:verify-issues` - 2026-08-05T06:13:24 - `89d36712-9423-4d75-a7df-dadb7534fce2.jsonl`
- `/ll:refine-issue` - 2026-08-05T06:04:25 - `38c9c078-62da-4c36-ab36-273e083c87b5.jsonl`
- `/ll:confidence-check` - 2026-08-05T02:22:34 - `20781823-2973-4b25-9054-bebe6629d257.jsonl`
- `/ll:confidence-check` - 2026-08-05T01:56:50 - `6569bf0b-4efa-4bb9-8b85-a0e909af608e.jsonl`
- `/ll:wire-issue` - 2026-08-05T01:49:15 - `2c309fa5-8c43-401a-82fc-22975e2f2e35.jsonl`
- `/ll:decide-issue` - 2026-08-05T01:40:16 - `f80f4891-ce9f-494e-aa23-5cc25bc1524e.jsonl`
- `/ll:refine-issue` - 2026-08-05T01:31:24 - `42ca0c4a-7282-4fbe-9b00-3b9e16ffcd31.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-05T00:25:09 - `b9710cb8-1d2b-4d04-8cf1-ad93d3cfccb7.jsonl`
- `/ll:capture-issue` - 2026-08-04T20:50:28 - `2a9240a9-e6df-4ed5-ad2a-73a280bc7d8b.jsonl`
