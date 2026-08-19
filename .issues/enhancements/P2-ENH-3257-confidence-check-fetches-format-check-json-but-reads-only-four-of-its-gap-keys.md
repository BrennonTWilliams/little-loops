---
id: ENH-3257
type: ENH
title: confidence-check fetches format-check JSON but reads only four of its gap keys
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-18'
captured_at: '2026-08-18T20:48:37Z'
completed_at: '2026-08-19T03:34:31Z'
parent: EPIC-2856
testable: true
relates_to:
- BUG-3249
- ENH-3256
- ENH-3248
- ENH-3247
- ENH-3047
- ENH-2852
confidence_score: 100
outcome_confidence: 95
score_complexity: 24
score_test_coverage: 23
score_ambiguity: 24
score_change_surface: 24
---

# ENH-3257: confidence-check fetches format-check JSON but reads only four of its gap keys

## Summary

`/ll:confidence-check` Phase 1.6 fetches the complete `format-check` JSON payload
once (`skills/confidence-check/SKILL.md:138`) and reuses it in Phase 1.8 rather
than re-invoking the CLI. Between the two phases it extracts exactly four keys:

| Phase | Key | Effect |
|---|---|---|
| 1.6 | `program_design_nonspecific` | `PD_GAP` display detail |
| 1.6 | (`ll-issues check-design` exit) | `PD_FAIL` — can force STOP |
| 1.8 | `missing_behavior_parity` | `PARITY_GAP` |
| 1.8 | `stale_symbol_ref` + `stale_cli_flag` | `CLAIM_GAP` — advisory only, explicitly cannot escalate to STOP (`:204-207`) |

`template_placeholders`, `boilerplate`, and `missing` are never read — grep
across the whole `skills/confidence-check/` directory returns no hits. The
payload containing them is already in `$FC_JSON`; the data is fetched and
discarded.

Observed on BUG-3249, which scored `confidence_score: 100` /
`outcome_confidence: 99` while `ll-issues format-check BUG-3249` reported:

```
  missing: Steps to Reproduce
  boilerplate: Impact
  template_placeholders: Motivation: [Why this issue matters - business value, ...]
  template_placeholders: Impact: [P0-P5]
  template_placeholders: Impact: [Justification]
  template_placeholders: Impact: [Small/Medium/Large]
  template_placeholders: Impact: [Low/Medium/High]
  template_placeholders: Impact: [Yes/No]
```

The sibling loop already treats one of these as routable: ENH-3248 added a
`check_placeholders` state (`scripts/little_loops/loops/refine-to-ready-issue.yaml:371-396`)
that reads `template_placeholders` via `--format json` and forces a refine. That
signal is gated in the *loop* but not in the *skill*, so a standalone
`/ll:confidence-check` sails past debris the loop would bounce.

Proposed direction: extract `template_placeholders` / `boilerplate` / `missing`
from the already-captured `$FC_JSON` in Phase 1.8 and feed them as a cap on
Criterion 4, mirroring exactly how `CLAIM_GAP` works today (advisory cap, not a
STOP escalation). No new CLI call and no re-derived predicate — `format-check`
stays the single source of truth.

Related: BUG-3249 (the instance), ENH-3248 (`check_placeholders`, the loop-side
precedent), ENH-3247 (`format-check --fix` repairing structural debris),
ENH-2852 (built the Phase 1.6 pre-fetch gate this extends), ENH-3047 (added the
Phase 1.8 keys, the pattern to follow).


## Current Behavior

Phase 1.6 captures the full `format-check` payload into `$FC_JSON` and Phase 1.8
reuses it, but between them only four keys are read
(`program_design_nonspecific`, `missing_behavior_parity`, `stale_symbol_ref`,
`stale_cli_flag`). `template_placeholders`, `boilerplate`, and `missing` are
fetched and discarded, so an issue full of unfilled template debris can score
`confidence_score: 100`.

## Expected Behavior

