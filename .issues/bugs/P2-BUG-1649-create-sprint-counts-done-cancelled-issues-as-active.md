---
captured_at: '2026-05-23T23:10:18Z'
completed_at: '2026-05-24T08:48:24Z'
discovered_date: 2026-05-23
discovered_by: capture-issue
status: done
depends_on: BUG-1648
labels:
- skills
- sprint
- create-sprint
- migration-aftermath
confidence_score: 95
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1649: `/ll:create-sprint` counts `done`/`cancelled` issues as active, polluting suggested sprints

## Summary

`/ll:create-sprint` Step 1.5.1 ("Scan Active Issues") defines "active" purely by directory location (raw Glob over `.issues/{bugs,features,enhancements}/*.md`) and never reads the `status:` frontmatter field. After the ENH-1390 migration consolidated completed/deferred issues into the same type-based directories as open ones, every glob over a type dir returns *every* issue regardless of status, so the skill counts `done` and `cancelled` issues as active. Observed in a downstream project: the skill reported `Total active issues: 54` and proposed a `critical-fixes` sprint of 13 P1 issues when the project actually had **13 open issues** total — `ll-issues list --json` would have returned the correct set. Every suggested sprint in that output was wrong, and `ll-sprint run` against it would have re-executed completed work.

## Steps to Reproduce

1. Use any repo that has lived through the ENH-1390 layout migration (this repo qualifies — `.issues/bugs/`, `.issues/features/`, and `.issues/enhancements/` each contain a mix of `status: open` and `status: done`/`cancelled` files).
2. Run `/ll:create-sprint` with no arguments.
3. Observe the banner: `Based on N active issues, here are suggested sprint groupings`.
4. Compare `N` to `ll-issues list --json | python -c 'import json,sys; print(len(json.load(sys.stdin)))'`. They diverge — the skill's `N` is the larger raw-glob count, not the status-filtered active set.
5. Inspect the suggested `critical-fixes` / `refined-ready` groupings. They include issues whose files have `status: done` or `status: cancelled` in frontmatter.

## Current Behavior

`commands/create-sprint.md:130-151` (Step 1.5.1) instructs Claude to:

```
Use Glob to find all active issues:
- Pattern: {issues.base_dir}/bugs/*.md
- Pattern: {issues.base_dir}/features/*.md
- Pattern: {issues.base_dir}/enhancements/*.md
```

