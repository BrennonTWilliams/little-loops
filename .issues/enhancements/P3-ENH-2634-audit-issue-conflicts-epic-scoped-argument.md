---
id: ENH-2634
title: audit-issue-conflicts ignores positional EPIC argument; always scans full backlog
type: ENH
priority: P3
status: done
captured_at: '2026-07-14T00:22:18Z'
completed_at: '2026-07-14T02:47:23Z'
discovered_date: 2026-07-14
discovered_by: capture-issue
relates_to:
- ENH-1801
- ENH-1802
confidence_score: 100
outcome_confidence: 85
score_complexity: 22
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 20
---

# ENH-2634: audit-issue-conflicts ignores positional EPIC argument; always scans full backlog

## Summary

`/ll:audit-issue-conflicts` accepts no positional argument. When invoked as
`/ll:audit-issue-conflicts EPIC-2457 --auto`, the `EPIC-2457` token matches none
of the recognized flags (`--auto`, `--dry-run`, `--cross-theme`) in Phase 0 and
is silently dropped. Phase 1 then unconditionally loads **every** active issue
in `.issues/{bugs,features,enhancements}/`, so the audit scans the whole backlog
instead of the named EPIC's sub-issues.

Users reasonably expect `audit-issue-conflicts EPIC-NNNN` to scope the conflict
scan to that EPIC's children — both because it matches the natural "audit this
epic for internal conflicts" use case and because it makes the audit far cheaper
than a full-backlog fan-out (an EPIC of ~28 children vs. the entire active set).

## Motivation

- The skill's own narration ("this audit needs to scan across all active issues")
  faithfully describes current behavior — the EPIC token has zero effect, which
  is surprising and wasteful.
- Scoping avoids spawning batch Task calls across the full backlog when the user
  only cares about one EPIC's internal consistency.
- Secondary gap: Phase 1's glob is `{bugs,features,enhancements}` — `epics/` is
  never loaded, so EPIC files themselves are never fingerprinted.

## Current Behavior

`skills/audit-issue-conflicts/SKILL.md`:
- **Phase 0 (Parse Flags)** only recognizes `--auto`, `--dry-run`,
  `--cross-theme`. No positional parsing. `argument-hint` is
  `"[--auto] [--dry-run] [--cross-theme]"`.
- **Phase 1 (Load Issues)** iterates `for dir in
  {{config.issues.base_dir}}/{bugs,features,enhancements}/` and collects every
  file with `status: open|in_progress|blocked` into `ISSUE_FILES`. No parent/EPIC
  filter anywhere in the 496-line skill.

## Proposed Change

1. **Phase 0**: parse an optional positional `EPIC-NNNN` (or bare `NNNN`
   normalized to `EPIC-NNNN`) argument into `SCOPE_EPIC`. Validate it resolves to
   an existing EPIC file; abort with a clear message if not.
2. **Phase 1**: when `SCOPE_EPIC` is set, restrict `ISSUE_FILES` to issues whose
   `parent:` resolves **transitively** to that EPIC via
   `ll-issues list --parent "$SCOPE_EPIC" --json` — this already walks the
   `parent:` chain transitively (cycle-guarded, through `done` intermediates)
   since ENH-2481 and emits child `id`/`path`. Extract the paths (mirror the
   `python3 -c` shim in `scripts/little_loops/loops/prompt-across-issues.yaml`),
   optionally appending the EPIC file itself. Include `epics/` in the unscoped
   load glob so the EPIC and any nested child epics are fingerprinted.
   (Note: `ll-issues epic-progress --format json` does not expose child paths and
   `ll-issues sequence` has no EPIC scoping — neither is usable here.)
3. Log the scoped mode and the resulting issue count
   (e.g. `Scoped to EPIC-2457: N child issues`).
4. Update `argument-hint` and the Examples section to document
   `/ll:audit-issue-conflicts EPIC-NNNN [flags]`.

## API/Interface

