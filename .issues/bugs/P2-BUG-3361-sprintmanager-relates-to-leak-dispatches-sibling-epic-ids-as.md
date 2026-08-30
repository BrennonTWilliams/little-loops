---
discovered_date: 2026-08-30
discovered_by: debug-loop-run
source_loop: sprint-refine-and-implement
source_state: resolve_set
---

# BUG-3361: SprintManager.load_or_resolve unions relates_to sibling-EPIC ids into an EPIC's dispatch set

## Current Behavior

`SprintManager.load_or_resolve()` (`scripts/little_loops/sprint.py:341`) builds
`forward_ids` as `set(epic_info.relates_to)` with no issue-type filter, then
unions it with the backward `parent:`-chain `backward_ids` to form the EPIC's
dispatch set. Because `relates_to:` is also used as a documentation
cross-reference between sibling EPICs (not a decomposition edge), an EPIC that
lists a sibling EPIC in `relates_to:` gets that sibling's raw `EPIC-*` id
unioned into its own dispatch set alongside its real leaf children.

## Summary

`sprint-refine-and-implement EPIC-2258` (instance `sprint-refine-and-implement-20260830T124555`,
manually stopped by the user 2026-08-30 18:01 UTC) dispatched
`EPIC-2178,EPIC-2257,FEAT-2797,FEAT-2263,FEAT-2261` into autodev — two raw EPIC
ids alongside EPIC-2258's real leaf children. autodev then ran
`ll-auto --only EPIC-2178` and `ll-auto --only EPIC-2257` directly, i.e. it
tried to implement the EPIC coordination docs themselves rather than their
sub-issues. This is what looked, from the live output, like the loop "trying
to implement an EPIC Issue itself, instead of the EPIC's sub-Issues."

Root cause: `SprintManager.load_or_resolve()`
(`scripts/little_loops/sprint.py:341`) builds an EPIC's dispatch set as
`forward_ids | backward_ids`, where:

```python
forward_ids: set[str] = set(epic_info.relates_to)
```

`forward_ids` is taken verbatim from the EPIC's `relates_to:` frontmatter with
**no issue-type filter**. EPIC-2258 declares
`relates_to: [EPIC-2257, EPIC-2178]` as a documentation cross-reference to
sibling epics ("Sequenced after Gemini (EPIC-2178)"; generic infra lives under
EPIC-2257) — not decomposition children. Those sibling EPIC ids get unioned
into the dispatch set exactly like real children (which are found correctly
via the backward `parent:` chain walk in the same function).

This is the same bug *class* as `BUG-2638` ("`ll-issues next-issues` leaks
EPIC ids into the implementable backlog") and shares a compounding factor with
`BUG-1183` ("autodev skips parent after breakdown signal, no children") — both
already fixed (`status: done`) — but in a third, unguarded code path:
EPIC-scoped sprint resolution via `relates_to`.

**Compounding factor** (not the primary fix target, but relevant context):
autodev's `check_epic_id` guard (inside `refine_current`'s sub-loop) correctly
detected EPIC-2178/EPIC-2257 as EPIC-type and ran `breakdown_issue`, but the
`check_broke_down` gate added by BUG-1183 only short-circuits when breakdown
produces *new* children (`[ -s autodev-new-children.txt ]`). Since these are
already fully-decomposed EPICs with nothing new to add, the gate fell through
to `run_size_review → reconcile_current → confidence-check → decide_current →
implement_current`, which unconditionally runs `ll-auto --only "$CURRENT"` on
whatever id is current — still the raw EPIC id.

`ll-auto`'s own coding agent caught the mismatch each time and refused to
falsely mark the EPIC done (no data corruption occurred), but ~4 minutes of
agent time were burned per misrouted EPIC before the user stopped the run.

## Loop Context

- **Loop**: `sprint-refine-and-implement` → `auto-refine-and-implement` →
  `autodev`
- **State**: `resolve_set` (root cause); `implement_current` (symptom)
- **Signal type**: config/logic defect — issue-type leak into a dispatch set
- **Occurrences**: 2 of 5 dispatched ids in this run (EPIC-2178, EPIC-2257)
- **Last observed**: 2026-08-30T17:54:48Z (start of `implement_current` for
  EPIC-2257, when the user stopped the run)

## History Excerpt

`resolve_set`'s resolved dispatch list (from `SprintManager.load_or_resolve("EPIC-2258")`):

```json
{"event": "action_complete", "ts": "2026-08-30T17:46:05.712741+00:00", "run_id": "2026-08-30T174555-auto-refine-and-implement", "loop": "auto-refine-and-implement", "exit_code": 0, "duration_ms": 5918, "output_preview": "EPIC-2178,EPIC-2257,FEAT-2797,FEAT-2263,FEAT-2261", "state": "resolve_set", "iteration": 2}
```

