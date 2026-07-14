---
id: ENH-2635
title: next-issue --include-blocked should report pending depends_on prerequisites
type: ENH
priority: P3
status: done
captured_at: '2026-07-14T00:33:55Z'
completed_at: '2026-07-14T01:23:33Z'
discovered_date: 2026-07-14
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 88
score_complexity: 21
score_test_coverage: 20
score_ambiguity: 24
score_change_surface: 23
---

# ENH-2635: next-issue --include-blocked should report pending depends_on prerequisites

## Summary

`ll-issues next-issue --include-blocked` annotates the top-ranked issue with hard
`blocked_by` status only. It does not surface unresolved soft `depends_on`
prerequisites, so an issue whose soft prerequisite is still open can be reported
as `"blocked": false, "blocked_by": []` in the JSON output — silently hiding a
real ordering deferral.

The default (no-flag) `next-issue` path is correct: it filters via
`find_issues(skip_blocked=True)` → `graph.get_ready_issues()`, which enforces
both hard `blocked_by` and soft `depends_on` ordering. Only the
`--include-blocked` reporting mode is incomplete.

## Current Behavior

In `cmd_next_issue` (`scripts/little_loops/cli/issues/next_issue.py`), the
`include_blocked` branch builds `blocked_by_map` purely from
`graph.blocked_by`:

```python
graph = DependencyGraph.from_issues(find_issues(config))
blocked_by_map = {
    issue_id: sorted(graph.blocked_by.get(issue_id, set()))
    for issue_id in (i.issue_id for i in ranked)
}
...
top_blocked = bool(blocked_by_map.get(top.issue_id))
top_blocked_by = blocked_by_map.get(top.issue_id, [])
```

`graph.get_pending_prerequisites(...)` (the `depends_on` accessor) is never
called. So the JSON row emits `blocked` / `blocked_by` reflecting hard edges
only. A top pick with an incomplete `depends_on` target reports as unblocked.

## Expected Behavior

The `--include-blocked` output should also reflect pending soft prerequisites,
e.g. add a `pending_prerequisites` (or `deferred_by`) field to the JSON row so
soft-dependency ordering is visible in this mode too. The `blocked` boolean
should either account for soft deferrals or be accompanied by a distinct
`deferred`/`pending_prerequisites` signal, so callers can tell "hard-blocked"
from "soft-deferred" from "ready".

## Motivation

`--include-blocked` is the "show me everything, blocked or not, with why" mode.
Omitting soft-prereq deferrals means the "why" is incomplete: a caller inspecting
the JSON can conclude an issue is ready to start when a `depends_on` prerequisite
is still open. Since `depends_on` became ordering-enforcing (BUG-2632), this is a
reporting gap against the documented model, not just cosmetics.

## Proposed Solution

In the `include_blocked` branch of `cmd_next_issue`, additionally compute pending
prerequisites from the same graph and attach them to the JSON row:

```python
pending = sorted(graph.get_pending_prerequisites(top.issue_id))
...
row["blocked"] = top_blocked
row["blocked_by"] = top_blocked_by
row["pending_prerequisites"] = pending  # soft depends_on not yet complete
```

Consider whether the human/plain output should surface the same. Keep the field
absent-or-empty semantics consistent with `blocked_by`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Verified API**: `DependencyGraph.get_pending_prerequisites(issue_id, completed=None)`
  (`scripts/little_loops/dependency_graph.py:183-201`) returns
  `depends_on_edges.get(issue_id, set()) - completed`. `depends_on_edges` is only
  populated with targets that exist in the graph and were not already completed at
  build time (`dependency_graph.py:129-143`). So calling it with no `completed`
  arg — as the Proposed Solution does — returns exactly the still-open soft
  prerequisites; no extra completed-set computation is needed.
- **Insertion point confirmed**: the `include_blocked` branch of `cmd_next_issue`
  (`scripts/little_loops/cli/issues/next_issue.py:47-62`) already holds `graph`
  and `top` in scope; add the `pending` computation after `top_blocked_by` and
  emit it in the JSON row where `blocked`/`blocked_by` are set (`next_issue.py:82-88`).
- **Sort ordering caveat**: `blocked_by_map` is built over `ranked` *before*
  `ranked.sort(key=sort_key)`, but `pending` should be computed for `top` (the
  post-sort pick), matching how `top_blocked`/`top_blocked_by` are derived. Compute
  `pending` after the sort, keyed on `top.issue_id`, not inside the pre-sort map.
