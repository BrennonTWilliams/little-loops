---
id: FEAT-1813
type: FEAT
priority: P3
status: open
captured_at: "2026-05-30T21:35:04Z"
discovered_date: "2026-05-30"
discovered_by: capture-issue
parent: EPIC-1694
depends_on: [FEAT-1739]
relates_to: [EPIC-1694, FEAT-1739, FEAT-1287, FEAT-1286]
---

# FEAT-1813: `migrate-sdk-version` FSM loop — re-prove stale learning-test records

## Summary

Add `scripts/little_loops/loops/migrate-sdk-version.yaml` — an FSM loop that is
the counterpart to `learning-tests-audit` (FEAT-1739). After audit marks
records stale on dependency bumps, this loop iterates the stale set,
re-runs `/ll:explore-api` against each target with current installed package
versions, and classifies each result as `still-valid` (re-prove without
changes), `needs-upgrade` (assertion bodies drifted but API contract is
intact), or `refuted` (API broke). The loop then updates `LearnTestRecord`
fields (`date`, `versions`, `assertions`, `status`) atomically.

## Current Behavior

`ll-learning-tests mark-stale` exists as a CLI command, and FEAT-1739 will
automate marking when registries publish newer versions than the record's
`date`. But there is no automated path from "marked stale" to "re-proven."
Today a developer must:

1. Run `ll-learning-tests list` to find every stale record.
2. Hand-invoke `/ll:explore-api "<target>"` for each one.
3. Manually decide whether the new record is the same shape, an upgrade, or
   a refute.
4. Manually clean up any drift between old assertions and the re-proven ones.

This is exactly the bulk loop FEAT-1739 sets up demand for. Without it,
"stale" is a sticker, not a workflow — and the registry's health degrades
as soon as more than a handful of records are stale at once.

## Expected Behavior

```bash
ll-loop run migrate-sdk-version
# or scoped:
ll-loop run migrate-sdk-version --context targets="anthropic,@anthropic-ai/sdk"
```

The loop:

1. `list_stale` (shell) — runs `ll-learning-tests list` and filters to
   records with `status: stale`. Empty → terminal `done_empty`.
2. `reprove_next` (shell, looped) — pops the head of the stale queue, calls
   `ll-action invoke explore-api --args "<target>"`. Captures the new
   `LearnTestRecord` JSON.
3. `classify_outcome` (prompt) — compares the new record to the old: same
   assertions and pass/fail map → `still-valid`; same shapes but new
   versions or extra assertions → `needs-upgrade`; any previously-passing
   assertion now refuted → `refuted`. Emits structured JSON.
4. `apply_update` (shell) — writes the new record over the old (atomic file
   replace), bumping `date` and `versions`. For `refuted`, marks the record
   `status: refuted` and surfaces the regression in the report.
5. `advance_queue` (shell) — pops, routes back to `reprove_next` or to
   `build_report`.
6. `build_report` (prompt) — writes
   `.loops/runs/migrate-sdk-version/report-<timestamp>.md` summarizing:
   re-proven (still-valid), upgraded (needs-upgrade), refuted, and
   per-record diffs.
7. `done` (terminal).

## Motivation

- **Closes the loop after FEAT-1739.** Audit marks stale; migrate re-proves.
  Without both, the registry rots whenever dependencies bump.
- **Bulk-friendly.** Manual re-exploration scales poorly past ~3 stale
  records. The loop runs them in a queue with a single report at the end.
- **Three-way classification surfaces real regressions.** Distinguishing
  "API shape unchanged but version bumped" from "API broke" is the signal
  that matters at sprint planning — refuted records need code changes, not
  just record updates.

## Proposed Solution

The state graph mirrors `ready-to-implement-gate`'s queue-driven pattern
(parse → check_next → branch → advance_queue) but with re-exploration in
the middle instead of registry lookup. Reuse `ll-action invoke explore-api`
to delegate the actual proof work — this loop is orchestration, not new
proof machinery.

## Scope Boundaries

- **In scope**: Bulk re-exploration of stale records; three-way
  classification; updating `LearnTestRecord` with new `date` / `versions` /
  `assertions`; a triage report.
- **Out of scope**: Cross-package migration (e.g. moving from SDK A to a
  forked SDK B — that's a manual decision); manual diff review of every
  assertion change (audit-loop's report and this loop's report give
  triage, but the developer still owns merging into code); generating
  codemods to update callers when assertions drift.

## Acceptance Criteria

- `ll-loop validate migrate-sdk-version` reports no ERRORs.
- `python -m pytest scripts/tests/test_builtin_loops.py -v` passes with
  the new loop name added to `test_expected_loops_exist`.
- `ll-loop list` surfaces the loop.
- End-to-end smoke: with one stale record and one proven record in the
  registry, the loop re-proves only the stale one and produces a report
  listing it under either "re-proven" or "upgraded."
- End-to-end smoke: with zero stale records, the loop reaches
  `done_empty` without invoking `/ll:explore-api`.

## Impact

- **Priority**: P3 — Pairs with FEAT-1739 (also P3) and unblocks
  "first-class learning testing" as defined by EPIC-1694.
- **Effort**: Medium — one new loop YAML (~7 states), tests, and a small
  classification prompt. Reuses existing `ll-action invoke explore-api`
  and `LearnTestRecord` write path.
- **Risk**: Low — additive loop; no changes to existing loops, schema, or
  CLI.
- **Breaking Change**: No.

## Related Key Documentation

| Document | Why Relevant |
|---|---|
| `docs/guides/LEARNING_TESTS_GUIDE.md` | Documents the registry lifecycle this loop participates in |
| `docs/guides/LOOPS_GUIDE.md` § API Adoption | Where this loop will be documented alongside `learning-tests-audit` |

## Labels

`feat`, `loop`, `learning-tests`, `migration`, `staleness`, `captured`

---

**Open** | Created: 2026-05-30 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-05-30T21:35:04Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f3ee23bc-341c-48d2-b09f-f34e658c7031.jsonl`
