---
id: ENH-3247
type: ENH
title: Extend format-check --fix to repair structural debris in issue files
priority: P2
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T19:30:05Z'
relates_to:
- ENH-3244
- BUG-3245
- ENH-3246
- ENH-3248
---

# ENH-3247: Extend format-check --fix to repair structural debris in issue files

## Summary

`ll-issues format-check --fix` already exists with a dry-run/`--apply` convention, but is hardcoded
to one gap class (`prose_dep_drift`). Add a dispatch layer and a second repair: deterministic
normalization of duplicate section headings and empty `_Added by_` provenance stubs. No LLM
involved — the correct output is fully determined by the input.

## Current Behavior

`format-check` already describes itself as a "Deterministic structural linter"
(`scripts/little_loops/cli/issues/format_check.py:60-68`) and enumerates 20 gap classes. It already
has a write mode with the right safety shape (`:95-105`):

```
--fix     Preview backfilling blocked_by from prose_dep_drift gaps via
          `ll-issues link` (dry-run by default; combine with --apply to write)
--apply   With --fix, write the proposed edges instead of previewing them
```

But `--fix` has **no dispatch layer**. Both call sites hardcode the single repair:

- `format_check.py:299` — sweep path (`--all`): `_fix_prose_deps(config, info.issue_id, gaps.prose_dep_drift, apply=apply_fix)`
- `format_check.py:343` — single-issue path: `_fix_prose_deps(config, source_id, gaps.prose_dep_drift, apply=apply_fix)`

So a second repairable gap class cannot be added without first generalizing those two sites.

Separately, the two structural defects this issue targets are not currently *detected* either:

- **Duplicate section headings** — ENH-3238 carried two `### Call Path` headings and two
  `### Dependent Files (Callers/Importers)` headings after one retry pass.
- **Empty provenance stubs** — three consecutive identical
  `_Added by \`/ll:refine-issue\` — <date> — based on codebase analysis:_` lines with no bullets
  between them.

The nearest existing gap class, `boilerplate`, cannot catch these: it fires only when a **required
section's body equals its `creation_template` in full**
(`scripts/little_loops/issue_parser.py:853-856`). Any partial fill defeats the whole-body equality
test — which is exactly why ENH-3238's `## Integration Map` passed while still holding five `TBD`
bullets.

## Expected Behavior

`ll-issues format-check <ID> --fix` previews, and `--fix --apply` writes, deterministic repairs for
structural debris:

- Duplicate `###` headings within the same parent `##` section are collapsed into one, with the
  bodies concatenated in document order.
- An `_Added by …:_` provenance stub with no bullet before the next heading is deleted.

Both are pure functions of the input file. Running the repair twice is a no-op.

## Motivation

This class of debris is not a content judgment — for any given input there is exactly one correct
output. Sending it to an LLM pass costs tokens and introduces the risk of collateral rewrites for
zero decision value. It belongs in the deterministic linter that already owns structural gaps.

Doing it inside `format-check` rather than as a new command avoids three costs:

- **No reimplementation.** The write path, dry-run default, and `--apply` gate exist and are tested.
- **No detection/repair drift.** A separate `normalize-structure` command would have to re-derive
  the same gap classes to know what to fix, and the two definitions would diverge.
- **No new gate plumbing.** `format-check` is already consumed by non-LLM shell gates via its JSON
  payload (`superseded_marker_count` → `autodev.yaml:1590-1596`), so the loop step is one existing-
  shape command.

The remaining argument for a separate command was "don't turn a checker into a writer." That already
happened; a new command would make the existing `--fix` read as an inconsistency.

## Proposed Solution

1. **Add a dispatch layer for `--fix`.** Replace the two hardcoded `_fix_prose_deps` calls
   (`:299`, `:343`) with a table mapping gap class → repair function, so repairs compose and future
   classes are additive. Preserve the existing `prose_dep_drift` behavior exactly.
2. **Detect the two structural classes.** New gap classes in `issue_parser.py` alongside the
   existing 20:
   - `duplicate_heading` — the same `###` heading text appearing more than once under one `##`
     parent.
   - `empty_provenance_stub` — an `_Added by …:_` line with no list item between it and the next
     heading or stub.
3. **Repair them.** Collapse duplicate headings (concatenate bodies in document order, keep the
   first position); delete empty stubs. Both under the existing dry-run/`--apply` convention.
4. **Assert idempotency**: applying the repair to its own output changes nothing.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/format_check.py` — the `--fix` dispatch layer (`:299`, `:343`)
  and the new repair functions next to `_fix_prose_deps` (`:110`).
- `scripts/little_loops/issue_parser.py` — the two new gap classes, added to `FormatGaps`
  (`:494`), its truthiness aggregate (`:520`), its dict serialization (`:546`), and the gap-class
  docstring table (`:623-650`).
- `scripts/little_loops/cli/issues/format_check.py` — `_print_gaps` (`:132`) for text output.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/autodev.yaml:1590-1596` — reads `format-check --format json`; new keys
  are additive and must not change existing ones.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — ENH-3248's proposed normalize step is the
  main consumer of the repair.
