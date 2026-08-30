---
discovered_date: 2026-08-30
discovered_by: debug-loop-run
source_loop: sprint-refine-and-implement
source_state: resolve_set
decision_needed: false
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

`SprintManager.load_or_resolve()` should never place a `relates_to`-sourced
EPIC-type id into an EPIC's own dispatch set. `relates_to:` on an EPIC is a
documentation cross-reference to sibling/related epics, not a decomposition
edge, and EPIC-shaped entries should be filtered out of `forward_ids` the same
way `next_issues.py` filters `find_issues()` results for BUG-2638.

**Scope note — backward path is intentionally untouched.** A genuine sub-EPIC
reached via the backward `parent:` chain (e.g. `parent: EPIC-A` on `EPIC-B`)
IS deliberately included in the dispatch set — ENH-2615 aligned this with
`compute_epic_progress()` so run construction and the EPIC-completion gate
agree on membership, and `test_load_or_resolve_nested_epic_grandchild_transitive`
(`scripts/tests/test_sprint.py:2884`) asserts `EPIC-801 in result.issues` for
exactly that case. This fix must not change backward-path semantics; only the
forward/`relates_to` path is filtered.

## Proposed Solution

In `scripts/little_loops/sprint.py`, filter `forward_ids` **only** (NOT the
final `child_ids` union — filtering the union would break
`test_load_or_resolve_nested_epic_grandchild_transitive` and silently change
the ENH-2615 backward-path sub-EPIC semantics; see Expected Behavior scope
note) to exclude EPIC-shaped ids, reusing the module's existing
case-insensitive `_EPIC_ID_RE` primitive (see Decision Rationale below for why
this is selected over a literal `.startswith("EPIC-")` check):

```python
# scripts/little_loops/sprint.py, SprintManager.load_or_resolve()
forward_ids: set[str] = {
    i for i in epic_info.relates_to if not _EPIC_ID_RE.match(i)
}
```

