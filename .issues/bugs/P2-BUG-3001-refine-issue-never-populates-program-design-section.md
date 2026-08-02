---
id: BUG-3001
title: 'refine-issue never populates ## Program Design despite being the prescribed
  remedy for the gate'
type: BUG
priority: P2
captured_at: '2026-08-02T15:46:46Z'
discovered_date: 2026-08-02
discovered_by: capture-issue
labels:
- refine-issue
- program-design-gate
- confidence-check
status: open
confidence_score: 96
outcome_confidence: 84
score_complexity: 21
score_test_coverage: 21
score_ambiguity: 20
score_change_surface: 21
---

# BUG-3001: refine-issue never populates ## Program Design despite being the prescribed remedy for the gate

## Summary

`## Program Design` is a `required: true` template section
(`scripts/little_loops/templates/feat-sections.json` and its `bug`/`enh`
siblings) graded by a
deterministic specificity check in
`scripts/little_loops/issues/program_design.py`. When it fails,
`skills/confidence-check/SKILL.md:303` issues a hard `STOP — ADDRESS GAPS`
override and names `/ll:refine-issue` (or `/ll:reconcile-issue`) as the
remedy. `commands/ready-issue.md:237` names the same remedy as an advisory.

`commands/refine-issue.md` contains **zero occurrences** of "Program Design" or
`program_design`. It has no enrichment rule for the section, no gap-category
row for types/signatures, and its post-write format-check gate ignores the
`program_design_nonspecific` key that `ll-issues format-check` already returns
in the very JSON payload it parses. The prescribed remedy cannot clear the gate
it is prescribed for.

## Steps to Reproduce

1. In a project with the cutover stamp present (`.ll/program-design-cutover.json`
   — this repo is stamped `2026-07-30`), take an issue whose `## Program Design`
   section is missing, empty, or prose-only.
2. Run `/ll:refine-issue <ID>`.
3. Run `ll-issues format-check <ID> --format json` and inspect
   `program_design_nonspecific` — still non-empty.
4. Run `/ll:confidence-check <ID>` — still `STOP — ADDRESS GAPS` via the
   Phase 1.6 / `:303` hard override, with the same remedy text pointing back at
   the command just run.

## Current Behavior

Verified by grep over `commands/` and `skills/` for
`Program Design|program_design`:

| File | Hits |
|---|---|
| `skills/confidence-check/SKILL.md` | 6 — computes the gate, hard-STOPs, prescribes refine/reconcile |
| `commands/ready-issue.md` | 4 — advisory surface only |
| `skills/manage-issue/SKILL.md` | 3 — post-hoc `### Deviations` logging |
| `commands/refine-issue.md` | **0** |
| `commands/reconcile-issue.md` | **0** (tracked separately — see BUG-3002) |

Two concrete gaps inside `commands/refine-issue.md`:

1. **Step 4 gap taxonomy** (`:286-314`) — the BUG/FEAT/ENH knowledge-gap
   tables enumerate root-cause location, integration surface, existing
   patterns, callers, tests. None of them is "the concrete types, signatures,
   and call path the implementation will follow." So Program Design is never
   marked FILLABLE and Step 5a never writes it.
2. **Step 6.5 Prose Dependency Gate** (`:644-658`) — runs
   `ll-issues format-check [ISSUE-ID] --format json` and inspects exactly two
   keys, `prose_dep_drift` and `stale_prose_dep`. The same response object
   carries `program_design_nonspecific` (produced by
   `cli/issues/format_check.py`), which is discarded.

This is not a research-capability gap: Step 3 already spawns
`ll:codebase-analyzer`, whose contract is anchor-level identifier output — the
exact material the gate wants. Step 5a's `#### Enrichment Rules` then files
that material into `## Integration Map` prose bullets and
`### Codebase Research Findings`, never into a signature block.

## Expected Behavior