Phase 1.8 extracts the structural-debris keys from the same `$FC_JSON` into a
`STRUCT_GAP` variable and `rubric.md` Criterion 4 caps at 10 when it is
non-empty — a ceiling, never a floor, never a Phase 3 `STOP` escalation. Only
directive-section `missing` entries participate (see Proposed Solution ›
Narrowing).

## Motivation

The data is already in memory; not reading it is a pure miss. `/ll:confidence-check`
is the gate before implementation, and an issue whose `## Summary` (or, for FEAT,
`## Acceptance Criteria`) section does not exist, or whose body still carries
unfilled `[bracketed template prompts]`, should not be able to score full marks
on "Issue Well-Specified."
The loop already bounces one of these signals (ENH-3248's `check_placeholders`),
so a standalone skill run is currently weaker than the same check inside a loop.

## Proposed Solution

Mirror the existing `CLAIM_GAP` idiom exactly (`skills/confidence-check/SKILL.md:187-207`,
`rubric.md:241-256`): extract the structural-debris keys from the already-captured
`$FC_JSON` in Phase 1.8 (no second `format-check` call), combine them into one
joined advisory variable — **named `STRUCT_GAP`** — the same way `CLAIM_GAP`
concatenates `stale_symbol_ref` + `stale_cli_flag`, and feed it into the
Criterion 4 cap in `rubric.md` alongside `PARITY_GAP`/`CLAIM_GAP` — a ceiling on
Criterion 4, never a Phase 3 `STOP` escalation.

### Narrowing: `missing` is filtered, not taken raw

Measured via `check_format_gaps()` over the **168 unresolved issues** in this repo
— `open` (74) + `in_progress`/`blocked` (3) + `deferred` (91). Note the
denominator: `deferred` issues are included because they re-enter the gate when
un-deferred. The strictly-open subset is only **77**; per-denominator rates are
given in both tables below, because the two differ enough to matter for this
issue's own success metric.

| key | issues firing (of 168 unresolved) |
|---|---|
| `template_placeholders` | 6 (3%) |
| `boilerplate` | 4 (2%) |
| `missing` (raw) | **102 (58%)** |
| any of the three | 106 (61%) |

Raw `missing` is dominated by ceremonial sections whose absence says nothing
about how well-specified an issue is — `Status` (63), `Current Behavior` (55),
`Impact` (39), `Scope Boundaries` (33), `Expected Behavior` (33), `Use Case` (23)
— versus the directive sections that actually gate implementation:
`Program Design` (10), `Acceptance Criteria` (5), `Summary` (5).

Taking `missing` raw would pin Criterion 4 at 10 for ~58% of the backlog because
an `## Impact` heading is absent, making the cap near-permanently on and
therefore uninformative. So `missing` is filtered to a directive allowlist:

```
{"Summary", "Acceptance Criteria"}
```

(Referred to below as *the directive allowlist*. It is an inlined `D={...}` set
literal inside the skill's `python -c` one-liner — **not** a Python constant, and
not a symbol to add to `issue_parser.py`; see Scope Boundaries.)

`template_placeholders` and `boilerplate` are taken unfiltered — at 3% and 2%
they are already rare and unambiguously mean "template debris left in place."

#### Why `template_placeholders` is unfiltered while `missing` is not

This asymmetry is deliberate and is the obvious objection to the design, so it is
stated explicitly: the BUG-3249 evidence quoted in the Summary is itself
dominated by *ceremonial*-section placeholders (`Motivation: [Why this issue
matters...]`, `Impact: [P0-P5]`) — the same sections the allowlist drops from
`missing`. So an unfilled `[P0-P5]` inside `## Impact` caps Criterion 4 while a
wholly absent `## Impact` heading does not.

The discriminator is authoring evidence, not section importance:

- An **unfilled placeholder** is positive proof the author instantiated the
  template and never edited that section — debris, regardless of which section
  carries it.
- An **absent optional heading** is frequently a deliberate authoring choice
  (nothing to say about `Impact` for a two-line doc fix), and at 58% raw it
  carries no signal.

The empirical rates back this: unfiltered `template_placeholders` costs 3%,
whereas unfiltered `missing` costs 58%.

#### Why only two entries (allowlist trimmed after measurement)

An earlier draft of this allowlist also carried `Program Design` and
`Implementation Steps`. Both were removed as dead or redundant, checked against
the real per-type required-section sets produced by `_required_sections()`
(`scripts/little_loops/issue_parser.py:338-348`):

| type | required sections |
|---|---|
| BUG | Current Behavior, Expected Behavior, Impact, Program Design, Status, Steps to Reproduce, Summary |
| FEAT | + Acceptance Criteria, Use Case |
| ENH | + Scope Boundaries |
| EPIC | Children, Goal, Impact, Scope, Status, Summary |

- **`Implementation Steps` is never a required section for any type**, so it can
  never appear in `missing`. Pure dead entry.
- **`Program Design` is always inert-or-redundant.** `_gate_program_design()`
  (`issue_parser.py:356-372`) drops it from `required` unless the project's
  cutover gate is armed *and* the issue is not grandfathered. When the gate *is*
  armed and the section is absent, `PD_FAIL` already fires — `"Program Design" in
  gaps.missing` is one of `check-design`'s three fail reasons
  (`issue_parser.py:585-591`) — and `PD_FAIL` is a Phase 3 **hard override
  forcing `STOP`**, strictly stronger than a Criterion 4 cap. So the entry either
  cannot fire or duplicates a STOP that already happened.

Re-measured against both denominators (re-verified 2026-08-18):

| allowlist | of 168 unresolved | of 77 strictly-open |
|---|---|---|
| 4-entry draft | 18 (10.7%) — of which **8 are `Program Design`-missing-only** | 13 (16.9%) |
| 2-entry final | **10 (6.0%)** | **6 (7.8%)** |

The trimmed allowlist roughly halves the firing rate on either denominator. Note
that on the strictly-open subset the 2-entry allowlist still fires at 7.8% —
above the ≤7% figure an earlier draft of this issue's Success Metrics asserted.
That threshold has been restated against the unresolved-issue denominator it was
actually measured on; see Success Metrics.

#### `Acceptance Criteria` is FEAT-only

Per the table above, `Acceptance Criteria` is a required section for **FEAT
only** — not BUG, ENH, or EPIC. A BUG or ENH with no `## Acceptance Criteria`
heading therefore does not contribute to `STRUCT_GAP`, by design: the template
does not require one. In practice the allowlist reduces to `Summary` for
non-FEAT issues. This is expected behavior, not a gap.

### Remedy differs per key

`ll-issues format-check --fix` (ENH-3247, completed) repairs `boilerplate` and
can insert `missing` sections structurally, but `template_placeholders` is
explicitly not auto-fixable — the CLI itself annotates those entries
`(literal template debris; no --fix, needs content)`. The `STRUCT_GAP` advisory
text under **Gaps to Address** should therefore say which entries `--fix`
resolves and which need authored content, rather than recommending `--fix`
uniformly.

All three fields are `list[str]` (`FormatGaps.to_dict()`,
`scripts/little_loops/issue_parser.py:546-573`), matching the shape the
existing `python -c "... '; '.join(...)"` extraction idiom already handles,
so no new parsing shape is needed.

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md:187-207` (Phase 1.8) — add the `STRUCT_GAP` extraction one-liner off the already-captured `$FC_JSON`, using the same `<!-- ll-prose-ok: mirrors the pre-existing PD_GAP idiom -->`-annotated convention used for `PARITY_GAP`/`CLAIM_GAP`; the `missing` allowlist filter lives inside this one-liner as a set intersection, so no `issue_parser.py` change is needed
- `skills/confidence-check/rubric.md:241-256` — extend the Criterion 4 "Parity/Claim Cap" row and its prose note to also apply when `STRUCT_GAP` is non-empty; rename the row to cover all three signals (e.g. "Parity/Claim/Structure Cap")

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/format_check.py` — `cmd_format_check()` already produces all three keys; no changes needed, confirmed no schema gap
- `scripts/little_loops/issue_parser.py:863` (`missing`), `:883-893` (`boilerplate`), `:1449-1500` `_template_placeholders()` (`template_placeholders`) — the three population sites; all already serialize into `FormatGaps.to_dict()` (`:546-573`) and require no changes for this issue
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:371-396` `check_placeholders` state — the ENH-3248 loop-side precedent; it re-invokes `format-check --format json` independently rather than sharing a cached `$FC_JSON` the way skill phases do, and gates on `len(d.get('template_placeholders', [])) == 0` rather than joining strings — a different consumer of the same field, not a shared implementation to touch

### Conventions in Force
- `$FC_JSON` is fetched exactly once (Phase 1.6, `SKILL.md:138`); every later phase reuses it via `python -c "import json,sys; ... '; '.join(...)"` one-liners, each preceded by the identical `<!-- ll-prose-ok: mirrors the pre-existing PD_GAP idiom (SKILL.md Phase 1.6) ... -->` comment marker — evidence: `SKILL.md:162,170,193,195`
- Two micro-variants of the extraction idiom coexist: inline single-key (`PD_GAP`, `PARITY_GAP`, `DECISION_GAP`) vs. named-dict multi-key combination (`CLAIM_GAP`, binding `d=json.load(sys.stdin)` then combining fields) — evidence: `SKILL.md:139-140,191-196`. Combining three keys (`template_placeholders`+`boilerplate`+`missing`) matches the `CLAIM_GAP` variant's shape. **All four use bare `python`, single-line** — only the Phase 1.7 `ll-issues show` extractors use `python3` (`SKILL.md:164,172`); an earlier draft of this issue mis-stated `python3` as the Phase 1.8 convention.
- Advisory-cap vs. hard-override is a documented binary in this file: gap keys that get a named "`X Hard Override`" paragraph in Phase 3 force `STOP — ADDRESS GAPS` regardless of score (Learning Test, Program Design, Dependencies — `SKILL.md:359,361,363`); gap keys with no such Phase 3 paragraph are cap-only, confined to a rubric.md table row (`PARITY_GAP`/`CLAIM_GAP` — `rubric.md:245-256`). No other criterion besides Criterion 4 has a documented cap mechanic.

### Tests
- `scripts/tests/test_confidence_check_skill.py` — structural tests for Phase 1.6/1.8 layout
- `scripts/tests/test_feat3048_symbol_cli_claim_gaps.py` — tests the Phase 1.8 `CLAIM_GAP`/`PARITY_GAP` pattern this issue mirrors
- `scripts/tests/test_ll_issues_format_check.py` — tests the JSON payload shape for all gap keys including the three currently unread ones

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_confidence_check_skill.py:502-550` `TestConfidenceCheckClaimParityPrefetch` / `:553-578` `TestConfidenceCheckRubricClaimParityCap` — the ENH-3047 pattern, useful as reference but **not** the classes to extend (see below)
- **Correction (review pass 2026-08-18):** an earlier draft warned that
  `test_phase_1_8_names_all_three_gap_keys` might go stale because it "asserts the
  set of variables Phase 1.8 declares." It does not — `test_confidence_check_skill.py:519-524`
  loops three key-name literals asserting `key in phase_text`, with no exclusivity
  or count check. Adding `STRUCT_GAP` cannot break it. **No existing test needs
  editing for this issue**; the work is purely additive.

_Review pass 2026-08-18 (supersedes the class targets above):_ ENH-3256 landed
after the wiring pass and established a closer precedent — a **dedicated class
pair per gap variable** rather than extending the ENH-3047 classes:
`TestConfidenceCheckDecisionGapPrefetch` (`test_confidence_check_skill.py:581`)
and `TestConfidenceCheckRubricDecisionCap` (`:620`). Follow that shape:
- new `TestConfidenceCheckStructGapPrefetch` — `test_phase_1_8_names_struct_gap_and_source_keys`, `test_phase_1_8_does_not_reissue_format_check`, `test_phase_1_8_marks_struct_gap_advisory`, `test_phase_1_8_filters_missing_to_directive_sections` (asserts the `Summary`/`Acceptance Criteria` allowlist literal appears and that `Program Design`/`Implementation Steps` do **not**), `test_phase_3_does_not_name_struct_gap`
- new `TestConfidenceCheckRubricStructCap` — `test_cap_row_present`,
  `test_cap_documented_as_ceiling`, `test_cap_documented_as_not_a_hard_override`,
  plus `test_cap_row_qualifies_missing_as_directive_only` (see the rubric-wording
  hazard below)
- new `test_phase_1_8_documents_remedy_split` on the prefetch class — asserts the
  Phase 1.8 prose names both remedies (`--fix` for `boilerplate`/`missing`,
  authored content for `template_placeholders`), so Implementation Step 2 is not
  the only thing holding that distinction up

**Rubric-wording hazard:** `test_cap_row_present` greps only for gap-key name
literals, so a Criterion 4 row reading "Any `missing` gap" would pass while
misdescribing the behavior by roughly 10x (58% raw vs. 6% filtered). The row text
must qualify the key — e.g. "directive-section `missing` (`Summary` /
`Acceptance Criteria` only)" — and `test_cap_row_qualifies_missing_as_directive_only`
must assert that qualification, not just the bare key name.

