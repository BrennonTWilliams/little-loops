---
captured_at: "2026-05-29T01:01:55Z"
discovered_date: 2026-05-28
discovered_by: capture-issue
parent: EPIC-1773
status: cancelled
---

# ENH-1774: Wave 1 — Add `ll_commit` and `playwright_screenshot` Shared Fragments

## Summary

Add two high-ROI shared lib fragments that eliminate duplicated state patterns across 11+ loops combined: `ll_commit` (6+ loops inline the same `/ll:commit` invocation) and `playwright_screenshot` (5 harness loops inline the same `npx playwright screenshot` invocation).

## Current Behavior

**`ll_commit` pattern** — 6+ loops each contain a commit state with an inline prompt action calling `/ll:commit`:

- `dead-code-cleanup.yaml` (commit state)
- `test-coverage-improvement.yaml` (commit state)
- `backlog-flow-optimizer.yaml` (commit state)
- `issue-staleness-review.yaml` (commit state)
- `docs-sync.yaml` (commit state)
- `incremental-refactor.yaml` (commit_step state)

Each duplicates the action text and exit_code evaluator.

**`playwright_screenshot` pattern** — 5 harness loops each inline a shell action running `npx playwright screenshot` with output_contains CAPTURED check:

- `html-website-generator.yaml`
- `svg-image-generator.yaml`
- `html-anything.yaml`
- `hitl-md.yaml`
- `hitl-compare.yaml`

Each duplicates the shell command, wait timeout, file paths, and CAPTURED pattern check.

## Expected Behavior

**`ll_commit` fragment** in `loops/lib/cli.yaml`:

```yaml
ll_commit:
  action_type: prompt
  action: "Run `/ll:commit` to commit the changes. Use message: \"${context.commit_message}\""
  evaluate:
    type: exit_code
```

Callers set `context.commit_message` and route from the fragment.

**`playwright_screenshot` fragment** in new `loops/lib/harness.yaml`:

```yaml
playwright_screenshot:
  action_type: shell
  action: |
    npx playwright screenshot --wait-for-timeout 1000 \
      "file://${context.run_dir}/output.html" \
      "${context.run_dir}/screenshot.png" 2>&1
  evaluate:
    type: output_contains
    pattern: "CAPTURED"
```

Callers set `context.run_dir`.

All 11 callers converted to reference the shared fragments instead of inlining the duplicated logic.

## Motivation

These are the two most-repeated patterns across the entire loop library. A single bugfix or improvement to either pattern currently requires editing 5-6 files. Extracting them as fragments makes behavior consistent and future changes trivial.

## Proposed Solution

1. Add `ll_commit` fragment to `loops/lib/cli.yaml`
2. Create `loops/lib/harness.yaml` with `playwright_screenshot` fragment
3. Convert all 6 `ll_commit` callers to reference the fragment
4. Convert all 5 harness loops to reference the `playwright_screenshot` fragment
5. Run `ll-loop validate` on each modified loop
6. Run `python -m pytest scripts/tests/ -v --tb=short`

## Integration Map

### Files to Modify
- `loops/lib/cli.yaml` — add `ll_commit` fragment
- `loops/lib/harness.yaml` — new file with `playwright_screenshot` fragment
- `loops/dead-code-cleanup.yaml` — convert commit state
- `loops/test-coverage-improvement.yaml` — convert commit state
- `loops/backlog-flow-optimizer.yaml` — convert commit state
- `loops/issue-staleness-review.yaml` — convert commit state
- `loops/docs-sync.yaml` — convert commit state
- `loops/incremental-refactor.yaml` — convert commit_step state
- `loops/html-website-generator.yaml` — convert screenshot state
- `loops/svg-image-generator.yaml` — convert screenshot state
- `loops/html-anything.yaml` — convert screenshot state
- `loops/hitl-md.yaml` — convert screenshot state
- `loops/hitl-compare.yaml` — convert screenshot state

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop_cmd.py` — `ll-loop validate` must resolve fragments from `lib/harness.yaml`

### Similar Patterns
- N/A — these are the canonical instances being deduplicated

### Tests
- `scripts/tests/` — regression suite; verify no loop validation failures

### Documentation
- N/A — no user-facing docs changes

### Configuration
- N/A

## Implementation Steps

1. Add `ll_commit` fragment to `loops/lib/cli.yaml`
2. Create `loops/lib/harness.yaml` with `playwright_screenshot` fragment
3. Convert all `ll_commit` callers to reference the shared fragment
4. Convert all `playwright_screenshot` callers to reference the shared fragment
5. Run `ll-loop validate` on every modified loop
6. Run `python -m pytest scripts/tests/ -v --tb=short` to verify no regressions

## Success Metrics

- `ll_commit` fragment eliminates 6 duplicate commit-state implementations
- `playwright_screenshot` fragment eliminates 5 duplicate screenshot implementations
- All 11 modified loops pass `ll-loop validate`
- Test suite passes with no regressions

## Scope Boundaries

- Fragment creation and caller conversion only — no new loops, no behavioral changes
- Only the two listed fragments; other fragments (convergence_gate, etc.) are in later waves

## API/Interface

N/A - No public API changes

## Impact

- **Priority**: P3 — High ROI cleanup but non-urgent; no user-facing impact
- **Effort**: Small — Two simple fragments, mechanical caller conversion
- **Risk**: Low — Fragments are additive; existing inlined states are well-understood
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Loop system design and fragment resolution |
| guidelines | .claude/CLAUDE.md | Loop authoring conventions |

## Labels

`enhancement`, `captured`

## Session Log
- `/ll:ready-issue` - 2026-06-01T16:33:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/92bcd8b4-38a6-46b1-9488-9de681167c3e.jsonl`
- `/ll:format-issue` - 2026-05-29T01:15:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/da7cd339-298e-476c-b35d-3d604e671cde.jsonl`
- `/ll:capture-issue` - 2026-05-29T01:01:55Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17b05161-9ff0-48f9-baaf-69470f937b48.jsonl`

---

---

## Resolution

- **Status**: Closed - Superseded
- **Completed**: 2026-05-28
- **Reason**: Superseded by ENH-1775 (Wave 2) via `/ll:audit-issue-conflicts` conflict resolution. The `ll_commit` and `playwright_screenshot` fragments are merged into Wave 2, since Wave 2's `generator-evaluator` sub-loop is the primary consumer of the `playwright_screenshot` fragment. Wave 2 must compose from these fragments rather than inlining.

## Status

**Done** | Closed: 2026-05-28 | Priority: P3
