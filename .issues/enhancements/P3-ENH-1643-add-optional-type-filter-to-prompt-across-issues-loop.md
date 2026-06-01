---
id: ENH-1643
title: Add optional type filter to prompt-across-issues loop
type: ENH
priority: P3
captured_at: "2026-05-23T20:52:54Z"
discovered_date: "2026-05-23"
discovered_by: capture-issue
status: open
parent: EPIC-1773
---

# ENH-1643: Add optional type filter to prompt-across-issues loop

## Summary

The `prompt-across-issues` FSM loop currently runs an arbitrary prompt against **every** open/active issue (default `ll-issues list` → `--status open`). There is no way to constrain the sweep to a specific issue type (`BUG`, `FEAT`, `ENH`, `EPIC`), so a user who only wants to refine all open bugs must either fork the loop or filter ad-hoc. Add one optional context variable, `type`, that — when supplied via `--context type=BUG` (or `FEAT`/`ENH`/`EPIC`) — narrows the pending list to issues of that type. When omitted, behavior is **exactly** what it is today.

## Current Behavior

`scripts/little_loops/loops/prompt-across-issues.yaml` (state `init`, ~lines 26–39) invokes `ll-issues list --json` unconditionally, building the pending-list temp file from **all** open/active issues regardless of type. Users wanting a type-scoped sweep must duplicate the loop or run external filtering.

## Expected Behavior

Invocation is unchanged by default:

```bash
ll-loop run prompt-across-issues "/ll:refine-issue {issue_id}"
```

When `type` is supplied, the sweep is narrowed:

```bash
ll-loop run prompt-across-issues "/ll:refine-issue {issue_id}" --context type=BUG
```

Internally, this passes `--type BUG` through to `ll-issues list`. Invalid type values are rejected by `ll-issues list`'s argparse `choices=["BUG", "FEAT", "ENH", "EPIC"]` validation (`scripts/little_loops/cli/issues/__init__.py:116-118`), causing `init` to exit non-zero and the loop to route via `on_error` instead of advancing to `discover`.

## Motivation

Issue-refinement and issue-sweep workflows (e.g. `/ll:refine-issue`, `/ll:ready-issue`, `/ll:normalize-issues`) are often type-scoped — a user wants to refine all open bugs, or normalize all enhancements, not touch the entire active backlog at once. Today this forces either (a) running the loop against the full backlog and hoping the inner prompt no-ops on non-matching types, (b) forking the loop, or (c) hand-rolling a one-off shell pipeline. A single optional `--context type=` flag is a minimal, idiomatic FSM extension that removes that friction without changing the default invocation path.

## Proposed Solution

Two edits, both in `scripts/little_loops/loops/prompt-across-issues.yaml`:

### 1. Declare `type` with an empty-string default

The FSM's interpolation layer (`scripts/little_loops/fsm/interpolation.py:102-124`) raises `InterpolationError` when an action references `${context.X}` for an undeclared `X`. Any new optional var must therefore be declared in a `context:` block at the loop top level with a default value — the established pattern in `scripts/little_loops/loops/test-coverage-improvement.yaml:20-22` (which declares `focus_dirs: ""`, `test_cmd: ""`, `coverage_cmd: ""` for the same reason).

Add immediately above `states:`:

```yaml
context:
  type: ""  # Optional: BUG, FEAT, ENH, or EPIC. When set, restricts the sweep
            # to open issues of that type. Empty (default) = all open issues.
```

### 2. Conditionally append `--type` to `ll-issues list` in `init`

Modify only the `init` state's `action` block. The rest of the loop (`discover`, `prepare_prompt`, `execute`, `advance`, `done`, `diagnose_error`, `error`) is untouched. Replace the existing `ll-issues list --json` invocation with a version that adds `--type` only when `context.type` is non-empty:

```yaml
action: |
  if [ -z "${context.input}" ]; then
    echo "ERROR: input prompt is required. Usage: ll-loop run prompt-across-issues \"<prompt>\""
    exit 1
  fi
  mkdir -p .loops/tmp
  TYPE_ARG=""
  if [ -n "${context.type}" ]; then
    TYPE_ARG="--type ${context.type}"
  fi
  ll-issues list $TYPE_ARG --json | python3 -c "
  import json, sys
  issues = json.load(sys.stdin)
  for i in issues:
      print(i['id'])
  " > .loops/tmp/prompt-across-issues-pending.txt
  COUNT=$(wc -l < .loops/tmp/prompt-across-issues-pending.txt | tr -d ' ')
  echo "Found $${COUNT} issues to process"
```

Notes:

- `TYPE_ARG=""` followed by unquoted `$TYPE_ARG` is intentional — an empty var expands to nothing, so `ll-issues list --json` runs verbatim when `type` is unset (preserving current behavior bit-for-bit).
- Invalid type values are caught by argparse in `scripts/little_loops/cli/issues/__init__.py:116-118` (`choices=["BUG", "FEAT", "ENH", "EPIC"]`). An invalid value causes `ll-issues list` to exit non-zero, which the `shell_exit` fragment (`scripts/little_loops/loops/lib/common.yaml:14-21`) treats the same way it already treats an empty `context.input`: by routing on exit code. No new validation logic is needed — we deliberately rely on `ll-issues list`'s own error message.
- The `init` state's existing fragment (`shell_exit`), captures, and transitions (`on_yes: discover`, `on_error: diagnose_error`) stay as-is.

### Header docstring update

Update the loop's top-level `description:` block to document the new optional flag and add a usage example:

```yaml
description: |
  Run an arbitrary prompt against every open/active issue, one at a time.
  ...
  Optionally constrain the sweep to a single issue type with --context type=<TYPE>
  (one of BUG, FEAT, ENH, EPIC). When omitted, all open issues are processed.

  Usage:
    ll-loop run prompt-across-issues "/ll:refine-issue {issue_id}"
    ll-loop run prompt-across-issues "/ll:refine-issue {issue_id}" --context type=BUG
```

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/prompt-across-issues.yaml` (the only file changed)

### Dependent Files (Callers/Importers)
- N/A — no Python code imports or references the loop YAML other than `ll-loop run` (`scripts/little_loops/cli/loop/lifecycle.py`), which is FSM-agnostic and reads context vars generically.

### Similar Patterns
- `scripts/little_loops/loops/test-coverage-improvement.yaml:20-22` — established pattern for declaring optional context vars with empty-string defaults.
- `scripts/little_loops/loops/lib/common.yaml:14-21` — the `shell_exit` fragment that the `init` state already uses for routing on exit code.

### Tests
- No new unit tests required. Existing FSM/interpolation tests in `scripts/tests/` cover the context-declaration mechanism. Verification is by `ll-loop validate` plus end-to-end dry-runs (see Verification section).

### Documentation
- The loop's own `description:` block (updated as part of this change).
- No external `docs/` updates required — `prompt-across-issues` is documented inline.

### Configuration
- N/A — no changes to `.ll/ll-config.json` schema or templates.

## Implementation Steps

1. Add `context: { type: "" }` block above `states:` in `prompt-across-issues.yaml`.
2. Update the `init` state's `action` to conditionally append `--type ${context.type}` when set.
3. Update the loop's top-level `description:` to document the new flag and add a usage example.
4. Run `ll-loop validate prompt-across-issues` to confirm the loop still parses.
5. Dry-run with and without `--context type=BUG` and confirm the rendered `ll-issues list` invocation matches expectations.

## API/Interface

```yaml
# New optional context variable on prompt-across-issues:
context:
  type: ""  # Optional: BUG | FEAT | ENH | EPIC (passed through to ll-issues list --type)
