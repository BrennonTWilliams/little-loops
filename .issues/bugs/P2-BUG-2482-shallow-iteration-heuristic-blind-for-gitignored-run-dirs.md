---
id: BUG-2482
title: Shallow-iteration heuristic blind for gitignored run dirs
type: BUG
priority: P2
status: open
captured_at: '2026-07-05T16:11:47Z'
discovered_date: '2026-07-05'
discovered_by: capture-issue
parent: EPIC-2087
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# BUG-2482: Shallow-iteration heuristic blind for gitignored run dirs

## Summary

`ll:audit-loop-run`'s Step 5.5 shallow-iteration heuristic (added by ENH-2082)
derives `AUX_MUTATION_COUNT` solely from `git diff HEAD`. Any loop whose
working/output directory lives under `.loops/runs/` is invisible to that
command, because `.gitignore:80` excludes the entire path. For such loops,
`AUX_MUTATION_COUNT` is always `0` regardless of how much real auxiliary
structure the run builds, so the heuristic produces false-positive
`warning`/`corroborated` shallow-iteration verdicts once `TOOL_CALL_COUNT > 30`
— a threshold that single-run generative loops (e.g. multi-round divergence
loops with several states per round) cross routinely as normal behavior, not
pathological iteration.

## Current Behavior

`skills/audit-loop-run/SKILL.md` Step 5.5 (lines 201-235) computes
`AUX_MUTATION_COUNT` exclusively from the `git diff HEAD` evidence collected in
Step 4 (line 170: `git diff HEAD -- <artifact_path>`). Files created or
modified under a gitignored path never appear in `git diff`, so a loop that
writes extensive auxiliary structure to `.loops/runs/<run_id>/...` is scored
identically to a loop that wrote nothing at all: `AUX_MUTATION_COUNT == 0`.
Combined with the `TOOL_CALL_COUNT > 30` threshold (line 214), this
mislabels healthy, structure-building runs as `shallow-iteration`.

## Expected Behavior

When the primary artifact/run path is itself gitignored (or falls under a
gitignored ancestor directory), Step 5.5 should fall back to a filesystem-based
mutation check — e.g. `find <run_dir> -newer <run_start_marker>` scoped to the
run's working directory — instead of relying on `git diff HEAD`, which is
structurally blind to that path. The heuristic should only report
`AUX_MUTATION_COUNT == 0` when there is actually no auxiliary file activity,
not merely when git can't see it.

## Motivation

This is a diagnostic-accuracy bug in a diagnostic tool: `audit-loop-run` exists
to give trustworthy verdicts about whether a loop is making real progress.
False-positive `shallow-iteration` warnings on legitimate runs erode trust in
the audit output and could cause users to "fix" loops that were never broken,
or to distrust `corroborated` verdicts generally once one is shown to be
wrong. The blind spot is not an edge case — `.loops/runs/` is the default
working-directory root for run artifacts and is gitignored by design
(`.gitignore:80`), so most run-directory-based loops are affected.

## Proposed Solution

In Step 5.5's "Identify auxiliary mutations" step
(`skills/audit-loop-run/SKILL.md:207`), before relying on `git diff HEAD`,
check whether the primary artifact path (or the run's working directory) is
covered by `.gitignore` (`git check-ignore <path>`). If ignored, substitute a
filesystem-based mutation check scoped to that directory, e.g.:

```bash
find <run_dir> -type f -newer <run_start_marker>
```

using the run's start timestamp (already available from the loaded history/
`events.jsonl`) as the `-newer` reference. Count the resulting file list as
`AUX_MUTATION_COUNT` instead of `0`. If neither git nor filesystem evidence is
available (e.g. run directory already cleaned up), report `AUX_MUTATION_COUNT`
as "unknown" and skip the heuristic rather than defaulting to 0.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`find -newer` needs a file, not a raw timestamp**: no existing helper in
  this repo converts an `events.jsonl` timestamp string into a
  `-newer`-compatible reference. Both existing `find ... -newer` precedents
  anchor to an actual file's mtime, not a converted string —
  `scripts/little_loops/loops/lib/task-templates/desktop-gui-task.yaml.tmpl`
  (`find "$RUN_DIR" ... -newer "$RUN_DIR/plan.sh"`) and
  `skills/update-docs/SKILL.md:104`
  (`find .issues/completed ... -newer ".git/refs/heads/$(git branch --show-current)"`).
  Since Step 5.5 has no marker file to point at, use GNU find's
  `-newermt "<iso-ts>"` (accepts a timestamp string directly) instead of
  `-newer <file>`; this is a GNU-find-only flag — BSD find (macOS default)
  requires `touch -d "<ts>" <marker> && find ... -newer <marker>` as the
  portable fallback.
