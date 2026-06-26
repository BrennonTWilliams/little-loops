---
id: BUG-2320
title: 'll-parallel silently skips the learning gate for unrefined issues'
type: BUG
status: open
priority: P2
captured_at: '2026-06-26T22:27:56Z'
discovered_date: '2026-06-26'
discovered_by: capture-issue
relates_to:
- ENH-2319
- ENH-2219
- FEAT-1282
labels:
- learning-tests
- ll-parallel
- automation
---

# BUG-2320: ll-parallel silently skips the learning gate for unrefined issues

## Summary

`ll-parallel`'s per-worktree learning gate
(`_run_per_worktree_proof_first_gate`) early-returns `True` whenever an issue's
`learning_tests_required` frontmatter is absent, so it only ever fires the
assumption firewall for issues that were already refined. An issue that reaches
`ll-parallel` without refinement (e.g. `capture-issue → ll-parallel`) has an
empty field and silently bypasses the gate — implementation proceeds against
unproven external-API assumptions with no `/ll:explore-api` ever invoked.

## Current Behavior

`scripts/little_loops/parallel/worker_pool.py:63`
(`_run_per_worktree_proof_first_gate`, called from
`WorkerPool._process_issue` between VALIDATING and IMPLEMENTING) opens with:

```python
if issue.learning_tests_required is None:
    return True
```

`None` is treated as "no external dependencies, proceed" — but it actually means
"nobody has computed the dependencies yet." Unlike `ll-sprint`'s preflight
(`scripts/little_loops/cli/sprint/run.py:164`), which falls back to
`extract_learning_targets()` when the field is `None`, the parallel gate has no
just-in-time extraction. The result is a silent skip, not a logged decision.

## Expected Behavior

When `learning_tests_required` is empty, the gate resolves targets just-in-time
from the issue text before deciding to proceed. If extraction yields targets,
the firewall runs as usual; if it yields none, the gate proceeds and logs that
no external dependencies were detected (an auditable outcome, not a silent
bypass). Behavior for issues with a populated field is unchanged.

## Steps to Reproduce

1. Capture an issue that depends on an external API (e.g. a new SDK call) and do
   **not** run `/ll:refine-issue`, `/ll:wire-issue`, or `/ll:scope-epic`, so
   `learning_tests_required` stays absent.
2. Run it through `ll-parallel`.
3. Observe: `_run_per_worktree_proof_first_gate` returns `True` immediately;
   `proof-first-task` never runs; implementation proceeds with no proof record
   in `.ll/learning-tests/`.

## Root Cause

`scripts/little_loops/parallel/worker_pool.py:77` (`if
issue.learning_tests_required is None: return True`) conflates "field unset" with
"no dependencies." The eager-population assumption (ENH-2209) does not hold for
issues that never pass through a refine step.

## Proposed Fix

Replace the `is None → return True` short-circuit with the shared
`resolve_learning_targets(issue)` helper introduced in ENH-2319:

- Resolve targets (field if populated, else extract from issue text).
- If targets is empty after resolution, log "no external dependencies detected"
  and return `True`.
- Otherwise run the `proof-first-task` gate as today.

Land this on the same shared gate-runner ENH-2319 factors out, so `ll-auto`,
`ll-parallel`, and `ll-sprint` share one code path. Honor the existing
`--skip-learning-gate` and `learning_tests.enabled` short-circuits (which
correctly precede the target resolution).

## Integration Map

- **Files to modify**:
  - `scripts/little_loops/parallel/worker_pool.py:63`
    (`_run_per_worktree_proof_first_gate`).
- **Depends on**: ENH-2319 (`resolve_learning_targets` helper / shared
  gate-runner). Can be implemented independently by inlining the resolver, but
  prefer landing after or with ENH-2319 to avoid duplicating logic.
- **Tests**: `scripts/tests/` (parallel worker pool gate tests) — add a case
  where `learning_tests_required is None` but the issue text contains an external
  API: assert the gate resolves targets and runs `proof-first-task` rather than
  early-returning.

## Impact

- **Severity**: P2 — a safety gate silently does nothing on a real code path,
  letting unverified API assumptions reach implementation under concurrent
  automation (where review attention is lowest).
- **Scope**: one function; small. Test coverage is the bulk of the work.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `skills/explore-api/SKILL.md` | Proof lifecycle the gate is meant to trigger |
| `.claude/CLAUDE.md` (CLI Tools) | `ll-parallel` / learning-test gate overview |

## Labels

- learning-tests
- ll-parallel
- bug

## Session Log
- `/ll:capture-issue` - 2026-06-26T22:27:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6b5f4713-4801-485e-9909-111bcbcf1d9a.jsonl`

---

## Status

open
