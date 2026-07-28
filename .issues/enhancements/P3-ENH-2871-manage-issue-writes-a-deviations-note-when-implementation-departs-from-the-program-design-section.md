---
id: ENH-2871
title: manage-issue writes a Deviations note when implementation departs from the
  Program Design section
type: ENH
priority: P3
status: done
discovered_date: 2026-07-27
completed_at: '2026-07-28T04:21:47Z'
epic: EPIC-2856
parent: EPIC-2856
relates_to:
- ENH-2852
- ENH-2870
labels:
- rework
- verification
confidence_score: 96
outcome_confidence: 92
score_complexity: 24
score_test_coverage: 23
score_ambiguity: 22
score_change_surface: 23
---

# ENH-2871: manage-issue writes a Deviations note when implementation departs from the Program Design section

Split from ENH-2852 (2026-07-27): the amendment path is independent of the gate itself —
it concerns implementation-time behavior, not refinement-time validation — and can land
before or after the gate is armed.

## Summary

ENH-2852's `## Program Design` section follows an amendment path, not a prohibition: the
implementing agent may deviate from the refine-time design (queue-latency staleness is
real — a design fixed at refine time can be invalidated by codebase changes before
implementation starts), but the deviation must be *recorded* in the issue, never silently
rewritten over the original. Without a writer, that contract is unenforced prose: nothing
in the system would ever produce a `Deviations` note. Give it a writer in
`skills/manage-issue/SKILL.md`.

## Current Behavior

`skills/manage-issue/SKILL.md`'s "Mismatch Handling Protocol" (`:325-334`) handles
plan/reality divergence interactively at implementation time but persists nothing
structured to the issue file. There is no existing "Deviations" section or frontmatter
convention anywhere in the codebase (confirmed by ENH-2852's refinement research).

## Expected Behavior

When implementation deviates from the issue's `## Program Design` section (different
signature, different call path, different type shape), `manage-issue` appends a
`Deviations` note under that section stating what changed and why — a new markdown
subsection convention, visible in the issue file — instead of rewriting the original
design or recording nothing. `/ll:reconcile-issue`'s by-design rewriting of directive
sections is unaffected.

## Proposed Change

1. **`skills/manage-issue/SKILL.md`** — extend the Mismatch Handling Protocol
   (`:325-334`, the attach point) with an explicit step: when the implemented shape departs from
   `## Program Design`, append (via `Edit`) a `#### Deviations` note under that section
   with a dated entry per deviation: what the design said, what was implemented, and why.
   Never modify the original `Types`/`Signatures`/`Call Path` content.

   **The step must fire on both branches, and be worded so it obviously applies to the
   non-`--gates` default.** The protocol's step 4 (`SKILL.md:332` — "Without `--gates`
   (default): Do NOT use `AskUserQuestion`. Adapt if minor…") is the autonomous branch `ll-auto` /
   `ll-parallel` / autodev actually take — it is precisely where deviations go
   unrecorded today. If the new step reads as belonging to the interactive `--gates`
   branch, it is dead code in automation and the issue delivers nothing.
2. **Format tolerance** — the `Deviations` subsection must not trip ENH-2852's specificity
   grading: grading operates on the `Types`/`Signatures`/`Call Path` subsections and the
   `Call Path` anchor extraction, so an appended prose `Deviations` note is inert to the
   gate. Add a test guarding this (a section that passes the gate still passes with a
   `Deviations` note appended).
3. **Docs** — `docs/reference/ISSUE_TEMPLATE.md`'s `Program Design` entry (added by
   ENH-2852) documents the `Deviations` convention: appended at implementation time,
   original design preserved.

## Acceptance Criteria

- [ ] `skills/manage-issue/SKILL.md` has an explicit step that writes a dated
      `#### Deviations` note under `## Program Design` when implementation departs from
      the recorded design — the convention ships with a writer, not as an unproduced
      section.
- [ ] The step appends; it never rewrites the original `Types`/`Signatures`/`Call Path`
      content.
- [ ] The step is written to fire on the non-`--gates` autonomous branch (step 4 of the
      protocol), not only the interactive `--gates` branch — that is the branch
      `ll-auto`/`ll-parallel`/autodev use.