- **Exact run-start timestamp source**: `events[0].ts` — confirmed via
  `scripts/little_loops/fsm/executor.py:336` (`_emit("loop_start", ...)` is
  always the first event emitted) and `:1953` (`_emit` stamps every event with
  `"ts": _iso_now()`). Extract with
  `jq -r '.ts' <(head -1 .loops/.history/<run>/events.jsonl)`.
- **`git check-ignore` has zero existing executable usage** in this codebase
  (only prose mentions in issue files) — this is new plumbing, not a wrapper
  around existing logic. `scripts/little_loops/git_operations.py`'s
  `_is_already_ignored()` reimplements gitignore matching in Python, but it's
  built for `ll-gitignore`'s "suggest new patterns" direction, not "is this
  already-known path currently ignored" — shelling out directly to
  `git check-ignore <path>` from the skill's bash block (matching the existing
  Step 4 style of `git log`/`git diff HEAD` calls) is simpler than reusing it.
- **`context.run_dir`** (the per-run working-directory context key required by
  this project's meta-loop rule MR-3, and referenced in
  `scripts/little_loops/fsm/persistence.py`) should be added to Step 4's
  path-like-context-key scan list (`context.prompt_file`, `context.output_file`,
  ...) as a candidate root to pass into the new `find` fallback.

## Implementation Steps

1. Add a `git check-ignore <primary_path>` (or equivalent) check before the
   `git diff HEAD` mutation count in Step 5.5.
2. When the path is ignored, replace the git-based count with a
   `find <run_dir> -newer <run_start>` filesystem scan, using the run start
   time already present in the loaded history.
3. When neither signal is available, report `AUX_MUTATION_COUNT` as unknown
   and route the heuristic to `clear`/skipped rather than a false `warning`.
4. Document the gitignored-path fallback alongside the existing heuristic
   description in `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`.
5. Add a regression test case covering a run rooted under `.loops/runs/`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The closest existing "primary signal, degrade to filesystem timestamp when
  unavailable" prose pattern in any `SKILL.md` is `skills/review-epic/SKILL.md`
  Step 4 (lines ~132-140): it tries a session-log-derived date first, then
  falls back to `date -r "PATH_TO_FILE" +"%Y-%m-%d"` when no session-log entry
  exists. Use this as the structural model for phrasing Step 5.5's new
  git → gitignore-check → filesystem-fallback branch.
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`'s shallow-iteration row lives in
  the `### Runtime Failure Modes` table at line 157 (table starting ~line
  154) — that's the exact row Implementation Step 4 should extend.

## Integration Map

### Files to Modify
- `skills/audit-loop-run/SKILL.md` — Step 5.5 auxiliary-mutation detection (lines 201-235)

### Dependent Files (Callers/Importers)
- N/A — `audit-loop-run` is a user-facing skill, not imported by automation code

### Similar Patterns
- Step 4's existing `git log` / `git diff HEAD` artifact-mutation check
  (`skills/audit-loop-run/SKILL.md:163-171`) has the same blind spot and may
  warrant the same fallback, though this issue scopes only Step 5.5.
- `scripts/little_loops/loops/lib/task-templates/desktop-gui-task.yaml.tmpl`
  (`screenshot` state) and `skills/update-docs/SKILL.md:104` — the only two
  existing `find ... -newer <marker>` precedents in this codebase; both
  anchor to an existing file's mtime rather than a converted timestamp string
  [from pattern-finder]

### Tests
- `scripts/tests/test_audit_loop_run_skill.py` — add a case for a run rooted
  under a gitignored path (e.g. `.loops/runs/`)
- `scripts/tests/fixtures/fsm/assess-shallow-iteration.yaml` — existing
  fixture to mirror; add a sibling
  `assess-shallow-iteration-gitignored.yaml` for the new case [from
  pattern-finder]
- This file tests skill *markdown prose*, not executed bash — follow the
  existing text-presence-assertion idiom (e.g.
  `test_shallow_iteration_skill_has_step_55`) that slices
  `content.index("## Step 5.5:")` / `content.index("## Step 5.6:")` and
  asserts on the step's text, rather than trying to execute the shell blocks
  [from pattern-finder]

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — note the gitignored-path
  fallback next to the existing shallow-iteration description

## Impact

- **Priority**: P2 — Produces false-positive verdicts from a trusted audit
  tool on the common case (default gitignored run directory), not an edge
  case; low urgency since it's diagnostic-only output, not a functional break.
- **Effort**: Small — Additive fallback check in an existing skill step; no
  new infrastructure.
- **Risk**: Low — Additive change to audit output only; no behavioral change
  to loop execution.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-07-05 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-07-05T16:30:45 - `ed0af048-0f6a-4637-a24d-a7563d4c8d1a.jsonl`
- `/ll:refine-issue` - 2026-07-05T16:21:53 - `8188c82e-404b-4ab6-90de-2e164948c69c.jsonl`
- `/ll:capture-issue` - 2026-07-05T16:11:47Z - `348bbd4d-a0ab-456a-97ff-446449a234a2.jsonl`
