---
id: ENH-3749
type: ENH
title: Add a parent-assignment option to ll-issues link for single child-to-EPIC assignment
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T23:41:53Z'
labels:
- issues
- link-epics
blocked_by:
- BUG-3738
relates_to:
- BUG-3739
---

# ENH-3749: Add a parent-assignment option to ll-issues link for single child-to-EPIC assignment

## Summary

Add a parent-assignment option to `ll-issues link` that assigns one child issue to one EPIC in a single, deterministic operation. It sets `parent:` (and `epic:` when present) in the child's frontmatter and adds the child's bullet to the EPIC's `## Children` section. Today no CLI command does this for an existing issue.

Two gaps motivate it:

- **One-winner apply (BUG-3738).** `link-epics --mode assign --apply` will apply only the highest-ranked EPIC per orphan. A user who wants a lower-ranked alternative from the proposal list can no longer reach it by adjusting `--threshold`, so the only remaining path is a hand edit of two files.
- **Children-listed drift (BUG-3739).** When an EPIC's `## Children` lists an issue that has no `parent:` back-reference, `link-epics` reports it as drift and excludes it, and `epic-consistency --fix` repairs only the opposite direction (category (a)). Category-(b) drift has no CLI remedy.

## Current Behavior

- `ll-issues link` writes only the list-valued dependency edges `blocked_by`, `depends_on`, and `relates_to` (`_FIELD_FLAGS` in `scripts/little_loops/cli/issues/link.py`). It has no option for the scalar `parent` relationship.
- `ll-issues create --parent` wires both sides, but only at creation time, so it cannot help an existing issue.
- `link-epics --apply` assigns from scored proposals only, and after BUG-3738 it applies only the top-ranked EPIC per orphan.
- Assigning an existing issue to a chosen EPIC therefore means editing the child's frontmatter and the EPIC's `## Children` section by hand. Both are error-prone: the edit can land outside the Children list, churn unrelated YAML, or skip one side.

## Expected Behavior

