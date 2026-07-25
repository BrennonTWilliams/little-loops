---
id: BUG-2799
type: BUG
priority: P1
status: done
captured_at: '2026-07-25T00:00:00Z'
completed_at: '2026-07-25T15:50:15Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 88
score_complexity: 25
score_test_coverage: 15
score_ambiguity: 25
score_change_surface: 23
---

# BUG-2799: review-epic has broken CLI invocations and a status-corrupting --cascade recommendation

## Summary

`skills/review-epic/SKILL.md` contains 6 broken or dangerous invocations of
`ll-issues`. The most severe are four places that recommend
`ll-issues set-status EPIC_ID {done|cancelled} --cascade`, which cascades
children to `deferred` (the default `--cascade-to`) as a side effect of
**terminally closing the EPIC**. A user following this recommendation to
"bulk defer stalled children" would instead permanently close the EPIC while
only deferring (not resolving) the children. The other two findings are
non-existent flags (`--format json` missing on `epic-progress`, implied
`--status all` shorthand not used consistently) that would cause the skill's
own JSON-parsing steps to fail or behave unexpectedly.

## Current Behavior

- **Line 105**: `ll-issues epic-progress EPIC_ID` is invoked with no
  `--format` flag (default is `text`), but the very next line says "Parse
  the JSON output" — the command as written never emits JSON.
- **Lines 48/65**: `ll-issues list` is invoked with the fully spelled-out
  `--status open,in_progress,blocked,done,cancelled,deferred` enumeration
  instead of the equivalent `--status all` value the CLI actually supports
  (confirmed via `ll-issues list --help`), which is more fragile — any future
  status value added to the enum silently falls out of this list.
- **Line 224**: "Recommendation: ... For bulk deferral of all stalled
  children, prefer `ll-issues set-status EPIC_ID done --cascade` to close
  everything at once."
- **Line 246**: "Use `--cascade` to close any remaining open children in the
  same call." (paired with `ll-issues set-status EPIC_ID done`)
