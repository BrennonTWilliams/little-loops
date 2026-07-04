---
id: EPIC-2330
title: 'scope-epic/link-epics: stop overloading relates_to + add post-write validation'
type: EPIC
priority: P3
status: done
captured_at: '2026-06-26T22:37:02Z'
completed_at: '2026-06-28T03:12:12Z'
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
confidence_score: 98
outcome_confidence: 80
score_complexity: 17
score_test_coverage: 20
score_ambiguity: 23
score_change_surface: 20
---

# EPIC-2330: Stop overloading `relates_to` in EPIC writers; validate after wiring

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/reference/COMMANDS.md` — remove `relates_to:` from the output descriptions of `scope-epic **Output:**`, `link-epics **Output:**`, and `capture-issue --parent` flag; describe children as wired via `parent:` + `## Children` only.
7. Update `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — in the "This does two things atomically:" list, remove step referencing "Appends the new issue ID to the EPIC's `relates_to:` list".
8. Before running the verify step, update the two breaking tests:
   - `test_scope_epic_skill.py::test_relates_to_wiring_referenced` → convert to absence assertion (child-write heading no longer present).
   - `test_link_epics_skill.py::test_relates_to_field_documented` → convert to absence assertion (Step 6b heading no longer present).
   - Add post-write validation assertions in both skill test files.
   - Inspect `test_wiring_skills_and_commands.py` for any `relates_to` presence assertions covering scope-epic/link-epics.
9. Advisory (follow-on, not blocking): update `scripts/little_loops/sprint.py::load_or_resolve()` docstring to reflect deprecation of `relates_to` forward-lookup under ARCHITECTURE-065; update `scripts/little_loops/recursive_finalize.py::finalize_decomposed_parent()` to stop writing children to EPIC's `relates_to:`.

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

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/sprint.py` — `load_or_resolve()` (lines 321–330) reads EPIC's `relates_to` as `forward_ids = set(epic_info.relates_to)` for membership forward-lookup, unioned with `parent:` backward refs. After ENH-2330 the forward path degrades gracefully to empty for new EPICs (no children lost); advisory — no immediate code change needed, but the docstring ("forward (relates_to:) + backward (parent:) lookup") diverges from ARCHITECTURE-065 and should be updated as a follow-on. [Agent 1/2 finding]
- `scripts/little_loops/recursive_finalize.py` — `finalize_decomposed_parent()` (lines 197–201) writes new child IDs into the EPIC's `relates_to` via `update_frontmatter()` (same anti-pattern as scope-epic Phase 5a). Parallel writer; out of scope for ENH-2330 but a required follow-on to prevent the overloading from reappearing on decomposed-parent workflows. [Agent 2 finding]
- `scripts/little_loops/cli/deps.py` — `forward_ids`/`backward_ids` union for epic membership (lines 277–330); reads `relates_to` as a membership channel. Advisory — degrades gracefully. [Agent 1 finding]
- `skills/capture-issue/SKILL.md` Phase 4c — identical three-channel wiring (`parent:` + `relates_to:` + `## Children`); the issue notes reference it as an out-of-scope follow-on, but it must be updated for full consistency with ARCHITECTURE-065. [Agent 2 finding]
- `skills/create-epics-from-unparented/SKILL.md` — EPIC template at line 259 pre-populates `relates_to: [CHILD_ID_1, CHILD_ID_2, ...]` inline (parallel writer, out of scope). [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/COMMANDS.md` — three output descriptions embed `relates_to:` as membership: (1) `capture-issue --parent` flag description, (2) `link-epics **Output:**`, (3) `scope-epic **Output:**`. All three must drop the `relates_to:` reference once the wiring changes. [Agent 2 finding]
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — under "This does two things atomically:" step 2 reads "Appends the new issue ID to the EPIC's `relates_to:` list and its `## Children` section." Must be updated to drop the `relates_to:` append. [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_

**Tests that will break (must update before verify step):**
- `scripts/tests/test_scope_epic_skill.py::TestScopeEpicSkillExists.test_relates_to_wiring_referenced` (line 55) — asserts `"relates_to" in content` on `skills/scope-epic/SKILL.md`. Once Phase 5a is removed, this will fail. Convert from presence to **absence** assertion: `assert "Add child ID to EPIC relates_to" not in content`. [Agent 3 finding]
- `scripts/tests/test_link_epics_skill.py::TestLinkEpicsSkillExists.test_relates_to_field_documented` (line 58) — asserts `"relates_to:" in SKILL_FILE.read_text()` on `skills/link-epics/SKILL.md`. The entire Step 6b section will be removed; this will fail. Convert to absence assertion: `assert "6b. Update EPIC relates_to:" not in content`. [Agent 3 finding]

**New test assertions to add:**
- `test_scope_epic_skill.py` — add assertion that post-write validation step (`epic-consistency` or inline equivalent) is referenced in `skills/scope-epic/SKILL.md`. [Agent 3 finding]
- `test_link_epics_skill.py` — add assertion that post-write validation step is referenced in `skills/link-epics/SKILL.md`. [Agent 3 finding]

**Additional test file to check:**
- `scripts/tests/test_wiring_skills_and_commands.py` — exercises scope-epic and link-epics skill structural references; inspect for any `relates_to` assertions that need adapting. [Agent 1 finding]

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


## Resolution

- Removed Phase 5a (`relates_to:` child-write) from `skills/scope-epic/SKILL.md`; renamed 5b→5a, 5c→5b.
- Removed Step 6b (`relates_to:` child-write) from `skills/link-epics/SKILL.md`; renamed 6c→6b; added new 6c post-write consistency check.
- Extended both skills with an inline post-write consistency assertion (checks `parent:` field and `## Children` presence) that substitutes for `ll-issues epic-consistency` until FEAT-2332 ships.
- Updated `docs/reference/COMMANDS.md` (3 output descriptions) and `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` to drop `relates_to:` membership language.
- Converted breaking presence-assertions in test files to absence assertions; added `test_post_write_validation_referenced` in both skill test files.

## Session Log
- `ll-auto` - 2026-06-28T03:12:12 - `b51169cf-6c2a-410b-8a70-484c629a0537.jsonl`
- `/ll:ready-issue` - 2026-06-28T02:58:35 - `76af9e89-724d-4481-a3fb-ff870509c133.jsonl`
- `/ll:confidence-check` - 2026-06-27T00:00:00Z - `6b436cf4-e677-490f-8251-57b34b0928fd.jsonl`
- `/ll:wire-issue` - 2026-06-28T01:27:51 - `5be78618-84a3-4f49-9f64-b3ead980bc01.jsonl`
- `/ll:verify-issues` - 2026-06-27T19:13:20 - `35d33eaf-2aad-4754-8c3e-650bb7940593.jsonl`
- `/ll:refine-issue` - 2026-06-26T23:10:38 - `e233d8ff-bda5-44d0-b347-301325d49c53.jsonl`
- `/ll:format-issue` - 2026-06-26T23:01:36 - `6584a8f8-113c-40e2-a4bb-bc7c209c1a03.jsonl`