- One command assigns a named child to a named EPIC. It writes the child's `parent` (and `epic` when that key is present), and inserts a title bullet into the EPIC's exact `## Children` section using the same placement rules as `link-epics --apply` and `create --parent`.
- **Idempotent:** re-running with the same pair changes neither file and performs no write. When the EPIC already lists the child (category-(b) drift), only the child's frontmatter is written, which is the remedy for that drift.
- **Conflict-safe:** if the child already has a different non-null `parent`/`epic`, the command fails with a nonzero exit and changes neither file, unless an explicit reparent switch is given.
- **Reparenting:** with the switch, the child's parent fields move to the new EPIC and the bullet is added there. Removing the stale bullet from the old EPIC is reported as a follow-up in this version, never deleted automatically (see Scope Boundaries).
- **Validation:** the target must resolve to an EPIC, and the child must be BUG, FEAT, or ENH. An EPIC child is rejected, because sub-EPICs use `relates_to` and prose (`epic-consistency`'s sub-EPIC advisory).
- **Missing heading:** when the EPIC has no exact `## Children` heading, the frontmatter is still written and the output says the body write was skipped. This is the same visible skip contract as BUG-3738.
- **Existing flags:** `--dry-run` reports both planned edits without writing, and `--json` emits a structured result.

## Motivation

BUG-3738 deliberately removes the threshold workaround for choosing a non-top EPIC, and BUG-3739 surfaces children-listed drift without a fix. With neither gap closed, both issues push users toward hand-editing two files, which is exactly the class of corruption BUG-3738 fixes in automated paths. A single assignment primitive closes both gaps and reuses machinery those issues already build.

## Proposed Solution

Extend `ll-issues link` with a new mutually exclusive option for the parent relationship, alongside the three existing edge options. It routes to a separate apply function, because `parent` is a scalar field on the child plus a body edit on the EPIC, not a list edge. Reuse BUG-3738's pieces without reimplementing them:

- the preserving scalar frontmatter upsert in `frontmatter.py` (not `update_frontmatter`, which re-dumps the whole mapping)
- the improved `_append_child_to_epic_children()` helper, with its three outcomes: no heading, already present, or an ambiguous section raising `AmbiguousChildrenSection`
- the shared Children recognizer (`find_children_section` / `iter_child_entries` in `epic_consistency.py`), for duplicate detection
- the per-pair pattern: one `acquire_lock(issue_lock_path(...))` around re-reading both files, validating, computing both texts, and writing changed files with `atomic_write(..., shared_mode=True)`, orphan side first

Prefer extracting BUG-3738's per-pair apply core into a function that both `link-epics --apply` and this option call, rather than duplicating it. `--unlink` with the new option clears the child's parent fields and removes its own bullet only when it is an exact recognized entry. If that turns out non-trivial, defer it (see Scope Boundaries).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/link.py` — new option in the mutually exclusive group, routing in `cmd_link`, a parent-assignment apply path, and `_report` output.
- `scripts/little_loops/cli/issues/link_epics.py` — only if the per-pair apply core is extracted for sharing; `apply_assignment` becomes a caller of it.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/create.py` — source of `_append_child_to_epic_children` (consumed, not changed).
- `scripts/little_loops/frontmatter.py` — BUG-3738's scalar upsert (consumed).
- `scripts/little_loops/cli/issues/epic_consistency.py` — shared Children recognizer (consumed).
- `scripts/little_loops/file_utils.py` — `acquire_lock`, `issue_lock_path`, `atomic_write` (consumed).

### Similar Patterns
- `apply_link` in `link.py`: lock, read, validate, write for list edges.
- BUG-3738's `apply_assignment`: the two-file preserving write this option should share.

### Tests
- `scripts/tests/test_link_cli.py` — new assignment cases:
  - fresh assignment, and idempotent re-run with no writes
  - category-(b) remedy (frontmatter-only write)
  - conflicting parent rejected with no writes, and allowed with the reparent switch
  - non-EPIC target and EPIC child rejected
  - missing heading visible in output
  - ambiguous Children section rejected
  - `--dry-run` and `--json`
  - lock timeout
- `scripts/tests/test_link_epics_cli.py` — regression coverage if the apply core is extracted.

### Documentation
- `docs/reference/CLI.md` (the `ll-issues link` section) and `docs/reference/COMMANDS.md`.
- `skills/link-epics/SKILL.md`: replace BUG-3738's "a different EPIC requires a manual edit" wording with this command, and point children-listed drift reports at it as the remedy. Regenerate host mirrors with `ll-adapt`.

### Configuration
- N/A

## Implementation Steps

1. After BUG-3738 lands, extract its per-pair apply core (lock, re-read, validate, compute both texts, ordered changed-file writes) into a reusable function, keeping `link-epics` behavior and tests unchanged.
2. Add the option to `ll-issues link`, with validation (EPIC target, BUG/FEAT/ENH child), conflict and reparent handling, and `--dry-run`/`--json` reporting.
3. Add the `test_link_cli.py` cases above, then update CLI.md, COMMANDS.md, the link-epics skill and its mirrors.
4. Run the focused suites, then `python -m pytest scripts/tests/`.

## Acceptance Criteria

- [ ] One command assigns an existing BUG/FEAT/ENH issue to a named EPIC. Both sides are written with BUG-3738's preserving writers, and unrelated bytes, line endings, and file modes are unchanged.
- [ ] Re-running the same assignment performs no write. An EPIC that already lists the child gets no duplicate bullet, and only the child's frontmatter is written (the category-(b) remedy).
- [ ] A conflicting existing parent fails nonzero with no writes. The explicit reparent switch moves the parent and reports, but does not delete, the stale listing on the old EPIC.
- [ ] A non-EPIC target, an EPIC child, an ambiguous Children section, and a lock timeout are each rejected with no writes. A missing `## Children` heading writes frontmatter and says the body write was skipped.
- [ ] `--dry-run` writes nothing, and `--json` output is a single structured document.
- [ ] The link-epics skill and the CLI docs name this command as the way to choose a non-top EPIC and to repair children-listed drift.

## Scope Boundaries

- **Out of scope:** deleting the stale bullet from the previous EPIC when reparenting. That is a body deletion with its own ambiguity rules, and can follow in a separate issue.
- **Out of scope:** batch or multi-pair assignment. `link-epics --apply` remains the batch path.
- **Out of scope:** changing `epic-consistency --fix` to repair category-(b) drift automatically, since which side is authoritative is a judgment call.
- **Out of scope:** `--reciprocal` semantics. Parent assignment is inherently two-sided.

## Backwards Compatibility

Additive: a new option in an existing mutually exclusive group. The existing `blocked_by`/`depends_on`/`relates_to` behavior and output are unchanged.

## API/Interface

A new mutually exclusive option on `ll-issues link` that takes the EPIC ID, plus an explicit reparent switch that is valid only with it. Exact flag spellings are decided at implementation, so check them against the existing `ll-issues link` surface to avoid collisions (`--force` already means "skip target-existence validation").

## Impact

- **Priority**: P3 — closes the manual-edit gaps that BUG-3738 and BUG-3739 leave open; not urgent until those land.
- **Effort**: Small — mostly CLI wiring on top of BUG-3738's writers, lock, and helper.
- **Risk**: Low — additive option; the risky text transforms are owned and tested by BUG-3738.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-05 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-10-05T23:43:06 - `dfedb32a-de04-4382-86b8-3c6cab5d9da5.jsonl`
