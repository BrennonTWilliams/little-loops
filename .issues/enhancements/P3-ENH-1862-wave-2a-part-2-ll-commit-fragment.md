---
id: ENH-1862
title: "Wave 2a Part 2 — Create `ll_commit` Fragment, Convert 6 Commit Loops, and Wire Docs"
type: ENH
priority: P3
captured_at: '2026-06-01T00:00:00Z'
discovered_date: 2026-06-01
parent: ENH-1854
relates_to:
- ENH-1854
- ENH-1775
- EPIC-1773
status: open
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

## Codebase Research Findings

### Fragment Placement Constraint

`test_all_fragments_are_shell_type` (line 879) and `test_all_fragments_have_exit_code_evaluate` (line 886) in `scripts/tests/test_fsm_fragments.py` unconditionally assert ALL fragments in `lib/cli.yaml` have `action_type == "shell"` and `evaluate.type == "exit_code"`. `ll_commit` (`action_type: prompt`, no evaluate) MUST NOT go in `lib/cli.yaml`. It must go in the new `lib/prompt-fragments.yaml`.

### ⚠ Design Constraint: `incremental-refactor.yaml` Commit Message

Current `commit_step` state has no commit message. After adopting `ll_commit`, the state will have `action: /ll:commit ${context.commit_message}` with `action_type: slash_command` (via deep-merge override). Must either:
- Add `context.commit_message: "refactor: apply incremental refactoring step"` at the state level
- Or override `action: "/ll:commit"` at the state level (dropping the message parameter)

Recommended: add `context.commit_message: "refactor: apply incremental refactoring step"`.

### Test File Structure

- `scripts/tests/test_fsm_fragments.py:TestScorePlanQualityFragment:1199-1255` — use as exact template for new `TestLlCommitFragment` class (4-test shape: `_load_yaml`, `test_ll_commit_defined`, `test_ll_commit_has_prompt_action_type`, `test_ll_commit_has_description`, `test_ll_commit_resolves_in_loop` using `resolve_fragments` with `import: ["lib/prompt-fragments.yaml"]`)
- `scripts/tests/test_builtin_loops.py:TestLearningTestsAuditLoop:507` — use for minimal structural test class pattern. Fragment assertion idiom: `assert state.get("fragment") == "ll_commit"`
- 6 commit-loop target loops have NO existing test classes — add minimal structural tests alongside each conversion

### Wiring: Documentation Stale Enumerations

- `docs/guides/AUDIT_REPORT.md:90` — explicitly enumerates known fragment library files (`common.yaml`, `cli.yaml`, `benchmark.yaml`); will be stale once `prompt-fragments.yaml` exists
- `docs/reference/CLI.md:645-647` and `755-757` — two `ll-loop fragments` example blocks enumerate built-in libraries by name; `prompt-fragments.yaml` must be added to both

## Integration Map

### Files to Create

- `loops/lib/prompt-fragments.yaml` — new library file with `ll_commit` fragment

### Files to Modify

- `loops/dead-code-cleanup.yaml` — convert `commit` state (lines 94-99)
- `loops/test-coverage-improvement.yaml` — convert `commit` state (lines 198-204)
- `loops/backlog-flow-optimizer.yaml` — convert `commit` state (lines 126-131)
- `loops/issue-staleness-review.yaml` — convert `commit` state (lines 67-72)
- `loops/docs-sync.yaml` — convert `commit` state (lines 57-62)
- `loops/incremental-refactor.yaml` — convert `commit_step` state (lines 34-37; structural outlier)
- `docs/guides/AUDIT_REPORT.md` — add `prompt-fragments.yaml` at line 90
- `docs/reference/CLI.md` — add `lib/prompt-fragments.yaml` to example blocks at lines 645-647 and 755-757

### Tests

- `scripts/tests/test_fsm_fragments.py` — new `TestLlCommitFragment` class following `TestScorePlanQualityFragment:1199` pattern
- `scripts/tests/test_builtin_loops.py` — 6 new minimal structural test classes (one per target loop): assert commit/commit_step state exists and uses `fragment: ll_commit`

### Documentation

- `docs/guides/LOOPS_GUIDE.md` — add `ll_commit` to fragment tables
- `skills/create-loop/reference.md` — add `ll_commit` to fragment catalog

## Implementation Steps

1. **Create `loops/lib/prompt-fragments.yaml`** — new library file. Define `ll_commit` fragment with `action_type: prompt`, `description:`, and `action: /ll:commit ${context.commit_message}`. Follow `lib/score-plan-quality.yaml` structure as template.

2. **Convert 6 commit loops** to use `ll_commit` fragment — For each state, replace inline body with `fragment: ll_commit` + `context.commit_message: "<loop-specific message>"`. For `incremental-refactor.yaml` (structural outlier): add `fragment: ll_commit` + `action_type: slash_command` (override) + `context.commit_message: "refactor: apply incremental refactoring step"`. Ensure `next:` and any other routing fields are preserved on the state.

3. **Add `TestLlCommitFragment` test class** in `scripts/tests/test_fsm_fragments.py` following `TestScorePlanQualityFragment:1199` pattern (4-test shape: `_load_yaml`, `test_ll_commit_defined`, `test_ll_commit_has_prompt_action_type`, `test_ll_commit_has_description`, `test_ll_commit_resolves_in_loop`).

4. **Add 6 minimal structural test classes** in `scripts/tests/test_builtin_loops.py` — one per target loop. Assert the commit/commit_step state exists and uses `fragment: ll_commit`. Follow `TestLearningTestsAuditLoop:507` pattern.

5. **Validate 6 modified loops** — `ll-loop validate` on all 6. Fix any ERROR-severity issues.

6. **Run regression suite** — `python -m pytest scripts/tests/test_fsm_fragments.py scripts/tests/test_builtin_loops.py -v --tb=short`. Verify `test_all_fragments_are_shell_type` and `test_all_fragments_have_exit_code_evaluate` still pass (ll_commit is NOT in cli.yaml).

7. **Update wiring docs** — Update `docs/guides/AUDIT_REPORT.md:90` to add `prompt-fragments.yaml`. Update `docs/reference/CLI.md:645-647` and `755-757` to add `lib/prompt-fragments.yaml` to example blocks.

8. **Update documentation** — Add `ll_commit` to fragment tables in `docs/guides/LOOPS_GUIDE.md` and `skills/create-loop/reference.md`.

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

## Session Log
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2cacc3f7-f908-4e86-8ef8-b96c1b43a157.jsonl`
