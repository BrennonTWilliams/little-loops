---
id: ENH-1862
title: "Wave 2a Part 2 \u2014 Create `ll_commit` Fragment, Convert 6 Commit Loops,\
  \ and Wire Docs"
type: ENH
priority: P3
captured_at: '2026-06-01T00:00:00Z'
completed_at: '2026-06-01T19:03:38Z'
discovered_date: 2026-06-01
parent: ENH-1854
relates_to:
- ENH-1854
- ENH-1775
- EPIC-1773
status: done
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1862: Wave 2a Part 2 — Create `ll_commit` Fragment, Convert 6 Commit Loops, and Wire Docs

## Summary

Create `loops/lib/prompt-fragments.yaml` with an `ll_commit` fragment, convert 6 loops that duplicate commit-state logic to use it, add structural tests for all 6 target loops, and update documentation to include `prompt-fragments.yaml` in fragment library enumerations.

## Parent Issue

Decomposed from ENH-1854: Wave 2a — Add `parse_tagged_json` and `ll_commit` Fragments

## Current Behavior

6 loops each inline a near-identical `action_type: prompt` commit state:

| Loop | State | Lines | `action_type` | `next` |
|------|-------|-------|---------------|--------|
| `dead-code-cleanup.yaml` | `commit` | 94-99 | `prompt` | `scan` |
| `test-coverage-improvement.yaml` | `commit` | 198-204 | `prompt` | `measure` |
| `backlog-flow-optimizer.yaml` | `commit` | 126-131 | `prompt` | `measure` |
| `issue-staleness-review.yaml` | `commit` | 67-72 | `prompt` | `find_stale` |
| `docs-sync.yaml` | `commit` | 57-62 | `prompt` | `verify_docs` |
| `incremental-refactor.yaml` | `commit_step` | 34-37 | `slash_command` | `check_complete` |

`loops/lib/prompt-fragments.yaml` does not exist.

### Exact Current Commit State YAML (all 6)

**`dead-code-cleanup.yaml:94-99`:**
```yaml
  commit:
    action_type: prompt
    action: |
      Run `/ll:commit` to commit the dead code removal.
      Use message: "refactor: remove dead code identified by scan"
    next: scan
```

**`test-coverage-improvement.yaml:198-204`:**
```yaml
  commit:
    # Commit the new tests and remeasure coverage.
    action_type: prompt
    action: |
      Run `/ll:commit` to commit the new tests.
      Use a message like: "test: add coverage for <module/function name>"
    next: measure
```

**`backlog-flow-optimizer.yaml:126-131`:**
```yaml
  commit:
    action_type: prompt
    action: |
      Run `/ll:commit` to commit the backlog changes.
      Use message: "chore(issues): optimize backlog flow"
    next: measure
```

**`issue-staleness-review.yaml:67-72`:**
```yaml
  commit:
    action_type: prompt
    action: |
      Run `/ll:commit` to commit the issue triage changes.
      Use message: "chore(issues): triage stale issues"
    next: find_stale
```

**`docs-sync.yaml:57-62`:**
```yaml
  commit:
    action_type: prompt
    action: |
      Run `/ll:commit` to commit the documentation fixes.
      Use message: "docs: sync documentation with codebase state"
    next: verify_docs
```

**`incremental-refactor.yaml:34-37` (structural outlier — `slash_command`, no message):**
```yaml
  commit_step:
    action: "/ll:commit"
    action_type: slash_command
    next: check_complete
```

## Expected Behavior

**`ll_commit` fragment** in `loops/lib/prompt-fragments.yaml` (new file):

```yaml
ll_commit:
  description: Commit staged changes via /ll:commit with a parameterized message
  action_type: prompt
  action: |
    /ll:commit ${context.commit_message}
```

The first 5 loops supply `context.commit_message` with a loop-specific message. `incremental-refactor.yaml` overrides `action_type: slash_command` at the state level via deep-merge (fragment provides base, state fields override).

`loops/lib/prompt-fragments.yaml` follows the `lib/score-plan-quality.yaml` structure as template (comment block explaining import/usage, single `fragments:` key, each fragment has `description:`, `action_type:`, and optional base fields).

