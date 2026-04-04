---
id: ENH-947
type: ENH
priority: P4
status: open
discovered_date: 2026-04-04
discovered_by: capture-issue
---

# ENH-947: Expand lib/common.yaml with More Reusable State Fragments

## Summary

Add `llm_gate` and `numeric_gate` fragments to `scripts/little_loops/loops/lib/common.yaml` to cover the two most common evaluate-block shapes beyond `shell_exit`. Both patterns appear in 7–8+ built-in loops and require callers to repeat the same `action_type` + `evaluate.type` boilerplate on every use.

## Current Behavior

`lib/common.yaml` has two fragments:

- `shell_exit` — `action_type: shell` + `evaluate.type: exit_code` — used in all 10 quality-check loops
- `retry_counter` — complete retry-counter action template

States that use `action_type: prompt` with `evaluate.type: llm_structured`, or `action_type: shell` with `evaluate.type: output_numeric`, must repeat those two fields manually every time. Based on a codebase scan of all 35 built-in loops:

- **`llm_structured` evaluator**: 8+ loops (`general-task`, `refine-to-ready-issue`, `sprint-build-and-validate`, `eval-driven-development`, `issue-staleness-review`, `issue-size-split`, `harness-multi-item`, `harness-single-shot`)
- **`output_numeric` evaluator**: 7+ loops (`issue-discovery-triage`, `incremental-refactor`, `dead-code-cleanup`, `worktree-health`, `rl-rlhf`, `harness-single-shot`, `harness-multi-item`)

## Expected Behavior

Two new fragments available in `lib/common.yaml`:

```yaml
# llm_gate: LLM prompt state evaluated by structured yes/no output.
# Caller must supply: action (the prompt text), evaluate.prompt (the yes/no question),
# on_yes, on_no (and optionally on_error, timeout, capture)
llm_gate:
  action_type: prompt
  evaluate:
    type: llm_structured

# numeric_gate: Shell command evaluated by numeric output comparison.
# Caller must supply: action (shell command that prints a number),
# evaluate.operator (eq|lt|gt|ge|le), evaluate.target (threshold),
# on_yes, on_no (and optionally on_error, timeout, capture)
numeric_gate:
  action_type: shell
  evaluate:
    type: output_numeric
```

Example usage after migration:

```yaml
# Before
check_done:
  action_type: prompt
  action: "Is the task complete? Answer YES or NO."
  evaluate:
    type: llm_structured
    prompt: "Is the task complete?"
  on_yes: done
  on_no: execute

# After
check_done:
  fragment: llm_gate
  action: "Is the task complete? Answer YES or NO."
  evaluate:
    prompt: "Is the task complete?"
  on_yes: done
  on_no: execute
```

```yaml
# Before
count_stale:
  action: "ll-issues list --json | python3 -c '...' | wc -l"
  action_type: shell
  evaluate:
    type: output_numeric
    operator: gt
    target: 0
  on_yes: review
  on_no: done

# After
count_stale:
  fragment: numeric_gate
  action: "ll-issues list --json | python3 -c '...' | wc -l"
  evaluate:
    operator: gt
    target: 0
  on_yes: review
  on_no: done
```

## Motivation

- **Consistency with `shell_exit`**: `shell_exit` already establishes the pattern of sharing `action_type` + `evaluate.type` as a fragment. `llm_gate` and `numeric_gate` are the same pattern applied to the next two most common evaluate types.
- **Reduces authoring errors**: LLM states missing `action_type: prompt` silently fall back to default behavior; numeric states with wrong `evaluate.type` produce confusing routing failures. A fragment makes the correct shape the default.
- **Scope**: These two fragments cover the most frequent patterns. Lower-frequency patterns (`output_contains`, `convergence`) have fewer instances and higher per-use variation — not worth fragmenting.

## Proposed Solution

Add both fragment definitions to `scripts/little_loops/loops/lib/common.yaml` after the existing `retry_counter` definition. No other files need to change immediately — migration of existing loops is optional and can be done incrementally.

Fragment definitions are additive; all existing loops continue to work unchanged.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/lib/common.yaml` — add `llm_gate` and `numeric_gate` fragment definitions

### Dependent Files (Callers/Importers)
- All 35 loop YAML files already `import: ["lib/common.yaml"]` via the `shell_exit` pattern — no changes needed for adoption
- Loops that currently don't use any fragment would need to add `import: ["lib/common.yaml"]` to use the new fragments

### Similar Patterns
- `shell_exit` in `lib/common.yaml` — the direct precedent; match its comment style and "caller must supply" documentation convention
- `retry_counter` in `lib/common.yaml` — precedent for context interpolation in fragment actions

### Tests
- `scripts/tests/test_fsm_fragments.py` — existing fragment tests; add test cases for `llm_gate` and `numeric_gate` using the `tmp_path` + inline YAML write pattern already established there
- `scripts/tests/test_builtin_loops.py` — runs `load_and_validate` on all built-in loops; passes without changes (fragments are additive)

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — "Reusable State Fragments" section (added in FEAT-937); update fragment table to list the new fragments
- `scripts/little_loops/loops/README.md` — update `lib/common.yaml` fragment list if present

### Configuration
- N/A

## Implementation Steps

1. **Add fragments** to `scripts/little_loops/loops/lib/common.yaml`: `llm_gate` (after `retry_counter`) and `numeric_gate` (after `llm_gate`), with matching comment style
2. **Add tests** to `scripts/tests/test_fsm_fragments.py`: deep-merge correctness for both new fragments, verify caller fields override fragment fields
3. **Update docs** in `docs/guides/LOOPS_GUIDE.md`: add `llm_gate` and `numeric_gate` to the fragment reference table
4. **Optional migration**: update 2–3 built-in loops as usage examples (not required for the issue to be complete)

## Impact

- **Priority**: P4 — reduces boilerplate for loop authors; existing loops are unaffected and migration is optional
- **Effort**: Small — two fragment definitions + tests + one doc update; no schema or engine changes needed
- **Risk**: Low — purely additive; `resolve_fragments` already handles arbitrary fragments in `lib/common.yaml`
- **Breaking Change**: No

## Scope Boundaries

- Does not migrate existing loops (optional follow-on)
- Does not add `output_contains`, `convergence`, or other evaluate types — frequency doesn't justify the complexity
- Does not introduce parameterized fragments (e.g., `${context.*}` in the evaluate block) — `llm_gate` and `numeric_gate` are simple type-only fragments like `shell_exit`

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enh`, `fsm`, `loops`, `dx`, `captured`

---

## Status

**Open** | Created: 2026-04-04 | Priority: P4

## Session Log
- `/ll:capture-issue` - 2026-04-04T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f5a4d820-f7ab-4175-bc5f-af74c64b0b11.jsonl`
