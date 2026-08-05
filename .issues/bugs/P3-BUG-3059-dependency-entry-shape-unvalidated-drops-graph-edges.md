---
id: BUG-3059
title: Dependency-entry shape is unvalidated, so a bare-numeric ID drops the graph
  edge
type: BUG
priority: P3
status: done
testable: true
discovered_by: run-forensics
discovered_date: 2026-08-05
captured_at: '2026-08-05T05:42:22Z'
completed_at: '2026-08-05T05:42:22Z'
relates_to:
- BUG-2769
- ENH-3046
- BUG-3057
labels:
- issues
- gates
- dependency-graph
---

# BUG-3059: Dependency-entry shape is unvalidated, so a bare-numeric ID drops the graph edge

## Summary

No gap kind validated the *shape* of entries in `blocked_by`, `depends_on`,
`blocks`, `relates_to`, or `supersedes`. `malformed_id` (BUG-2769) only checks
the frontmatter `id:` key against the filename. A bare-numeric entry such as
`depends_on: [3038]` therefore passed every gate, while `DependencyGraph` matched
IDs by exact string and silently dropped the edge.

## Steps to Reproduce

1. Write an issue with `depends_on:\n- 3038` (missing the `FEAT-` prefix), where
   `FEAT-3038` exists on disk.
2. Run `ll-issues format-check <ID>` — pre-fix, reports nothing about it.
3. Run any command that builds the dependency graph (`ll-issues list`) and
   observe:
   ```
   Issue FEAT-3039 has depends_on unknown issue 3038
   ```
4. Confirm the edge is absent, not merely warned about:
   `dependency_graph.py:139-146` hits `if target_id not in all_issue_ids:` and
   `continue`s past the edge construction.

Live instances found: `FEAT-3039:12` (`depends_on: - 3038`) and `FEAT-3037:12-14`
(`blocks: - 3038 / - 3039 / - 3040`) — four entries across two files, all in the
3037–3040 advisor cluster, all naming targets that exist on disk.

## Current Behavior

The warning does fire — `dependency_graph.py` emits
`logger.warning(f"Issue {issue.issue_id} has depends_on unknown issue {target_id}")`
on all three passes. But it is a library-logger line that appears among roughly
27 other pre-existing "unknown issue" warnings on a normal invocation, so in
practice it is invisible. The failure is not silence; it is that a real,
edge-dropping data defect is indistinguishable from ambient noise.

Only one of the four entries was live: `FEAT-3037` is `status: done` and excluded
from the graph, so its three `blocks:` entries were inert. `FEAT-3039`'s
`depends_on` edge was genuinely missing.

## Expected Behavior

`ll-issues format-check` reports a `malformed_dep_id` gap for any entry in the
five edge keys that is not a well-formed `TYPE-NNN` ID, so the defect is caught
at authoring time rather than inferred from log noise. The optional `P<n>-`
filename prefix is accepted, matching `prose_deps._ID_RE`.

## Root Cause

The gap-kind family grew around section structure and prose content; frontmatter
validation was only ever added for the single `id:` key. Dependency values were
consumed by `DependencyGraph` and `check_format_gaps` alike via
`str(v).strip().upper()`, which normalizes case but never validates shape, so a
malformed entry flowed through as an ordinary string that simply matched nothing.

## Program Design

### Signatures

- `check_format_gaps(issue_path: Path, templates_dir: Path | None = None, issue_statuses: dict[str, str] | None = None, ref_index=None) -> FormatGaps` — existing, `issue_parser.py:396`.
- `FormatGaps.malformed_dep_id: list[str]` — new field, `issue_parser.py:261`.
- `FormatGaps.to_dict(self) -> dict[str, list[str]]` — existing, `issue_parser.py:290`.
- `_DEP_ID_RE: re.Pattern[str]` — new module constant.

### Call Path

`cmd_format_check` (`cli/issues/format_check.py:176`) -> `check_format_gaps` (`issue_parser.py:396`) -> `_DEP_ID_RE.fullmatch`; rendered by `_print_gaps` (`cli/issues/format_check.py:120`). The edge consumer this protects is `DependencyGraph` (`dependency_graph.py:139`), whose exact-string membership test drops a malformed entry.

Detection sits beside the existing `malformed_id` block and runs unconditionally
— it is pure frontmatter-shape validation and needs neither `issue_statuses` nor
`ref_index`. Each of the five keys is normalized to a list (a scalar string is
wrapped), then every entry is `fullmatch`ed; failures append
`f"{dep_key}: {dep_entry} (expected TYPE-NNN)"`.

Wiring follows the ENH-3046 precedent exactly: `FormatGaps` field, `has_gaps`,
`to_dict`, the `Gap classes:` docstring, a `_print_gaps` loop, the three prose
gap-kind enumerations (`format-check` subparser help, `cmd_format_check`
docstring, `cli/issues/__init__.py` dispatch banner), and both doc references
(seventeen → eighteen).

## Implementation Steps

1. Correct the four live entries in `FEAT-3039` and `FEAT-3037`.
2. Add `_DEP_ID_RE` and the `malformed_dep_id` field to `issue_parser.py`;
   include it in `has_gaps` and `to_dict`; document it under `Gap classes:`.
3. Add the detection loop after the `malformed_id` block.
4. Add the `_print_gaps` loop and update the three prose enumerations.
5. Update `docs/reference/CLI.md` and `docs/reference/API.md`.
6. Tests: `TestCheckFormatGapsMalformedDepId` (bare numeric, all five keys,
   well-formed IDs, `P<n>-` prefix, scalar value, unknown type prefix, absent
   keys, no-`issue_statuses` path) plus `TestCorpusHasNoMalformedDepIds` as a
   standing corpus guard.

## Impact

Dependency edges vanish from the graph without any effective signal, so
`ll-issues ready`, sequencing, and sprint planning all operate on an incomplete
graph. The failure is quiet and cumulative: each malformed entry is one missing
constraint, and the only evidence is a warning line lost among dozens.

Scope was small at discovery (one live edge), but the class is open-ended — every
future hand-edited or agent-generated frontmatter block could add another.

## Resolution

Data corrected and the `malformed_dep_id` gap kind added as the eighteenth class.
The `FEAT-3039` graph warning no longer appears. Verified end-to-end through the
CLI in text, JSON, and sweep modes; `TestCorpusHasNoMalformedDepIds` passes across
the full corpus.

Note the earlier characterization of "three `--kinds` CSVs" was inaccurate:
`format-check` has no `--kinds` flag. The three sites are prose gap-kind
enumerations, and those are what this change updates.

## Status

**Completed** — 2026-08-05

## Session Log
- `hook:posttooluse-status-done` - 2026-08-05T05:45:21 - `fb7ca535-1f06-49a2-8ac3-7943736f7215.jsonl`

- run-forensics - 2026-08-05 - Root-caused from a warning emitted at the head of a
  failed `ll-auto` run; data fixed and gap kind added.