`/ll:refine-issue` should, in auto mode, populate `## Program Design` with
concrete identifiers (a handful of signatures plus one call chain, per the
template's `quality_guidance`), and should self-check that result before
declaring success — so that the command named as the gate's remedy actually
clears the gate.

Where research genuinely cannot produce a design (a one-line config change, a
docs fix), refine should say so in its output report and point at the
`program_design_not_applicable: true` opt-out rather than padding the section
with prose that will fail the specificity check anyway.

## Root Cause

`commands/refine-issue.md` was written before the Program Design gate landed
(ENH-2852) and was never extended when the gate began naming it as the remedy.
The gate's authors wired the *detection* side (`program_design.py`,
`format_check.py`, `confidence-check` Phase 1.6/`:303`) and the *reporting*
side (`ready-issue.md`, `ll-issues deferred-triage` reason code
`design_gate_failed`) but not the *remediation* side.

Supporting detail: the `full` creation variant in
`scripts/little_loops/templates/feat-sections.json` (and the `bug`/`enh`
siblings) — `creation_variants.full.include_common` — does
**not** list `Program Design`, even though the section is `required: true` in
`common_sections`. So `/ll:capture-issue` does not emit even a stub, and no
downstream refinement command fills one in — the section's only reliable
authors today are humans and `/ll:format-issue`.

## Proposed Solution

Two changes to `commands/refine-issue.md`, both additive:

1. **Add a Program Design enrichment rule to Step 5a.** Add a
   types/signatures/call-path row to each of the three Step 4 gap tables
   (source: `codebase-analyzer`), and add a `#### Enrichment Rules` block that
   emits the template's three-subheading shape:

   ```markdown
   ## Program Design

   ### Types
   - `FieldName: type`

   ### Signatures
   - `function_name(param: type) -> ReturnType`

   ### Call Path
   `existing_caller` -> `new_function` -> `existing_callee`
   ```

   The existing `#### Preservation Rule` already covers the "section has real
   content" case correctly (append, don't replace) — a placeholder-only stub is
   already excluded from preservation by its own "not `TBD` or placeholders"
   carve-out, so no change is needed there.

2. **Extend Step 6.5 to inspect `program_design_nonspecific`.** Same
   `format-check --format json` call, one more key. On non-empty, refine
   revises the section it just wrote and re-runs the check; if it still fails,
   it reports the gap explicitly in Step 8's output report under a new line so
   the operator knows the gate is still armed. Gate the whole check on
   `program_design_gate_active()` semantics so it stays inert in unstamped
   projects (the CLI already returns empty there — see BUG-2956 for the
   `program_design_not_applicable` opt-out handling in `format-check`).

Optionally (smaller, separable): add `Program Design` to
`creation_variants.full.include_common` in the three section templates so
captured issues carry a stub for refine to fill.

## Program Design

### Signatures

No Python signature changes are required for the primary fix — the change is
to the prose contract in `commands/refine-issue.md`. The CLI surface refine
consumes already exists and is unchanged:

- `ll-issues format-check <ISSUE_ID> --format json` →
  `dict[str, list[str]]` including the `program_design_nonspecific` key
  (`scripts/little_loops/cli/issues/format_check.py`)
- `program_design_gate_active(issue_path: Path, content: str) -> bool`
  (`scripts/little_loops/issues/program_design.py:414`) — the authority on
  whether the gate applies; refine's new check must not contradict it

For the optional template change:

- `creation_variants.full.include_common: list[str]` in
  `scripts/little_loops/templates/feat-sections.json` (and the `bug`/`enh`
  siblings) — append `"Program Design"`

### Call Path

Refine's Step 6.5 shells out to `ll-issues format-check`, whose existing
resolution chain already produces the verdict the new check must read:

`cmd_format_check` → `check_format_gaps` → `_gate_program_design` →
`program_design_gate_active` → `grade_issue_section` → `grade_program_design`

On the refine side (prose, not Python): Step 5a
(`commands/refine-issue.md:323`) writes `## Program Design` → Step 6.5
(`:644`) invokes the chain above and reads
`FormatGaps.program_design_nonspecific` → Step 8 output report (`:707`).

Downstream consumer that must go green as a result:
`skills/confidence-check/SKILL.md` Phase 1.6 (`:132`) → `:303` hard override

## Integration Map