- Every caller of `ll-issues format-check` — the exit-code contract (`1` when `gaps.has_gaps`,
  `format_check.py:379`) now also fires on the two new classes, so a previously-clean issue with
  duplicate headings starts reporting. Intended, but it is a behavior change for existing callers.

### Similar Patterns
- `_fix_prose_deps` (`format_check.py:110-130`) — the existing repair's shape: a dedicated helper
  taking `apply: bool`, delegating to an idempotent write path rather than editing frontmatter
  directly. Match it.
- `duplicate_findings_block` — an already-enumerated gap class in the same family, useful precedent
  for how duplicate-content classes are named and reported.

### Tests
- `scripts/tests/` — per gap class: detection on a crafted fixture, `--fix` previewing without
  writing, `--fix --apply` writing, and idempotency (apply twice → byte-identical). Use ENH-3238's
  pre-cleanup revision as a real-world fixture.
- Existing `--fix` tests must still pass unchanged, proving the dispatch refactor is behavior-preserving.

### Documentation
- `docs/reference/CLI.md` — `ll-issues format-check` gap classes and `--fix` scope.

### Configuration
- N/A

## Program Design

### Call Path

`cmd_format_check` -> `_fix_prose_deps` -> `superseded_marker_count`

- `cmd_format_check` (`scripts/little_loops/cli/issues/format_check.py:191`) is the entry point;
  returns `1 if gaps.has_gaps else 0` (`:379`).
- `_fix_prose_deps` (`:110`) is the only current repair, invoked from `:299` and `:343` — the two
  sites the dispatch layer replaces.
- `superseded_marker_count` (`scripts/little_loops/issue_parser.py:1173`) is the precedent for a
  deterministic public count consumed by a non-LLM gate.

### Decision Rules

- **Determinism requirement**: a repair qualifies only if the correct output is fully determined by
  the input. Duplicate-heading collapse and empty-stub deletion both qualify. Anything requiring a
  content judgment does not belong here — it goes to `/ll:reconcile-issue` (ENH-3246).
- **Duplicate-heading merge order**: keep the first occurrence's position, concatenate subsequent
  bodies in document order. Never drop a body — this is a *move*, not a deletion.
- **Empty-stub deletion is a true deletion**, justified because the stub carries no information: it
  is a provenance marker for content that does not exist.
- **Safety convention (inherited)**: `--fix` previews, `--fix --apply` writes. Do not introduce a
  second convention.

### Signatures
- `cmd_format_check(config: BRConfig, args: argparse.Namespace) -> int` — the entry point gaining
  the `--fix` dispatch layer, at `scripts/little_loops/cli/issues/format_check.py:191`; returns 1
  when any gap remains.
- `_fix_prose_deps(config: BRConfig, source_id: str, targets: list[str], apply: bool) -> None` — the
  existing single repair whose shape the new repairs mirror, at
  `scripts/little_loops/cli/issues/format_check.py:110`.

## Implementation Steps

1. Refactor `--fix` into a gap-class → repair dispatch table; prove `prose_dep_drift` behavior is
   unchanged by the existing tests.
2. Add the `duplicate_heading` and `empty_provenance_stub` gap classes to `issue_parser.py`
   (`FormatGaps`, `has_gaps`, dict serialization, docstring table) and to `_print_gaps`.
3. Implement the two repairs behind the existing dry-run/`--apply` convention.
4. Add detection, preview, apply, and idempotency tests; use ENH-3238's pre-cleanup revision as a
   fixture.
5. Update `docs/reference/CLI.md`.
6. `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P2 - Removes an entire debris class from every issue deterministically and at
  near-zero cost, and supplies the cheap first stage of ENH-3248's triage.
- **Effort**: Small-Medium - the dispatch refactor is mechanical; the two repairs are small; the
  test matrix (4 cases × 2 classes) is the bulk of it.
- **Risk**: Medium - `--fix --apply` mutates issue files, and the duplicate-heading merge moves
  content between locations. Mitigated by dry-run default, the never-drop-a-body rule, and
  idempotency tests. The exit-code widening also affects existing `format-check` callers.
- **Breaking Change**: No - new gap classes are additive to the JSON payload; the exit code fires on
  strictly more conditions, which is the intent.

## Scope Boundaries

**Determinism is the admission test.** Only repairs with a single correct output belong here.
Filling a `TBD` requires knowing what should replace it — that is `/ll:reconcile-issue`'s job
(ENH-3246), not this command's. Detecting the placeholder is ENH-3244's.

**Not a new command.** `format-check --fix` already exists with the right convention; a separate
`normalize-structure` would duplicate the write path and split detection from repair.

## Related Issues

- BUG-3245 — stops new duplicate headings and empty stubs being created; this issue cleans existing
  ones. Both are needed.
- ENH-3244 — placeholder detection, which lands in the same `format-check` payload.
- ENH-3246 — owns the non-deterministic half (filling placeholders from findings).
- ENH-3248 — consumes this as the first, cheapest stage of the retry triage.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-17 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-08-17T19:29:38 - `3ce34465-00fd-4ba7-a470-b61774849ebd.jsonl`