`implement_current` running `ll-auto --only EPIC-2178` and getting refused by its own coding agent:

```json
{"event": "action_complete", "ts": "2026-08-30T17:54:14.772689+00:00", "run_id": "2026-08-30T174607-autodev", "loop": "autodev", "exit_code": 1, "duration_ms": 211664, "output_preview": "...the next real task is implementing FEAT-2186 (hook adapter) — that's the actual next open child... [12:54:14] REFUSING to mark EPIC-2178 as completed: no code changes detected despite returncode 0 ... Issue EPIC-2178 was attempted but verification failed", "state": "implement_current", "iteration": 39}
```

`check_epic_id` correctly flagging EPIC-2178 during refine, before the pipeline nonetheless continued to `implement_current`:

```json
{"event": "route", "ts": "2026-08-30T17:46:18.195642+00:00", "from": "check_issue_resolved", "to": "check_epic_id"}
{"event": "route", "ts": "2026-08-30T17:46:18.223992+00:00", "from": "check_epic_id", "to": "breakdown_issue"}
```

EPIC-2258's frontmatter (the actual leak source):

```
relates_to:
- EPIC-2257
- EPIC-2178
```

## Steps to Reproduce

1. Create `EPIC-A` and `EPIC-B` as separate, independently-decomposed epics.
2. Add `relates_to: [EPIC-B]` to `EPIC-A`'s frontmatter as a documentation
   cross-reference (not a `parent:` decomposition edge).
3. Give `EPIC-A` its own real leaf children via `parent: EPIC-A` on their
   frontmatter.
4. Call `SprintManager.load_or_resolve("EPIC-A")` (or run
   `sprint-refine-and-implement EPIC-A` / any sprint path that resolves an
   EPIC id).
5. Observe: the returned `Sprint.issues` includes `EPIC-B` alongside
   `EPIC-A`'s real children — `EPIC-B` is not a child of `EPIC-A` and should
   not be dispatched for implementation.

## Expected Behavior

`SprintManager.load_or_resolve()` should never place an EPIC-type id into an
EPIC's own dispatch set. `relates_to:` on an EPIC is a documentation
cross-reference to sibling/related epics, not a decomposition edge, and should
either be excluded entirely from `forward_ids`, or filtered the same way
`next_issues.py` filters `find_issues()` results for BUG-2638
(`not info.issue_id.startswith("EPIC-")`).

## Proposed Solution

In `scripts/little_loops/sprint.py`, filter `forward_ids` (and/or the final
`child_ids` union) to exclude ids starting with `EPIC-`, mirroring the
`not i.issue_id.startswith("EPIC-")` guard already used in
`cli/issues/next_issues.py` (BUG-2638):

```python
# scripts/little_loops/sprint.py, SprintManager.load_or_resolve()
forward_ids: set[str] = {
    i for i in epic_info.relates_to if not i.startswith("EPIC-")
}
```

As defense in depth, consider also hardening `implement_current` in
`autodev.yaml` to refuse (or redirect to the EPIC's own
confidence-check-identified next child) when `$CURRENT` matches
`^EPIC-\d+$`, so a future leak from any resolution path can't reach
`ll-auto --only` on an EPIC id.

## Program Design

### Signatures

- `SprintManager.load_or_resolve(self, arg: str) -> Sprint | None` — signature unchanged; only the `forward_ids` computation inside changes

### Call Path

`SprintManager.load_or_resolve()` -> filtered `forward_ids` (excludes `EPIC-`-prefixed ids) -> unioned with `backward_ids` into `child_ids` (`sprint.py:367`)

## Impact

- **Priority**: P2 - Misroutes ~4 minutes of agent time per leaked EPIC id into a doomed `ll-auto --only` attempt; no data corruption (the coding agent's own completion guard refuses to mark the EPIC done), but wastes autodev run time and requires manual intervention to stop/redirect the run.
- **Effort**: Small - single-line filter change to `forward_ids` construction, mirroring an existing, already-shipped pattern (BUG-2638's `next_issues.py` fix).
- **Risk**: Low - additive filter on a set comprehension; only removes ids that were never valid children of the EPIC, cannot regress legitimate dispatch behavior.
- **Breaking Change**: No.

## Acceptance Criteria

- [ ] `SprintManager.load_or_resolve("EPIC-2258")` (or an equivalent unit
      test fixture with a `relates_to:` pointing at another EPIC) never
      includes an `EPIC-*` id in the returned `Sprint.issues`
- [ ] A regression test mirrors BUG-2638's coverage but targets
      `sprint.py`'s forward/`relates_to` path specifically
- [ ] `python -m pytest scripts/tests/` passes

## Labels

`bug`, `loops`, `captured`

## Status

**Open** | Created: 2026-08-30 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-08-30T18:30:07 - `94b795f5-375b-4a55-9190-f07c0af5f00b.jsonl`
