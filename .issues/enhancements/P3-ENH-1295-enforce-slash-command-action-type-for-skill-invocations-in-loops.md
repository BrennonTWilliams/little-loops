---
id: ENH-1295
type: ENH
priority: P3
status: done
completed_at: 2026-04-26T00:00:00Z
---

# ENH-1295: Enforce slash_command action_type for skill invocations in loops

## Summary

Audit all built-in loop YAML files and fix any state that invokes a `/ll:*` skill using a long `action_type: prompt` prose block instead of the clean `action_type: slash_command` pattern established in `autodev.yaml`.

## Problem

The correct pattern for a state whose sole purpose is invoking a skill is:

```yaml
action: "/ll:skill-name args"
action_type: slash_command
```

Several loops were using `action_type: prompt` with multi-line prose like "Run `/ll:skill-name` to do X. Focus on Y. Do not Z." This is wrong because:
- Behavior that belongs in the skill gets buried in loop YAML
- It adds an unnecessary Claude intermediary layer (prose → Claude → Skill tool → subprocess)
- It's harder to maintain: logic lives in two places

## Changes Made

Audited all 48 loop YAML files. Three confirmed violations fixed:

### `issue-size-split.yaml` — `find_large`
```yaml
# Before: 3-line prose describing what the skill does
action_type: prompt
action: |
  Run `/ll:issue-size-review` to evaluate the size and complexity of
  all active issues. Identify any issues that are too large for a
  single implementation session.

# After
action: "/ll:issue-size-review"
action_type: slash_command
```

### `issue-discovery-triage.yaml` — `discover`
```yaml
# Before: 3-line prompt with guidance that belongs in the skill
action_type: prompt
action: |
  Run `/ll:scan-codebase` to discover new technical issues in the codebase.
  Focus on genuine bugs, missing error handling, and code quality problems.
  Do not re-file issues that already exist in .issues/.

# After
action: "/ll:scan-codebase"
action_type: slash_command
```

### `fix-quality-and-tests.yaml` — `analyze-type-errors`
```yaml
# Before: 11-line prompt that ran the skill then asked Claude to categorize output
action_type: prompt
action: |
  Run `/ll:check-code types` to get the current type errors.
  If mypy exits cleanly (no errors), state: "No type errors found."
  Otherwise, categorize the errors found: ...

# After
action: "/ll:check-code types"
action_type: slash_command
```

The downstream `fix-type-errors` state's guard condition was also updated (from checking for the literal string "No type errors found" to checking whether mypy reports no issues) since the simplified state now captures raw mypy output instead of Claude-generated prose.

## Acceptable Exceptions

These patterns were reviewed and kept as `action_type: prompt` intentionally:

- **Commit states** (2 lines): pass a specific commit message the skill can't receive as a CLI arg
- **`sprint-build-and-validate.yaml`** states: must tell Claude to read `${captured.sprint_name.output}.yaml` before calling the skill — the sprint file path is runtime context
- **`backlog-flow-optimizer.yaml`** `close_dead_weight`: uses `${context.stale_threshold_days}` runtime variable in guidance
- **`backlog-flow-optimizer.yaml`** `fix_oversized`: multi-step orchestration across two skills
- **`dead-code-cleanup.yaml`** `scan`: exclusion-file context is legitimate runtime state
- **`greenfield-builder.yaml`** and **`eval-driven-development.yaml`** states: pass large `${captured.xxx.output}` blocks that cannot be CLI args

## Verification

All 276 tests passed after changes: `python -m pytest scripts/tests/test_builtin_loops.py -v`

---

**Completed** | Session: 2026-04-26
