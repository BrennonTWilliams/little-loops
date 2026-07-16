---
id: ENH-2658
title: Add `ids` filter to prompt-across-issues loop
type: enhancement
priority: P3
status: open
captured_at: "2026-07-16T18:24:41Z"
discovered_date: 2026-07-16
discovered_by: capture-issue
labels:
  - enhancement
  - loops
  - fsm
  - prompt-across-issues
  - captured
relates_to:
  - ENH-1643
  - EPIC-1853
---

# ENH-2658: Add `ids` filter to prompt-across-issues loop

## Summary

The `prompt-across-issues` FSM loop currently filters its sweep via `--context type=TYPE` or `--context parent=EPIC-NNN`. Neither accepts an explicit comma-separated list of issue IDs, so a user who wants to run a prompt against a hand-picked, unrelated set has no first-class path. Today they must either (a) hand-drive a shell `for` loop calling the host CLI per issue, or (b) temporarily edit each issue's `parent:` frontmatter to point at a new synthetic EPIC — both heavyweight for an ad-hoc sweep.

The fix: add a third optional `context.ids` variable that, when set, overrides `type`/`parent` and writes the parsed IDs directly to the pending list. Mirrors the existing filter precedent (ENH-1643 added `type`; EPIC-1853 / ENH-2481 added `parent`).

## Current Behavior

`scripts/little_loops/loops/prompt-across-issues.yaml` declares exactly two filter axes:

```yaml
context:
  type: ""
  parent: ""
```

The `init` state (line 68) only branches on those two: `ll-issues list $TYPE_ARG $PARENT_ARG --json`. An explicit ID list is unreachable. The conversation that triggered this issue: a user wanting to sweep 10 sibling-but-unparented enhancements had no way to scope the loop to exactly those IDs.

## Expected Behavior

Add a third filter axis that overrides `type`/`parent` when set:

```bash
ll-loop run prompt-across-issues "/ll:refine-issue {issue_id}" \
  --context ids=ENH-2463,ENH-2464,ENH-2466,ENH-2496,ENH-2497,ENH-2505,ENH-2507,ENH-2508,ENH-2509,ENH-2580
```

The comma-separated value is split on `,`, whitespace is trimmed, empty entries are dropped, and the resulting IDs are written to `${context.run_dir}/pending.txt` — bypassing the `ll-issues list` call entirely. When `ids` is empty, the existing type/parent branch runs unchanged.

## Motivation

The loop is the project's go-to tool for batch operations on the issue backlog (refine, normalize, format, audit, etc.). Forcing users to either hand-drive a shell loop or mutate issue frontmatter for an ad-hoc sweep is a friction point. Two existing precedents already establish the `--context KEY=VALUE` filter shape (ENH-1643, EPIC-1853), so the implementation follows established patterns — minimal design risk.

Concrete motivating use case (from the conversation that surfaced this issue): 10 sibling ENH issues (2463, 2464, 2466, 2496, 2497, 2505, 2507, 2508, 2509, 2580) that belong to the same analytics-history initiative but were never parented under a single EPIC. Running a sweep against exactly those IDs without parent-ing them is the natural workflow.

## Proposed Solution

Add `ids: ""` to the loop's `context:` block and branch the `init` state on it:

```yaml
context:
  type: ""
  parent: ""
  ids: ""  # Optional: comma-separated issue IDs (e.g. ENH-2463,ENH-2464).
           # When set, overrides type/parent and processes exactly these IDs.
```

```yaml
  init:
    action: |
      cat > "${context.run_dir}/validate-input.txt" <<'LL_INPUT_EOF'
      ${context.input}
      LL_INPUT_EOF
      if ! grep -q '[^[:space:]]' "${context.run_dir}/validate-input.txt"; then
        echo "ERROR: input prompt is required. Usage: ll-loop run prompt-across-issues \"<prompt>\""
        exit 1
      fi
      if [ -n "${context.ids}" ]; then
        # Explicit ID list overrides type/parent filters.
        echo "${context.ids}" | tr ',' '\n' \
          | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' \
          | grep -v '^$' > "${context.run_dir}/pending.txt"
      else
        TYPE_ARG=""
        if [ -n "${context.type}" ]; then
          TYPE_ARG="--type ${context.type}"
        fi
        PARENT_ARG=""
        if [ -n "${context.parent}" ]; then
          PARENT_ARG="--parent ${context.parent}"
        fi
        ll-issues list $TYPE_ARG $PARENT_ARG --json | python3 -c "
        import json, sys
        issues = json.load(sys.stdin)
        for i in issues:
            print(i['id'])
        " > "${context.run_dir}/pending.txt"
      fi
      COUNT=$(wc -l < "${context.run_dir}/pending.txt" | tr -d ' ')
      echo "Found $${COUNT} issues to process"
    fragment: shell_exit
    on_yes: discover
    on_error: diagnose_error
```

