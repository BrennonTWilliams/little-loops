---
discovered_date: 2026-03-16
discovered_by: /ll:capture-issue
source_loop: issue-refinement
---

# BUG-786: issue-refinement loop `evaluate` conflates `formatted=False` and `has_verify=False` into one route

## Summary

The `issue-refinement` loop's `evaluate` state outputs `NEEDS_FORMAT <id>` for two distinct failure conditions — an issue that is not yet formatted AND an issue that is formatted but hasn't had `/ll:verify-issues` run yet — and routes both to the `format_issues` state. The `format_issues` state always runs `/ll:format-issue` first, so an already-formatted issue gets unnecessarily re-formatted on every cycle until the session log is recognised.

## Current Behavior

The evaluate script in the loop's `evaluate` state:

```python
has_verify = '/ll:verify-issues' in cmds
if not issue.get('formatted', False) or not has_verify:
    print(f'NEEDS_FORMAT {issue["id"]}')
    sys.exit(1)
```

Both `formatted=False` and `has_verify=False` produce identical output (`NEEDS_FORMAT`) and route to `format_issues`, which always runs:

```
1. /ll:format-issue <id> --auto
2. /ll:verify-issues <id> --auto
```

When an issue is already fully formatted but `has_verify=False` (e.g. because `parse_session_log` returns `[]` due to BUG-785), every loop iteration re-runs `/ll:format-issue` unnecessarily. Observed: FEAT-638 had format-issue called 9 times across one run, with the second invocation already reporting "0 structural gaps, 0 actionable quality findings — no changes needed."

## Root Cause

The evaluate script does not distinguish between "needs formatting" and "needs verification" as separate failure modes. The single `NEEDS_FORMAT` signal hides which step is actually needed, and the loop has no `NEEDS_VERIFY`-only route that skips format-issue.

## Proposed Fix

Split the evaluate condition into two distinct output tokens and add a `NEEDS_VERIFY` route in the loop YAML that goes directly to a `verify_only` state (running only `/ll:verify-issues`):

```python
has_verify = '/ll:verify-issues' in cmds
if not issue.get('formatted', False):
    print(f'NEEDS_FORMAT {issue["id"]}')
    sys.exit(1)
if not has_verify:
    print(f'NEEDS_VERIFY {issue["id"]}')
    sys.exit(2)
```

Then add a `route_format` branch for `NEEDS_VERIFY` that routes to a `verify_only` state instead of `format_issues`.

## Acceptance Criteria

- [ ] Issues that are `formatted=True` but lack a `verify-issues` session log entry are routed to verify-only (not re-formatted)
- [ ] Issues that are `formatted=False` continue to be routed to `format_issues` (which runs both)
- [ ] `NEEDS_FORMAT` output only appears when `formatted=False`
- [ ] Loop no longer calls `/ll:format-issue` on an issue that already reports "0 structural gaps"
- [ ] Loop YAML has a `NEEDS_VERIFY` branch and corresponding `verify_only` state

## Related Issues

- BUG-785: Root cause of `has_verify=False` persisting for FEAT-638 despite verify running (parser reads wrong section)
- BUG-773 (active): Prompt states missing timeout/on-error in issue-refinement loop

## Labels

`bug`, `loops`, `issue-refinement`, `captured`

## Status

**Open** | Created: 2026-03-16 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-03-16T20:08:11Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