**Prose-ordering hazard:** `test_phase_1_8_marks_decision_gap_advisory`
(`test_confidence_check_skill.py:610`) locates the first occurrence of
``"DECISION_GAP` is"`` and requires the word `advisory` within the following **200
characters**. Inserting the `STRUCT_GAP` prose paragraph between that anchor and
its advisory clause breaks an ENH-3256 test. Append `STRUCT_GAP` prose *after* the
existing `DECISION_GAP` advisory sentence, never between them.

All are pure text-slice assertions against `SKILL.md`/`rubric.md`; no fixtures or
subprocess calls.
- Note: `test_feat3048_symbol_cli_claim_gaps.py` tests `check_format_gaps()` in `issue_parser.py` directly (a different layer — the gap-population sites, not the skill prose); confirmed out of scope since Program Design states no `issue_parser.py` changes are needed

### Documentation
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- Host skill mirrors `.gemini/skills/confidence-check/`, `.kimi-code/skills/confidence-check/`, `.qwen/skills/confidence-check/` (both `SKILL.md` and `rubric.md`) are git-tracked verbatim copies enforced by `scripts/tests/test_wiring_skills_and_commands.py:413-443` (`test_skill_mirrors_carry_companions`, generic over `SKILL_MIRROR_ROOTS`). After editing `skills/confidence-check/SKILL.md`/`rubric.md`, run `ll-adapt --host gemini --apply && ll-adapt --host kimi-code --apply && ll-adapt --host qwen --apply` or the mirror-companion test fails on drift. (The wiring pass noted this as shared with ENH-3256; ENH-3256 has since landed and run its own `ll-adapt` pass, so this issue needs a fresh one of its own.)