New optional positional argument (backward compatible — omitting it preserves
today's full-backlog behavior):

```
/ll:audit-issue-conflicts [EPIC-NNNN] [--auto] [--dry-run] [--cross-theme]
```

## Acceptance Criteria

- [ ] `/ll:audit-issue-conflicts EPIC-NNNN` loads only that EPIC's transitive
      children (plus the EPIC file), and logs the scoped count.
- [ ] A bare `NNNN` matching an EPIC is normalized and accepted.
- [ ] An unrecognized / non-EPIC positional argument aborts with a clear message
      rather than being silently ignored.
- [ ] Omitting the argument preserves current full-backlog behavior.
- [ ] `argument-hint` and Examples document the new form.
- [ ] `epics/` is included in the Phase 1 load glob.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `skills/audit-issue-conflicts/SKILL.md` — Phase 0 (add `SCOPE_EPIC`
  positional parse + validation), Phase 1 (scope `ISSUE_FILES` when set; add
  `epics/` to glob), frontmatter `argument-hint` + `arguments:` block, Examples.

### Dependent Files (Callers/Invokers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — the
  `audit_conflicts` state (line 100) invokes `/ll:audit-issue-conflicts --auto`.
  Behavior is backward-compatible (no positional passed → full-backlog scan
  preserved), but this is the one live automated invoker; a future follow-up
  could pass the sprint's EPIC scope here. No change required for this issue.
  [Agent 1 finding]

### Reusable Primitive (correction to Proposed Change)
- `ll-issues list --parent EPIC-NNN --json` — **this is the tool to reuse**, not
  `epic-progress`/`sequence` as the issue currently states:
  - `ll-issues list --parent` already resolves an EPIC's **transitive**
    children (cycle-guarded) via `compute_epic_progress()` since **ENH-2481**
    (`scripts/little_loops/cli/issues/list_cmd.py`; decision recorded at
    `.ll/decisions.yaml:3925`). It emits child `id`/`path`, which is exactly
    what Phase 1 needs.
  - `ll-issues epic-progress EPIC-NNN --format json` does **NOT** expose the
    child ID/path list — `EpicProgress.to_dict()`
    (`scripts/little_loops/issue_progress.py:30-48`) only serializes aggregate
    counts. Not usable from a bash skill for scoping.
  - `ll-issues sequence` has **no** EPIC-scoping code path (filters by
    `--type` only; `scripts/little_loops/cli/issues/sequence.py`). The issue's
    "reuse ... sequence" phrasing is not implementable as written.
  - Canonical shell shim precedent:
    `scripts/little_loops/loops/prompt-across-issues.yaml` `init` action —
    forwards `--parent` to `ll-issues list --json`, then extracts `id`s in a
    `python3 -c` block. Model Phase 1's scoped branch on this.

### Transitive-Walk Source (if Python-level access is preferred)
- `scripts/little_loops/issue_progress.py` — `compute_epic_progress()`,
  `_issue_descends_to()` (per-issue upward chain walk, cycle-guarded),
  `build_parent_map()`. Walks through `done` intermediates so grandchildren roll
  up (confirmed by `test_issue_progress.py::test_transitive_chain_includes_grandchildren`).

### EPIC-NNNN / bare-NNNN Normalization
- Full normalization pattern (accepts `EPIC-NNN`, bare `NNN`, `P#-EPIC-NNN`,
  case-insensitive, numeric-fallback): `_resolve_issue_id()` in
  `scripts/little_loops/cli/issues/show.py:39` (used by `ll-issues path/show`).
  Mirror this for AC "bare NNNN accepted".
- Narrower strict-prefix + not-found abort shape:
  `cmd_epic_progress()` (`scripts/little_loops/cli/issues/epic_progress.py:48-51`)
  — `strip().upper()`, require `startswith("EPIC-")`, else print error + exit 1.
  This is the "abort with clear message" precedent for the AC.

### Similar Patterns (positional EPIC arg in a skill)
- `skills/review-epic/SKILL.md` — required positional `<EPIC-ID>`:
  `argument-hint: "<EPIC-ID> [--skip-drift]"`, an `arguments:` block with
  `name: epic_id / required: true`, Step 1 "first token... uppercase it", and
  Step 2a existence-validation via `ll-issues list --type EPIC --json` → abort
  message if not found. Adapt to **optional** for ENH-2634 (backward compat).
  Note: review-epic's inline predicate is deliberately *direct-only* (BUG-2333);
  ENH-2634 wants *transitive*, so follow `list --parent`, not that predicate.

### Tests
- `scripts/tests/test_audit_issue_conflicts_skill.py` — existing structural
  tests (read SKILL.md, assert substrings). Add assertions: `SCOPE_EPIC` parse
  block present, epic-not-found abort message present, `epics/` in Phase 1 glob,
  `--parent` used for scoping.

  _Wiring pass correction by `/ll:wire-issue`:_ do **not** copy assertions from
  `test_review_epic_skill.py` — despite `EPIC_ID` appearing throughout
  `skills/review-epic/SKILL.md`, none of that file's 8 tests assert on
  `argument-hint`, positional parsing, or abort-on-not-found (that behavior is
  currently untested there). The new tests are novel. Mirror instead the
  **phase-slicing idiom** already in `test_audit_issue_conflicts_skill.py`
  (`test_phase4b_idempotency_guard_present` lines 84–92: slice `content` between
  two `## Phase N` headers before asserting) so Phase 0 / Phase 1 assertions
  don't false-positive on other phases. The `epics/`-glob assertion mirrors
  `test_config_issues_base_dir_glob` (lines 48–51). All 12 existing tests are
  unaffected. [Agent 3 finding]
- `scripts/tests/test_issues_cli.py:1027` (`test_list_parent_includes_transitive_grandchild`)
  + `:1068` (excludes-unrelated) already prove `list --parent` transitivity —
  no new CLI test needed if the skill reuses that command.

### Documentation
- `docs/reference/CLI.md` and `.claude/CLAUDE.md` `ll-issues list` line — update
  if surfacing the new positional usage.

_Wiring pass added by `/ll:wire-issue`:_
- `commands/help.md` — restates this skill's invocation **independently** of the
  SKILL.md frontmatter: usage synopsis `/ll:audit-issue-conflicts [flags]` (line 91)
  and a `Flags:` line (line 94) documenting only `--auto` / `--dry-run`. Already
  stale (omits the existing `--cross-theme`); add the new `[EPIC-NNNN]` positional
  to keep it consistent with the updated `argument-hint`. [Agent 2 finding]
- `docs/reference/COMMANDS.md` — the `### /ll:audit-issue-conflicts` section has a
  `**Flags:**` line but **no `**Arguments:**` subsection**. Add one documenting the
  optional `epic-id` positional, following the sibling pattern already used by
  `/ll:tradeoff-review-issues` (`issue-ids`) and `/ll:product-analyzer`
  (`focus-area`). [Agent 2 finding]
- Note: no other doc (ISSUE_MANAGEMENT_GUIDE, LOOPS_REFERENCE, ARCHITECTURE,
  API.md) depends on the no-positional-arg behavior — flag-only references there
  need no change. No `config-schema.json` coupling (confirmed). [Agent 2 finding]

## Codebase Research Findings

_Added by `/ll:refine-issue`:_

- **The "epics/ never fingerprinted" secondary gap is real**: Phase 1 glob is
  literally `{bugs,features,enhancements}/` — `epics/` is absent, so EPIC files
  are never loaded/fingerprinted regardless of scoping. Fixing the glob is
  independent of (and can land alongside) the scoping change.
- **Phase 0 has zero positional handling today**: it only does
  `if ARGUMENTS contains "--auto"`-style boolean checks; any `EPIC-NNNN` token
  is unmatched and silently dropped, exactly as the Summary states.
- **Recommended implementation shape**: in Phase 1, when `SCOPE_EPIC` is set,
  replace the full-backlog glob with
  `ll-issues list --parent "$SCOPE_EPIC" --status open,in_progress,blocked --json`
  piped through a `python3 -c` id/path extractor (mirroring
  `prompt-across-issues.yaml`), then optionally append the EPIC file's own path.
  When unset, keep the existing glob (but add `epics/` to it). This satisfies
  every AC while reusing tested, transitive resolution.
- **CORRECTION — `--status` does not accept a comma-separated list** (verified
  2026-07-13): `ll-issues list --parent EPIC-2457 --status open,in_progress,blocked
  --json` exits **2** (argparse usage error). `--status` is a single-choice enum
  (`{open,in_progress,blocked,deferred,done,cancelled,all}`); it takes exactly one
  value. The comma form in the "Recommended implementation shape" above will not
  run. Use one of instead:
  - `ll-issues list --parent "$SCOPE_EPIC" --status all --json`, then filter to
    `open|in_progress|blocked` inside the `python3 -c` id/path extractor
    (recommended — one CLI call, mirrors `prompt-across-issues.yaml`), **or**
  - three separate `--status open` / `--status in_progress` / `--status blocked`
    calls unioned in the extractor.
  The default (`--status open` when omitted) would silently drop `in_progress`
  and `blocked` children, so an explicit `--status all` + in-extractor filter is
  the correct shape.

## Related Issues

- ENH-1801 (cross-theme detection) and ENH-1802 (Scope Boundary idempotency) are
  adjacent audit-issue-conflicts work but address different concerns.
- ENH-2481 — made `ll-issues list --parent` transitive; the enabling dependency
  for this issue's scoping.

## Session Log
- `/ll:manage-issue` - 2026-07-14T02:47:23 - `ede330da-d2ce-4145-ba37-0ba7c2d053a4.jsonl`
- `/ll:refine-issue` - 2026-07-14T02:32:40 - `a822510e-834e-45a1-84d2-bab591a111bd.jsonl`
- `/ll:wire-issue` - 2026-07-14T00:38:34 - `b93a45e7-4dc4-4669-8b86-f4f503426c69.jsonl`
- `/ll:refine-issue` - 2026-07-14T00:28:18 - `621ca141-d10e-4326-b2c3-52c93473a7ab.jsonl`
- `/ll:capture-issue` - 2026-07-14T00:22:18Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bf6876a0-2fb4-4626-99a4-da1569d51511.jsonl`