- **Line 268**: "Bulk option: `ll-issues set-status EPIC_ID cancelled
  --cascade`"
- **Line 277**: `ll-issues set-status EPIC_ID done --cascade` in the
  Recommendations checklist

Per `ll-issues set-status --help`, `--cascade` propagates a status to active
children with a **default `--cascade-to deferred`**, while the *parent*
`issue_id` (the EPIC itself) transitions to whatever terminal status was
given (`done` or `cancelled`). So every one of these four recommendations
permanently closes the EPIC while only deferring — not resolving — its
children. A user intending to "park" stalled children ends up terminally
closing the EPIC as an unintended side effect.

## Expected Behavior

- Line 105: `ll-issues epic-progress EPIC_ID --format json` (or update the
  prose to say "text output" if JSON isn't actually needed).
- Lines 48/65: use `ll-issues list --status all ...` for consistency and to
  avoid drift if the status enum changes.
- Lines 224, 246, 268, 277: replace the `--cascade` "close EPIC + bulk
  defer/close children" recommendation with one of:
  - A per-child loop: `ll-issues set-status <CHILD_ID> deferred` for each
    stalled child, leaving the EPIC's own status untouched, **or**
  - If the intent is genuinely to also park the EPIC (not just its
    children): `ll-issues set-status EPIC_ID deferred` (no `--cascade`).
  - Never recommend `done`/`cancelled` + `--cascade` as a "bulk
    deferral/park" action — `--cascade` to a terminal status should only be
    recommended when the user actually wants BOTH the EPIC and its children
    terminally resolved (and even then, `--cascade-to done` or
    `--cascade-to cancelled` should be made explicit rather than relying on
    the `deferred` default).

## Root Cause

`skills/review-epic/SKILL.md` — the Recommendations/Closure section
(Step 8, around lines 220–285) was written assuming `--cascade` closes
children to match the parent's new status. In reality `--cascade-to`
defaults to `deferred` regardless of what status the parent transitions to,
so `done --cascade` and `cancelled --cascade` both leave children merely
deferred while the EPIC itself is terminally closed. Line 105's JSON claim
and lines 48/65's status enumeration are separate, lower-severity
documentation-drift bugs in the same file.

## Proposed Solution

1. Fix line 105: append `--format json` to the `epic-progress` invocation.
2. Fix lines 48/65: replace the six-value status enumeration with
   `--status all`.
3. Fix lines 224, 246, 268, 277: remove the `--cascade` bulk-close
   recommendation entirely and replace with the per-child
   `ll-issues set-status <CHILD_ID> deferred` loop / `set-status EPIC_ID
   deferred` alternative described in Expected Behavior. Since `review-epic`
   is explicitly read-only (Step 9 Guard Rails: "Never write to any issue
   file... all mutations are user-initiated follow-up commands"), this is a
   text-only change to the Recommendations section — no runtime behavior in
   the skill itself changes, only the commands it prints for the user to
   run.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **File to modify**: `skills/review-epic/SKILL.md` (321 lines total) — all 6
  findings confirmed still present at the cited line numbers on current
  `main`.
- **CLI behavior verified** (`scripts/little_loops/cli/issues/__init__.py:752-765`,
  `scripts/little_loops/cli/issues/set_status.py:97-206`): `--cascade` is a
  `store_true` flag; `--cascade-to` has `default="deferred"` and is
  independent of the terminal `status` argument — confirms the issue's Root
  Cause claim exactly. Cascade traversal is `parent:`-edge BFS over active
  descendants only.
- **`--format json` confirmed real and working**
  (`scripts/little_loops/cli/issues/epic_progress.py:27-33,60-64`) — the
  fix at line 105 is a docs-completeness change to the skill file, not a
  missing CLI capability.
- **`--status all` confirmed real and working**
  (`scripts/little_loops/cli/issues/__init__.py:183-189`,
  `list_cmd.py:41-43`) — equivalent to enumerating every status value.
- **Test coverage**: `scripts/tests/test_review_epic_skill.py` covers child
  resolution logic and report structure but does not currently assert on
  the exact CLI invocation strings printed by the skill (i.e., would not
  catch a regression of these 6 findings). No test changes are required by
  this bug's fix (the fix is skill-markdown-only per the read-only
  Guard Rails), but a future structural lint asserting skill-printed
  commands match `--help` output could prevent recurrence.
- **Same `--cascade` bulk-close pattern found elsewhere**:
  `skills/manage-issue/SKILL.md:439-443` also recommends
  `set-status ... --cascade` for EPIC closure — but in a context that
  explicitly documents cascade-to-children semantics correctly, unlike
  `review-epic`. Out of scope for this bug (which is limited to
  `review-epic/SKILL.md`), but worth a follow-up sweep if similar drift is
  suspected elsewhere.

## Impact

Read-only audit skill (`ll:review-epic`) currently prints commands that, if
copy-pasted and run by a user, silently and irreversibly close an EPIC while
only deferring (not resolving) its children — a status-integrity hazard
flagged as most likely to cause irreversible damage. The two flag bugs
(lines 48/65, 105) cause the skill's own internal steps to either fail
JSON parsing or use a more fragile status enumeration.

## Resolution

Fixed all 6 findings in `skills/review-epic/SKILL.md`:
- Line 48/65: replaced the six-value status enumeration with `--status all`.
- Line 105: appended `--format json` to the `epic-progress` invocation.
- Lines 224, 246, 268, 277: removed the `--cascade` bulk-close recommendations
  and replaced with per-child `set-status CHILD_ID deferred` loop guidance,
  with explicit warnings against using `--cascade` for bulk deferral (it
  terminally closes the EPIC while only deferring children).

Doc-only change (`review-epic` is read-only per its own Guard Rails); no
runtime behavior changed, only the commands the skill prints for users to run.

## Session Log
- `/ll:confidence-check` - 2026-07-25T00:00:00Z - `922d5bf6-c165-4eb3-a25e-81b99ee38299.jsonl`
- `/ll:wire-issue` - 2026-07-25T15:42:48 - `a1801104-7c9b-47a7-8eb8-3d812566ae74.jsonl`
- `/ll:refine-issue` - 2026-07-25T15:38:55 - `f677cd6a-439e-423c-a8b9-eee718e93c28.jsonl`
- `/ll:capture-issue` - 2026-07-25 - session JSONL not resolved (non-interactive capture)
- `/ll:manage-issue` - 2026-07-25T15:49:41Z - `3e6a21bb-7799-40f3-a91f-684a6e142c01.jsonl`