### Configuration
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- Phase 3's hard-override list (`skills/confidence-check/SKILL.md:357-365`) must NOT gain an entry for `STRUCT_GAP` — confirmed only Learning Test, Program Design (`PD_FAIL`), and Dependencies (`DEP_FAIL`) are named there; `CLAIM_GAP`/`PARITY_GAP` are deliberately absent, and `STRUCT_GAP` follows the same cap-only discipline

## Program Design

### Signatures
- `FormatGaps.to_dict()` — already serializes `template_placeholders`, `boilerplate`, `missing` as `list[str]` (`scripts/little_loops/issue_parser.py:546`); no signature change needed

### Call Path
`cmd_format_check` produces the JSON payload via `FormatGaps.to_dict` (both defined above) -> captured once into `$FC_JSON` (`skills/confidence-check/SKILL.md:138`) -> Phase 1.8 extraction one-liners extend to add the new combined variable (`SKILL.md:187-207`) -> Criterion 4 cap row extends (`rubric.md:241-256`) -> Criterion 4 score only, never Phase 3 STOP overrides (`SKILL.md:357-365`)

### Decision Rules

**Variable name:** `STRUCT_GAP` (the earlier draft left it unnamed as
`<new_var>`, which made its Implementation Steps and prescribed tests
unwriteable).