**Unlike `score_plan_quality`**, `ll_commit` DOES define `action:` in the fragment body — the action is always `/ll:commit ${context.commit_message}`. The caller only needs to supply `context.commit_message` in the loop's `context:` block (not override `action:` at the state level).

## Codebase Research Findings

### Fragment Placement Constraint

`test_all_fragments_are_shell_type` (line **922**) and `test_all_fragments_have_exit_code_evaluate` (line **929**) in `scripts/tests/test_fsm_fragments.py` unconditionally assert ALL fragments in `lib/cli.yaml` have `action_type == "shell"` and `evaluate.type == "exit_code"`. `ll_commit` (`action_type: prompt`, no evaluate) MUST NOT go in `lib/cli.yaml`. It must go in the new `lib/prompt-fragments.yaml`.

### ⚠ Design Constraint: `incremental-refactor.yaml` Commit Message

Current `commit_step` state has no commit message. After adopting `ll_commit`, the state will have `action: /ll:commit ${context.commit_message}` with `action_type: slash_command` (via deep-merge override). Must either:
- Add `commit_message: "refactor: apply incremental refactoring step"` to the existing `context:` block (lines 8-10)
- Or override `action: "/ll:commit"` at the state level (dropping the message parameter)

Recommended: add `commit_message: "refactor: apply incremental refactoring step"` to the `context:` block.

### ⚠ Context Block Wiring — Per-Loop Requirements

Each converted loop must have `context.commit_message` resolvable at runtime. The 6 loops differ in their current wiring state:

| Loop | Has `context:` block? | Has `import:` block? | Action needed |
|------|-----------------------|----------------------|---------------|
| `dead-code-cleanup.yaml` | **No** | Yes (line 10) | Add new `context:` block with `commit_message`; add `lib/prompt-fragments.yaml` to existing `import:` |
| `test-coverage-improvement.yaml` | Yes (line 18) | Yes (line 23) | Add `commit_message:` key to existing `context:`; add to `import:` |
| `backlog-flow-optimizer.yaml` | Yes (line 10) | **No** | Add `commit_message:` key to existing `context:`; add new `import:` block |
| `issue-staleness-review.yaml` | Yes (line 9) | **No** | Add `commit_message:` key to existing `context:`; add new `import:` block |
| `docs-sync.yaml` | **No** | Yes (line 11) | Add new `context:` block with `commit_message`; add to `import:` |
| `incremental-refactor.yaml` | Yes (line 8) | **No** | Add `commit_message:` key to existing `context:`; add new `import:` block |

3 loops need a new `import:` block (backlog-flow-optimizer, issue-staleness-review, incremental-refactor). 2 loops need a new `context:` block (dead-code-cleanup, docs-sync).

### Test File Structure

- `scripts/tests/test_fsm_fragments.py:TestScorePlanQualityFragment:1242-1297` — use as exact template for new `TestLlCommitFragment` class (4-test shape: `_load_yaml` static method, `test_ll_commit_defined`, `test_ll_commit_has_prompt_action_type`, `test_ll_commit_has_description`, `test_ll_commit_resolves_in_loop` using `resolve_fragments` with `import: ["lib/prompt-fragments.yaml"]`)
- `scripts/tests/test_fsm_fragments.py:TestCommonYamlNewFragments:523` — alternative template: `parse_tagged_json` 4-test variation at lines 664-705; shows how to handle the `resolves_in_loop` integration test when the fragment DOES define `action:`
- `scripts/tests/test_builtin_loops.py:TestLearningTestsAuditLoop:507` — use for minimal structural test class pattern. Fragment assertion idiom: `assert state.get("fragment") == "ll_commit"`
- 6 commit-loop target loops have NO existing test classes — add minimal structural tests alongside each conversion

### `resolve_fragments` Deep-Merge Semantics

`scripts/little_loops/fsm/fragments.py:resolve_fragments:64` — state-level fields WIN over fragment base fields. `description:` is stripped from the fragment copy before merging (popped at line ~136) — it is metadata only, never appears in the resolved state. `${context.commit_message}` in the fragment's `action:` is interpolated at runtime by `scripts/little_loops/fsm/interpolation.py:interpolate`, NOT at fragment-resolve time. Fragment resolution is a pure parse-time YAML merge.

