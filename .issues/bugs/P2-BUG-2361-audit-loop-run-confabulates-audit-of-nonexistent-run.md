---
id: BUG-2361
type: BUG
priority: P2
status: done
captured_at: '2026-06-28T00:32:26Z'
completed_at: '2026-06-28T00:32:26Z'
discovered_date: 2026-06-27
discovered_by: manual
labels:
- audit-loop-run
- phantom-output
- verdict-accuracy
confidence_score: 95
---

# BUG-2361: `audit-loop-run` confabulates a full audit of a nonexistent run

## Summary

`/ll:audit-loop-run` produced a complete, confident audit report
(`sprint-build-and-validate-audit-2026-06-27.md`) — verdict, 9-step state
transition trace, captured outputs, timing breakdown, and ranked improvement
proposals — for a run that **never happened**. Every concrete artifact the
report cited was missing or contradicted by reality. The skill read empty/error
output from a nonexistent run path and fabricated a run rather than refusing to
audit.

This is the same phantom-output integrity failure class as [[BUG-2351]]
(`phantom` mislabel) and [[BUG-2352]] (laundering false positives) — all three
are precision/honesty defects in the `audit-loop-run` skill.

## Current Behavior

`skills/audit-loop-run/SKILL.md` only guarded run existence on the
*auto-resolve* path (Step 1: "If empty: report 'No archived runs found' and
stop"). When a run folder/ID was supplied directly, **Step 2 loaded
`events.jsonl`/`state.json` with no existence-or-nonempty gate**
(`skills/audit-loop-run/SKILL.md:96`, `wc -l … events.jsonl`). With nothing to
read, the model confabulated an entire run.

### Evidence (from the audited report vs. repository reality)

| Report claim | Reality |
|---|---|
| Run folder `.loops/.history/2026-06-27T235105-sprint-build-and-validate/` | Does not exist; no `sprint-build-and-validate` run exists anywhere in `.loops/`. The `235105` string only appears coincidentally in an unrelated `rn-implement` run from 2026-06-07. |
| `.sprints/p0-audit-fixes.yaml` committed in `12ba010` | Commit `12ba010` does not exist; the sprint file was never in git history. |
| `.sprints/p0-bug-fixes.yaml` (claimed root cause) | Never existed in history. |
| Trace: `route_input` exits 1 → `create_sprint` | Contradicts the committed FSM (commit `4dea1ad1`, which predates the claimed run): a named-but-missing sprint does `exit 2`, and the `exit_code` evaluator maps `2+ → error → failed` (`scripts/little_loops/fsm/evaluators.py:148-153`). A real run would fast-fail at `route_input`, never reaching `create_sprint`. |

Because the loop already fast-fails on a missing named sprint, the report's top
proposals (pre-flight validation, fail-loudly) were already implemented; acting
on its YAML diffs would have been redundant or wrong.

## Steps to Reproduce

1. Invoke `/ll:audit-loop-run <run-id>` with a run ID/folder that does not exist
   (or whose `events.jsonl` is empty) — e.g. a `sprint-build-and-validate` run
   that was never executed.
2. The skill reaches `## Step 2: Load Loop Definition and History` and loads
   `events.jsonl`/`state.json` from the nonexistent path with no
   existence-or-nonempty gate (`skills/audit-loop-run/SKILL.md:96`).
3. Observe: instead of refusing on empty/error output, the skill emits a
   complete, confident audit — verdict, state-transition trace, captured
   outputs, timing breakdown, and ranked improvement proposals — entirely
   fabricated for a run that never happened.

## Expected Behavior

Before any analysis, `audit-loop-run` must assert the run artifacts exist and
are non-empty (`events.jsonl` non-empty AND `state.json` present). If not, it
emits a single refusal line and stops — no verdict, trace, captured outputs, or
proposals. Every concrete claim in a report must be backed by a line actually
read from `events.jsonl`/`state.json`; empty/error tool output is absence of
evidence, not license to confabulate.

## Root Cause

- **File**: `skills/audit-loop-run/SKILL.md`
- **Anchor**: `## Step 2: Load Loop Definition and History`
- **Cause**: The existence guard lived only in Step 1's auto-resolve branch.
  Any path that supplied a run ID/folder directly reached Step 2's history load
  with no gate, so a missing/empty run produced a fabricated audit instead of a
  refusal.

## Impact

- **Priority**: P2 — A confabulated audit silently drives wrong/redundant
  remediation work (the bogus report's top proposals were already implemented),
  but it requires a missing/empty run path rather than the common case; this is
  an integrity/honesty defect, not a crash.
- **Effort**: Small — a single hard pre-flight gate added at the top of `## Step
  2` in one SKILL.md; no Python/code changes.
- **Risk**: Low — the gate only adds an early refusal on absent/empty artifacts;
  it cannot produce false audits, only refuse sooner. Skill stays within the
  500-line budget.
- **Breaking Change**: No.

## Fix (applied this session)

Added a **hard pre-flight gate** at the top of `## Step 2` covering every path
into the audit (auto-resolved, directly-supplied run ID, running-loop
selection):

- Checks `<run_dir>/events.jsonl` is non-empty AND `state.json` exists.
- On miss: report `Run '…' not found or empty — refusing to audit.` and stop,
  with no verdict/trace/proposals emitted.
- Added an explicit anti-confabulation instruction: every concrete claim must
  trace to a line read from the run artifacts; empty/error output is absence of
  evidence.

Skill remains within the 500-line budget (402 lines; `ll-verify-skills`
passes).

## Verification

- `ll-verify-skills` → exit 0 ("All SKILL.md files within 500-line limit").
- Manual trace: confirmed the cited run folder, commit, and sprint files do not
  exist in `.loops/`, git history, or `.sprints/`.

## Notes

The `sprint-build-and-validate` loop itself required no changes — it already
fast-fails on a missing named sprint via `route_input` `exit 2 → on_error →
failed`. The bogus audit document `sprint-build-and-validate-audit-2026-06-27.md`
remains untracked in the working tree pending the user's decision to delete it.

Relates to [[BUG-2351]], [[BUG-2352]].


## Session Log
- `/ll:format-issue` - 2026-06-28T00:36:32 - `b6c2cd65-a097-40ed-a32d-98d2221600fd.jsonl`
- `hook:posttooluse-status-done` - 2026-06-28T00:32:57 - `fa16026d-9fe1-4642-94f7-2714dd98d646.jsonl`