- **Test pattern to follow**: `scripts/tests/test_next_issue.py:661`
  (`test_include_blocked_json_has_blocked_field`) is the closest model — it asserts
  the JSON row shape for the `--include-blocked` path. The new soft-defer test
  (AC #4) should mirror its fixture setup, giving the top pick an open `depends_on`
  target (not a `blocked_by` edge) and asserting `pending_prerequisites` is
  populated while `blocked` stays `False`. Contrast with
  `test_include_blocked_returns_blocked_first:619` (hard-blocked case) and
  `test_done_blocker_does_not_block:757` (completed-target exclusion).

## Integration Map

_Wiring pass added by `/ll:wire-issue`:_

### Files to Modify

- `scripts/little_loops/cli/issues/next_issue.py` — primary change: `include_blocked`
  branch of `cmd_next_issue` (lines 42–91). Compute `pending` from
  `graph.get_pending_prerequisites(top.issue_id)` after the sort and stamp it into
  the JSON row where `blocked`/`blocked_by` are set. [Agent 1 finding]
- `scripts/little_loops/cli/issues/next_issues.py` (plural) — apply the same additive
  `pending_prerequisites` field for parity (**decision resolved — see § Sibling Command
  Parity**). `cmd_next_issues` builds an identical `blocked_by_map` (lines 39–70) and
  JSON-row shape from the same `DependencyGraph`; compute pending prerequisites per row
  and stamp them into each JSON row alongside `blocked`/`blocked_by`. [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/CLI.md` — update **both** the `next-issue` JSON field table
  (~line 1224) and the `next-issues` field table (lines 1230–1245); each currently
  describes only `blocked`/`blocked_by`. Add `pending_prerequisites` to both to keep
  the parallel wording consistent. Goes stale the moment the field lands. [Agent 2 finding]
- `docs/reference/API.md` — update **both** `#### next-issue` (lines 3681–3728) and
  `#### next-issues` (lines 3730–3778) prose; add the new field and the "hard-blocked
  vs soft-deferred vs ready" distinction the Motivation calls out. [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md` — lines 943, 3285 reference `--include-blocked`
  conceptually (not field-level). Advisory only; no edit needed unless the meaning of
  `blocked` is redefined rather than kept purely additive. [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_next_issue.py` — new test(s) needed. The `_make_issue` helper
  (lines 19–70) currently supports only `blocked_by`, **not `depends_on`** — it must
  be extended with a `depends_on` parameter (or a sibling helper added) before the
  soft-defer fixture can be written. Model the new test after
  `test_include_blocked_json_has_blocked_field` (line 661, subset-key assertions —
  additive field will NOT break it), giving the top pick an open `depends_on` target
  and asserting `pending_prerequisites` is populated while `blocked` stays `False`.
  Add a completed-`depends_on`-target variant (mirror `test_done_blocker_does_not_block`,
  line 757) and a mixed `blocked_by`+`depends_on` variant. [Agent 1 + 3 findings]
- `scripts/tests/test_next_issues.py` — mirror the soft-defer JSON coverage for the
  plural command so `next_issues.py`'s parity change is tested too. [Agent 1 finding]
- `scripts/tests/test_dependency_graph.py` — `get_pending_prerequisites` is already
  covered (`test_depends_on_edges_populated` line 190, `test_depends_on_completed_target_skipped`
  line 200); no change needed, referenced as the fixture-construction model for
  `depends_on` edges. [Agent 3 finding]

### Sibling Command Parity (Decision: RESOLVED — include for parity)

_Wiring pass added by `/ll:wire-issue`:_

**Decision:** `next_issues.py` (plural) **is in scope** for this issue and gets the
same additive `pending_prerequisites` field.

Rationale: `cmd_next_issues` contains an **identical** `blocked_by_map` construction
(lines 39–70) and the same JSON-row shape, built from the same `DependencyGraph`. If
the plural command were left unchanged, `next-issue --include-blocked --json` would
report `pending_prerequisites` while `next-issues --include-blocked --json` would not,
for identical dependency data — a documentation-visible asymmetry (CLI.md lines
1230–1245, API.md lines 3730–3778 describe the two commands in parallel wording). The
change is additive and low-risk, so applying it to both keeps the surface consistent.

Scope of the parity change (all folded into the sections above):
- `scripts/little_loops/cli/issues/next_issues.py` — compute + stamp `pending_prerequisites`
  per JSON row (see § Files to Modify).
- `docs/reference/CLI.md` / `docs/reference/API.md` — update the `next-issues` field
  table and prose alongside `next-issue` (see § Documentation).
- `scripts/tests/test_next_issues.py` — add soft-defer coverage (see § Tests). [Agent 1 + 2 findings]

### No Coupling Found

- No runtime consumer parses the `--include-blocked --json` output: grep across
  `skills/`, `commands/`, and `loops/` found no code consuming the `blocked`/`blocked_by`
  keys. FSM loops (`loops/lib/cli.yaml:55`, `refine-to-ready-issue.yaml:29`,
  `auto-refine-and-implement.yaml:141`) consume plain ID/path output only. No JSON
  schema file describes this output (`docs/reference/schemas/` holds only `LLEvent`
  schemas). No config-schema or error-message coupling. [Agent 2 finding]

## Impact

- Affected: `scripts/little_loops/cli/issues/next_issue.py` **and**
  `scripts/little_loops/cli/issues/next_issues.py` (`--include-blocked` JSON path only,
  both commands for parity — see Integration Map § Sibling Command Parity). Default
  paths unchanged.
- Also touched: `docs/reference/CLI.md`, `docs/reference/API.md` (doc field list for
  both commands), `scripts/tests/test_next_issue.py` (extend `_make_issue` for
  `depends_on`), `scripts/tests/test_next_issues.py` (parity coverage).
- Low blast radius — additive JSON field. Any consumer relying on `blocked` alone
  to gauge readiness benefits from the correction.

## Scope Boundaries

In scope:
- Add an additive `pending_prerequisites` field to the `--include-blocked --json`
  output of both `next-issue` and `next-issues`.
- Extend `_make_issue` (and the plural test module) to construct `depends_on` edges
  for fixtures.
- Update the `next-issue`/`next-issues` field tables in `docs/reference/CLI.md` and
  `docs/reference/API.md`.

Out of scope:
- Changing default (no-flag) `next-issue`/`next-issues` behavior, ordering, or exit
  codes — those already enforce soft `depends_on` via `get_ready_issues()`.
- Redefining the semantics of the existing `blocked`/`blocked_by` fields (kept purely
  additive; `blocked` stays hard-edge-only).
- Any new runtime consumer of the JSON output (no consumers exist today — see
  § No Coupling Found).

## Acceptance Criteria

- `next-issue --include-blocked --json` includes pending `depends_on`
  prerequisites for the top pick (empty list when none).
- An issue that is soft-deferred (open `depends_on` target) is distinguishable
  from a genuinely ready issue in the `--include-blocked` output.
- Default `next-issue` behavior and exit codes are unchanged.
- Test coverage for a top pick that is soft-deferred but not hard-blocked
  (requires extending `_make_issue` with a `depends_on` param).

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/CLI.md` and `docs/reference/API.md` `next-issue` **and `next-issues`**
  sections mention the new `pending_prerequisites` field and the blocked/deferred/ready
  distinction.
- `next-issues --include-blocked --json` (plural) also includes `pending_prerequisites`
  for parity with `next-issue`, covered by `test_next_issues.py`.


## Resolution

**Done** — 2026-07-14. Added an additive `pending_prerequisites` field to the
`--include-blocked --json` output of both `next-issue` and `next-issues`.

- `scripts/little_loops/cli/issues/next_issue.py` — computes
  `sorted(graph.get_pending_prerequisites(top.issue_id))` after the sort (keyed on
  the post-sort `top`) and stamps it into the JSON row alongside `blocked`/`blocked_by`.
  The non-`--include-blocked` branch emits an empty list.
- `scripts/little_loops/cli/issues/next_issues.py` — builds a `pending_prereq_map`
  parallel to `blocked_by_map` and stamps `pending_prerequisites` per row (parity).
- `blocked` stays hard-`blocked_by`-edge-only, so callers can now distinguish
  hard-blocked / soft-deferred / ready. Default (no-flag) paths unchanged — they
  already filter soft `depends_on` via `get_ready_issues()`.
- Extended the `_make_issue` test helper in both `test_next_issue.py` and
  `test_next_issues.py` with a `depends_on` param, and added soft-defer / ready /
  done-prereq / mixed-hard-and-soft JSON coverage.
- Updated `docs/reference/CLI.md` and `docs/reference/API.md` field tables/prose for
  both commands.

All acceptance criteria met. Full suite: 14882 passed, 36 skipped. Lint + mypy clean.

## Status

**Done** | Created: 2026-07-14 | Completed: 2026-07-14 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-07-14T01:22:52 - `4c543f5a-a89a-4026-a3bb-82f808ce9096.jsonl`
- `/ll:ready-issue` - 2026-07-14T01:11:56 - `82850630-6ee6-45d8-a849-9f6a55a252a7.jsonl`
- `/ll:wire-issue` - 2026-07-14T00:43:59 - `fd4d0ee0-3009-440f-aebb-109c902cef3c.jsonl`
- `/ll:refine-issue` - 2026-07-14T00:36:21 - `db508eb9-b933-4dbd-9d51-19f77e3f7336.jsonl`