### Wiring: Documentation Stale Enumerations

- `docs/guides/AUDIT_REPORT.md:90` — explicitly enumerates known fragment library files (`common.yaml`, `cli.yaml`, `benchmark.yaml`); will be stale once `prompt-fragments.yaml` exists
- `docs/reference/CLI.md:644-648` and `755-757` — two `ll-loop fragments` example blocks enumerate built-in libraries by name; `prompt-fragments.yaml` must be added to both
- `docs/guides/LOOPS_GUIDE.md:3148-3248` — "Built-in Libraries" section with fragment tables for `lib/common.yaml`, `lib/benchmark.yaml`, `lib/score-plan-quality.yaml`, `lib/cli.yaml`; needs new `lib/prompt-fragments.yaml` section with `ll_commit` row
- `skills/create-loop/reference.md:1109-1128` — "Fragment Catalog" section; needs `ll_commit` row under a new `lib/prompt-fragments.yaml` entry

## Integration Map

### Files to Create

- `loops/lib/prompt-fragments.yaml` — new library file with `ll_commit` fragment

### Files to Modify

- `loops/dead-code-cleanup.yaml` — convert `commit` state (lines 94-99); add `context:` block; add `lib/prompt-fragments.yaml` to existing `import:` (line 10)
- `loops/test-coverage-improvement.yaml` — convert `commit` state (lines 198-204); add `commit_message:` to existing `context:` (line 18); add `lib/prompt-fragments.yaml` to existing `import:` (line 23)
- `loops/backlog-flow-optimizer.yaml` — convert `commit` state (lines 126-131); add `commit_message:` to existing `context:` (line 10); add new `import:` block
- `loops/issue-staleness-review.yaml` — convert `commit` state (lines 67-72); add `commit_message:` to existing `context:` (line 9); add new `import:` block
- `loops/docs-sync.yaml` — convert `commit` state (lines 57-62); add `context:` block; add `lib/prompt-fragments.yaml` to existing `import:` (line 11)
- `loops/incremental-refactor.yaml` — convert `commit_step` state (lines 34-37; structural outlier); add `commit_message:` to existing `context:` (line 8); add new `import:` block
- `docs/guides/AUDIT_REPORT.md` — add `prompt-fragments.yaml` at line 90
- `docs/reference/CLI.md` — add `lib/prompt-fragments.yaml` to example blocks at lines 644-648 and 755-757
- `docs/guides/LOOPS_GUIDE.md` — add `lib/prompt-fragments.yaml` section with `ll_commit` row to "Built-in Libraries" section (lines 3148-3248); update "Four libraries" count to "Five libraries"
- `skills/create-loop/reference.md` — add `ll_commit` row under new `lib/prompt-fragments.yaml` entry in "Fragment Catalog" section (lines 1109-1128)
- `scripts/little_loops/loops/README.md` — add `lib/prompt-fragments.yaml` row to "Fragment Libraries" table (line 165); add `ll-loop fragments lib/prompt-fragments.yaml` example command (line 191) [wiring pass]

### Tests

- `scripts/tests/test_fsm_fragments.py` — new `TestLlCommitFragment` class following `TestScorePlanQualityFragment:1242` pattern
- `scripts/tests/test_builtin_loops.py` — 6 new minimal structural test classes (one per target loop): assert commit/commit_step state exists and uses `fragment: ll_commit`

### Documentation