- [ ] **Positional assertion** (the only mechanically checkable guard that the writer is
      not dead code in automation): a test asserts the Deviations instruction text appears
      within the Mismatch Handling Protocol section *at or after* the step-4
      "Without `--gates`" line, not confined to the step-3 `--gates` block. Every other
      AC here is prose-only; without this one, "the step exists" and "the step fires in
      automation" are indistinguishable to the suite — which is exactly the failure mode
      this issue names as the thing that makes it deliver nothing.
- [ ] A test asserts a gate-passing `## Program Design` section still passes
      `ll-issues format-check` with a `Deviations` note appended (the note is inert to
      specificity grading).
- [ ] `docs/reference/ISSUE_TEMPLATE.md` documents the `Deviations` convention alongside
      the `Program Design` section entry.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Attach point moved**: `skills/manage-issue/SKILL.md`'s Mismatch Handling Protocol
  now lives at lines `332-341` (not `325-334` as stated above — the file has grown
  since this issue was filed). The numbered steps are at lines `336-339`; step 4
  ("Without `--gates` flag (default): Do NOT use `AskUserQuestion`. Adapt if minor,
  mark `INCOMPLETE` if significant") is at line `339`. This is still the correct
  attach point — only the line numbers drifted.
- **AC "grading-inertness test" is already satisfied, no new test needed**:
  `scripts/tests/test_program_design_gate.py:260-288`,
  `TestGrading.test_deviations_subsection_is_inert`, already asserts (a) a
  `### Deviations` subsection alone doesn't rescue a prose `## Program Design`
  section, and (b) appending one to an already-valid section doesn't break its
  passing verdict. This is backed by `_evidence_body()` and
  `extract_call_path_anchors()` in `scripts/little_loops/issues/program_design.py`
  (both reference ENH-2871 in their docstrings/comments), which only read the
  `Types`/`Signatures`/`Call Path` subsections — a `Deviations` heading terminates
  subsection scanning by construction. **Scope Boundaries note**: item 2 of the
  Proposed Change ("Add a test guarding this") is done; no new work required there.
- **AC "docs" is already satisfied, no new writing needed**:
  `docs/reference/ISSUE_TEMPLATE.md:50-51` already documents the convention: "An
  appended `### Deviations` note (recorded at implementation time) is inert: it
  neither rescues a prose section nor breaks a valid one." Item 3 of the Proposed
  Change is done.
- **What remains is only item 1 of the Proposed Change** — the `SKILL.md` writer
  step itself and its positional test. No existing code writes a `Deviations` note
  anywhere in the codebase today (confirmed: only `program_design.py`'s grading
  logic and the docs mention it; there is no writer).
- **Test pattern to model the writer step's test after**:
  `scripts/tests/test_manage_issue_changelog_gate.py` (`TestSkillGateContract`,
  ~lines 38-56) is the established precedent for testing `SKILL.md` prose directly
  — it reads `SKILL_FILE.read_text()` and asserts literal substrings/snippets are
  present, one assertion message per invariant.
- **Positional-assertion idiom already used elsewhere in this test suite** (for the
  required "at or after step 4" check): `text.index(a) < text.index(b)` /
  `.find(...) > anchor_idx`, e.g. `scripts/tests/test_session_log.py:121`,
  `scripts/tests/test_rn_remediate.py:231`, `scripts/tests/test_ll_loop_commands.py:1654`,
  `scripts/tests/test_issues_cli.py:1169-1170`. Compare
  `SKILL_FILE.read_text().index("<Deviations instruction text>")` against
  `.index("Without \`--gates\` flag (default)")` and assert the former is `>=` the
  latter.
- **Established "fire on both branches" phrasing precedent**: `SKILL.md:321-328`'s
  `### Default Behavior` section already uses the framing "By default (no `--gates`
  flag): ..." to make autonomous-branch applicability unambiguous — the new
  Deviations instruction should follow the same framing so it obviously covers the
  non-`--gates` default per this issue's own wording requirement.
- **Nearby "Deviations" heading precedent in the FSM/loop world** (different
  mechanism, same wording): `scripts/little_loops/loops/oracles/plan-node-refine.yaml:122`
  uses a `## Deviations from prior implemented leaves` heading emitted by a shell
  action — confirms "Deviations" as an established convention name, not a new
  coinage, though this issue's mechanism is skill-instructed `Edit`, not a shell
  action.