### Files to Modify
- `commands/refine-issue.md` — Step 4 gap tables (`:286-314`), Step 5a
  enrichment rules (`:323-460`), Step 6.5 format-check gate (`:644-658`),
  Step 8 output report (`:707-755`)
- `scripts/little_loops/templates/feat-sections.json`,
  `scripts/little_loops/templates/bug-sections.json`,
  `scripts/little_loops/templates/enh-sections.json` — optional,
  `creation_variants.full.include_common`

### Dependent Files (Callers/Consumers)
- `skills/confidence-check/SKILL.md:132, :303` — the gate that should stop
  firing after a successful refine
- `commands/ready-issue.md:233-237` — advisory surface; wording may need to
  stop implying refine already handles this
- `scripts/little_loops/loops/autodev.yaml:1090, 1586, 1758` — the three
  `DESIGN_FAIL` states; their remedy routing is BUG-3002's scope, but they are
  the automated consumer of this fix

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/rn-remediate.yaml:98-106` — `ensure_formatted`
  state gates on `program_design_nonspecific` alongside `prose_dep_drift`/
  `stale_prose_dep` from the same `ll-issues format-check` call; a second
  automated consumer whose pass/fail behavior changes once refine actually
  clears the key [Agent 1/2 finding]
- `skills/manage-issue/SKILL.md:337-344` — Step 5's Deviations-logging note
  for `## Program Design` skips silently when the section is absent; will
  fire more often once refine reliably populates the section — behavioral
  consequence, not a required edit, but worth knowing when verifying the fix
  [Agent 2 finding]
- `skills/format-issue/SKILL.md:176, 191` — references `check_format_gaps()`
  behavior (ENH-2946 extension point); shares the same JSON payload contract
  refine's Step 6.5 will read [Agent 1 finding]

### Similar Patterns
- Step 6.5's existing `prose_dep_drift`/`stale_prose_dep` handling is the
  precedent to model the new key's handling on — same call, same shape,
  same skip-on-`DRY_RUN` rule
- `/ll:wire-issue` is the precedent for a refinement command that writes one
  specific section from research findings

### Tests
- `scripts/tests/test_program_design_gate.py` — existing coverage for the
  gate itself; extend only if the optional template change lands
- Prose-side changes to `commands/refine-issue.md` are not directly unit
  testable; if the template change lands, assert `Program Design` is present
  in the `full` variant for all three types

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_refine_issue_command.py` — new test file, not new
  coverage of an existing one: this repo's established pattern (see
  `TestResearchTriageWiring`/`TestGapAnalysisMode`) for asserting on
  `commands/refine-issue.md` prose is to slice text between two `###`
  heading anchors via a private `_step_3_text()`/`_section_5c_text()`-style
  helper, then assert required substrings are present in that slice — not
  anywhere in the 700+ line file. Add one class scoping Step 5a's
  `### 5a. Fill Gaps with Research Findings` slice to assert a Program
  Design enrichment-rule marker (e.g. `"## Program Design"` /
  `"#### Enrichment Rules"`) is present, and a second class scoping the
  Step 6.5 slice to assert `"program_design_nonspecific"` is read there
  [Agent 3 finding]
