---
id: FEAT-2851
type: FEAT
priority: P2
status: done
parent: FEAT-2846
discovered_date: 2026-07-26
discovered_by: issue-size-review
blocked_by:
- FEAT-2849
labels:
- issues-cli
- dependency-graph
relates_to:
- FEAT-2842
confidence_score: 98
outcome_confidence: 81
score_complexity: 18
score_test_coverage: 23
score_ambiguity: 18
score_change_surface: 22
completed_at: '2026-07-27T04:24:40Z'
---

# FEAT-2851: Optional --fix to backfill blocked_by from prose dependencies

## Summary

Add an opt-in `--fix` mode to `ll-issues format-check` that backfills
`blocked_by:` from confidently-matched prose dependency claims, staging a
reviewable diff rather than writing silently (the `anchor-sweep --dry-run`
posture). Decomposed from FEAT-2846; built on FEAT-2849's extractor and
gap taxonomy.

## Parent Issue

Decomposed from FEAT-2846: Detect prose dependency claims that are missing
from frontmatter. Covers Implementation Step 6 of the parent.

## Current Behavior

`ll-issues format-check` (built by FEAT-2849) reports `prose_dep_drift`
gaps — prose text naming an active dependency that's missing from
`blocked_by`/`depends_on` — but only as a report. Resolving a drift hit
today means a human hand-edits the issue's frontmatter (or runs
`ll-issues link` manually) for each of the 9 currently-drifting issues
(see FEAT-2850); there is no `--fix` path that backfills the edge
automatically.

## Use Case

A backlog owner runs `ll-issues format-check --all` and sees a dozen
`prose_dep_drift` hits across the repo. Instead of opening each issue file
and hand-editing `blocked_by:` frontmatter, they run
`ll-issues format-check --all --fix` to preview the proposed edges (dry-run
by default), confirm they look right, then re-run with an apply flag to
write them via `ll-issues link`'s cycle-safe path in one pass.

## Expected Behavior

`--fix` writes via `ll-issues link` (FEAT-2842) rather than editing
frontmatter directly, and defaults to a dry-run so the operator sees the
proposed edges before they're applied. This directly benefits this repo's
9 currently-drifting issues (see FEAT-2850) as an alternative or
complement to hand-fixing them.