### Wiring Findings

_Wiring pass added by `/ll:wire-issue`:_

- **Heading-level mismatch between this issue's Proposed Change and the already-shipped
  docs convention.** Item 1 of Proposed Change specifies `#### Deviations` (four hashes).
  But `docs/reference/ISSUE_TEMPLATE.md:50-51` (already shipped, per this issue's own
  Codebase Research Findings) documents the convention one level shallower: `### Deviations`
  (three hashes) — *"An appended `### Deviations` note (recorded at implementation time) is
  inert..."*. `TestGrading.test_deviations_subsection_is_inert`
  (`scripts/tests/test_program_design_gate.py:260-288`) is the existing fixture that pins
  whichever level it was written against. **Use `### Deviations` (matching the shipped docs
  and the `##`-level `Program Design` parent, consistent with sibling `###`-level
  `Types`/`Signatures`/`Call Path` subsections) when writing the `SKILL.md` step and its
  positional test** — the grading regex (`#{2,6}`) accepts either level, so this is a
  documentation-consistency requirement, not a gate-functional one, but shipping `####`
  would contradict the already-published convention. [wiring pass, side-effect-surface trace]
- No other coupling requires new files. `program_design.py`'s `_evidence_body()` and
  `extract_call_path_anchors()` are confirmed inert to a `Deviations` heading by direct
  reading (their docstrings/comments already reference ENH-2871); `docs/ARCHITECTURE.md`,
  `config-schema.json`, and the *-sections.json templates have no coupling. Other skills/loops
  that generically mention "manage-issue" or "Program Design" (confidence-check, format-issue,
  autodev.yaml, rn-refine.yaml, etc.) are pre-existing consumers of the gate/grading mechanism
  this issue's Scope Boundaries already excludes — not new wiring for this issue's writer step.
  [wiring pass, caller/importer trace — filtered per issue's own Scope Boundaries]
- Test placement for the new positional test has two equally-precedented options, no
  wiring gap either way: a new class in `scripts/tests/test_manage_issue_changelog_gate.py`
  (reusing its existing `SKILL_FILE`/`REPO_ROOT` constants) or a new sibling file
  `scripts/tests/test_manage_issue_deviations_note.py`. Positional-assertion idiom to copy:
  `text.index(a) < text.index(b)`, as used in `scripts/tests/test_session_log.py:121` and
  `scripts/tests/test_rn_remediate.py:231`. [wiring pass, test-gap trace]

## Scope Boundaries

- **In scope**: the `manage-issue` Deviations-writing step, the grading-inertness test,
  and the `ISSUE_TEMPLATE.md` convention docs.
- **Out of scope**: the gate, grading, grandfathering (ENH-2852); autodev routing and
  stamp arming (ENH-2870); any change to `/ll:reconcile-issue`'s by-design rewriting of
  directive sections.
- **Known coverage limit** (deliberate, not an oversight): `rn-implement.yaml` and
  `rn-stepwise.yaml` do **not** invoke `/ll:manage-issue` — grep confirms only
  `harness-single-shot.yaml`, `harness-plan-research-implement-report.yaml`,
  `rl-coding-agent.yaml`, and `issue_manager.py:942` (the `ll-auto`/`ll-parallel`/autodev
  path) do. So this writer covers the autodev path but leaves the `rn-*` implement loops
  unenforced. Recording the limit here rather than silently shipping a partial contract;
  extending it to the `rn-*` loops is a follow-up, unowned.

## Impact

- **Priority**: P3 - the gate functions without it; this closes the "may deviate, but it
  is recorded" contract so refine-time designs stay auditable against what shipped.
- **Effort**: Small - one skill-prose step, one grading-inertness test, one docs entry.
- **Risk**: Low - additive skill instruction; the only interaction with the gate is
  covered by the inertness test.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-07-27 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-07-28T04:21:15 - `7f05c8cc-b967-4589-af2b-77b4cea4c84a.jsonl`
- `/ll:wire-issue` - 2026-07-28T04:14:09 - `8ff438b9-2c5a-49f6-b389-bfdfbd96bfed.jsonl`
- `/ll:refine-issue` - 2026-07-28T04:10:26 - `745b3b56-2216-4c20-9d01-25c9f3ef2f8d.jsonl`