No `status:` frontmatter read happens anywhere in the step. Result, observed in a downstream project's run captured at `create-sprint-loop-viz-debug.txt`:
- `803 issues found` (initial pattern search — recursive `find` over `.issues/`)
- `Total active issues: 54` (Step 1.5.1's non-recursive glob, no status filter)
- `13` = what `ll-issues list --json` would have returned
- A `critical-fixes` sprint surfaced low-numbered, unscored P1s (`FEAT-134`, `FEAT-162`, `FEAT-166`) that are almost certainly closed — exactly the failure mode the diagnosis predicts.

## Expected Behavior

Step 1.5.1 produces the same set as `ll-issues list --json` — issues whose frontmatter `status:` is in `{open, in_progress, blocked}`. Suggested sprints contain only those issues. The banner count matches `ll-issues list --json | python -c 'import json,sys; print(len(json.load(sys.stdin)))'`.

## Root Cause

Step 1.5.1 was correct under the pre-ENH-1390 layout where completed/deferred issues lived in separate sibling directories (`.issues/completed/`, `.issues/deferred/`) — there, a glob over `.issues/bugs/*.md` *was* effectively "active bugs". The ENH-1390 migration (still shipped today as `ll-migrate`, per `CLAUDE.md`) consolidated all statuses into the type-based directories with canonical status tracked in frontmatter (`open` | `in_progress` | `blocked` | `deferred` | `done` | `cancelled`). The skill prompt was not updated to follow the migration.

The corresponding CLI command already does this correctly: `ll-issues list` calls `_load_issues_with_status(...)` in `scripts/little_loops/cli/issues/list_cmd.py:38` and defaults to the active set (`open`, `in_progress`, `blocked`). Step 1.5.1 simply never delegates to it.

Step 3 Option B (line 341) already hints at the right approach (`"Use ll-issues list --json to get all active issues (frontmatter status: open/in_progress/blocked)"`) but the auto-grouping path in Step 1.5.1 doesn't share that source of truth.

## Motivation

`/ll:create-sprint` is the canonical entry point for sprint planning. When its candidate set is polluted with finished/cancelled work, every suggested sprint is wrong, and a user who runs `ll-sprint run` against one would re-execute completed issues — wasting tokens, producing churn commits, and potentially regressing fixed bugs. The skill's banner currently overstates the live backlog by 4× in the observed project (54 vs 13), which also misleads any human reading the output as a workload signal.

## Proposed Solution

Replace the raw-glob discovery in Step 1.5.1 with a call to `ll-issues list --json`, which is already the project's source of truth for "active issues". Keep a graceful fallback that still respects status when the CLI isn't available.

## Implementation Steps

1. **Replace Step 1.5.1's Glob instruction** in `commands/create-sprint.md:130-151`:

   ```
   Run `ll-issues list --json` to get the canonical set of active issues
   (frontmatter status in {open, in_progress, blocked}). For each entry
   extract priority, type, id, title, summary, file paths, goal_alignment,
   blocked_by, confidence_score, outcome_confidence, and is_normalized
   exactly as before. If `ll-issues` is not installed, fall back to the
   existing Glob patterns BUT additionally read each file's frontmatter
   and skip any entry whose `status` is not in
   {open, in_progress, blocked}.
   ```

   Map each `ll-issues list --json` field to the existing extraction names (priority/type/id/title/summary/file paths/goal_alignment/blocked_by/confidence_score/outcome_confidence/is_normalized) so downstream steps (1.5.2 grouping, 1.5.3 presentation) are unchanged.

2. **Tighten Step 3 Option B wording** (`commands/create-sprint.md:341`): keep `ll-issues list --json` as the preferred path and remove the "Or use Glob on type dirs" fallback now that Step 1.5.1 shares the same source of truth.

3. **No permissions change needed** — the `allowed-tools` frontmatter already permits `Bash(ll-issues:*)` (line 6).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Write `scripts/tests/test_bug1649_doc_wiring.py` — doc-wiring test asserting (a) `ll-issues list --json` is present in `commands/create-sprint.md` Step 1.5.1 region and (b) the old raw Glob paths (`bugs/*.md`, `features/*.md`, `enhancements/*.md`) are absent from the active-scan path. Follow the pattern in `scripts/tests/test_enh1130_doc_wiring.py`.

## API/Interface

No code-level API changes. Skill-level contract: the auto-grouping path now produces the same set as `ll-issues list --json`, matching what `Step 3 Option B` and `ll-sprint create` already use.

## Out of Scope

- Don't change `ll-issues list` itself — already correct.
- Don't change the migration (`ll-migrate`) — the consolidated layout is the desired end state.
- Don't touch sprint *execution* (`ll-sprint run`); the bug is purely in candidate selection.

## Verification

1. **Repro the symptom against this repo's `.issues/`** (mixed active and done):
   ```bash
   ll-issues list --json | python -c 'import json,sys; print(len(json.load(sys.stdin)))'
   ls .issues/bugs/*.md .issues/features/*.md .issues/enhancements/*.md 2>/dev/null | wc -l
   ```
   Before the fix the two diverge (active < glob count). After the fix the skill's "Total active issues" banner equals the first number.

2. **Run `/ll:create-sprint` with no arguments** in this repo. Inspect the suggested groupings:
   - No suggested sprint contains an issue whose file has `status: done` or `status: cancelled` in frontmatter.
   - The `Based on N active issues, here are suggested sprint groupings` banner matches the count from `ll-issues list --json`.

3. **Smoke check on the original downstream project** (the one that produced `create-sprint-loop-viz-debug.txt`): re-run `/ll:create-sprint` and confirm "Total active issues" prints `13` (or whatever `ll-issues list --json` says), not `54`. Confirm `critical-fixes` no longer surfaces `FEAT-134` / `FEAT-162` / `FEAT-166` if those are closed.

4. **Regression check**: `python -m pytest scripts/tests/ -k create_sprint -v` still passes. There are no unit tests for the skill *prompt*, but underlying `ll-issues list` behaviour is covered.

## Integration Map

### Files to Modify
- `commands/create-sprint.md` — Step 1.5.1 (lines 130–151) and Step 3 Option B wording (line 341).

### Existing Utilities to Reuse (do not reinvent)
- `scripts/little_loops/cli/issues/list_cmd.py:38` — canonical active filter (`status in {open, in_progress, blocked}` by default; `--status all` to include everything).
- `scripts/little_loops/cli/issues/search.py:106` — `_load_issues_with_status(config, include_open, include_done, include_deferred)` definition; the status gate is at line 135: `if status in ("open", "in_progress", "blocked")`. Replicate this exact set for the fallback Glob path in Implementation Step 1.
- `little_loops.issue_parser.IssueParser` — already used elsewhere in the same command file (Step 4.5, line 383) when the JSON CLI isn't enough.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — invokes `/ll:create-sprint --auto` in the `create_sprint` state (no `--issues` arg, hits Step 1.5); will benefit automatically from the fix — no change needed [Agent 1 finding]
- `commands/review-sprint.md` — Phase 2 Backlog Scan uses the identical raw-Glob pattern (`{issues.base_dir}/bugs/*.md` etc.) with the same ENH-1390 blindspot; out of scope for BUG-1649 but a structural sibling that warrants a follow-up issue [Agent 2 finding]
- `skills/ll-create-sprint/SKILL.md` — Codex bridge stub that defers entirely to `commands/create-sprint.md`; no change needed [Agent 1 finding]

### Tests
- `scripts/tests/test_issues_cli.py` — `ll-issues list` subcommand tests with active-issue filtering; key regression suite for the underlying behaviour this fix delegates to.
- `scripts/tests/test_issues_search.py` — `_load_issues_with_status` tests; fixture at line 64 creates a `done` issue and asserts it is excluded from the active set.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_sprint.py` — primary SprintManager test suite; `TestSprintEdit.test_edit_prune_removes_completed` (line 1690) and `TestSprintEdit.test_edit_prune_nothing_to_prune` (line 1771) cover `status: done` frontmatter recognition in sprint edit/prune operations; regression check that the underlying contract holds after the fix [Agent 1 + 3 finding]
- `scripts/tests/test_sprint_integration.py` — integration tests for sprint lifecycle; `TestDependencyHandling.test_sprint_completed_dependencies_satisfied` (line 1267) tests `status: done` recognition in the dependency graph [Agent 1 + 3 finding]
- `scripts/tests/test_bug1649_doc_wiring.py` — **new file to write** — doc-wiring test asserting `ll-issues list --json` is present in Step 1.5.1 and raw type-dir Glob patterns are absent; follow the pattern in `scripts/tests/test_enh1130_doc_wiring.py` (assert on `Path("commands/create-sprint.md").read_text()`) [Agent 3 finding]

### Permissions Note
`allowed-tools` in `commands/create-sprint.md` lists `Bash(ll-issues:*)` and `Bash(mkdir:*)` but does **not** explicitly list `Glob`. Step 1.5.1's current Glob usage is implicitly permitted by the system. After the fix, the replacement `ll-issues list --json` call is already covered by the existing `Bash(ll-issues:*)` entry — no frontmatter change needed.

## Impact

- **Priority**: P2 — produces incorrect sprint suggestions on every invocation in post-ENH-1390 repos; users who run `ll-sprint run` against the bad output re-execute completed work (wasted tokens, churn commits, potential regressions). Not P1 because the user can spot-check suggested sprints before executing, and the correct CLI (`ll-issues list --json`) is one step away.
- **Effort**: Small — prompt-only edit to a single skill file (`commands/create-sprint.md`); no code changes; the canonical CLI (`ll-issues list --json`) already exists and is used elsewhere in the same file.
- **Risk**: Low — replaces a raw Glob with a CLI call that has unit-test coverage (`_load_issues_with_status`); falls back to a status-filtered Glob if the CLI is unavailable; no schema or behaviour change to `ll-issues` itself.
- **Breaking Change**: No

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `.claude/CLAUDE.md` § Issue File Format | Canonical status enum (`open`, `in_progress`, `blocked`, `deferred`, `done`, `cancelled`) the fix must respect |
| `commands/create-sprint.md` | The file being changed; Step 1.5.1 is the broken path, Step 3 Option B is the correct pattern to align with |

## Resolution

- Replaced Step 1.5.1's raw Glob patterns in `commands/create-sprint.md` with a `ll-issues list --json` call — the canonical active-issue source that filters by frontmatter status.
- Retained a status-filtered Glob fallback (for environments without `ll-issues`) with an explicit note to skip non-active statuses.
- Tightened Step 3 Option B to remove the raw-Glob alternative path.
- Added `scripts/tests/test_bug1649_doc_wiring.py` asserting `ll-issues list --json` is present in the Step 1.5.1 region and raw type-dir Glob patterns are absent as the primary path.

## Session Log
- `/ll:ready-issue` - 2026-05-24T08:46:59 - `d5233105-9101-4433-89af-4dc5fefd739a.jsonl`
- `/ll:confidence-check` - 2026-05-24T00:00:00Z - `fcaf8e82-e9b0-459c-b420-b2d6516dcebf.jsonl`
- `/ll:wire-issue` - 2026-05-24T07:37:46 - `76307c23-ef5c-42f1-98e8-10d70af3ea53.jsonl`
- `/ll:refine-issue` - 2026-05-24T07:28:35 - `ad2cb799-0357-40ae-ae3b-03344aed447c.jsonl`
- `/ll:format-issue` - 2026-05-23T23:14:46 - `748c0c41-2378-4021-99b4-82ad38e41ef1.jsonl`
- `/ll:capture-issue` - 2026-05-23T23:10:18Z - source: `~/.claude/plans/we-ran-ll-create-sprint-in-purring-hanrahan.md`