**Composition:**
```
STRUCT_GAP = '; '.join(
    d.get('template_placeholders', [])
    + d.get('boilerplate', [])
    + [m for m in d.get('missing', []) if m in _CRITERION4_DIRECTIVE_SECTIONS]
)
```
where the directive allowlist is `{"Summary", "Acceptance Criteria"}` (see
Proposed Solution › Narrowing for why `Program Design`/`Implementation Steps`
were dropped). **The allowlist exists only as an inlined `D={...}` set literal
inside the skill's `python -c` one-liner** (the `CLAIM_GAP` named-dict variant,
`SKILL.md:194`) — it is not a named Python constant and must not be added to
`issue_parser.py`, which Scope Boundaries forbids. The pseudocode above spells it
`_CRITERION4_DIRECTIVE_SECTIONS` for readability only; no such symbol is created.
The allowlist is a confidence-check scoring policy, not a property of the gap key
itself, and `format-check` must keep reporting all `missing` sections to its
other consumers.

**Shell form:** single-line, bare `python` (not `python3`), matching every other
Phase 1.8 extractor verbatim. The whole `python -c` body stays on one physical
line so the text-slice assertions used by this file's test classes keep working,
and the preceding `<!-- ll-prose-ok: ... -->` marker must be the full string used
by its siblings, character for character.

