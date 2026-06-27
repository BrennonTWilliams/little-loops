---
id: ENH-2330
title: 'scope-epic/link-epics: stop overloading relates_to + add post-write validation'
type: ENH
priority: P3
status: open
captured_at: '2026-06-26T22:37:02Z'
discovered_date: '2026-06-26'
discovered_by: capture-issue
relates_to:
- FEAT-2332
- BUG-2333
decision_ref:
- ARCHITECTURE-065
labels:
- captured
- epic
- issue-management
- scope-epic
- link-epics
- parent-child
---

# ENH-2330: Stop overloading `relates_to` in EPIC writers; validate after wiring

## Summary

`scope-epic` and `link-epics` write every child into the EPIC's `relates_to:`
frontmatter as a membership channel, conflating membership with genuine
cross-references. Under ARCHITECTURE-065 (`parent:` is the source of truth),
membership is carried by the child's `parent:` plus the derived body
`## Children`; `relates_to:` should hold only non-membership cross-refs. The
writers should stop populating `relates_to` with children and should assert
consistency before returning.

## Current Behavior

- `skills/scope-epic/SKILL.md` Phase 5a (lines ~382-400): appends each child ID
  to the EPIC's `relates_to:`.
- `skills/link-epics/SKILL.md` Phase 6b (lines ~204-236): appends each accepted
  orphan to the EPIC's `relates_to:`.
- Both also write `parent:` on the child (5c / 6a) and a `## Children` bullet
  (5b / 6c), but **neither asserts the three agree** afterward (audit finding
  F6). This is the upstream source that makes `relates_to` overloaded and feeds
  BUG-2333's reader divergence.

## Proposed Solution

- **Stop writing children into `relates_to:`.** New children get `parent:` on
  the child and a bullet in the EPIC `## Children` section; `relates_to:` is left
  for human-curated cross-references only. (If a transitional period is needed
  while BUG-2333 lands, keep writing but rely on parent:-only readers — decide
  per ARCHITECTURE-065.)
- **Post-write validation.** After wiring, assert the child's `parent:` points
  at the EPIC and the child appears once in `## Children`; emit a clear warning
  if not. Optionally call `ll-issues epic-consistency <EPIC>` (FEAT-2332) as the
  check.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **The validator (`ll-issues epic-consistency`) does not exist yet.** FEAT-2332
  is unimplemented — there is no `epic-consistency` subcommand in
  `scripts/little_loops/cli/issues/__init__.py` (registered subcommands stop at
  `epic-progress`, ~line 718) and no `epic_consistency.py` module. The post-write
  assertion must therefore EITHER be sequenced after FEAT-2332 lands OR be
  implemented **inline in the skill** (re-read the child's `parent:` and grep the
  EPIC `## Children` for the child ID), mirroring the existing inline check in
  scope-epic Phase 5c. **Recommendation: inline**, so ENH-2330 is not blocked on
  FEAT-2332; swap to `ll-issues epic-consistency` later if/when it ships.
- **The transitional-window risk is narrower than stated.** Removing children
  from `relates_to:` is already SAFE for the primary readers:
  `compute_epic_progress()` (`scripts/little_loops/issue_progress.py:87`) resolves
  children via `parent:` ONLY and intentionally excludes `relates_to:` (docstring
  lines 73–77); `ll-issues list --parent` and `set-status --cascade` behave the
  same. The **only** reader that unions `relates_to:` into membership is
  `review-epic` Step 2c (`skills/review-epic/SKILL.md` lines ~70–80) — which is
  exactly BUG-2333. Net: sequence ENH-2330 to land with the BUG-2333 fix; no broad
  transitional period is needed because no other reader depends on `relates_to`
  membership. The `## Children` body section is never read programmatically by any
  reader.
- **Validation pattern to model.** Follow the write→validate→warn shape used by
  loop skills: `skills/review-loop/SKILL.md` (write, run validator, warn on
  failure) and `skills/cleanup-loops/SKILL.md` Step 6 (`[WARN] …` prefix on
  non-zero exit). Surface failures as a non-blocking warning, consistent with
  scope-epic Phase 5c's existing inline patch behavior.

## Acceptance Criteria

- `scope-epic` and `link-epics` no longer add children to the EPIC `relates_to:`
  list (or the behavior is reconciled with ARCHITECTURE-065 and documented).
- Both skills run a post-wiring consistency assertion and surface failures.
- `scripts/tests/test_scope_epic_skill.py` and
  `scripts/tests/test_link_epics_skill.py` updated to reflect the new wiring and
  the validation step.

## Implementation Steps

_Added by `/ll:refine-issue` — concrete, file-referenced steps from research:_