```

CLI surface (unchanged for default case, new option for filtered case):

```bash
ll-loop run prompt-across-issues "<prompt>"                        # all open issues (unchanged)
ll-loop run prompt-across-issues "<prompt>" --context type=BUG     # open bugs only
```

## Scope Boundaries

- **Out of scope**: multi-type selection (e.g. `type=BUG,ENH`). If the user needs more than one type, they can run the loop twice. `ll-issues list --type` does not support comma-separated lists today, and adding it would be a separate enhancement.
- **Out of scope**: filtering by priority, label, or any other attribute. Only `type` is added here.
- **Out of scope**: a `--type` flag on `ll-loop run` itself. The plumbing is via the existing generic `--context KEY=VALUE` mechanism.
- **Out of scope**: changing how `ll-issues list` validates its `--type` argument; we deliberately rely on its existing argparse `choices=` validation.

## Success Metrics

- `ll-loop validate prompt-across-issues` exits 0 after the change.
- Invocation without `--context type=` produces an `init` shell command **textually identical** (modulo the empty `TYPE_ARG` prefix) to the pre-change one — verified by dry-run inspection.
- Invocation with `--context type=BUG` results in `ll-issues list --type BUG --json` being the command executed.
- Invocation with `--context type=NOPE` causes `init` to exit non-zero and the loop to route to `diagnose_error` / terminate — verified by running and observing FSM transitions.

## Impact

- **Priority**: P3 — Quality-of-life improvement for issue-sweep workflows. Not blocking any current work; the workaround (forking the loop) exists but is friction.
- **Effort**: Small — two localized edits in one YAML file (~10 lines added), one description block update. No Python changes, no new tests.
- **Risk**: Low — `type: ""` default preserves current behavior bit-for-bit; the conditional shell construct (`$TYPE_ARG` unquoted, empty by default) is a well-established pattern. Reuses existing argparse validation in `ll-issues list`. No FSM-runner or interpolation changes required.
- **Breaking Change**: No — purely additive. Existing invocations continue to work without modification.

## Verification

1. **Schema/syntax check** — confirm the loop still parses cleanly:
   ```bash
   ll-loop validate prompt-across-issues
   ```

2. **Default behavior unchanged** — dry-run with no `--context type` and confirm `ll-issues list --json` is invoked without `--type`:
   ```bash
   ll-loop run prompt-across-issues "/ll:ready-issue {issue_id}" --dry-run --max-iterations 1
   ```
   Compare the rendered init action against the pre-refactor version — the only difference should be the conditional `TYPE_ARG` plumbing; the issued shell command must be identical when `type` is empty.

3. **Type filter applied** — dry-run with a real type and confirm `--type BUG` reaches `ll-issues list`:
   ```bash
   ll-loop run prompt-across-issues "/ll:ready-issue {issue_id}" --context type=BUG --dry-run --max-iterations 1
   ```
   Inspect the rendered action to verify `ll-issues list --type BUG --json` is what gets executed.

4. **End-to-end smoke** — run a no-op prompt across one type with a low iteration cap, then confirm the `Found N issues to process` count printed by `init` matches:
   ```bash
   ll-loop run prompt-across-issues "echo Touching {issue_id}" --context type=ENH --max-iterations 2
   ll-issues list --type ENH --json | python3 -c "import json,sys; print(len(json.load(sys.stdin)))"
   ```

5. **Invalid type rejected** — confirm argparse's error message surfaces and the loop terminates rather than silently processing everything:
   ```bash
   ll-loop run prompt-across-issues "/ll:ready-issue {issue_id}" --context type=NOPE --max-iterations 1
   ```
   Expected: `ll-issues list` prints its argparse error, `init` exits non-zero, loop does not advance to `discover`.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `loops`, `fsm`, `captured`

## Session Log
- `/ll:verify-issues` - 2026-05-31T05:40:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:format-issue` - 2026-05-23T20:56:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e841fa07-af71-463d-ab27-a39fa5403a77.jsonl`
- `/ll:capture-issue` - 2026-05-23T20:52:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fbeefa69-751d-4d94-afeb-e4cac2a5473b.jsonl`

---

**Open** | Created: 2026-05-23 | Priority: P3