**Cap semantics:** non-empty `STRUCT_GAP` caps Criterion 4 at 10 regardless of
which other row would otherwise apply — a ceiling, never a floor. It is
cap-only: no Phase 3 hard-override paragraph, matching `PARITY_GAP`/`CLAIM_GAP`.

**Interaction with the sibling cap:** ENH-3256's `DECISION_GAP` (now shipped —
`SKILL.md:196`, `rubric.md:313-321`) caps Criterion C (Ambiguity); `STRUCT_GAP`
caps Criterion 4 (Well-Specified). Different criteria, so the caps compose
additively with no ordering dependency, and `rubric.md` carries one cap row per
criterion rather than a merged row.

**Interaction with `PD_FAIL`:** none by construction — `Program Design` is
excluded from the allowlist precisely so a missing Program Design section is
reported once, as the stronger Phase 3 hard override, and never also as a
Criterion 4 cap.

**Inert cases:** all three keys empty, or only non-directive `missing` entries
present (e.g. just `Status`/`Impact`) — `STRUCT_GAP` is the empty string and
Criterion 4 scoring is untouched.

## Implementation Steps

1. Add the `STRUCT_GAP` extraction to Phase 1.8 in
   `skills/confidence-check/SKILL.md` per Decision Rules above, off the
   already-captured `$FC_JSON` — no second `format-check` invocation, matching
   the explicit "do not issue a second format-check call" comment already
   present for `PARITY_GAP`/`CLAIM_GAP` (`SKILL.md:189-190`).
2. Add the prose paragraph describing `STRUCT_GAP` beside the existing
   `PARITY_GAP`/`CLAIM_GAP` paragraph, stating the directive-section allowlist,
   the cap-not-STOP discipline, and the per-key remedy split (`--fix` repairs
   `boilerplate`/`missing`; `template_placeholders` needs authored content).
   Append it **after** the existing `DECISION_GAP` advisory sentence — never
   between ``"DECISION_GAP` is"`` and the word `advisory` — or
   `test_phase_1_8_marks_decision_gap_advisory` (`:610`, 200-char window) breaks.
