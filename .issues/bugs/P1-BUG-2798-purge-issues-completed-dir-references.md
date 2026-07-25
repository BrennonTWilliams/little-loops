---
id: BUG-2798
title: Purge stale .issues/completed/ directory references across skills and docs
status: done
priority: P1
captured_at: '2026-07-25T15:03:20Z'
completed_at: '2026-07-25T15:36:02Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
testable: false
confidence_score: 100
outcome_confidence: 89
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 25
score_change_surface: 22
---

# BUG-2798: Purge stale .issues/completed/ directory references across skills and docs

## Summary

Multiple skills and one README still reference a `.issues/completed/` directory
that no longer exists — status now lives in frontmatter (`status: done`), not
directory location (see `.claude/CLAUDE.md` § Issue File Format). Several of
these also use `ll-issues show ... --format path`, which is not a valid flag.
The fix is to replace directory-scanning/prose against `.issues/completed/`
with `ll-issues list --status done --json` (verified to exist and work), which
also fixes the invalid `--format path` usage in `skills/capture-issue/SKILL.md:202`.

## Current Behavior

Several skills and one README still tell an agent (or run code that assumes)
`.issues/completed/` exists as a scannable directory, and three call sites use
`ll-issues list --format path`, a flag that does not exist on `list` (see
Affected Locations below for exact files/lines).

## Expected Behavior

All listed files use frontmatter-based status checks (`ll-issues list
--status done --json`, or the DB-preferred `scan_completed_issues_from_db`/
`scan_completed_issues` pattern for `update-docs`) instead of scanning or
referencing a `.issues/completed/` directory, and no call site passes the
invalid `--format path` flag.

## Root Cause

Legacy status-via-directory-location model was replaced by frontmatter-based
status, but prose/code in several skills and one doc were never updated to
match.

## Steps to Reproduce

1. Grep the repo for `.issues/completed/` under `skills/` and
   `hooks/adapters/codex/README.md`, or for `ll-issues list --format path` —
   both patterns are still present (see Affected Locations).
2. Run any of the three occurrences of `ll-issues list --format path` — `list`
   has no `--format` flag (confirmed at
   `scripts/little_loops/cli/issues/__init__.py:172-195`), so the command
   errors or silently ignores the flag depending on the caller.

## Impact

Agents following these skills' instructions attempt to scan a directory that
no longer exists (silently finding nothing, masking genuinely completed/
reopen-candidate issues in `audit-docs` and `update-docs`) or invoke an
invalid CLI flag (`capture-issue`, `align-issues`, `analyze_log`), which either
errors or silently returns no results instead of the intended filtered list.

## Status

Done — all affected locations updated, links verified, tests passing.

## Affected Locations

- `skills/audit-docs/SKILL.md:289` — `grep -r "README.md" .issues/completed/`
- `skills/audit-docs/SKILL.md:320` — `git mv .issues/completed/P2-BUG-XXX-broken-link.md .issues/bugs/`
- `skills/update-docs/SKILL.md:81,98,104` — scans `.issues/completed/` directly
  and calls `scan_completed_issues(Path('.issues/completed'))`. Should switch
  to the pattern at `scripts/little_loops/decisions.py:564` — prefer
  `scan_completed_issues_from_db(db_path)` when `.ll/history.db` exists, else
  fall back to `scan_completed_issues(project_root / config.issues.base_dir)`.
- `skills/confidence-check/rubric.md:20` — `- \`--all\` — Evaluate all active
  issues (bugs/, features/, enhancements/), skip completed/ and deferred/.
  Implies \`--auto\`.` (line corrected from original 113).
- `skills/wire-issue/SKILL.md:265` — `- The file is in \`completed/\` (already done)`.
- `skills/adversarial-verify-loop/SKILL.md:66`, `skills/verify-issue-loop/SKILL.md:65`,
  `skills/create-eval-from-issues/SKILL.md:184` — "the `ll-issues show` command
  searches all categories including `completed/` and `deferred/`" — these are
  the three loop-generator skills; rewrite the prose to reflect frontmatter-based
  status (no `completed/` subdirectory exists). Their frontmatter `description:`
  lines (line 11 each) are accurate as-is and don't need changing.
- `skills/capture-issue/SKILL.md:202` and `commands/align-issues.md:183` —
  both use `ll-issues list --status done --format path`; `list` has no
  `--format` flag at all (confirmed against `scripts/little_loops/cli/issues/__init__.py:172-195`),
  fix both to `ll-issues list --status done --json`.
