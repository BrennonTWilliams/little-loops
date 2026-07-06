---
id: ENH-2481
title: Scope prompt-across-issues to full EPIC subtree (transitive children)
type: ENH
priority: P3
captured_at: '2026-07-04T00:00:00Z'
completed_at: 2026-07-06 02:58:17+00:00
discovered_date: 2026-07-04
discovered_by: capture-issue
status: done
relates_to:
- EPIC-1853
decision_needed: false
confidence_score: 98
outcome_confidence: 91
score_complexity: 23
score_test_coverage: 23
score_ambiguity: 23
score_change_surface: 22
---

# ENH-2481: Scope prompt-across-issues to full EPIC subtree (transitive children)

## Summary

`ll-issues list --parent EPIC-NNN` and the `prompt-across-issues` loop's `--context parent=EPIC-NNN` filter only match **direct one-hop children** (`issue.parent == parent_filter` and `i.get('parent') == parent` respectively), so grandchildren nested under an intermediate FEAT/ENH are silently skipped. Make `--parent` resolve the **full transitive descendant set** using the existing `compute_epic_progress` resolver, and rewire the loop to forward `--parent` instead of its inline equality filter so it inherits the behavior.

This completes the intent of EPIC-1853 (`add-parent-epic-filter-to-prompt-across-issues-loop`), which shipped with direct-only semantics.

## Current Behavior

- `scripts/little_loops/cli/issues/list_cmd.py:65` — filter predicate `issue.parent == parent_filter` matches only direct children of the given parent.
- `scripts/little_loops/loops/prompt-across-issues.yaml` (`init` action, lines 56-58) — post-filters the JSON output with `i.get('parent') == parent`, again direct-only.
- A user running `ll-loop run prompt-across-issues "<prompt>" --context parent=EPIC-NNN` against an EPIC whose grandchildren sit under a completed FEAT/ENH sees those grandchildren silently dropped.

## Expected Behavior

```bash
# Sweeps every active issue transitively descending from EPIC-1773
# (children of children included)
ll-loop run prompt-across-issues "<prompt>" --context parent=EPIC-NNN

# Same transitive semantics on the underlying CLI
ll-issues list --parent EPIC-1773
```

The filter set still respects `--status` (default `open`), so only *active* descendants are selected — done grandchildren are not re-prompted. The previously-implemented CLI flag stays; only the predicate changes.

## Motivation

Wave-based EPIC work (EPIC-1773, EPIC-1853 era) routinely layers child issues under intermediate feature/enhancement tasks. After EPIC-1853 shipped, users sweeping "everything tied to EPIC-NNN" hit the one-hop wall and had to manually enumerate descendants. The transitive resolver already exists (`compute_epic_progress` in `scripts/little_loops/issue_progress.py:83`) — it's cycle-safe, walks through `done` intermediates, and is already imported by `list_cmd.py`'s `group_by == "epic"` branch.

Two other loops (`goal-cluster.yaml:76`, `rn-build.yaml:435`) also shell out to `--parent` and currently get only direct descendants — making `--parent` transitive globally fixes their long-standing scope gap (per `rn-build-failure-findings.md:117-128`) for free.

## Proposed Solution

Reuse the existing public transitive resolver; do not write a new chain walker.

### 1. Make `ll-issues list --parent` transitive — `scripts/little_loops/cli/issues/list_cmd.py`

Before the existing `filtered = [...]` comprehension at line 55, resolve the transitive descendant set when `parent_filter` is set:

- Load **all** issues regardless of status (intermediate parents may be `done`), reusing the pattern already inlined at `list_cmd.py:154-166`: `find_issues(config, status_filter=_ALL_STATUSES)`.
- `prog = compute_epic_progress(parent_filter, _all_issues)`; build `descendant_ids = {c.issue_id for c in prog.children} if prog else set()`.
- Change the filter predicate at line 65 from `issue.parent == parent_filter` to `issue.issue_id in descendant_ids`.