`cmd_link()` (`scripts/little_loops/cli/issues/link.py:92-176`) is
idempotent (no-ops to `unchanged` if the edge already exists), supports
`--dry-run` (`would_link`/`would_unlink` status), and gates every write
through `_check_cycle()` — builds a `DependencyGraph` including the
prospective edge and calls `topological_sort()`, catching `ValueError` on a
cycle — before allowing a `blocked_by`/`depends_on` write. `--fix` should
invoke this (in-process or via `ll-issues link <id> --blocked-by
<target>`), not call `update_frontmatter()` directly.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/format_check.py` — add `--fix` flag,
  dry-run by default
- `scripts/little_loops/cli/issues/link.py:92-176` — `cmd_link()`, the
  target write path for confidently-matched prose deps

### Tests
- `scripts/tests/test_link_cli.py` — existing `cmd_link()` coverage; model
  for asserting `--fix` invokes the same idempotent/cycle-safe write path
- `scripts/tests/test_ll_issues_format_check.py` — add `--fix` dry-run and
  apply cases

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/epic_consistency.py` (`cmd_epic_consistency`/`fix_epic`, lines 209-324) — closest existing `--fix`-flag precedent in this codebase; its detect → mutate → **re-run detection** → report shape is the template `format-check --fix` should follow, but note it has no `--dry-run` (returns 0 unconditionally under `--fix`) — `link.py`'s `--dry-run` flag/status vocabulary (`would_link`/`would_unlink`, `link.py:82-88,230-253`) is the actual precedent for this issue's dry-run-by-default requirement, not epic-consistency's polarity.
- `scripts/little_loops/loops/rn-remediate.yaml` (lines 103, 108, 282) — FSM loop invokes `ll-issues format-check "$ID"` per-issue as part of the format-remediation path; does not currently pass `--fix`, but is the natural future caller once `--fix` exists (no change required for this issue's ACs, informational).
- `scripts/little_loops/cli/issues/__init__.py` (lines 53-58, 798, 852, 908-909, 922-923) — CLI dispatcher wiring both `add_format_check_parser`/`cmd_format_check` and `add_link_parser`/`cmd_link`; no changes needed (arg parsing already delegates to the per-command `add_*_parser` functions) but confirms there is no existing in-process caller pattern for invoking `cmd_link` from another command module — constructing a synthetic `argparse.Namespace` to call it directly would be novel; extracting `link.py:157-176`'s "add edge to frontmatter" block into a standalone helper (mirroring `fix_epic()`) is the lower-friction, precedent-matching alternative.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` (`#### ll-issues format-check`, lines 1609-1621) — argument/example block currently shows only `issue_id`/`--all`/`--format`; needs a `--fix` (and dry-run-by-default) row once implemented, mirroring the adjacent `ll-issues link` argument table's `--dry-run` row.

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- None found — `epic-consistency --fix` and `link --dry-run` both ship with no `config-schema.json` entries; confirms CLI flags in this codebase are not schema-backed by default, no schema change implied.

## Implementation Steps

1. Define what counts as a "confidently-matched" prose dependency (exact ID
   match, unambiguous phrasing) versus one that should stay a reported gap
   only.
2. Implement `--fix` as dry-run by default, printing proposed
   `blocked_by`/`depends_on` edges.
3. Wire the apply path through `ll-issues link`, inheriting its
   idempotency and cycle guard.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 1 has no existing data to build on**: `extract_prose_deps()`
  (`scripts/little_loops/issues/prose_deps.py`) returns a bare `set[str]`
  of normalized target IDs — it does not retain which of its three
  phrasings matched ("Depends on X" / "Blocked by X" / "Requires X" /
  `## Blocked By` list), nor a confidence tier. `FormatGaps.prose_dep_drift`
  (`scripts/little_loops/issue_parser.py`) is likewise just
  `list[str]` of target IDs, keyed to the source issue only via the outer
  `--all` sweep dict. Since the extractor is already deliberately
  precision-biased (its docstring: "Recall matters less than not crying
  wolf") and every match is an exact `TYPE-NNN` ID, "confidently-matched"
  in practice likely means "any current `prose_dep_drift` hit" — but if a
  future implementer wants to gate on phrasing type specifically, that
  distinction does not survive past `extract_prose_deps()` today and would
  need to be added there.
- **Closer `--fix` precedent than `anchor-sweep`**: `anchor-sweep --dry-run`
  writes by default and requires `--dry-run` to preview (opposite polarity
  from what this issue wants). `scripts/little_loops/cli/issues/epic_consistency.py`
  (`cmd_epic_consistency()`) has the actual matching shape for a
  report-only-by-default `--fix` flag: `--fix` is off by default (pure
  report mode), and when passed it calls `fix_epic()` per drifted item then
  **re-runs drift detection afterward** so the printed result reflects
  post-fix state. `fix_epic()` is documented idempotent ("Running twice on
  an already-fixed file is a no-op") — the same idempotency contract this
  issue's AC #3 requires.
- **No in-process precedent for calling `cmd_link()` from another command**:
  grep confirms `cmd_link()` is currently only reached through the
  `ll-issues` CLI dispatcher (`scripts/little_loops/cli/issues/__init__.py:908-909`).
  `--fix` would be the first caller invoking it in-process rather than via
  subprocess/`ll-issues link ...`. The workable shape is constructing an
  `argparse.Namespace` with the attributes `cmd_link()` reads (`issue_id`,
  one of `blocked_by`/`depends_on`/`relates_to`, `unlink`, `reciprocal`,
  `force`, `json_output`, `dry_run` — defined in `link.py:33-89`'s
  `add_link_parser()`) and calling `cmd_link(config, ns)` directly.
- **`_check_cycle()` runs before the dry-run branch** in `cmd_link()`
  (`link.py:205-227`), so a would-be-cyclic prose-dep edge is refused even
  under dry-run preview — no extra cycle-checking work needed in
  `format_check.py` itself.

### Wiring Pass Findings (added by `/ll:wire-issue`)

- **Test template to follow**: `TestEpicConsistencyFix`/`TestEpicConsistencyIdempotency`
  (`scripts/tests/test_epic_consistency.py:357-544`) is the structural
  precedent for the `--fix`/idempotency tests this issue's AC #3 requires —
  isolated fixture dir per test, a "before" test (gap reported, file
  untouched), a "fix" test (mutates frontmatter, re-checks that the gap no
  longer appears — the re-run-detection-after-fix spine from
  `cmd_epic_consistency`), an idempotency test (run `--fix` twice, assert
  byte-identical file content), and a preserve-existing-content test
  (pre-existing `blocked_by` entries survive untouched). Combine with
  `link.py`'s `--dry-run` flag/test pattern
  (`scripts/tests/test_link_cli.py:204`, `test_link_dry_run_does_not_modify_file`)
  since format-check's dry-run-by-default polarity is the opposite of
  epic-consistency's (which has no `--dry-run` and returns 0 unconditionally
  under `--fix`).
- **Output-format regression guard**: `TestProseDepGaps`
  (`scripts/tests/test_ll_issues_format_check.py`, ~lines 378-435) asserts
  verbatim on the no-`--fix` gap-report lines (`f"  prose_dep_drift: {entry}"`,
  from `_print_gaps` in `format_check.py:58-59`) — the default (no-`--fix`)
  output path must not change.
- **CI-facing consumer of exit code**: `scripts/tests/test_prose_dep_sweep_gate.py`
  (`test_no_prose_dependency_drift_in_repo`) gates on `format-check --all`'s
  exit code, though it currently calls `check_format_gaps`/`find_issues`
  directly rather than exercising `--fix`; confirm `--fix`'s exit-code
  semantics (0 after successfully fixing, matching `cmd_epic_consistency`'s
  convention) don't collide with this gate if it's ever extended to cover
  `--fix`.

## Acceptance Criteria

- [x] `--fix` defaults to dry-run and prints proposed edges without
      writing.
- [x] Applying `--fix` writes via `ll-issues link`'s cycle-safe path, not
      direct frontmatter edits.
- [x] `--fix` is idempotent — running it twice produces no additional
      changes on the second run.

## Impact

- **Users**: backlog owners can resolve prose-dependency drift in bulk
  instead of hand-editing frontmatter for each drifting issue.
- **Risk**: Low. Dry-run default and reuse of `ll-issues link`'s existing
  cycle guard bound the blast radius.
- **Effort**: Small, once FEAT-2849 lands.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `scripts/little_loops/cli/issues/link.py:92-176` | Idempotent, cycle-safe write path to reuse |

## Context

Decomposed from FEAT-2846 by `/ll:issue-size-review` (score 11/11, Very
Large); the parent issue itself notes this piece is "optional" and
separable from the core detection mechanism (FEAT-2849) and the sweep
(FEAT-2850).

## Session Log
- `/ll:ready-issue` - 2026-07-27T04:14:50 - `fe2030bd-4595-4dde-96ed-a1f8e06e24a3.jsonl`
- `/ll:confidence-check` - 2026-07-27T04:20:00 - `64b15053-1bfe-4e28-be00-e72db74d416e.jsonl`
- `/ll:wire-issue` - 2026-07-27T04:11:48 - `22f99404-f27b-4173-ad8a-ca131b5eeb78.jsonl`
- `/ll:refine-issue` - 2026-07-27T04:06:09 - `700467cd-45e2-4981-b788-c16fd9d5d5c4.jsonl`
- `/ll:issue-size-review` - 2026-07-26T00:00:00 - `52f8c37a-8768-4813-8704-c3364dbd6e28.jsonl`
- `/ll:manage-issue` - 2026-07-27T04:24:01 - `006ae3e2-7e33-4a3f-bb4c-52aaa8255fde.jsonl`

---

## Status

open