- `docs/guides/LOOPS_GUIDE.md` — add `ll_commit` to fragment tables
- `skills/create-loop/reference.md` — add `ll_commit` to fragment catalog

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/README.md` — enumerates all fragment library files by name in "Fragment Libraries" table (lines 162-165) and in `ll-loop fragments` example commands (lines 190-191); needs `lib/prompt-fragments.yaml` row added [Agent 1 + Agent 2 finding]

## Implementation Steps

1. **Create `loops/lib/prompt-fragments.yaml`** — new library file. Follow `lib/score-plan-quality.yaml` (header comment explaining import/usage, single `fragments:` key). Define `ll_commit` fragment with `action_type: prompt`, `description:`, and `action: /ll:commit ${context.commit_message}`. Unlike `score_plan_quality`, `ll_commit` SHOULD define `action:` in the fragment body.

2. **Convert 6 commit loops** — For each loop, make three changes: (a) add `lib/prompt-fragments.yaml` to the `import:` block (creating the block if it doesn't exist); (b) add `commit_message: "<loop-specific message>"` to the `context:` block (creating the block if it doesn't exist); (c) replace the inline commit state body with `fragment: ll_commit` while preserving `next:` and all other routing fields. For `incremental-refactor.yaml`: also add `action_type: slash_command` as a state-level override to preserve `slash_command` behavior.

3. **Add `TestLlCommitFragment` test class** in `scripts/tests/test_fsm_fragments.py` following `TestScorePlanQualityFragment:1242` pattern (4-test shape: `_load_yaml` staticmethod resolving to `lib/prompt-fragments.yaml`, `test_ll_commit_defined`, `test_ll_commit_has_prompt_action_type`, `test_ll_commit_has_description`, `test_ll_commit_resolves_in_loop`). In `test_ll_commit_resolves_in_loop`, the resolved state should have `action_type == "prompt"` and `action == "/ll:commit ${context.commit_message}"` (fragment action passes through; no caller `action:` override).

4. **Add 6 minimal structural test classes** in `scripts/tests/test_builtin_loops.py` — one per target loop. Follow `TestLearningTestsAuditLoop:507` pattern (LOOP_FILE constant, `data` fixture, `test_required_top_level_fields`, `test_required_states_exist`, fragment-specific assertion). Assert the commit/commit_step state exists and uses `fragment: ll_commit`.

5. **Validate 6 modified loops** — `ll-loop validate` on all 6. Fix any ERROR-severity issues.

6. **Run regression suite** — `python -m pytest scripts/tests/test_fsm_fragments.py scripts/tests/test_builtin_loops.py -v --tb=short`. Verify `test_all_fragments_are_shell_type` (line 922) and `test_all_fragments_have_exit_code_evaluate` (line 929) still pass (ll_commit is NOT in cli.yaml).

7. **Update wiring docs** — Update `docs/guides/AUDIT_REPORT.md:90` to add `prompt-fragments.yaml`. Update `docs/reference/CLI.md:644` and `:755` to add `lib/prompt-fragments.yaml` to both example blocks. Update `scripts/little_loops/loops/README.md:165` to add `lib/prompt-fragments.yaml` row to "Fragment Libraries" table and add `ll-loop fragments lib/prompt-fragments.yaml` example command at line 191.

8. **Update documentation** — Add `ll_commit` to fragment tables in `docs/guides/LOOPS_GUIDE.md:3148` (new `lib/prompt-fragments.yaml` section in "Built-in Libraries") and `skills/create-loop/reference.md:1109` (new row in "Fragment Catalog" section).

## Success Metrics

- `ll_commit` fragment eliminates 6 duplicate commit-state implementations
- All 6 modified loops pass `ll-loop validate`
- `test_all_fragments_are_shell_type` and `test_all_fragments_have_exit_code_evaluate` still pass
- New `TestLlCommitFragment` class passes (4 tests)
- 6 new minimal structural test classes pass
- Documentation enumerations include `prompt-fragments.yaml`
- Full regression suite passes

## Impact

- **Priority**: P3
- **Effort**: Small — mechanical substitution across 6 enumerated files plus new test classes
- **Risk**: Low — `prompt-fragments.yaml` is a new file (no existing callers); commit state conversions are isolated per-loop; test assertions on `action_type` in cli.yaml unaffected

## Labels

`enhancement`, `fragments`, `loops`, `refactoring`

## Status

**Open** | Created: 2026-06-01 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-01T18:57:20 - `eb6e93ea-e494-4ca8-8920-3a041bd01f0c.jsonl`
- `/ll:wire-issue` - 2026-06-01T18:50:11 - `3cd19c9f-6780-4c0b-8ecb-81ed7d5d8630.jsonl`
- `/ll:refine-issue` - 2026-06-01T18:44:10 - `c2378c0a-2bf5-4f29-84da-cb4e09635135.jsonl`
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `2cacc3f7-f908-4e86-8ef8-b96c1b43a157.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00Z - `d7130e47-1d39-4176-b6ac-edaabbcc8f05.jsonl`