`compute_epic_progress` works for any parent id (not just EPIC-typed) and uppercases the id internally, so a FEAT/ENH parent still works. Missing id → `prog is None` → empty set → "No active issues" (same as today's empty result).

### 2. Rewire the loop — `scripts/little_loops/loops/prompt-across-issues.yaml`

Replace the inline Python `parent` filter (lines 56-58) with a forwarded CLI flag in the `init` action, mirroring the existing `TYPE_ARG` handling:

```sh
PARENT_ARG=""
if [ -n "${context.parent}" ]; then
  PARENT_ARG="--parent ${context.parent}"
fi
ll-issues list $TYPE_ARG $PARENT_ARG --json | python3 -c "
import json, sys
issues = json.load(sys.stdin)
for i in issues:
    print(i['id'])
"
```

Keeps `${context.parent}` referenced in the init action (existing structural test still passes) and inherits transitive behavior for free.

### 3. Docs / help text

- `scripts/little_loops/cli/issues/__init__.py:235-240` — update `--parent` help to note it includes transitive descendants (children of children).
- `docs/reference/CLI.md:~1028` — update the `--parent` row wording.
- `scripts/little_loops/loops/prompt-across-issues.yaml` `description:` (lines 11-12) — note the sweep now covers the full EPIC subtree (grandchildren included).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/list_cmd.py` — transitive resolution + line-65 predicate
- `scripts/little_loops/cli/issues/__init__.py` — `--parent` help text
- `scripts/little_loops/loops/prompt-across-issues.yaml` — init action uses `--parent`
- `docs/reference/CLI.md` — `--parent` description

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/goal-cluster.yaml:76` — shells out to `ll-issues list --parent`; **wants** transitive (currently silently misses grandchildren)
- `scripts/little_loops/loops/rn-build.yaml:435` — shells out to `ll-issues list --parent`; **wants** transitive (per `rn-build-failure-findings.md:117-128` — file is at the project root, not under `thoughts/`)

### Other out-of-scope direct-only `parent ==` callers (verified, do not touch)

- `scripts/little_loops/cli/issues/epic_consistency.py:125,130` — epic-consistency linter; uses `i.parent == epic_id` to surface issues lacking an EPIC ancestor (intentional direct-only)
- `skills/review-epic/SKILL.md:77` — review-epic skill prompt; inlines `i.parent == epic_id` for `epic_id` discovery
- `scripts/tests/test_review_epic_skill.py:19` — test pinning the snippet above

These complement the already-listed `sprint.py:326` and `cli/deps.py:278` exclusions. Total direct-only callers not affected by this issue: 5 (incl. `goal-cluster.yaml:76` and `rn-build.yaml:435`, which ARE in scope but incidentally improve from transitive).

Investigation confirmed **no caller relies on direct-only semantics** — both other call sites benefit, not regress, from the change.

### Reused utilities (no new code)
- `compute_epic_progress` — `scripts/little_loops/issue_progress.py:83` (transitive resolver; cycle-safe, walks through `done` intermediates)
- `find_issues(..., status_filter=_ALL_STATUSES)` — `scripts/little_loops/issue_parser.py:1033`
- `_ALL_STATUSES` set literal — already inlined at `list_cmd.py:156-163`

### Tests
- `scripts/tests/test_issues_cli.py` — add `test_list_parent_includes_transitive_grandchild` (reuse the BUG-2382 fixture `issues_dir_with_completed_intermediate`: EPIC → done FEAT → ENH grandchild); assert `list --parent EPIC-xxx` output contains the grandchild. Add `test_list_parent_excludes_unrelated`.
- `scripts/tests/test_builtin_loops.py` (`TestPromptAcrossIssuesLoop`, ~line 1676) — extend `test_init_supports_parent_filter` to assert the init action forwards `--parent` / builds `PARENT_ARG` (i.e. no longer the inline `i.get('parent')` equality filter).
- `compute_epic_progress` transitive behavior is already covered by `scripts/tests/test_issue_progress.py` — no new unit test needed.

### Documentation
- `scripts/little_loops/cli/issues/__init__.py:235-240` — `--parent` help text
- `docs/reference/CLI.md:~1028` — `--parent` row wording
- `scripts/little_loops/loops/prompt-across-issues.yaml` description (lines 11-12)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md:724` — loop catalog table row for `prompt-across-issues` says "Optionally scope to children of an epic via `--context parent=EPIC-NNN`"; needs the same direct-only → transitive wording update as `docs/reference/CLI.md` (verified `docs/reference/COMMANDS.md` does NOT duplicate this text — no change needed there)
- `scripts/little_loops/loops/prompt-across-issues.yaml:33` — inline context-schema comment `# Optional: EPIC-NNN. When set, restricts sweep to issues with matching parent: field.` describes direct-match semantics and goes stale alongside the `description:` block (lines 11-12) once the init action is rewired

### Configuration
- N/A

## Implementation Steps

1. In `scripts/little_loops/cli/issues/list_cmd.py`: load `_all_issues` (when `parent_filter` is set), call `compute_epic_progress(parent_filter, _all_issues)`, build `descendant_ids`, swap the line-65 predicate to `issue.issue_id in descendant_ids`.
2. In `scripts/little_loops/loops/prompt-across-issues.yaml` `init` action: replace the inline `i.get('parent') == parent` Python line with the `PARENT_ARG` shim mirroring `TYPE_ARG`, and pass `--parent ${context.parent}` to `ll-issues list`.
3. Update `--parent` help text in `scripts/little_loops/cli/issues/__init__.py` and the corresponding row in `docs/reference/CLI.md` to note transitive scope.
4. Update the `prompt-across-issues.yaml` loop `description:` (lines 11-12) and the inline `context.parent` schema comment (line 33) to note full-subtree coverage; also update the loop catalog row in `docs/guides/LOOPS_REFERENCE.md:724`.
5. Add `test_list_parent_includes_transitive_grandchild` and `test_list_parent_excludes_unrelated` to `scripts/tests/test_issues_cli.py` using the BUG-2382 fixture pattern.
6. Extend `test_init_supports_parent_filter` in `scripts/tests/test_builtin_loops.py` to assert the `--parent` forwarding path.
7. Verify: `python -m pytest scripts/tests/test_issues_cli.py scripts/tests/test_builtin_loops.py scripts/tests/test_issue_progress.py -q`; `python -m mypy scripts/little_loops/`; `ruff check scripts/`.
8. Manual end-to-end (in a project with a nested EPIC): `ll-issues list --parent EPIC-1773 --json | python3 -c "import json,sys; print([i['id'] for i in json.load(sys.stdin)])"` — confirm grandchildren appear.
9. Confirm `goal-cluster`/`rn-build` unaffected structurally: `python -m pytest scripts/tests/test_goal_cluster.py -q`.

## API/Interface

```python
# scripts/little_loops/cli/issues/list_cmd.py
# When --parent EPIC-NNN is supplied, the predicate resolves the full
# transitive descendant set via compute_epic_progress.
# Behavior change: previously direct children only; now includes grandchildren
# (through done intermediates). Default --status still applies.
```

```bash
# All active descendants (children of children) of EPIC-NNN
ll-issues list --parent EPIC-NNN
ll-loop run prompt-across-issues "<prompt>" --context parent=EPIC-NNN
```

## Scope Boundaries

- **Out of scope**: `sprint.py:326` and `cli/deps.py:278` keep their own direct-only `parent ==` resolution; this task is the `list`/loop path only. (Verified by `ll:codebase-locator`: 3 additional direct-only sites also intentionally remain direct-only — see `Integration Map` listing.)
- **Out of scope**: multi-parent selection.
- **Out of scope**: changing `ll-loop run` itself — uses existing `--context KEY=VALUE` mechanism.
- **Out of scope**: re-running done grandchildren — only active (`open`/`in_progress`/`blocked`) descendants are surfaced under default `--status`.

## Impact

- **Priority**: P3 — fixes a known scope gap in a recently-shipped EPIC-1853 deliverable; investigation shows no call sites rely on direct-only semantics.
- **Effort**: Small — reuses `compute_epic_progress` (no new resolver); ~5-15 LOC across `list_cmd.py` + loop YAML + 2 doc strings.
- **Risk**: Low — `_ALL_STATUSES` resolution already inlined at `list_cmd.py:154-166`; semantics remain `--status`-gated; verified no caller relies on direct-only.
- **Breaking Change**: Behaviorally yes for `--parent` (broader set), but the previous behavior was a defect and no downstream consumer relied on it.

## Labels

`enhancement`, `loops`, `fsm`, `cli`, `epic-scoped`

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/CLI.md` (`ll-issues list --parent`) | Documents the CLI flag whose semantics change |
| `docs/reference/API.md` (`compute_epic_progress`) | Reused utility — already a public symbol |

## Codebase Research Findings

_Added by `/ll:refine-issue ENH-2481 --auto` — based on codebase analysis:_

### Verification summary
- All 12 file paths exist; 11/12 line anchors match the current source exactly. One near-match: the issue says `~line 1676` for `TestPromptAcrossIssuesLoop` — the **class** is at `test_builtin_loops.py:1576`, but the referenced method `test_init_supports_parent_filter` is at `test_builtin_loops.py:1676` exactly (as planned).
- All behavioral claims verified: `list_cmd.py:65` predicate is direct-only, `compute_epic_progress` walks through `done` intermediates, `_issue_descends_to` (`issue_progress.py:67-80`) is the cycle-safe chain walker, `find_issues` accepts `status_filter` kwarg, and the proposed `PARENT_ARG` shim mechanically mirrors `TYPE_ARG`.
- Existing transitive tests already cover `_issue_descends_to`: `test_transitive_chain_includes_grandchildren` at `test_issue_progress.py:244` and `test_cycle_in_parent_chain_does_not_loop` at `test_issue_progress.py:254` — so the upstream resolver is provably safe; this issue only stitches it onto the CLI filter.

### Resolver choice — code-level alternative
The proposal picks `compute_epic_progress(parent_filter, _all_issues)` (full aggregator with title lookup and `by_status`). A lighter alternative is `_issue_descends_to(issue_id, parent_filter, parent_map)` (`issue_progress.py:67-80`) which only walks the chain. If implementer wants to avoid the title-lookup overhead and `_ALL_STATUSES` round-trip, they can build the `parent_map` inline and use `_issue_descends_to` per-issue in the comprehension. Either is fine; `compute_epic_progress` reuses the existing `prog.children` (no extra resolver), so it remains the recommendation.

### Cross-references
- Related bug `BUG-2480` (`group-by-epic-renderer-filters-nested-epic-children`) — staged but not committed; same root pattern (`parent ==` direct-only) in the `--group-by epic` renderer.
- Related bug `BUG-2441` (`epic-progress-rollup-direct-children-only-disagrees-with-list-bucketing`) — `epic-progress.py` rolls up `len(prog.children)` which IS transitive, but `by_status` buckets used elsewhere are direct-only in some paths; intersects this area.
- Decisions log already captures the rule: `.ll/decisions.yaml:3925-3930` ("Make ll-issues list --parent transitive globally; rewire prompt-across-issues") — this issue is the explicit follow-through.

### Documentation accuracy caveat
`docs/reference/CLI.md:1028` currently claims `--parent` "Accepts short form (`101`)" — argparse does NOT normalize this (it's a plain `metavar="ISSUE_ID"`); `--parent 101` returns empty today. The proposed rewording should drop that misleading tail, since the issue scope is transitive descendants (not input-form normalization). Implementer may want to file a separate issue for the doc-vs-code mismatch.

### `compute_epic_progress` callers (full set)
The function is invoked from 3 places:
- `scripts/little_loops/cli/issues/list_cmd.py:198` (group-by epic badges — already cited)
- `scripts/little_loops/cli/issues/epic_progress.py:46,54` (`ll-issues epic-progress` command) — already transitive
- (After this issue lands) `scripts/little_loops/cli/issues/list_cmd.py:65` (new transitive filter for `--parent`)

No other call sites — adding transitive filtering does not regress any other consumer.

## Resolution

Implemented as scoped. `ll-issues list --parent` now resolves the full transitive
descendant set via `compute_epic_progress` (loading `_ALL_STATUSES` so `done`
intermediates don't sever the chain), replacing the direct-only
`issue.parent == parent_filter` predicate in `list_cmd.py`. The
`prompt-across-issues` loop's `init` action was rewired to forward a `--parent`
`PARENT_ARG` shim (mirroring `TYPE_ARG`) instead of inline
`i.get('parent') == parent` post-filtering, so it inherits the transitive
behavior — as do `goal-cluster` and `rn-build` which shell out to the same flag.
Help text (`__init__.py`), `docs/reference/CLI.md` (dropped the inaccurate
"short form (`101`)" claim), the loop `description:`/schema comment, and the
`LOOPS_REFERENCE.md` catalog row were updated to note transitive scope.

**Tests**: `test_list_parent_includes_transitive_grandchild` /
`test_list_parent_excludes_unrelated` (test_issues_cli.py, reusing the BUG-2382
`issues_dir_with_completed_intermediate` fixture) and an extended
`test_init_supports_parent_filter` (test_builtin_loops.py) asserting `--parent`
forwarding. Full suite green (pre-existing unrelated failures in
`test_ll_logs.py::TestEvalExport` and a `test_hooks_integration` ordering flake
confirmed present without this change). mypy + ruff clean.

## Session Log
- `/ll:manage-issue` - 2026-07-06T02:58:17Z - `ac6b8a93-299d-4e0a-8b17-eeddf1f743fa.jsonl`
- `/ll:confidence-check` - 2026-07-05T00:00:00Z - `484259f2-5221-4ca0-85ec-6687b9946b78.jsonl`
- `/ll:wire-issue` - 2026-07-05T15:48:19 - `92635b63-1dd3-4d74-884a-fdcece6c774c.jsonl`
- `/ll:refine-issue` - 2026-07-05T01:02:22 - `b75573d6-6f9f-475d-ab44-123e72f36c81.jsonl`

- `/ll:capture-issue` - 2026-07-04T00:00:00Z - capture from plan file `noble-forging-robin.md`

---

## Status

**Open** | Created: 2026-07-04 | Priority: P3
