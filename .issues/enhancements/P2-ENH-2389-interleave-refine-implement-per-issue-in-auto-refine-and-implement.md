---
id: ENH-2389
title: Interleave refine→implement per issue (incl. sub-issues) in auto-refine-and-implement
type: ENH
status: done
priority: P2
captured_at: '2026-06-29T02:32:25Z'
discovered_date: '2026-06-28'
discovered_by: capture-issue
labels:
- enhancement
- loops
- issue-management
completed_at: '2026-06-29T02:32:25Z'
---

# ENH-2389: Interleave refine→implement per issue (incl. sub-issues) in `auto-refine-and-implement`

## Summary

`sprint-refine-and-implement` — and the `auto-refine-and-implement` engine it
delegates to — refined an issue's **entire decomposition subtree before
implementing any of it**, a two-phase "refine-all-then-implement-all" shape. This
session reworked `auto-refine-and-implement` to **interleave refinement and
implementation per issue and per sub-issue** by delegating the per-issue work to
the existing `autodev` engine, then removed the now-dead two-phase implementation
oracle.

## Current Behavior (before this change)

`auto-refine-and-implement`, for each top-level issue, called `recursive-refine`,
which depth-first drains the **whole** decomposition tree (refines the root and
every child it decomposes into) into `recursive-refine-passed.txt` — implementing
nothing. It then called `oracles/implement-issue-chain`, which read that passed
list and implemented the **entire batch** via `ll-auto --only`. Net effect for any
issue that decomposes: refine ALL sub-issues, then implement ALL of them.

## Expected Behavior (after this change)

Each issue is refined to readiness (`refine-to-ready-issue`) and **immediately
implemented** (`ll-auto --only`) before the next issue; when an issue decomposes,
its children are prepended **depth-first** so each child is refined AND implemented
before the next sibling. First implementation runs as soon as the first leaf passes
refinement — there is no refine-all-then-implement-all gap. This applies to both
full-backlog runs and scoped sprint/EPIC runs.

## Motivation

The two-phase shape delayed all implementation until the entire (potentially
decomposing) refinement pass completed, which is slow to first result, hides
implementation failures until late, and contradicts the user's expectation that a
sprint processes issues one at a time. The `autodev` loop already implemented the
desired interleave; the fix converges `auto-refine-and-implement` onto that engine
rather than duplicating its depth-first machinery.

## Resolution

### Decisions (locked with the user)
- **Scope**: fix `auto-refine-and-implement` itself so both backlog and scoped
  sprint/EPIC runs benefit (`sprint-refine-and-implement` is a thin alias and
  inherits the fix unchanged).
- **Approach**: reuse the existing, tested `autodev` engine via delegation rather
  than an inline rewrite.
- **go-no-go**: drop the per-issue go-no-go gate, so `autodev` needs no changes
  (its `implement_current` runs `ll-auto --only` directly).

### What was done
- Rewrote `auto-refine-and-implement.yaml` to:
  `init` (snapshot `.issues/completed/` baseline) → `resolve_set` (scope →
  `SprintManager.load_or_resolve`; else backlog via `ll-issues next-issues`, capped
  at `max_issues`; emits one comma-separated list captured as `issue_set`) →
  `delegate` (`loop: autodev` with `input=${captured.issue_set.output}`;
  `on_error` → `record_error`) → `record_error` → `finalize` → `done`.