Also update the YAML header `## description` block to document the new usage:

```yaml
  ll-loop run prompt-across-issues "/ll:refine-issue {issue_id}" --context ids=ENH-1,ENH-2,ENH-3
```

`${context.ids}` content is alphanumeric + commas only (no shell metacharacters), so MR-11 is satisfied — bare interpolation in the shell action is safe.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/prompt-across-issues.yaml` — add `ids` context var, branch `init`, update description header.

### Dependent Files (Callers/Importers)
- None. The loop is a leaf FSM loop; callers invoke `ll-loop run prompt-across-issues` and don't import the YAML.

### Similar Patterns
- `ENH-1643` (type filter) and `EPIC-1853` / `ENH-2481` (parent filter) established the exact `--context KEY=VALUE` shape — match it.
- `${context.input:shell}` (line 102) is precedent for `context.*` references inside shell actions.

### Tests
- `scripts/tests/test_builtin_loops.py` — add a prompt-across-issues test case for the `ids` filter asserting pending.txt contains exactly the supplied IDs in order.
- Regression test: when `ids=""`, the existing `type`/`parent` paths produce the same output as before the change.

### Documentation
- `docs/guides/LOOPS_REFERENCE.md` — add the `ids` example to the prompt-across-issues usage section.
- The loop YAML header `## description` block lists usage examples; add the `ids` example there.

### Configuration
- N/A — no config schema change.

## Implementation Steps

1. Add `ids: ""` to the loop's `context:` block.
2. Branch the `init` action on `${context.ids}`; preserve the existing type/parent path.
3. Update the YAML header `description` block with the new usage line.
4. Run `ll-loop validate prompt-across-issues` to confirm FSM schema and lint compliance (MR-7, MR-11).
5. Add a unit test in `scripts/tests/test_builtin_loops.py` exercising the new filter.
6. Verify the empty `ids=""` case preserves existing behavior via a regression test.

## Impact

- **Priority**: P3 — extends an existing filter surface; doesn't unblock any current bottleneck, but completes the filter axis set.
- **Effort**: Small — ~15-line YAML edit + one new test case. Reuses established pattern (ENH-1643, EPIC-1853).
- **Risk**: Low — purely additive filter; existing `type`/`parent` paths untouched. Only edge risk is if a user pastes shell metacharacters into `ids=`, which the expected value shape (alphanumeric + commas) makes unlikely.
- **Breaking Change**: No.

## Scope Boundaries

- **Out of scope**: regex/glob matching against IDs (e.g. `ENH-2*`), file-based ID lists (`--ids-file=path`), or a generic issue-set query DSL. The minimal comma-separated value covers current use cases; richer filters can be a follow-on.
- **Out of scope**: changes to `ll-issues list` itself. This is a loop-level filter; CLI changes are not required.

## Success Metrics

- A user can sweep an arbitrary 1–N list of IDs in one `ll-loop run` invocation with no file edits.
- The empty-`ids` path produces byte-identical pending.txt content for any `type`/`parent` input that existed before this change.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/guides/LOOPS_REFERENCE.md` | Usage examples for prompt-across-issues — needs the new `ids` example added |
| `docs/development/TROUBLESHOOTING.md` | May reference loop filters; verify no breakage |

## Labels

`enhancement`, `loops`, `fsm`, `prompt-across-issues`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-07-16T18:24:41Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c0f165e-7365-4933-89f9-474cf4409fae.jsonl`

## Status

**Open** | Created: 2026-07-16 | Priority: P3
