---
id: ENH-2119
type: ENH
priority: P3
status: open
captured_at: '2026-06-13T19:18:13Z'
discovered_date: '2026-06-13'
discovered_by: capture-issue
labels:
  - loops
  - rn-remediate
  - rn-implement
  - reliability
---

# ENH-2119: rn-remediate: move implemented counter increment to `emit_implemented`

## Summary

The `implemented_count.txt` increment in rn-remediate's `implement` state is gated on `ll-auto`'s exit code (`if [ $EXIT_CODE -eq 0 ]`). Under a double Option J cascade, `ll-auto` can return non-zero while the issue is actually implemented — causing the rn-implement summary to undercount `implemented` even though the work succeeded. Moving the counter increment to the `emit_implemented` state decouples it from ll-auto's exit code and ties it to structural proof of success instead.

## Current Behavior

rn-remediate's `implement` state:

```bash
ll-auto --only "$ID" 2>&1
EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
  ALREADY_COUNTED=$(grep -cxF "$ID" "${context.run_dir}/counted.txt" 2>/dev/null || echo 0)
  if [ "$ALREADY_COUNTED" -eq 0 ]; then
    COUNT=$(cat "${context.run_dir}/implemented_count.txt" 2>/dev/null || echo 0)
    echo $((COUNT + 1)) > "${context.run_dir}/implemented_count.txt"
    echo "$ID" >> "${context.run_dir}/counted.txt"
  fi
fi
exit $EXIT_CODE
```

When `ll-auto` exits non-zero (even if the issue ends up done), the increment block is skipped.

**Observed in**: `rn-implement-20260613T133723` — ENH-2116 was correctly implemented (committed, marked done, `subloop_outcome_ENH-2116.txt` = "IMPLEMENTED"), but `implemented_count.txt` stayed at 1 because `ll-auto --only ENH-2116` triggered a double Option J cascade (490% → 123%) and apparently returned non-zero. The FSM correctly routed `✓ yes → emit_implemented`, but the counter was never written.

## Expected Behavior

The `implemented` counter in the rn-implement summary reflects the actual number of issues that reached `emit_implemented`, regardless of `ll-auto`'s exit code path. The counter is a consequence of structural FSM routing, not of ll-auto's subprocess exit code.

## Motivation

The counter increment's current placement in `implement` creates a dependency on `ll-auto`'s exit code that doesn't match the counter's semantic intent ("how many issues reached the IMPLEMENTED outcome"). The FSM already has a state that means exactly that: `emit_implemented`. Moving the increment there eliminates the mismatch and makes the counter self-consistent with the FSM's own routing.

This also removes the `counted.txt` double-count guard from `implement` — since `emit_implemented` is only reached once per issue per sub-loop invocation, the guard is unnecessary there.

## Scope Boundaries

- **In scope**: rn-remediate's `implement` and `emit_implemented` states only
- **Out of scope**: rn-implement's `report` state, `ll-auto` exit code handling, Option J behavior

## Proposed Solution

**Remove** the counter increment from rn-remediate's `implement` state — keep only the ll-auto call and exit:

```yaml
implement:
  action_type: shell
  action: |
    ID="${context.issue_id}"
    ll-auto --only "$ID" 2>&1
    exit $?
  on_yes: emit_implemented
  on_no: emit_implement_failed
  on_error: emit_implement_failed
```

**Add** the counter increment to rn-remediate's `emit_implemented` state:

```yaml
emit_implemented:
  action_type: shell
  action: |
    ID="${context.issue_id}"
    echo "IMPLEMENTED" > "${context.run_dir}/subloop_outcome_${ID}.txt"
    # Increment parent counter (resilience: here over implement state so it
    # fires on structural success, not on ll-auto exit code)
    ALREADY_COUNTED=$(grep -cxF "$ID" "${context.run_dir}/counted.txt" 2>/dev/null || echo 0)
    if [ "$ALREADY_COUNTED" -eq 0 ]; then
      COUNT=$(cat "${context.run_dir}/implemented_count.txt" 2>/dev/null || echo 0)
      echo $((COUNT + 1)) > "${context.run_dir}/implemented_count.txt"
      echo "$ID" >> "${context.run_dir}/counted.txt"
    fi
  next: done
```

### Scope

- **In scope**: rn-remediate's `implement` and `emit_implemented` states only
- **Out of scope**: rn-implement's `report` state, `ll-auto` exit code handling, Option J behavior

### Acceptance Criteria

1. `rn-remediate.yaml` `implement` state no longer references `implemented_count.txt` or `counted.txt`
2. `rn-remediate.yaml` `emit_implemented` state increments `implemented_count.txt` and appends to `counted.txt`
3. Test: a simulated run where ll-auto returns exit code 1 but routes to `emit_implemented` still increments the counter
4. Existing tests in `test_rn_remediate.py` continue to pass

## Implementation Steps

1. Edit `scripts/little_loops/loops/rn-remediate.yaml`:
   - Remove the `ALREADY_COUNTED` / `implemented_count` / `counted.txt` block from `implement`'s shell action (lines 262–267)
   - Add the same block to `emit_implemented`'s shell action (after the `echo "IMPLEMENTED" > ...` line)
2. Write a regression test in `test_rn_remediate.py` verifying that when ll-auto exits 1 but the FSM routes to `emit_implemented`, `implemented_count.txt` is incremented
3. Run `ll-loop validate rn-remediate` — should be clean
4. Run `python -m pytest scripts/tests/test_rn_remediate.py` — all pass

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-remediate.yaml` — `implement` state (remove counter block) and `emit_implemented` state (add counter block)

### Dependent Files (Callers/Importers)
- N/A — rn-remediate.yaml is invoked by rn-implement sub-loop; no Python callers import this file

### Similar Patterns
- `scripts/little_loops/loops/rn-implement.yaml` — parent loop reads `implemented_count.txt` in its `report` state

### Tests
- `scripts/tests/test_rn_remediate.py` — add regression test: ll-auto exits non-zero but FSM routes to `emit_implemented` → counter increments

### Documentation
- N/A

### Configuration
- N/A

## API/Interface

N/A — no public API changes (YAML-only state refactor)

## Impact

- **Priority**: P3 — cosmetic only; actual implementation work is unaffected
- **Effort**: XS — two-state YAML edit, one test
- **Risk**: Low — the counter increment is identical logic, only moved to a different state
- **Breaking change**: No

## Session Log
- `/ll:format-issue` - 2026-06-13T19:25:01 - `ccf64f00-fdbe-43e8-91a3-b7eccc08992b.jsonl`
- `/ll:capture-issue` - 2026-06-13T19:18:13Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