**Out of scope — backward-path sub-EPIC dispatch (file separately).** Even
with this fix, a legitimate sub-EPIC included via the backward `parent:` chain
is still dispatched as a raw `EPIC-*` id and will hit the same
`ll-auto --only EPIC-*` misroute in autodev. The fix for that path is defense
in depth in `autodev.yaml`: harden `implement_current` to refuse (or redirect
to the EPIC's own confidence-check-identified next child) when `$CURRENT`
matches `^EPIC-\d+$`. This belongs in a separate issue (mirroring the
BUG-3362 split for the `deps.py` duplicate), since it is a loop-YAML change
with different testing needs than this `sprint.py` filter.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-30 — based on codebase analysis:_

Two viable filter primitives for excluding EPIC-typed ids from `forward_ids`:

**Option A**: `{i for i in epic_info.relates_to if not i.startswith("EPIC-")}` — the literal snippet already in this issue's Proposed Solution, mirroring BUG-2638's `next_issues.py` pattern exactly (`not i.issue_id.startswith("EPIC-")`, `next_issues.py:52,83,86`). Case-sensitive: a `relates_to: [epic-2178]` entry would not be filtered, since `IssueInfo.relates_to` parsing (`issue_parser.py:3624-3671`) does not normalize entries to uppercase.

**Option B**: `{i for i in epic_info.relates_to if not _EPIC_ID_RE.match(i)}` — reuses the module's existing EPIC-id-shape primitive (`_EPIC_ID_RE = re.compile(r"^EPIC-\d+$", re.IGNORECASE)`, `sprint.py:14`), already applied case-insensitively at `sprint.py:319` for the `arg` parameter and exercised by `test_load_or_resolve_epic_id_case_insensitive` (`test_sprint.py:2841`) for that same input path.

> **Selected:** Option B — reuses the module's existing case-insensitive `_EPIC_ID_RE` primitive, avoiding the case-sensitivity regression Option A would leave open on a lowercase/mixed-case sibling-EPIC `relates_to` entry.

**Recommended**: Option B — `relates_to` entries are unnormalized free text, and the module already holds a case-insensitive EPIC-id convention for exactly this shape of check; Option A silently regresses on a lowercase or mixed-case sibling-EPIC reference.

### Decision Rationale

**Selected**: Option B — `{i for i in epic_info.relates_to if not _EPIC_ID_RE.match(i)}`

**Reasoning**: `epic_info.relates_to` is parsed verbatim from frontmatter with no case normalization (`issue_parser.py:3624-3671`), so a case-sensitive `.startswith("EPIC-")` filter (Option A) would silently fail to exclude a sibling-EPIC id written as `epic-2178` or `Epic-2178`, leaving the exact bug this issue reports open under a different casing. `sprint.py` already establishes case-insensitive EPIC-id-shape detection as its local convention — `_EPIC_ID_RE = re.compile(r"^EPIC-\d+$", re.IGNORECASE)` (`sprint.py:14`), used at `sprint.py:319` together with an `.upper()` normalization step (`sprint.py:322`) — and Option B is the only option consistent with that existing convention.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|:-:|:-:|:-:|:-:|:-:|
| A — `.startswith("EPIC-")` | 2 | 3 | 3 | 1 | 9/12 |
| B — `_EPIC_ID_RE.match(...)` | 3 | 3 | 3 | 3 | **12/12** |

**Key evidence**:
- `_EPIC_ID_RE` already defined and used case-insensitively in this same module: `sprint.py:14`, `sprint.py:319`, `sprint.py:322`.
- An identically-shaped case-insensitive regex exists in a sibling module (`recursive_finalize.py:35`), confirming this is the established codebase-wide convention for EPIC-id-shape checks, not a one-off.
- `relates_to` entries are unnormalized free text (`issue_parser.py:3624-3671`) — no upstream uppercasing to rely on.
- No real EPIC id in `.issues/epics/*.md` deviates from the `EPIC-\d+` shape, so `_EPIC_ID_RE` has full coverage with no over/under-matching risk.
- Existing test `test_load_or_resolve_epic_id_case_insensitive` (`test_sprint.py:2841`) covers case-insensitivity only for the `arg` parameter, not for a `relates_to` entry — the regression test this issue's Acceptance Criteria calls for is new coverage, not inherited from that test.

**Rationale precision — the case-insensitivity argument is about convention/robustness, not an observable leak today.** A lowercase `relates_to: [epic-2178]` entry never leaks even without this fix: `child_ids = (forward_ids | backward_ids) & active_ids_set` (`sprint.py:367`) intersects against canonical uppercase ids from `find_issues()`, so the lowercase string is dropped by the intersection regardless. Option B is still correct (matches the module's convention; stays safe if the intersection ever changes), but the regression test's must-fail-before-fix case is the **uppercase** sibling-EPIC repro — a lowercase-entry test passes trivially both before and after and may be added only as a secondary safety assertion.

## Integration Map

### Codebase Research Findings

### Files to Modify
- `scripts/little_loops/sprint.py` — `forward_ids` construction at `sprint.py:341` inside `SprintManager.load_or_resolve()`; the union/active-filter at `sprint.py:365-368` is downstream and unaffected by the fix itself

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/sprint/edit.py:17` — `manager.load_or_resolve(args.sprint)`
- `scripts/little_loops/cli/sprint/manage.py:73` — `manager.load_or_resolve(args.sprint)`
- `scripts/little_loops/cli/sprint/show.py:166` — `manager.load_or_resolve(args.sprint)`
- `scripts/little_loops/cli/sprint/run.py:380` — `manager.load_or_resolve(args.sprint)`
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:146,356` — `resolve_set` state builds `SprintManager(...).load_or_resolve(arg)`, the loop-context call site this issue's Summary traces the leak through

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/goal-cluster.yaml:110` — `sm.load_or_resolve(stripped)` inside an inline `subprocess` Python block; guarded by `not re.match(r'^(EPIC-\d+|\[)', stripped, re.IGNORECASE)` at line 105 so an EPIC-shaped `arg` never reaches this call site — unaffected by the leak scenario itself, but still a live caller of the function being changed

### Related Findings (Out of Scope)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/deps.py:288-290` (`main_deps()`, the `ll-deps tree --epic` branch) contains an **independent, unfixed reimplementation of the identical bug**: `forward_ids: set[str] = set(epic_info.relates_to)` unioned with `backward_ids` with no EPIC-shape filter. It does not call into `sprint.py` and is untouched by this fix — `ll-deps tree --epic EPIC-2258` would still render sibling EPIC ids as children after this issue ships. No existing test (`scripts/tests/test_deps_cli.py`) covers an EPIC-shaped `relates_to` entry for this branch either. Recommend filing as a separate bug rather than expanding this issue's scope, since Decision Rationale above selected a `sprint.py`-only fix.

### Conventions in Force
- EPIC-typed ids are excluded from implementable/dispatch sets by matching on the candidate's own id shape, not by a separate config flag — evidence: `scripts/little_loops/cli/issues/next_issues.py:52,83,86` (`not i.issue_id.startswith("EPIC-")`, BUG-2638)
- A sibling subsystem treats `relates_to:` as a non-child cross-reference and excludes it entirely from its own child-resolution logic, rather than filtering by type — evidence: `scripts/little_loops/issue_progress.py:120-132`, `compute_epic_progress()` docstring: "`relates_to:` is a cross-reference field (siblings, dependencies) and is intentionally excluded to avoid inflating counts with non-child references"
- EPIC-id shape matching elsewhere in this same module is case-insensitive via a shared regex, not a literal prefix check — evidence: `_EPIC_ID_RE = re.compile(r"^EPIC-\d+$", re.IGNORECASE)` (`sprint.py:14`), used at `sprint.py:319`
- Architectural intent already on record that `relates_to:` should hold only non-membership cross-refs, not children — evidence: `.issues/epics/P3-EPIC-2330-stop-overloading-relates-to-in-epic-writers.md` (status: done)

### Tests
- `scripts/tests/test_sprint.py:2606` (`test_load_or_resolve_epic_id_forward_lookup`) and `:2746` (`test_load_or_resolve_epic_id_union_dedup`) construct `relates_to: [BUG-001]` and assert `BUG-001` is included in `result.issues` — the fix must preserve this: non-EPIC `relates_to` entries stay in the dispatch set
- `scripts/tests/test_sprint.py:2825-3043` — existing `load_or_resolve` EPIC-dispatch coverage (no-active-children, case-insensitive arg, nested-grandchild-transitive, multi-hop, done-intermediate chain, cycle-guard, unprefixed-filename, genuinely-absent) has no case for a sibling-EPIC `relates_to` entry — the AC's regression test is new coverage, not a modification of these
- `scripts/tests/test_next_issues.py`, `scripts/tests/test_next_issue.py` — regression coverage for the BUG-2638 precedent pattern this fix mirrors

### Documentation
- `docs/reference/API.md:6980` — documents `load_or_resolve`'s forward (`relates_to:`) + backward semantics; will need updating once forward excludes EPIC-typed ids
- `docs/reference/CLI.md:563,580` — documents the same forward/backward union semantics for sprint resolution

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
      includes a `relates_to`-sourced `EPIC-*` id in the returned
      `Sprint.issues` (backward-path sub-EPICs via `parent:` chains remain
      included per ENH-2615 — see Expected Behavior scope note)
- [ ] A regression test mirrors BUG-2638's coverage but targets
      `sprint.py`'s forward/`relates_to` path specifically, using an
      uppercase sibling-EPIC entry as the must-fail-before-fix repro
- [ ] `test_load_or_resolve_nested_epic_grandchild_transitive`
      (`test_sprint.py:2884`) still passes unmodified — backward-path
      sub-EPIC inclusion is unchanged
- [ ] `docs/reference/API.md:6980` and `docs/reference/CLI.md:563,580` updated
      to note forward/`relates_to` resolution excludes EPIC-typed ids
- [ ] `python -m pytest scripts/tests/` passes

## Labels

`bug`, `loops`, `captured`

## Status

**Open** | Created: 2026-08-30 | Priority: P2


## Session Log
- `/ll:wire-issue` - 2026-08-30T18:50:09 - `00726072-62d6-4f81-b684-ed899628cec1.jsonl`
- `/ll:decide-issue` - 2026-08-30T18:42:34 - `485b5d3f-a476-487f-b5bc-30b3083dcc2d.jsonl`
- `/ll:refine-issue` - 2026-08-30T18:36:06 - `3caa0a54-1798-44b0-ac84-0105003d8212.jsonl`
- `/ll:format-issue` - 2026-08-30T18:30:07 - `94b795f5-375b-4a55-9190-f07c0af5f00b.jsonl`
