---
id: ENH-3047
title: 'confidence-check: consume unverified-claim and missing-parity gaps as Criterion
  4 deductions'
type: ENH
priority: P2
status: done
discovered_by: capture-issue
discovered_date: 2026-08-04
captured_at: '2026-08-04T20:47:11Z'
completed_at: '2026-08-05T18:25:42Z'
relates_to:
- FEAT-3048
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

> **Rescoped 2026-08-05 (review pass).** Both dependencies have now landed, so this ships as a
> single stage — the earlier stage 1 / stage 2 split is gone. The claim signal is wired as a
> **soft cap, not a hard override**: a measured sweep found it would `STOP` 51% of the active
> backlog, largely on forward-looking design claims. See § Blast Radius and § Why Claims Are a
> Cap, Not an Override.

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
- **Superseded 2026-08-05 (review pass) — FEAT-3048 has since landed** (commit `6477b4db`, status
  `done`). The "no precedent for defensively reading a not-yet-emitted key" concern is now moot for
  all three keys. `stale_symbol_ref` and `stale_cli_flag` are live `list[str]` fields on `FormatGaps`
  (`scripts/little_loops/issue_parser.py:264-265`), mirrored in `has_gaps` (`:289-290`) and
  `to_dict()` (`:314-315`), and documented (`docs/reference/CLI.md:1872`, `:1924-1931`, JSON example
  at `:1984`; `docs/reference/API.md:864`, `:883-884`). All three keys are schema-present today, so
  the only fail-open shape that exists is **present-but-empty**, and this issue ships as one stage.
- **Both claim keys are populated unconditionally by the CLI.** `check_format_gaps()` only reports
  them when given `symbol_index`/`cli_index`, but `cmd_format_check` builds both eagerly
  (`scripts/little_loops/cli/issues/format_check.py:265-266`) and threads them into every call site,
  so a plain `ll-issues format-check <ID> --format json` always carries them. No flag is required.
  It also means the call now costs **~5.3s wall / ~19s CPU** — see Integration Map § Cost.

## Expected Behavior

A new Phase 1.8 block reads three gap keys out of the `format-check --format json` payload that
Phase 1.6 already fetches (see Integration Map § Coordination for the block shape and § Cost for
why the payload is fetched once, not twice):

- missing behavior parity (`missing_behavior_parity` — shipped by ENH-3045)
- unverified claims (`stale_symbol_ref` + `stale_cli_flag` — shipped by FEAT-3048)

Both signals are wired to the **same** mechanism: a Criterion 4 cap. Neither forces
`STOP — ADDRESS GAPS`.

- **Parity → cap at 10.** A missing `### Behavior Parity` subsection means the issue may have
  under-described what it replaces. That is a specification weakness, not an unimplementable issue.
- **Claims → cap at 10.** A `stale_symbol_ref`/`stale_cli_flag` gap means the issue asserts
  something about the codebase that did not resolve. That is strong evidence of a specification
  problem and belongs in the score — but it is not reliable enough to gate on. See § Why Claims
  Are a Cap, Not an Override.

Both fail open on the present-but-empty shape: all three keys are schema-present, so an issue with
no gaps yields empty strings, the cap rows are unreachable, and the score is exactly what it is
today.

### Why Claims Are a Cap, Not an Override

_Added 2026-08-05 (review pass). This reverses the original design, which routed claims to a Phase
3 hard override following the Learning Test / Program Design shape._

The original reasoning was: "a false claim about the implementation surface is not a well-specified
issue at any score." That premise assumes a detector precision `stale_symbol_ref` does not have on
forward-looking issues.

`symbol_claims.py` extracts claims from the **entire issue body**, with no section scoping — its
`_SENTENCE_BOUNDARY_RE` / `_MAX_ATTRIBUTION_DISTANCE` grammar controls false positives *within* a
sentence, but nothing excludes `## Program Design § Signatures`, `### Files to Modify`, or
`## Implementation Steps`. Those sections exist precisely to name symbols the issue will **create**.
A symbol that does not resolve yet is the expected state there, not a defect.

Measured consequence — sweep of all 72 active issues via
`ll-issues format-check --all --format json`:

| Gap | Issues | % of active |
|---|---|---|
| `missing_behavior_parity` | 1 | 1% |
| `stale_symbol_ref` | 33 | 46% |
| `stale_cli_flag` | 7 | 10% |
| **either claim key (would have hard-stopped)** | **37** | **51%** |

Spot-checking confirms the forward-reference failure mode dominates:

- **FEAT-2942** (this issue's own motivating example) reports 8 claim gaps. Two of them:
  `add_epic_consistency_parser` and `cmd_epic_consistency`, both "claimed in
  `scripts/little_loops/cli/issues/__init__.py`" — and both are functions FEAT-2942 proposes to
  *add*, not ones it claims already exist.
- **ENH-3047 itself** reports two, both false:
  `design_gate_failed`, attributed to `check_design.py` because that is the nearby file this issue
  cites, when it is genuinely defined in `program_design.py` and merely *called* there; and
  `missing_behavior_parity`, a `FormatGaps` field name this issue says the new test will assert on
  — a data key, not a def-site.

  These two false positives no longer trip the gate as of BUG-3063 (A1 scoping excludes
  `## Expected Behavior`, where this section lives, from claim extraction entirely) — the
  `<!-- ll-prose-ok -->` markers previously here are no longer needed.

The better an issue's Program Design section, the more likely a hard override fires. That inverts
Criterion 4's intent. Capping the criterion still moves the score in the right direction while
leaving the decision with the reviewer, and it degrades gracefully under a noisy detector in a way
a `STOP` does not.

**Follow-up owed:** the false-positive class above is FEAT-3048's to fix — either scope extraction
away from design/planning sections, or add a forward-reference discriminator. Revisit the hard
override only once that lands and the false-positive rate is re-measured. `stale_cli_flag` (10%,
and "no such subcommand" is a much sharper signal than an unresolved symbol) is the more defensible
future override candidate of the two.

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

**Dependency (resolved 2026-08-05):** this issue was captured as hard-`blocked_by: [FEAT-3048]`
on the reasoning that "without it there is nothing to read," then relaxed to `depends_on` when
ENH-3045 landed, with the work split into two stages. **Both dependencies have now landed**
(ENH-3045, and FEAT-3048 at commit `6477b4db`), so the edge is a plain `relates_to` and the stage
split is removed — this ships as one change reading all three keys from one payload.

### Deduction Rows (resolves the open Option A row-authoring gap)

`/ll:decide-issue` settled the table *shape* (Option A — inline rows in Criterion 4's existing
`Finding | Score` table) but not the row *content*, which is what Option B's critique had
objected to ("would require inventing prose bands"). Resolved here so implementation does not
re-litigate it. Criterion 4's table becomes:

| Finding | Score |
|---------|-------|
| Clear acceptance criteria, specific files, defined scope; no parity or claim gaps | 20 |
| Most details present, 1-2 minor gaps fillable from context; no parity or claim gaps | 15 |
| Any `missing_behavior_parity`, `stale_symbol_ref`, or `stale_cli_flag` gap (cap — apply regardless of otherwise-higher row) | 10 |
| Key details missing but inferrable from codebase research | 10 |
| Vague requirements, significant guesswork needed | 0 |

Both gap kinds share one cap row rather than getting a row each: they carry the same weight and the
same direction, and a single row keeps the table at five rows instead of six.

The cap is a **ceiling, never a floor**: it lowers an otherwise-higher row to 10 and never raises a
lower one (an issue that would score 0 on "vague requirements" still scores 0 with a parity gap).
It preserves the table's absolute-value convention (the one Option A property Option B challenged)
while still expressing a count-driven signal.

_Revised 2026-08-05 (review pass): the original six-row version scored claim gaps 0 and routed them
to a Phase 3 hard override. Both are removed — see Expected Behavior § Why Claims Are a Cap, Not an
Override._

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

**In scope:** a new Phase 1.8 block reading three existing `format-check` gap keys out of the
payload Phase 1.6 already fetches, one Criterion 4 table revision in `rubric.md`, the matching test
class, and regenerating the two adapter mirrors.

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
- The Dependencies hard override — that is BUG-3051's scope, not this issue's.
- **Any Phase 3 hard override.** Removed from scope 2026-08-05; `SKILL.md`'s Phase 3 block is now
  untouched by this issue. See Expected Behavior § Why Claims Are a Cap, Not an Override.
- **Reducing `stale_symbol_ref`'s forward-reference false positives.** That is FEAT-3048's
  detector, not this consumer. This issue absorbs the current noise level by capping rather than
  gating; the fix is the follow-up named in that same section.

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — new Phase 1.8 block, plus a one-line change to Phase 1.6 so
  the `format-check` payload is captured once and shared (see § Cost). Phase 3 is **not** modified
  (441 lines total; three hard overrides live at `:336-340` as of BUG-3051 and stay as they are)
- `skills/confidence-check/rubric.md` — Criterion 4 deduction table (`:236-243` today)
- `scripts/tests/test_confidence_check_skill.py` — scoring assertions for the deduction path

### Cost: fetch the payload once, not twice

_Added 2026-08-05 (review pass)._

FEAT-3048 made `ll-issues format-check <ID> --format json` substantially more expensive: it now
builds a repo-wide symbol index (`build_symbol_index`) and scrapes every `ll-*` tool's `--help` to
build a CLI surface index (`build_cli_surface_index`), both unconditionally at
`format_check.py:265-266`. Measured on this repo: **~5.3s wall, ~19s CPU** for a single issue.

Phase 1.6 already pays that once. A Phase 1.8 block issuing its own `format-check` call would pay
it a **second** time — ~11s per `/ll:confidence-check` run — to re-parse a byte-identical payload.

So Phase 1.8 must **not** call `format-check` itself. Capture the JSON once in Phase 1.6 into a
shell variable and have both phases extract from it:

```bash
FC_JSON=$(ll-issues format-check {{issue_id}} --format json 2>/dev/null || true)
```

Phase 1.6's `PD_GAP` and Phase 1.8's `PARITY_GAP` / `CLAIM_GAP` then each pipe `$FC_JSON` into
their own one-line `python -c` extraction, preserving the per-call `2>/dev/null || true`
fail-open tail on each. `PD_FAIL` is unaffected — `ll-issues check-design` calls
`check_format_gaps()` directly without either index (`check_design.py:38`), so it stays cheap and
keeps its own invocation.

Note this diverges from Phase 1.7's precedent in one respect: Phase 1.7 is a self-contained block
because `ll-issues show` is cheap and unrelated to `format-check`. The separate-block *structure*
is still the precedent to follow (see § Coordination); the separate *invocation* is not.

### Similar Patterns
- `ENH-2852` / `ENH-2967` — Program Design gate pre-fetch and its `check-design` CLI owner;
  the exact shape to copy for the pre-fetch (though **not** for CLI ownership — see Program
  Design § Signatures)
- `ENH-2946` — confidence-check already consuming `format-check` output

### Coordination: BUG-3051 (landed 2026-08-05 — resolved)

`BUG-3051` **has landed** (commit `5cfaf967`). The anticipated edit collision is resolved in its
favor: this issue is the one that rebases. Concretely, as of that commit:

- Phase 3 now carries **three** overrides at `skills/confidence-check/SKILL.md:336`, `:338`, `:340`
  (Learning Test, Program Design, Dependencies) — not lines ~300-306 as originally written, and not
  four as an earlier revision of this bullet miscounted. **This issue no longer edits Phase 3 at
  all** (review pass, 2026-08-05), so the collision this section anticipated cannot occur.
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
  `docs/reference/API.md:862`/`:878`. No CLI.md change is needed for parity.
- **Resolved 2026-08-05 (review pass):** the residual note — that `stale_symbol_ref`/`stale_cli_flag`
  were FEAT-3048's obligation to document, with Phase 1.8 the first consumer to break if skipped —
  is discharged. FEAT-3048 documented both: `CLI.md:1872` (now "twenty classes"), `:1924-1931`
  (description), `:1984` (JSON example), `API.md:864` and `:883-884`. **This issue needs no
  documentation changes at all** [Agent 2 finding, closed]

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
  **441 lines** (`wc -l`, re-verified 2026-08-05 on `main` — the wire-issue pass's "442, off-by-one
  in AC6" note was itself the off-by-one and is withdrawn), leaving ~59 lines of headroom. With the
  Phase 3 override dropped from scope, Phase 1.8 is the only addition and the gate is not close
  [Agent 3 finding, corrected].

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
- **Phase 3 override paragraph template (pattern-finder, new detail).** Each hard-override paragraph follows: condition ("if Phase 1.N set X to ...") → consequence ("`STOP — ADDRESS GAPS` regardless of aggregate score") → what to list under **Gaps to Address** → remedy sentence → inert-condition sentence. Learning Test's override (`SKILL.md:336`) is terser and skips the last two parts; Program Design (`:338`) and Dependencies (`:340`) both have all four, and Dependencies additionally closes by tying back to its Criterion's existing 0-20 scoring ("This is additive to Criterion 5's existing 0-20 scoring, which is unchanged for the non-blocking case"). _Superseded 2026-08-05 (review pass): this finding described the template for an Unverified Claim override that is no longer in scope. Retained only as reference for the future revisit noted in § Why Claims Are a Cap, Not an Override._
- **Test-class convention (pattern-finder, new detail beyond the existing Tests § pointer to `TestConfidenceCheckDependenciesPrefetch`).** The codebase keeps a SKILL.md-phase test class and a rubric.md-override test class separate rather than combined (`test_confidence_check_skill.py:432`, `:489`). Both use a private `_phase_text(self, heading)` helper, but the slice boundary differs by file: SKILL.md slicing stops at the next `\n###` heading (`:435-440`, matching `TestConfidenceCheckPhase4CLI._phase_text` at `:15-20`), while the rubric.md override test slices from the Criterion heading to the next `\n---` divider instead (`:493-496`) — using the SKILL.md-style `\n###` boundary on rubric.md would silently include unrelated Criterion sections. Every individual `test_*` assertion message across both classes ends with the issue ID in parens, e.g. `"... (BUG-3051)"` (`:445`, `:451`, `:457`, `:463`, `:469`, `:477`, `:485`, `:498`).
- **Rubric/SKILL pairing convention (pattern-finder, new detail).** Criterion 5's rubric table (`rubric.md:245-252`) is immediately followed, with no divider, by a `**Dependencies Hard Override** (BUG-3051):` paragraph inside the same `### Criterion 5` section (`rubric.md:254-259`) that cross-references "see SKILL.md Phase 3" rather than duplicating the STOP instruction in full — this is the second rubric.md precedent (alongside the Program Design § Signatures note already in this issue) for where stage 2's Criterion 4 override language could live if a rubric-side pointer is wanted.

### Conventions in Force

- Rubric deduction tables are one `###`-level table per criterion/gate, `Finding | Score` (absolute point value), not a delta — evidence: 5 of 6 tables in `skills/confidence-check/rubric.md` "Phase 2 — Readiness Scoring Tables" (lines 176-252), including the existing `### Criterion 4: Issue Well-Specified` table this issue targets (lines 236-243).
- One documented exception exists: gate-driven modifiers use a different `Target Status | Score Modifier | Action` shape, signed delta applied "on top of" the base criterion rather than folded into its Finding/Score rows — evidence: "Learning Test Status Scoring (Criterion 1 Modifier)" table, `rubric.md` lines 161-172.
- Phase 3 hard overrides are named bolded paragraphs ("**X Hard Override**") placed before score summation, gated on a Phase-1.6-set variable being non-empty/non-zero, forcing `STOP — ADDRESS GAPS` "regardless of aggregate score" — evidence: Learning Test Hard Override and Program Design Hard Override, `skills/confidence-check/SKILL.md` "Phase 3: Score and Recommend" lines 300-306. This is the pattern the issue's Expected Behavior cites for "nonzero unverified-claim count as a readiness blocker."
- `format-check --format json` keys are referenced two ways in this codebase, both established: inline bash/python extraction into shell variables (confidence-check's Phase 1.6), and pure markdown prose naming the key plus its non-empty/nonzero condition with no code shown (`commands/refine-issue.md` Step 6.7, lines 781-831, for `prose_dep_drift`/`stale_prose_dep`/`program_design_nonspecific`/`superseded_marker_count`/`duplicate_findings_block`).
<!-- ll-prose-ok: quoted docstring; design_gate_failed is defined in issue_parser.py, not the cited check_design.py -->
- `check_design.py`'s `cmd_check_design` is the CLI-owner precedent named in this issue's "Similar Patterns" — its docstring states it is the "single CLI owner of the `design_gate_failed()` predicate, replacing the three independent inline `python3 -c "..."` blocks in autodev.yaml that each re-derived the same boolean from raw `format-check --format json` output," and that it "fails open (exit 0) on projects that haven't armed the ... gate, mirroring `check_format_gaps()`'s existing fail-open behavior."

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

- **Line-citation corrections (re-verified 2026-08-05, post ENH-3046/BUG-3059):** `FormatGaps` (`scripts/little_loops/issue_parser.py:236`) now has **18** `list[str]` gap-kind fields, not 16 — `soft_dep_hard_edge` (ENH-3046) and `malformed_dep_id` (BUG-3059) landed after this issue's Types section was written. `stale_symbol_ref`/`stale_cli_flag` remain correctly absent. The `missing_behavior_parity` mention in `has_gaps` is at `issue_parser.py:282` (not `:280`); its `to_dict()` entry is at `:305` (not `:301`, which is now the unrelated `stale_file_ref` entry). `docs/reference/CLI.md:1872` itself now says "eighteen classes."
- `cmd_format_check`'s actual location is `scripts/little_loops/cli/issues/format_check.py:182` — all prior citations in this issue (`:163`, `:165`, `:178`) are stale.
- Additional rubric.md precedent for the table-shape decision (does not change the already-decided Option A): Criterion 5 (`rubric.md:245-259`) already pairs a plain two-column base table (`:249-252`) with a named "**Dependencies Hard Override** (BUG-3051)" prose paragraph directly beneath it in the same `### Criterion N` section (`:254-259`) — a second precedent, alongside SKILL.md's Phase 3 override paragraphs, for where Criterion 4's own override language could live if stage 2 needs a rubric-side pointer.

### Types

- `FormatGaps` (`scripts/little_loops/issue_parser.py:236`) — the dataclass all `format-check` JSON/text consumers key off; **20** `list[str]` gap-kind fields as of FEAT-3048, each mirrored in `has_gaps` and `to_dict()`. All three keys this issue reads are present and need no schema work: `missing_behavior_parity` (`:261`), `stale_symbol_ref` (`:264`), `stale_cli_flag` (`:265`). _(Re-verified 2026-08-05 review pass. Earlier revisions of this bullet said all three keys were absent, then that two were; both are now stale — treat `dataclasses.fields(FormatGaps)` as authoritative over any count written here, per CLI.md's own instruction.)_
- `PD_GAP: str` / `PD_FAIL: str` — the two shell-variable shapes Phase 1.6 currently populates from `format-check`/`check-design` output (`skills/confidence-check/SKILL.md:132-150`): a joined reason-string (`PD_GAP`, from a `list[str]` JSON key) and a separate pass/fail verdict (`PD_FAIL`, `""` or `"yes"`, from a dedicated CLI's exit code rather than re-derived from JSON).

### Signatures

- `program_design_gate_active(issue_path: Path, content: str) -> bool`

  `scripts/little_loops/issues/program_design.py:415` — the activation-gating pattern (unstamped project / grandfathered / `*_not_applicable: true` frontmatter all return `False`) that the Program Design gate uses to fail open; a parity/claim equivalent, if the CLI layer needs one, would follow this same shape.
- `cmd_format_check() -> None`

  `scripts/little_loops/cli/issues/format_check.py:182` — the JSON-serialization entry point (`gaps.to_dict()` via `check_format_gaps()`). All three keys are already threaded through it; it builds `symbol_index` and `cli_index` eagerly at `:265-266` and passes them to every `check_format_gaps()` call site, so no work is owed here. _(All earlier `:163`/`:165`/`:178` citations were stale.)_
<!-- ll-prose-ok: design_gate_failed is defined in issue_parser.py, not the cited check_design.py -->
- `cmd_check_design` (`scripts/little_loops/cli/issues/check_design.py`) — sole CLI owner of the `design_gate_failed()` boolean predicate, which is itself defined in `scripts/little_loops/issue_parser.py:319` (not `issues/program_design.py`, contrary to an earlier revision of this bullet).

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

`skills/confidence-check/SKILL.md` Phase 1.6 bash block -> `ll-issues format-check {{issue_id}} --format json` (**one** invocation, captured into `FC_JSON` — see Integration Map § Cost) -> `cmd_format_check()` (`format_check.py:178`) -> `check_format_gaps()` with `symbol_index`/`cli_index` (`issue_parser.py`) -> `FormatGaps.to_dict()` -> `$FC_JSON` re-read by the Phase 1.8 block's inline `python -c` -> stored in `PARITY_GAP` / `CLAIM_GAP` -> read by `rubric.md`'s Criterion 4 cap row. Phase 3 is not on this path.

## Implementation Steps

_Single stage as of the 2026-08-05 review pass — both dependencies have landed._

1. In `SKILL.md` Phase 1.6, hoist the `format-check` invocation into `FC_JSON` and rewrite the
   existing `PD_GAP` line to extract from `$FC_JSON` instead of re-invoking. Leave `PD_FAIL`
   (`ll-issues check-design`) alone. See Integration Map § Cost.
2. Add a new `### Phase 1.8: Pre-Fetch Claim and Parity Gaps (ENH-3047)` block to `SKILL.md`,
   immediately after Phase 1.7, populating from `$FC_JSON`:
   - `PARITY_GAP` — `.get('missing_behavior_parity', [])` joined with `; `
   - `CLAIM_GAP` — `.get('stale_symbol_ref', []) + .get('stale_cli_flag', [])` joined with `; `

   Same extraction shape as the existing `PD_GAP` line, including the `2>/dev/null || true`
   fail-open tail on each, and the `<!-- ll-prose-ok: ... -->` annotation naming the Phase 1.6
   idiom it copies (Phase 1.7's convention). Do **not** extend Phase 1.6's block itself (see
   Integration Map § Coordination) and do **not** issue a second `format-check` call.
3. Close the block with the three-part prose the Phase 1.6/1.7 precedent requires: what each
   variable means, when it is empty/inert, and an explicit "do not re-judge claims yourself, the
   CLI is the source of truth" instruction. Add a fourth sentence here that the other blocks do
   not need: `CLAIM_GAP` is **advisory input to Criterion 4 only** — it caps the criterion and
   must not be escalated to a `STOP` verdict, because forward-looking design claims legitimately
   do not resolve (cross-reference Expected Behavior § Why Claims Are a Cap, Not an Override).
4. Revise the Criterion 4 table in `rubric.md` (`:236-243`) to the five rows specified in
   Proposed Solution § Deduction Rows, including the shared cap row.
5. Add the new test class to `scripts/tests/test_confidence_check_skill.py` (structural slice,
   per the wiring note below).
6. Regenerate both adapter mirrors.
7. File the FEAT-3048 follow-up for the forward-reference false-positive class (Expected Behavior
   § Why Claims Are a Cap, Not an Override), so the hard-override question can be revisited on
   evidence rather than dropped.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add a new test class to `scripts/tests/test_confidence_check_skill.py` covering Phase 1.8's
  gap-field parsing and Criterion 4's new deduction rows, following the
  `TestConfidenceCheckDependenciesPrefetch` structural-slice pattern (BUG-3051)
- Regenerate the generated adapter mirrors — `ll-adapt --host kimi-code --apply` and
  `ll-adapt --host gemini --apply` — after editing `skills/confidence-check/SKILL.md`, so
  `.kimi-code/skills/confidence-check/SKILL.md` and `.gemini/skills/confidence-check/SKILL.md`
  stay in sync
- ~~Update `docs/reference/CLI.md`'s gap-class enumeration and JSON example to include the new gap
  keys once they exist~~ — **discharged 2026-08-05**: ENH-3045 and FEAT-3048 each documented their
  own keys. This issue owes no documentation change (see § Documentation).

## Acceptance Criteria

1. A `format-check --format json` payload with a non-empty `missing_behavior_parity`,
   `stale_symbol_ref`, or `stale_cli_flag` list caps that issue's Criterion 4 score at 10.
2. Fail-open. All three keys are schema-present, so the only shape is **present-but-empty**: an
   issue with no gaps yields empty `PARITY_GAP` and `CLAIM_GAP`, the cap row is unreachable, and
   scoring is identical to today — no error, no stderr output, no score change.

   _Revised 2026-08-05: the former "absent key" case is deleted. It described the pre-FEAT-3048
   world and is now unreachable and untestable._
3. **No `STOP` from either signal.** A non-empty `CLAIM_GAP` caps Criterion 4 and appears under
   **Gaps to Address** as an advisory line, but does not change the PROCEED/CAUTION/STOP verdict
   on its own. Concretely: an issue whose only gap is `stale_symbol_ref` and which would otherwise
   score above the readiness threshold must still come back as PROCEED (with a reduced score), not
   `STOP — ADDRESS GAPS`.
4. `scripts/tests/test_confidence_check_skill.py` gains a test class asserting that the sliced
   `### Phase 1.8:` block names all three gap keys, that the sliced Criterion 4 table contains the
   cap row, and that the sliced Phase 3 block does **not** name `CLAIM_GAP` (the regression guard
   for AC3); `python -m pytest scripts/tests/` exits 0.
   _Slice `SKILL.md` to the next `\n###` and `rubric.md` to the next `\n---`, per the
   `TestConfidenceCheckDependenciesPrefetch` / `TestConfidenceCheckRubricDependenciesOverride`
   convention, and end each assertion message with `(ENH-3047)`._
5. `.kimi-code/skills/confidence-check/SKILL.md` and `.gemini/skills/confidence-check/SKILL.md`
   match a fresh `ll-adapt --host <host> --apply` run — no drift.

   _Note (2026-08-05): both mirrors are **already drifted** — neither contains BUG-3051's Phase
   1.7. The regen this issue performs will therefore also carry BUG-3051's content into the
   mirrors. That is correct, but expect a larger mirror diff than this issue's own edits._
6. `skills/confidence-check/SKILL.md` stays under the 500-line cap enforced by `ll-verify-skills`
   (concretely `scripts/tests/test_skill_size_checker.py::TestSkillLineLimit::test_all_skills_within_limit`).
   **441** lines today, re-verified by `wc -l` on `main` 2026-08-05; Phase 1.8 adds roughly 12,
   landing near 453. Comfortable margin now that the Phase 3 override is out of scope, but keep
   the Phase 1.8 prose tight and push explanatory detail to `rubric.md` regardless.
7. **End-to-end validation fixture.** Re-running `/ll:confidence-check` on an issue with a
   `missing_behavior_parity` gap reports **Criterion 4 = 10** and reproduces the parity reason
   string under **Gaps to Address**. Record which issue was used.

   _Rewritten 2026-08-05 — the original wording ("scores at or below 85 readiness") is
   unfalsifiable with the only available fixture. `FEAT-2787` is the sole parity carrier
   (`missing_behavior_parity: ['scripts/little_loops/adapters/omp.py']`) and already scores
   **56 readiness**, so a ≤85 assertion passes whether or not the cap fires. The criterion-level
   assertion above is the one with signal. If a fixture that would otherwise score >85 is wanted,
   construct a synthetic issue rather than hunting the backlog._

8. **Claim-path validation fixture.** Re-running `/ll:confidence-check` on an issue with a
   `stale_symbol_ref` gap reports **Criterion 4 = 10** and a **PROCEED or PROCEED WITH CAUTION**
   verdict — not `STOP` — with the claim reason strings listed advisorily under **Gaps to
   Address**. Record which issue was used.

   _Note (2026-08-05): `FEAT-2942`, the Summary's motivating example, is a poor fixture here. Its
   8 claim gaps are dominated by forward references to functions it proposes to create
   (`add_epic_consistency_parser`, `cmd_epic_consistency`, `synthesize_clusters`), which is
   exactly the false-positive class § Why Claims Are a Cap documents. It does demonstrate the
   no-`STOP` requirement well — it is 93/76 today and must not drop to `STOP` — so use it for
   AC8 while treating its gap list as noise, not as validation that detection works._

   **Verified 2026-08-05 (implementation pass).** Ran the exact Phase 1.6/1.8 bash (with the
   shipped `FC_JSON`/`PARITY_GAP`/`CLAIM_GAP` extraction) against live `format-check` output for
   both fixtures, since the `Skill` tool's in-session cache of `SKILL.md` predates this session's
   edits and a literal skill re-invocation would score against stale Phase 1.6/1.8 logic rather
   than what shipped:
   - **FEAT-2787** (AC7 parity fixture): `PARITY_GAP = "scripts/little_loops/adapters/omp.py"`
     (non-empty) → Criterion 4 caps at 10 per the rubric.md cap row. It also carries a non-empty
     `CLAIM_GAP` (5 stale symbol refs), which caps the same criterion via the same row — no
     double-penalty since the cap is a ceiling, not additive.
   - **FEAT-2942** (AC8 claim fixture): `PARITY_GAP = ""`, `CLAIM_GAP` non-empty (8 entries,
     matching the Summary's motivating example) → Criterion 4 caps at 10. Phase 3 has no
     `CLAIM_GAP`-keyed override (confirmed by
     `TestConfidenceCheckClaimParityPrefetch::test_phase_3_does_not_name_claim_gap`), so the
     aggregate score changes (Criterion 4 drops from whatever it scored before to 10) but the
     verdict tier is driven by the aggregate, not forced to `STOP` — satisfying AC3/AC8's
     no-`STOP` requirement.

## Impact

- **Priority**: P3 — fully unblocked; both ENH-3045 and FEAT-3048 have landed
- **Effort**: Low — prompt/rubric wiring on an existing pre-fetch
- **Risk**: **Medium**, raised from Low on 2026-08-05. Still a scoring-only change with no code
  path, but it re-scores half the active backlog downward, and that score is consumed by
  `/ll:go-no-go`, `ll-auto`, and sprint selection. The risk is concentrated in the claim signal's
  false-positive rate, which is why it caps rather than gates.
- **Blast radius (re-measured 2026-08-05 via `ll-issues format-check --all --format json`,
  72 active issues)**:

  | Gap | Issues | % |
  |---|---|---|
  | `missing_behavior_parity` | 1 (`FEAT-2787`) | 1% |
  | `stale_symbol_ref` | 33 | 46% |
  | `stale_cli_flag` | 7 | 10% |
  | **any → Criterion 4 capped at 10** | **37** | **51%** |

  This supersedes both the original "10 of 170 (6%)" figure and the 2026-08-05 "1 of 65 (1.5%)"
  correction — **each measured parity only**, the latter because FEAT-3048 had not landed at the
  time. The parity cap really is near-inert against today's backlog (1 issue). The claim cap is
  not: it costs 37 issues up to 10 Criterion 4 points, i.e. up to 10 readiness points each.

  Whether that is a re-scoring event worth absorbing depends on the follow-up: if FEAT-3048's
  forward-reference false positives are fixed, the 46% should fall substantially and the
  remaining hits are genuine. Shipping the cap now is still net-positive — a capped score is
  recoverable and visible, and it surfaces the false-positive rate as a measurable signal — but
  do not treat the 51% as a steady-state expectation.

  The cap value (10 vs. a softer 15) now *does* have empirical consequence at this volume. Keep
  10: a 5-point difference across 37 issues is not worth a second round of re-scoring once the
  detector improves, and 10 matches the parity row it shares.

## Related Key Documentation

- `.claude/CLAUDE.md` — confidence gate thresholds in `.ll/ll-config.json`
  (`commands.confidence_gate`: readiness 85, outcome 65)
- `docs/reference/COMMANDS.md` — `/ll:confidence-check`

## Status

**Open** | Created: 2026-08-04 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-04_

> **Stale as of 2026-08-05 — re-run before implementing.** All three recorded concerns are now
> resolved: the `FEAT-3048` blocker has **landed** (commit `6477b4db`), so the dependency edge is
> gone entirely and Criterion 5 no longer scores 0; the open `check-claims` CLI decision was
> resolved (no new CLI); and the missing Scope Boundaries section was added. The 75 readiness
> score below predates all three and understates current readiness.
>
> Note the design has also changed materially since this run: the claim signal is now a Criterion 4
> cap rather than a Phase 3 hard override, and the second listed Outcome Risk Factor ("test
> coverage can only be structurally slice-tested until FEAT-3048's gap kinds actually exist") no
> longer applies.

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
- `/ll:manage-issue` - 2026-08-05T18:25:22 - `eb9eaf26-0b22-40bb-b5f6-1c9e4c21208b.jsonl`
- `/ll:ready-issue` - 2026-08-05T18:02:54 - `6bc27eb1-e57d-4d36-bf3d-51921c3bfa9b.jsonl`
- `/ll:confidence-check` - 2026-08-05T17:55:18 - `5e23105c-4eb4-4528-b7fe-55b105cf37c3.jsonl`
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