1. **scope-epic** — In `skills/scope-epic/SKILL.md`, remove the child-write from
   Phase 5a (lines ~383–400) and reword the Phase 5 preamble (lines ~377–378,
   which currently says children "appear in the `relates_to` list and `## Children`
   section") so children are carried by `parent:` + `## Children` only. Keep
   Phase 5b (`## Children` bullet) and Phase 5c (`parent:` verify). Leave the
   initial `relates_to: []` placeholder at Phase 4 Step 1 (~line 298) as-is.
2. **link-epics** — In `skills/link-epics/SKILL.md`, remove the child-write from
   Step 6b (lines ~204–237). Keep Step 6a (`parent: EPIC-NNN` on the child) and
   Step 6c (`## Children` bullet).
3. **Post-write assertion (inline)** — Add a check after wiring in both skills:
   re-read each child's `parent:` (must equal the EPIC ID) and confirm the child
   appears exactly once in the EPIC `## Children`; emit a `⚠ …` warning on
   mismatch (model on the `review-loop` / `cleanup-loops` warn pattern). Extend
   scope-epic's existing Phase 5c re-read rather than adding a separate pass. If
   FEAT-2332 has landed, `ll-issues epic-consistency <EPIC>` may replace the
   inline check.
4. **Tests** — Update `scripts/tests/test_scope_epic_skill.py` and
   `scripts/tests/test_link_epics_skill.py` (note: the AC above says
   `skills/tests/…` but the files actually live under `scripts/tests/…`). Keep the
   existing structural assertions (`test_relates_to_wiring_referenced` still passes
   because the skill still mentions `relates_to`), add a negative assertion that
   children are NOT wired into `relates_to`, and assert the post-write validation
   step is referenced. No change needed to `scripts/tests/test_issue_progress.py`
   (`test_forward_resolution_via_relates_to` / `test_union_deduplication` already
   assert `relates_to` is not membership).
5. **Verify** — Run `python -m pytest scripts/tests/test_scope_epic_skill.py
   scripts/tests/test_link_epics_skill.py scripts/tests/test_issue_progress.py -v`.

## Integration Map

- `skills/scope-epic/SKILL.md` (Phase 5 wiring + new validation step).
- `skills/link-epics/SKILL.md` (Phase 6 wiring + new validation step).
- Depends on FEAT-2332 if reusing `epic-consistency` as the validator.
- Pairs with BUG-2333 (reader side of the same model).

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified against the current codebase:_

**Exact edit sites (verified):**

- `skills/scope-epic/SKILL.md`:
  - Phase 5 preamble (lines ~377–378) — states children "appear in the
    `relates_to` list and `## Children` section"; **also needs editing** (not just
    Phase 5a).
  - Phase 5a (lines ~383–400) — appends each child ID to the EPIC `relates_to:`
    (three-case absent/empty/populated `Edit`). **Remove the child write.**
  - Phase 5b (lines ~403–419) — appends the `## Children` bullet (keep).
  - Phase 5c (lines ~421–423) — already re-reads/patches `parent:` per child;
    extend this for the post-write assertion.
- `skills/link-epics/SKILL.md`:
  - Step 6a (lines ~185–199) — writes `parent: EPIC-NNN` on the child (keep).
  - Step 6b (lines ~204–237) — appends accepted child IDs to EPIC `relates_to:`
    via `Edit` (it explicitly uses `Edit`, not `update_frontmatter`, to preserve
    inline-list notation). **Remove the child write.**
  - Step 6c (lines ~239–254) — appends the `## Children` bullet (keep).
- `skills/capture-issue/SKILL.md` Phase 4c uses the **same** three-case
  `relates_to` + `## Children` wiring — out of scope here, but a likely follow-on
  for consistency.

**Test files — correct paths** (the Acceptance Criteria lists `skills/tests/…`;
the files actually live under `scripts/tests/…`):

- `scripts/tests/test_scope_epic_skill.py` (`TestScopeEpicSkillExists`).
- `scripts/tests/test_link_epics_skill.py` (`TestLinkEpicsSkillExists`,
  `TestUpdateFrontmatterRoundTrip`, `TestParentlessIssueDetection`).
- `scripts/tests/test_issue_progress.py` — confirms the parent:-only reader is
  already correct; no change needed.

## Out of Scope

- Reconciling already-drifted EPICs (FEAT-2332 `--fix`).
- `type:` casing / EPIC-1880 normalization (ENH-2331).

## Impact

- **Priority**: P3 - Consistency/cleanup enhancement; not blocking. Fixes the
  upstream source of `relates_to` overloading that feeds BUG-2333's reader
  divergence, but the system functions today via parent:-aware readers.
- **Effort**: Small-Medium - Edits to two `SKILL.md` wiring phases
  (scope-epic Phase 5, link-epics Phase 6), a shared post-write assertion, and
  updates to two skill test files. Reuses `ll-issues epic-consistency`
  (FEAT-2332) as the validator rather than building a new check.
- **Risk**: Medium - Changes how children are wired into EPIC frontmatter;
  must be sequenced with the reader-side change (BUG-2333) and ARCHITECTURE-065
  so no transitional window leaves readers expecting `relates_to` membership.
  Well-scoped but cross-cutting across the EPIC membership model.
- **Breaking Change**: No - Behavioral change to generated frontmatter only;
  membership readers should already prefer `parent:` per ARCHITECTURE-065.

---
**Open** | Created: 2026-06-26 | Priority: P3


## Session Log
- `/ll:verify-issues` - 2026-06-27T19:13:20 - `35d33eaf-2aad-4754-8c3e-650bb7940593.jsonl`
- `/ll:refine-issue` - 2026-06-26T23:10:38 - `e233d8ff-bda5-44d0-b347-301325d49c53.jsonl`
- `/ll:format-issue` - 2026-06-26T23:01:36 - `6584a8f8-113c-40e2-a4bb-bc7c209c1a03.jsonl`