- `hooks/adapters/codex/README.md:41,207` — two broken links pointing to
  `../../../.issues/completed/` (FEAT-1116 references).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/commands/analyze_log.md:174` — `ll-issues list --format path | xargs grep -l "<keywords>"`,
  the same invalid `--format path` usage as `skills/capture-issue/SKILL.md:202`
  and `commands/align-issues.md:183`; missed by the original scope. This file
  is git-tracked (confirmed via `git ls-files`), not a local-only override —
  fix it alongside the other two `--format path` occurrences.

## Explicitly Out of Scope

- `commands/normalize-issues.md` — its `.issues/completed/` mention is a
  deliberate legacy-format detector and needs no change.

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`scan_completed_issues`/`scan_completed_issues_from_db` actual location**: these
  live in `scripts/little_loops/issue_history/parsing.py:289` and `:351`
  respectively (not `decisions.py:564` as originally stated — `decisions.py`
  only imports/calls them). `scan_completed_issues`'s docstring (lines 293-311)
  confirms status is now detected via in-place `status: done` frontmatter
  (bugs/, features/, enhancements/, epics/, per ENH-1418), but the function
  still unconditionally also scans a legacy `.issues/completed/` sibling dir
  if present (lines 334-338, `legacy_completed = issues_dir / "completed"`) for
  backward compat — so the dir isn't invalid to reference in *that one file's
  fallback logic*, only in current-instruction prose telling authors/agents to
  create or scan it as the primary path.
- **`ll-issues list` flags confirmed** (`scripts/little_loops/cli/issues/__init__.py:172-195`):
  `--status`/`-S` accepts `done` (line 184-189), `--json`/`-j` is a real
  boolean flag (line 195). **No `--format` flag exists on `list`** — that flag
  only exists on the sibling `search` subcommand (line 267, `choices=["table","list","ids"]`).
  `ll-issues list --status done --json` is valid and correct as proposed.
- **Additional `--format path` occurrence not in the original scope**:
  `commands/align-issues.md:183` — `mapfile -t ISSUE_FILES < <(ll-issues list --format path | sort)`.
  Same invalid-flag bug as `skills/capture-issue/SKILL.md:202`; add to scope.
- **`skills/confidence-check/rubric.md` line number correction**: the relevant
  reference is at **line 20**, not 113 — `- \`--all\` — Evaluate all active
  issues (bugs/, features/, enhancements/), skip completed/ and deferred/.
  Implies \`--auto\`.`
- **Loop-generator skills confirmed** (exact text, all three use identical
  phrasing): `skills/adversarial-verify-loop/SKILL.md:66`,
  `skills/verify-issue-loop/SKILL.md:65`, `skills/create-eval-from-issues/SKILL.md:184`
  — `**Both open and completed issues are accepted.** The \`ll-issues show\`
  command searches all categories including \`completed/\` and \`deferred/\`.`
  Each of these three files also has a frontmatter `description:` line (line 11
  in all three) saying "Accepts open or completed issues" — this phrasing is
  accurate as-is (issues can still be *logically* completed, i.e. `status: done`)
  and does not need to change; only the `completed/`-as-a-directory claim on
  the body line does.
- **`skills/wire-issue/SKILL.md` exact line**: line 265 —
  `- The file is in \`completed/\` (already done)`.
- **`skills/audit-loop-run/SKILL.md` has zero relevant references** — confirmed
  no `.issues/completed` or directory-based "completed" text exists in this
  file (its one "completed" hit, line 314, refers to loop-run completion
  status, unrelated). Drop it from the working set in Step 2 — no change needed.
- **Broken-link fix for `hooks/adapters/codex/README.md:41,207`**: FEAT-1116's
  current path is `.issues/features/P3-FEAT-1116-hook-intent-abstraction-layer.md`.
  Valid replacement relative link (from `hooks/adapters/codex/README.md`):
  `../../../.issues/features/P3-FEAT-1116-hook-intent-abstraction-layer.md`.