- `scripts/tests/test_ll_issues_sections.py::TestLabelsNotRequired` — if the
  optional template change lands, add a positive-assertion sibling to
  `test_labels_not_in_full_variant_include_common` (`:259-272`), inverted:
  iterate `["feat", "bug", "enh"]` (no `epic` — out of this issue's scope),
  load each `*-sections.json`, assert
  `"Program Design" in data["creation_variants"]["full"]["include_common"]`.
  This is the only existing precedent in the repo for asserting
  `include_common` membership [Agent 3 finding]

### Documentation
- `.claude/CLAUDE.md` § Issue File Format — no change expected; the Program
  Design gate is not currently described there
- `docs/reference/ISSUE_TEMPLATE.md` — check whether it claims refine
  populates this section

_Wiring pass added by `/ll:wire-issue`:_
- Both docs above confirmed clean by the wiring pass: `docs/reference/ISSUE_TEMPLATE.md:30, 37-44`
  documents `## Program Design` as `required` once armed and the
  `program_design_not_applicable: true` opt-out, but does not claim any
  specific command populates it; `.claude/CLAUDE.md` § Issue File Format has
  no mention of Program Design at all. No documentation edit is required by
  the primary fix [Agent 2 finding]
- `.issues/enhancements/P3-ENH-2968-no-test-asserts-committed-ll-adapt-mirrors-are-current.md`
  (open, separately tracked) — `commands/refine-issue.md` has a committed
  `.gemini/commands/refine-issue.toml` mirror that will silently drift from
  the new Step 4/5a/6.5/8 prose unless `ll-adapt --host gemini --only
  refine-issue --apply` is run manually after this change lands; nothing in
  CI flags the omission today. FYI only, not a blocking dependency of this
  issue [Agent 2 finding]

### Configuration
- N/A — `.ll/program-design-cutover.json` is a stamp, not a setting to change

## Implementation Steps

1. Program Design gaps are detected by refine's own Step 4 taxonomy and filled
   in Step 5a with anchor-level identifiers from the `codebase-analyzer`
   findings that step already has in hand.
2. Refine's Step 6.5 gate reads `program_design_nonspecific` alongside the two
   prose-dep keys it already reads, and a still-failing section is reported in
   the Step 8 output rather than passing silently.
3. Verification is empirical, not structural: pick an issue currently failing
   the gate, run `/ll:refine-issue` on it, and confirm
   `ll-issues format-check <ID> --format json` returns an empty
   `program_design_nonspecific` and `/ll:confidence-check` no longer emits the
   hard override.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

4. Add `scripts/tests/test_refine_issue_command.py` coverage for the new Step
   5a enrichment rule and Step 6.5 gate extension, following the existing
   section-slice assertion pattern in that file.
5. If the optional template change lands, add a positive-assertion test to
   `scripts/tests/test_ll_issues_sections.py::TestLabelsNotRequired` (or a
   sibling class) asserting `"Program Design"` is present in
   `creation_variants.full.include_common` for `feat`/`bug`/`enh`.
6. When verifying the fix empirically (Step 3 above), also spot-check that
   `scripts/little_loops/loops/rn-remediate.yaml`'s `ensure_formatted` state
   and `skills/manage-issue/SKILL.md`'s Deviations-logging step behave as
   expected against a freshly-populated `## Program Design` section — both
   consume the same gate output and are not directly modified by this fix.

## Impact

This is the load-bearing half of the Program Design gate. Today the gate can
detect and block but the prescribed manual remedy is a no-op, so every failing
issue requires a human to hand-write the section — the workflow the gate was
built to automate. Compounding it: because
`issues/program_design.py:391-410` derives grandfathering from the most recent
`/ll:refine-issue` Session Log date, running refine on a previously-grandfathered
issue *arms* the gate (the stamp moves past the cutover date) while writing
nothing into the section — so refine currently converts passing issues into
blocked ones. That secondary effect largely dissolves once refine populates the
section, which is why it is folded in here rather than tracked separately.

Blast radius is limited to the refinement chain (no runtime code path), and
the fix is inert in projects with no cutover stamp.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `skills/confidence-check/SKILL.md` | Defines the gate and prescribes this command as the remedy |
| `scripts/little_loops/issues/program_design.py` | The deterministic specificity check and grandfathering logic |
| `.claude/CLAUDE.md` | Issue File Format conventions |

## Status

**Open** | Created: 2026-08-02 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-08-02T16:06:10 - `7350086a-c582-4853-bc33-c455a6cf8d34.jsonl`
- `/ll:wire-issue` - 2026-08-02T16:01:40 - `2e08df07-a323-43c7-be95-67426e4a306f.jsonl`
- `/ll:refine-issue` - 2026-08-02T15:53:25 - `db0d0569-e597-40a8-acbc-c57cea59645a.jsonl`
- `/ll:capture-issue` - 2026-08-02T15:49:44 - `757e6b7e-c10a-4a24-9492-2b31e8e379e5.jsonl`
