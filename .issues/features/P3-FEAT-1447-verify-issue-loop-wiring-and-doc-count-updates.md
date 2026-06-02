---
id: FEAT-1447
priority: P3
type: FEAT
parent: FEAT-1310
size: Small
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
status: done
completed_at: 2026-05-11T23:56:06Z
---

# FEAT-1447: verify-issue-loop — wiring & doc count updates

## Summary

After FEAT-1446 ships the skill, update the static help catalog and hardcoded skill counts that are enforced by `ll-verify-docs` CI check. This is the registration/doc-update tail of the FEAT-1310 decomposition.

## Parent Issue

Decomposed from FEAT-1310: verify-issue-loop skill (FSM loop generator from issue acceptance criteria)

## Depends On

FEAT-1446 must be merged first (this child updates references to a skill that FEAT-1446 creates).

**Status (2026-05-11):** FEAT-1446 is merged (commit `57ae6786 feat(skill): add verify-issue-loop skill`). `skills/verify-issue-loop/SKILL.md` exists; `ls skills/ | wc -l` returns `30`. This issue is now unblocked and `ll-verify-docs` is failing on the four expected spans (see Integration Map).

## Integration Map

_Added by `/ll:refine-issue` — verified against current tree on 2026-05-11._

### Files to Modify (count strings: 29 → 30)

- `README.md:161` — `- **29 skills** ...` → `- **30 skills** ...` (enforced by `ll-verify-docs`)
- `CONTRIBUTING.md:122` — `├── skills/               # 29 skill definitions ...` → `30 skill definitions` (enforced by `ll-verify-docs`)
- `docs/ARCHITECTURE.md:26` — `SKL[Skills<br/>29 composable skills]` → `30 composable skills` (enforced by `ll-verify-docs`)
- `docs/ARCHITECTURE.md:97` — directory tree line `├── skills/                  # 29 skill definitions` → `30 skill definitions` (enforced by `ll-verify-docs`)

### Files to Modify (skills tree insertion)

- `CONTRIBUTING.md:148–149` — insert `│   ├── verify-issue-loop/            # Generate FSM verification loop from issue acceptance criteria` **immediately before** `│   └── workflow-automation-proposer/` and convert the existing `└──` on line 149 to `├──`. **Correction to acceptance criteria:** `wire-issue/` is NOT present in this tree — alphabetically `verify-issue-loop/` lands directly before `workflow-automation-proposer/` (the current last entry). The "between `wire-issue/` and `workflow-automation-proposer/`" wording in the criteria below is misleading; the operative invariant is that the entry sits alphabetically in the tree and is the new penultimate row.

### Files to Modify (help catalog)

- `commands/help.md:166–186` — `AUTOMATION & LOOPS` verbose block currently lists `create-loop`, `create-eval-from-issues`, `loop-suggester`, `audit-loop-run`. Add a `verify-issue-loop` stanza parallel to the `create-eval-from-issues` stanza at lines 171–174 (i.e., 3-line block with command signature, summary, and output path).
- `commands/help.md:291` — `**Automation & Loops**: create-loop, create-eval-from-issues, loop-suggester, audit-loop-run` → append `, verify-issue-loop`.

### Tests / CI Dependents

- `scripts/tests/test_feat1287_doc_wiring.py:56–92` — **NOT in current acceptance criteria but will break.** Hardcoded assertions:
  - `TestReadmeSkillCount.test_skill_count_updated` asserts `"29 skills" in README` AND `"28 skills" not in README` (lines 61–62)
  - `TestContributingWiring.test_skill_count_updated` asserts `"29 skill definitions" in CONTRIBUTING` (line 70)
  - `TestClaudeMdWiring.test_skill_count_updated` asserts `"(29 skills)" in CLAUDE_MD` (line 86)
  Update each `29` → `30` and each prior `28`-style negative assertion → `29`.
- `.claude/CLAUDE.md:38` — `# Skill definitions (29 skills)` → `(30 skills)`. **Not currently enforced by `ll-verify-docs`** (CLAUDE.md is not in its scan list) but asserted by `TestClaudeMdWiring` above, so it must be updated when the test is updated.

### `ll-verify-docs` Baseline

Current run (verified 2026-05-11) reports 5 mismatches:

```
skills: documented=29, actual=30   at README.md:161
skills: documented=29, actual=30   at CONTRIBUTING.md:122
skills: documented=0,  actual=30   at CONTRIBUTING.md:521
skills: documented=29, actual=30   at docs/ARCHITECTURE.md:26
skills: documented=29, actual=30   at docs/ARCHITECTURE.md:97
```

The `documented=0` hit at `CONTRIBUTING.md:521` is a likely **false positive** in `verify_documentation()` — line 521 reads `... 2000-token budget — shorten descriptions or tag more skills with disable-model-invocation: true ...`, which the scanner appears to parse as `0 skills`. Not in scope here; flag for a follow-up `ll-verify-docs` regex tightening if it persists after the four real fixes.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/doc_counts.py` — implements `verify_documentation()` and `check_skill_budget()`; auto-discovers `skills/*/SKILL.md` via glob, so `verify-issue-loop/SKILL.md` is picked up automatically. **No code changes needed** — the skill count mismatch is what drives CI failures.
- `scripts/little_loops/cli/docs.py` — entry points `main_verify_docs()` and `main_verify_skill_budget()`. **No changes needed.**

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — contains a quick-reference table (~line 792–797) listing all loop skills (`create-loop`, `create-eval-from-issues`, `loop-suggester`, `review-loop`, `debug-loop-run`, `audit-loop-run`, `cleanup-loops`, `rename-loop`, `workflow-automation-proposer`). `verify-issue-loop` is **absent**. The file also lacks a `### /ll:verify-issue-loop` subsection parallel to other loop skills. Not enforced by `verify_documentation()` (not in `DOC_FILES`) and has no test assertion, so CI will not catch this automatically.

### Correction: `.claude/CLAUDE.md` Skill Listing Already Up-to-Date

_Wiring pass finding:_ `.claude/CLAUDE.md` line 56 (`Automation & Loops:` listing) **already includes** `verify-issue-loop`^ — no change needed to the skill listing row. Only the count comment at line 38 (`(29 skills)` → `(30 skills)`) requires updating.

### Similar Pattern to Follow

- `.issues/features/P2-FEAT-1287-ll-explore-api-skill.md` is the most recent precedent (28→29 bump for the explore-api skill). Its plan (`thoughts/shared/plans/2026-05-11-FEAT-1287-management.md`) and resulting commits show the canonical pattern: same four-file count bump plus `test_feat1287_doc_wiring.py` for assertion updates. Mirror that approach — consider adding `scripts/tests/test_feat1447_doc_wiring.py` (parallel to `test_feat1287_doc_wiring.py`) that asserts `"30 skills"`/`"30 skill definitions"`/`"verify-issue-loop/" in CONTRIBUTING` to lock the new state in.

## Implementation Steps

7. Update `commands/help.md` — add `verify-issue-loop` stanza to the "AUTOMATION & LOOPS" verbose block (parallel to `create-eval-from-issues`) and append `verify-issue-loop` to the `Automation & Loops:` quick-reference comma list.
   - **Note**: `/ll:help` does NOT auto-discover skills — `commands/help.md` is a fully static file.
8. Update skill count from `29` to `30` in:
   - `README.md` (`` `29 skills` `` line)
   - `CONTRIBUTING.md` (`29 skill definitions` line)
   - `docs/ARCHITECTURE.md` (Mermaid node `SKL[Skills<br/>29 composable skills]` and directory tree — two occurrences)
   All four spans are enforced by `ll-verify-docs` via `verify_documentation()` — CI will fail after FEAT-1446 if these are not updated.
9. Insert `verify-issue-loop/` entry into `CONTRIBUTING.md`'s explicit alphabetical skill directory tree (between `wire-issue/` and `workflow-automation-proposer/`).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `docs/reference/COMMANDS.md` — add `verify-issue-loop` row to the loop-skills quick-reference table (~line 792–797) and add a `### /ll:verify-issue-loop` subsection parallel to the other loop-skill subsections (e.g., `create-loop`, `audit-loop-run`). Not CI-enforced, but is the user-facing reference that maintainers consult.
11. When writing `scripts/tests/test_feat1447_doc_wiring.py`, include a `TestArchitectureSkillCount` class with two test methods: `test_mermaid_skill_count_updated` (asserts `"30 composable skills" in content`) and `test_tree_skill_count_updated` (asserts `"# 30 skill definitions" in content`). The ARCHITECTURE.md count lines have **zero existing test coverage** — this is a gap not covered by `test_feat1287_doc_wiring.py`.

## Acceptance Criteria

- [ ] `commands/help.md` AUTOMATION & LOOPS verbose block contains a `verify-issue-loop` stanza parallel to `create-eval-from-issues`.
- [ ] `commands/help.md` quick-reference `Automation & Loops:` comma list includes `verify-issue-loop`.
- [ ] `README.md` skill count reads `` `30 skills` ``.
- [ ] `CONTRIBUTING.md` skill count reads `30 skill definitions`.
- [ ] `docs/ARCHITECTURE.md` Mermaid node reads `SKL[Skills<br/>30 composable skills]`.
- [ ] `docs/ARCHITECTURE.md` directory tree count updated to `30`.
- [ ] `CONTRIBUTING.md` alphabetical skill directory tree includes `verify-issue-loop/` between `wire-issue/` and `workflow-automation-proposer/`.
- [ ] `ll-verify-docs` passes without errors after all updates (the four real spans; the `CONTRIBUTING.md:521` `documented=0` hit is a separate scanner false positive — see Integration Map).
- [ ] `.claude/CLAUDE.md:38` skill-count phrase updated from `(29 skills)` to `(30 skills)`.
- [ ] `scripts/tests/test_feat1287_doc_wiring.py` `TestReadmeSkillCount` / `TestContributingWiring` / `TestClaudeMdWiring` assertions bumped to `30` (and prior negative `28` assertions bumped to `29`); `python -m pytest scripts/tests/test_feat1287_doc_wiring.py` passes.
- [ ] (Recommended) New `scripts/tests/test_feat1447_doc_wiring.py` mirroring the FEAT-1287 pattern asserts `30 skills` / `30 skill definitions` / `verify-issue-loop/` in CONTRIBUTING.md / `verify-issue-loop` in commands/help.md.

## Impact

- **Priority**: P3
- **Effort**: Small — mechanical text edits across 4 files
- **Risk**: Very Low — doc-only changes; CI (`ll-verify-docs`) validates correctness
- **Breaking Change**: No

## Session Log
- `/ll:manage-issue` - 2026-05-11T23:56:06Z - `c68c3c3a-b624-4f70-a5a0-b69ed4de962c.jsonl`
- `/ll:ready-issue` - 2026-05-11T23:49:05 - `548f2518-e860-4fc5-b4e4-5adf74b19e8e.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00Z - `d6fbd4c8-ff6c-4c9d-82fd-2417bede4ffa.jsonl`
- `/ll:wire-issue` - 2026-05-11T23:45:50 - `046d7355-7a57-46cc-b2a7-69260e6df370.jsonl`
- `/ll:refine-issue` - 2026-05-11T23:41:12 - `34d8a666-5ea7-481a-9ce9-bff27bd8aae5.jsonl`
- `/ll:issue-size-review` - 2026-05-11T00:00:00Z - `03785380-ad15-4700-be73-f3d5f0c746ce.jsonl`

---

## Resolution

Completed 2026-05-11. All four `ll-verify-docs`-enforced spans bumped 29→30, `verify-issue-loop/` inserted in the CONTRIBUTING.md alphabetical skill tree, and the help catalog updated in both verbose and quick-reference forms. Added `docs/reference/COMMANDS.md` quick-ref table row and a `### /ll:verify-issue-loop` subsection. Bumped `test_feat1287_doc_wiring.py` assertions 29→30 and added `test_feat1447_doc_wiring.py` (8 tests) mirroring the FEAT-1287 pattern with new `TestArchitectureSkillCount` coverage for the previously-unasserted ARCHITECTURE.md count lines. `ll-verify-docs` now reports only the known `CONTRIBUTING.md:522` `documented=0` scanner false positive on the "2000-token budget" line (out of scope per the Integration Map). All 23 doc-wiring tests pass; ruff clean.

## Status
- **Status**: Completed
- **Discovered**: 2026-05-11
- **Discovered by**: issue-size-review
- **Completed**: 2026-05-11
