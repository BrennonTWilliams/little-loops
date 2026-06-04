---
id: BUG-1937
title: run_size_review missing on_rate_limit_exhausted routing in rn-implement.yaml
type: BUG
priority: P3
status: done
captured_at: "2026-06-04T14:53:54Z"
discovered_date: 2026-06-04
discovered_by: capture-issue
labels: [bug, loops, fsm, rate-limiting]
---

# BUG-1937: run_size_review missing on_rate_limit_exhausted routing in rn-implement.yaml

## Summary

In `scripts/little_loops/loops/rn-implement.yaml`, the `run_size_review` state (line 518) uses `fragment: with_rate_limit_handling` but does not declare `on_rate_limit_exhausted`. The other five states using this fragment (`assess`, `decide`, `wire`, `refine`, `re_assess`) all route to `rate_limit_diagnostic`. If `/ll:issue-size-review` hits a sustained 429 storm, the state has no defined routing, which will cause a runtime error or undefined behavior.

## Context

Identified during a structural review of `rn-implement.yaml` for sub-loop decomposition opportunities (ENH-1936). The `with_rate_limit_handling` fragment (defined in `lib/common.yaml` lines 61–74) requires `on_rate_limit_exhausted` to be set — its description states "State must supply: on_rate_limit_exhausted (target state when the full budget is spent)."

## Current Behavior

`run_size_review` at line 518–524:
```yaml
run_size_review:
    fragment: with_rate_limit_handling
    action: "/ll:issue-size-review ${captured.input.output} --auto"
    action_type: slash_command
    on_success: detect_children
    on_error: skip_issue
    on_rate_limit_exhausted: rate_limit_diagnostic  # ← MISSING
```

When the fragment's rate-limit budget is exhausted (3 short retries at 30s backoff + long-wait ladder up to 21600s), the fragment will attempt to route to `on_rate_limit_exhausted`. Since `run_size_review` doesn't declare it, the routing is undefined — likely causing a `KeyError`-style failure or falling through to the FSM's default error handling.

## Expected Behavior

`run_size_review` should declare `on_rate_limit_exhausted: rate_limit_diagnostic`, matching the pattern used by all other `with_rate_limit_handling` fragment states in the same loop:

- `assess` (line 149): `on_rate_limit_exhausted: rate_limit_diagnostic`
- `decide` (line 331): `on_rate_limit_exhausted: rate_limit_diagnostic`
- `wire` (line 339): `on_rate_limit_exhausted: rate_limit_diagnostic`
- `refine` (line 347): `on_rate_limit_exhausted: rate_limit_diagnostic`
- `re_assess` (line 359): `on_rate_limit_exhausted: rate_limit_diagnostic`

## Motivation

This is a latent runtime defect. Under normal operation (no rate limiting), the bug is invisible. Under sustained 429 pressure, the loop will crash instead of gracefully skipping the issue and continuing to the next queue item. The `rate_limit_diagnostic` state logs the event to `rate_limits.txt` and returns to `dequeue_next`, which is the correct behavior — the bug is solely that this escape hatch is unreachable for `run_size_review`.

## Steps to Reproduce

1. Configure a test environment where `/ll:issue-size-review` consistently returns HTTP 429 (or mock the rate-limit detection in the fragment)
2. Run `ll-loop run rn-implement "<issue-id>"` on an issue that routes to the decomposition path (convergence stalled or budget exhausted)
3. Observe that when `run_size_review` exhausts its rate-limit retry budget, the loop crashes instead of routing to `rate_limit_diagnostic`

## Root Cause

- **File**: `scripts/little_loops/loops/rn-implement.yaml`
- **Anchor**: `run_size_review` state (line 518)
- **Cause**: The `on_rate_limit_exhausted` routing key was omitted when the state was authored. The `with_rate_limit_handling` fragment documentation states this is required, but `ll-loop validate` may not catch the omission at load time (the fragment applies defaults at runtime, and the missing route key is only detected when the fragment attempts to transition).

## Proposed Solution

Add `on_rate_limit_exhausted: rate_limit_diagnostic` to the `run_size_review` state. This is a one-line fix:

```yaml
run_size_review:
    fragment: with_rate_limit_handling
    action: "/ll:issue-size-review ${captured.input.output} --auto"
    action_type: slash_command
    on_success: detect_children
    on_error: skip_issue
    on_rate_limit_exhausted: rate_limit_diagnostic  # ADD THIS LINE
```