- **Out-of-scope confirmation**: broader `docs/` references (`ARCHITECTURE.md:1056`,
  `docs/demo/scenarios.md:212`, `RECURSIVE_LOOPS_GUIDE.md:324`,
  `EXAMPLES_MINING_GUIDE.md:415`, `EVENT-SCHEMA.md:844,868`, `LOOPS_REFERENCE.md`
  multiple, `CLI.md:1360`) and loop YAMLs (`backlog-flow-optimizer.yaml`,
  `issue-staleness-review.yaml`, `auto-refine-and-implement.yaml`,
  `examples-miner.yaml`, `scan-and-implement.yaml`) also mention
  `.issues/completed/`, largely as historical/legacy-format documentation or
  `find -not -path` exclusions guarding against the legacy dir's *possible*
  existence — these read as intentional and are out of scope per the issue's
  stated boundary (skills/ + one README), consistent with the existing
  "Explicitly Out of Scope" entry for `commands/normalize-issues.md`.

## Implementation Steps

1. In `skills/update-docs/SKILL.md`, replace the `.issues/completed/` scan
   with the pattern used by callers of `scan_completed_issues`/
   `scan_completed_issues_from_db` (defined at
   `scripts/little_loops/issue_history/parsing.py:289` and `:351`): prefer
   `scan_completed_issues_from_db(db_path)` when `.ll/history.db` exists, else
   fall back to `scan_completed_issues(project_root / config.issues.base_dir)`.
2. In `skills/audit-docs/SKILL.md` (lines 289, 320), `skills/confidence-check/rubric.md:20`,
   `skills/wire-issue/SKILL.md:265`, and the three loop-generator skills
   (`skills/adversarial-verify-loop/SKILL.md:66`, `skills/verify-issue-loop/SKILL.md:65`,
   `skills/create-eval-from-issues/SKILL.md:184` — `audit-loop-run/SKILL.md` has
   no such reference and needs no change), replace `.issues/completed/`
   directory prose/commands with `ll-issues list --status done --json`
   equivalents. Leave each file's frontmatter `description:` line (all three
   loop-generator skills, line 11) unchanged — "accepts open or completed
   issues" is accurate as a status claim, not a directory claim.
3. Fix `skills/capture-issue/SKILL.md:202`, `commands/align-issues.md:183`,
   and `.claude/commands/analyze_log.md:174`'s invalid `--format path` to use
   `ll-issues list --status done --json` (or `--json` without a status filter
   for `analyze_log.md`'s active-issue search, since that call has no status
   filter today) (`ll-issues list` has no `--format` flag at all — confirmed at
   `scripts/little_loops/cli/issues/__init__.py:172-195`; `--format` only
   exists on the sibling `search` subcommand).
4. Fix the two broken links in `hooks/adapters/codex/README.md` (lines 41, 207)
   to point at a valid target (e.g. the FEAT-1116 issue file itself, or remove
   the dead directory link).
5. Run `ll-check-links` and `python -m pytest scripts/tests/` to confirm no
   regressions.

## Acceptance Criteria

- [x] No remaining references to `.issues/completed/` in `skills/` or
      `hooks/adapters/codex/README.md` (except the deliberate legacy detector
      in `commands/normalize-issues.md`).
- [x] No remaining `ll-issues ... --format path` invocations (`skills/capture-issue/SKILL.md:202`,
      `commands/align-issues.md:183`, and `.claude/commands/analyze_log.md:174`).
- [x] `skills/update-docs/SKILL.md` uses `scan_completed_issues`/
      `scan_completed_issues_from_db` per `decisions.py:564`'s DB-preferred pattern.
- [x] `hooks/adapters/codex/README.md`'s two links resolve to valid targets.
- [x] `python -m pytest scripts/tests/` passes (5 pre-existing failures unrelated
      to this change, confirmed present on main before this fix: history_reader,
      assistant_messages schema version, history_context_cli).

## Session Log
- `/ll:manage-issue` - 2026-07-25T15:36:02Z - `47234ae1-2725-4863-97ec-1212813e1924.jsonl`
- `/ll:ready-issue` - 2026-07-25T15:29:19 - `9d658bb5-d612-4b90-8d4b-1b52546bc1ba.jsonl`
- `/ll:confidence-check` - 2026-07-25T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a9ace3f0-e5f3-4f90-90d6-7afe6a951ebd.jsonl`
- `/ll:wire-issue` - 2026-07-25T15:26:36 - `37481539-9960-4ac7-941c-f334d4aa55b2.jsonl`
- `/ll:refine-issue` - 2026-07-25T15:24:42 - `ff8c2af7-3508-44bb-a1ff-1a2f29fa9d76.jsonl`
- `/ll:capture-issue` - 2026-07-25T15:03:20Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f5a3c0e4-074e-4e25-9ad0-d2bf4695b3c3.jsonl`