3. Update the existing Phase 1.8 summary sentence *"All three are empty/inert on
   the present-but-empty case"* (`SKILL.md`, in the paragraph following the bash
   block) to read **"All four"** — `STRUCT_GAP` makes the current count wrong.
4. Extend `rubric.md`'s Criterion 4 cap row and prose note to cover
   `STRUCT_GAP`, staying a cap — consistent with `SKILL.md:204-207`'s statement
   that `CLAIM_GAP` "must not be escalated to a STOP verdict." The row must
   qualify `missing` as directive-section-only (`Summary`/`Acceptance Criteria`),
   not name the bare key.
5. Confirm Phase 3's hard-override list (`SKILL.md:357-365`) gains no
   `STRUCT_GAP` entry.
6. Run `ll-adapt --host gemini --apply && ll-adapt --host kimi-code --apply &&
   ll-adapt --host qwen --apply` to refresh the three verbatim skill mirrors.
   (`SKILL_MIRROR_ROOTS` also lists `.omp`, but no `.omp/skills/` tree is tracked
   in this repo and the mirror test early-returns for it — three hosts is
   correct here.)

## Acceptance Criteria

- [ ] Phase 1.8 of `skills/confidence-check/SKILL.md` names `STRUCT_GAP` and all
      three source keys (`template_placeholders`, `boilerplate`, `missing`).
- [ ] Phase 1.8 issues no second `format-check` call — `$FC_JSON` is still
      fetched exactly once, in Phase 1.6.
- [ ] The `missing` contribution is filtered to the two-entry directive allowlist
      (`Summary`, `Acceptance Criteria`); an issue whose only `missing` entries
      are `Status` and `Impact` leaves `STRUCT_GAP` empty.
- [ ] Neither `Program Design` nor `Implementation Steps` appears in the
      allowlist — a missing Program Design section is reported once, via the
      `PD_FAIL` hard override, and never also as a Criterion 4 cap.
- [ ] An issue with a non-empty `template_placeholders` list caps Criterion 4 at
      10 and does **not** produce a `STOP — ADDRESS GAPS` verdict.
- [ ] `rubric.md`'s Criterion 4 cap row names `STRUCT_GAP` and is documented as a
      ceiling and explicitly not a hard override.
- [ ] The Criterion 4 cap row qualifies `missing` as directive-section-only
      (`Summary`/`Acceptance Criteria`) rather than naming the bare key — a row
      reading "Any `missing` gap" would pass `test_cap_row_present` while
      overstating the trigger rate ~10x (58% raw vs. 6% filtered).
- [ ] Phase 1.8 prose documents the per-key remedy split: `format-check --fix`
      repairs `boilerplate` and `missing`, while `template_placeholders` requires
      authored content and has no `--fix`.
- [ ] Phase 1.8's existing "All three are empty/inert" sentence reads "All four".
- [ ] `STRUCT_GAP` does not appear in Phase 3's hard-override paragraphs
      (`test_phase_3_does_not_name_struct_gap`).
- [ ] The three host skill mirrors match `skills/confidence-check/` byte-for-byte.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P2 - Weakens the pre-implementation gate, but the loop-side `check_placeholders` already covers the highest-value signal in automated runs.
- **Effort**: Small - Two prose files, one extraction one-liner and one rubric row; no Python change.
- **Risk**: Low - Cap-only semantics with a measured allowlist; the narrowing keeps the trigger rate at a measured 6% of open issues rather than 58%.
- **Breaking Change**: No - Scores can drop for issues carrying real debris, which is the intent; no interface changes.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-18 | Priority: P2

## Success Metrics

- A synthetic issue fixture carrying unfilled `[bracketed]` template prompts
  caps Criterion 4 at 10 without producing a `STOP` verdict. (ENH-3256/ENH-3257
  are no longer usable as the live example — both now format-check clean, all
  gap keys empty.)