If ENH-1936 is implemented first and `rn-decompose` is extracted as a sub-loop, the fix should be applied to the sub-loop's equivalent state instead. The root cause (missing route key) is the same regardless of which file the state lives in.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-implement.yaml` — Add `on_rate_limit_exhausted: rate_limit_diagnostic` to `run_size_review` state (line ~524)
- OR `scripts/little_loops/loops/rn-decompose.yaml` — If ENH-1936 is implemented first, apply fix to the extracted sub-loop

### Dependent Files (Callers/Importers)
- N/A — No callers depend on this specific routing key

### Similar Patterns
- Five other states in `rn-implement.yaml` correctly declare `on_rate_limit_exhausted: rate_limit_diagnostic` — audit them to confirm consistency
- Search for other loops using `fragment: with_rate_limit_handling` without `on_rate_limit_exhausted`:
  ```bash
  grep -A10 'fragment: with_rate_limit_handling' scripts/little_loops/loops/*.yaml | grep -B10 -v 'on_rate_limit_exhausted'
  ```

### Tests
- `scripts/tests/` — Add a test that validates all `with_rate_limit_handling` fragment states declare `on_rate_limit_exhausted`
- `ll-loop validate rn-implement` — Verify no new warnings after fix

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `on_rate_limit_exhausted: rate_limit_diagnostic` to `run_size_review` in `rn-implement.yaml`
2. Run `ll-loop validate rn-implement` to verify no regressions
3. Run a codebase-wide grep to find any other `with_rate_limit_handling` fragment states missing `on_rate_limit_exhausted`
4. If ENH-1936 is in progress, coordinate to apply the fix to the extracted `rn-decompose.yaml` instead

## Error Messages

No visible error under normal operation. Under rate-limit exhaustion, the expected behavior is a `KeyError` or similar routing failure when the FSM executor attempts to look up the `on_rate_limit_exhausted` transition target.

## Location

- **File**: `scripts/little_loops/loops/rn-implement.yaml`
- **Line(s)**: 518–524
- **Anchor**: `run_size_review` state definition

## Impact

- **Priority**: P3 — Latent defect; only triggers under sustained rate-limiting (rare in practice). No user-visible impact under normal operation.
- **Effort**: Small — One-line YAML addition.
- **Risk**: Low — The fix only adds a routing key that matches existing convention; no behavioral change under normal operation.
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|---|---|
| `scripts/little_loops/loops/lib/common.yaml` | `with_rate_limit_handling` fragment definition (lines 61–74) |
| `docs/reference/API.md` | Fragment resolution and required routing keys |
| `.claude/CLAUDE.md` | Loop authoring conventions and fragment usage patterns |

## Labels

`bug`, `loops`, `fsm`, `rate-limiting`, `captured`

## Verification Notes

- **Verified**: 2026-06-04 by `/ll:verify-issues`
- **Verdict**: RESOLVED — the bug no longer exists
- **Details**: `rn-implement.yaml` was rewritten (commit `16187096`) from a ~500-line monolithic loop into a 242-line queue orchestrator that delegates to sub-loops. The `run_size_review` state was extracted to `rn-decompose.yaml` (commit `29c663d7`), where `on_rate_limit_exhausted: rate_limit_diagnostic` is correctly declared at line 80. The five other states referenced in the issue (`assess`, `decide`, `wire`, `refine`, `re_assess`) were also removed during the restructuring. No other instances of this bug pattern were found across the codebase — all `with_rate_limit_handling` fragment states in `autodev.yaml`, `recursive-refine.yaml`, `rn-remediate.yaml`, and `rn-decompose.yaml` correctly declare `on_rate_limit_exhausted`.

## Session Log
- `/ll:verify-issues` - 2026-06-04T18:30:46 - `4ac40910-bc0a-40df-b18a-1e280b6b401f.jsonl`
- `/ll:format-issue` - 2026-06-04T14:58:42 - `8fedb6e2-8a49-473f-ae3b-e7306b2f84ea.jsonl`
- `/ll:capture-issue` - 2026-06-04T14:53:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8570b512-4a4b-43bb-b25c-c2274b77d0ef.jsonl`

---

**Open** | Created: 2026-06-04 | Priority: P3