- Preserved the ENH-2385 ground-truth closure verdict in `finalize` (CLOSED from
  the `.issues/completed/` diff), re-sourcing NOT_CLOSED/SKIPPED from autodev's
  `autodev-passed.txt` / `autodev-skipped.txt` (shared `run_dir`) and ERRORED from
  `auto-refine-and-implement-errored.txt`; still emits `summary.json` plus the
  `subloop_outcome_auto-refine-and-implement.txt` token (ENH-2005 contract that the
  sprint alias's `read_outcome` consumes).
- Removed the now-dead `oracles/implement-issue-chain.yaml` (zero callers after the
  change) and its references.

### Files Changed
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — rewritten (delegate to autodev + re-sourced finalize)
- `scripts/little_loops/loops/oracles/implement-issue-chain.yaml` — deleted (dead)
- `scripts/little_loops/loops/README.md` — removed the implement-issue-chain row
- `docs/reference/loops.md` — removed the `## oracles/implement-issue-chain` section
- `docs/guides/LOOPS_REFERENCE.md` — rewrote the `sprint-refine-and-implement` and `auto-refine-and-implement` sections (technique, FSM flow, closure accounting)
- `scripts/tests/test_builtin_loops.py` — removed `TestImplementIssueChainOracle`; rewrote `TestAutoRefineAndImplementLoop` for the new structure (delegate→autodev, resolve_set, autodev-ledger-sourced finalize); removed unused `import os`
- `scripts/tests/test_doc_counts.py` — removed `test_implement_issue_chain_is_runnable`

### Not changed (intentionally)
- `sprint-refine-and-implement.yaml` — thin alias; inherits the fix.
- `autodev.yaml` — already the desired engine.
- `recursive-refine.yaml` — still used by `autodev`, `issue-refinement`,
  `sprint-build-and-validate`, `rn-build`.

### Behavior changes (intended)
- The backlog set is resolved **once upfront** (not re-polled per issue);
  decomposition children created mid-run are still processed depth-first by
  `autodev`, but brand-new unrelated issues created during the run are not picked up
  — a deliberate, more deterministic semantic.
- The go-no-go "worth implementing?" gate no longer runs before each implementation.

### Verification Results
- `ll-loop validate` clean for `auto-refine-and-implement`,
  `sprint-refine-and-implement`, and `autodev`.
- Full test suite green: **12925 passed, 23 skipped** (`python -m pytest scripts/tests/`).
- `ruff check scripts/` clean.
- Interpolation guard (`test_builtin_loop_interpolation.py`) passes the new YAML;
  `resolve_set` runtime-tested (backlog → capped comma-separated ranked list;
  bogus scope → exit 1 → `finalize`/no-op).

### Gotchas discovered
- FSM shell actions must use `$VAR` (no braces) for bash variables; `${...}` is
  reserved for `namespace.path` interpolation.
- Sub-loops share the parent's `run_dir` via executor `setdefault` (the same
  mechanism the sprint→auto delegation already relied on), which is what lets
  `finalize` read autodev's `*-passed.txt` / `*-skipped.txt`.

### Pre-existing issue noted (not addressed here)
- `ll-verify-docs` reports stale hardcoded counts in the **root** `README.md`
  (skills 67 vs actual 39; loops 81 vs actual 95). Root README was not touched this
  session; this drift predates the change and is out of scope.

## Impact

- **Priority**: P2 — corrects a user-visible behavior defect in core automation loops.
- **Effort**: Medium — one loop rewrite + finalize re-sourcing, dead-loop removal, doc + test updates.
- **Risk**: Low/Medium — reuses the tested `autodev` engine; full suite green.
- **Breaking Change**: No (behavior-improving; verdict/summary contract preserved).

## Related Key Documentation

- `docs/guides/LOOPS_REFERENCE.md` — `auto-refine-and-implement`, `sprint-refine-and-implement`, `autodev` sections
- Plan: `~/.claude/plans/the-built-in-fsm-serene-sun.md`

## Labels

`enhancement`, `loops`, `issue-management`

---

## Resolution

- **Action**: improve
- **Completed**: 2026-06-29
- **Status**: Completed
- **Implementation**: `auto-refine-and-implement` now delegates per-issue refine+implement to the `autodev` engine (interleaved, depth-first for sub-issues); dead `implement-issue-chain` oracle removed; docs and tests updated. Full suite green (12925 passed).


## Session Log
- `hook:posttooluse-status-done` - 2026-06-29T02:33:09 - `f54772ee-64de-45d1-bc78-6ab1a1de495f.jsonl`