- `STRUCT_GAP` fires on **≤ 7% of the 168 unresolved issues** (`open` +
  `in_progress`/`blocked` + `deferred`) — measured **10/168 = 6.0%** with the
  two-entry allowlist, versus 58% for raw `missing` and 10.7% for the four-entry
  draft. Verify by re-running the measurement in Proposed Solution › Narrowing
  against that same denominator.
- On the narrower **strictly-open** subset (77 issues) the same allowlist fires
  at **6/77 = 7.8%**; the bar there is **≤ 10%**. Both thresholds are stated
  because the two denominators differ enough that a single "≤7% of open issues"
  claim — as an earlier draft of this issue asserted — fails on the strictly-open
  set on day one despite the design being correct.

## Scope Boundaries

**In scope:** reading three already-fetched keys in Phase 1.8 and the Criterion 4
cap row in `rubric.md`.

**Out of scope:**
- Any change to `scripts/little_loops/issue_parser.py` or
  `cli/issues/format_check.py` — all three keys already exist and serialize
  correctly; the allowlist is a scoring policy local to confidence-check.
- `refine-to-ready-issue.yaml`'s `check_placeholders` state (ENH-3248). It
  re-invokes `format-check` independently and gates on a count rather than a
  joined string — a separate consumer, deliberately not unified here.
- Auto-remediation. `STRUCT_GAP` is advisory; running `format-check --fix` or
  authoring the missing content stays the user's action.
- Criterion C (Ambiguity), which ENH-3256 covers.

## Backwards Compatibility

No interface change. `$FC_JSON` is already fetched; this reads three more keys
from it. Issues carrying real structural debris will score up to 10 points lower
on Criterion 4 than before, which is the intended correction — previously scored
issues keep their frontmatter until re-run. The cap cannot lower an issue below
its existing row (ceiling, never floor) and cannot produce a `STOP` verdict.

## API/Interface

```bash
# skills/confidence-check/SKILL.md Phase 1.8 — reuses $FC_JSON from Phase 1.6.
# Single-line body, bare `python`, full ll-prose-ok marker: matches PARITY_GAP /
# CLAIM_GAP / DECISION_GAP character for character.
# <!-- ll-prose-ok: mirrors the pre-existing PD_GAP idiom (SKILL.md Phase 1.6) for a one-off JSON field extraction, not a reimplemented algorithm -->
STRUCT_GAP=$(echo "$FC_JSON" | python -c "import json,sys; d=json.load(sys.stdin); D={'Summary','Acceptance Criteria'}; print('; '.join(d.get('template_placeholders', []) + d.get('boilerplate', []) + [m for m in d.get('missing', []) if m in D]))" 2>/dev/null || true)
```


## Session Log
- `/ll:manage-issue` - 2026-08-19T03:34:09 - `47b33c1f-0be6-43ba-8a7e-c08b78b7dd7e.jsonl`
- `/ll:confidence-check` - 2026-08-19T02:26:16 - `3ac46c0e-24a3-4309-88b6-5d1bfb5b7a78.jsonl`
- `/ll:verify-issues` - 2026-08-18T23:42:05 - `5babd785-d270-4764-90c8-5811c9188fb7.jsonl`
- `/ll:confidence-check` - 2026-08-18T22:04:27 - `bb66018c-ab8d-4e0a-a8d9-81ae552f7d58.jsonl`
- `/ll:wire-issue` - 2026-08-18T22:00:40 - `b37bf726-239f-4f1a-b2e3-9f5b456cd984.jsonl`
- `/ll:refine-issue` - 2026-08-18T21:39:54 - `1598a616-9bb3-45c4-9fb9-f9f87bed73c9.jsonl`
- `/ll:capture-issue` - 2026-08-18T20:48:47 - `fdfd9556-8841-4d2f-baeb-50bd68feb80e.jsonl`
