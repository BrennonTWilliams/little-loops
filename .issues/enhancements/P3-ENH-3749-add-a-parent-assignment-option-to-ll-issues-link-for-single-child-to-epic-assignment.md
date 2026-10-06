---
id: ENH-3749
type: ENH
title: Add a parent-assignment option to ll-issues link for single child-to-EPIC assignment
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T23:41:53Z'
verify_verdict: VALID
labels:
- issues
- link-epics
relates_to:
- BUG-3738
- BUG-3739
decision_needed: false
confidence_score: 95
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-3749: Add a parent-assignment option to ll-issues link for single child-to-EPIC assignment

## Summary

Add `ll-issues link CHILD --parent EPIC [--reparent]` to assign an existing BUG, FEAT, or ENH to a chosen EPIC. Set the child's `parent:` and synchronize `epic:` only if that key already exists; add its title/status bullet to the EPIC's exact `## Children` section. This supplies the explicit alternative-selection and children-listed-drift remedy missing from `link-epics`.

## Current Behavior

Verified on branch `main` on 2026-10-05:

- `link.py` exposes only the list fields in `_FIELD_FLAGS`: `blocked_by`, `depends_on`, and `relates_to`. `cmd_link` selects one with `next(...)`; it cannot accept a scalar relationship by adding another parser flag alone.
- `create --parent` wires both sides only when creating an issue and writes `parent:` alone. `link_epics.apply_assignment` writes both `parent:` and `epic:` unconditionally.
- BUG-3738 is done. Its preserving scalar upsert, Children recognizer, and locked per-pair apply helper are already available. `link-epics --apply` chooses one highest-ranked EPIC per orphan; selecting another EPIC still requires manual edits.
- BUG-3739 identifies category-(b) drift (body listing with no child back-reference). `epic-consistency --fix` repairs only category-(a) drift; users must explicitly choose whether to assign a body-listed child.
- `apply_assignment` locks and computes the pair before writing, then writes child first and EPIC second. Each write is atomic individually; the pair is not a filesystem transaction. Its second-write error names `ll-issues epic-consistency --fix EPIC`.

## Expected Behavior

- `--parent EPIC` is mutually exclusive with the three list-edge options. `--reparent` is valid only with `--parent`; reject `--parent` with `--unlink`/`--remove`, `--force`, or `--reciprocal` before any write. Parent unlink and stale-bullet deletion are deferred explicitly.
- Resolve both inputs using the existing resolver, then use the resolved files' canonical identities. Numeric and stale-prefix shorthand work; user-typed prefixes do not establish type. Target must be EPIC, child BUG/FEAT/ENH. Reject inconsistent filename/frontmatter identity or type, malformed relationship values, and unsafe frontmatter with no writes. Parenting keys stranded after the closing fence must be repaired first, not silently shadowed by a new in-fence assignment.
- Always upsert `parent:`. Synchronize `epic:` when the key exists, including an explicit null; do not add it when absent. Check both existing non-null keys for conflicts. Without `--reparent`, either key pointing elsewhere rejects the pair, including disagreement between the two keys. With `--reparent`, synchronize the applicable keys and report every distinct displaced relationship.
- A same-parent rerun still repairs a missing Children bullet. Once both sides agree, neither file is written. A body-listed child without a back-reference requires only a child write. For a newly inserted bullet, use the child's validated current status, including done/deferred/blocked; do not label every existing issue `(open)`. Already recognized bullets retain their existing title/status text. Preserve unrelated bytes, CRLF/LF, and file modes.
- Missing exact `## Children` is exit 0 with an explicit `missing_heading` body outcome, even on an otherwise unchanged pair; ambiguous sections reject before either write.
- Reparenting adds the new listing and reports possible stale listings for displaced parents; it does not delete old bullets or imply the old EPIC is clean. A missing/unresolvable old parent is reported without preventing the explicitly requested reassignment. An explicit `--parent` is allowed for an intentionally parentless child; preserve unrelated `parentless_reason` metadata and report the opt-out override as a warning.
- `--dry-run` takes the same lock, rereads, validates, and computes the same changes as apply, but performs zero writes. Errors are errors in preview too.
- `--json` emits one structured document for success, rejection, or partial failure; diagnostics never add a second stdout document. Exit 1 on rejection/write failure. A failed child write leaves the EPIC untouched; a failed EPIC write may leave the child assigned and must identify that partial state and its repair command.

## Motivation

The chosen-EPIC operation closes two concrete manual-edit gaps and lets users resolve category-(b) drift deliberately. Sharing preserving transforms prevents a new CLI path from reintroducing YAML churn or incorrect Children placement.

## Proposed Solution

Extract the locked pair preparation/write logic from `apply_assignment` into a small shared core and add a non-printing `apply_parent_link` plus a thin CLI reporter. The core takes an explicit policy for adding `epic:` and for accepting conflicting relationships; it acquires the issue-tree lock exactly once. Resolve paths, then reread and validate authoritative file data under that lock before computing either output. Read with `newline=""`; write changed files only through `atomic_write(..., shared_mode=True)`, child first.

Reuse `upsert_frontmatter_scalars`, `_append_child_to_epic_children`, `find_children_section`, and `iter_child_entries`. Add an optional keyword-only child-status argument to the Children append helper, defaulting to `open` for existing callers; only the new parent path supplies the locked child's actual status. Do not extend `apply_link`'s list-field tuple or reuse its full-mapping YAML dump. Keep the existing `apply_assignment` signature, module-global dispatch, unconditional `epic:` behavior, boolean heading result, and error messages as a compatibility wrapper. Sharing the core is not a migration of the other writers' field policies.

Map `ConflictingParent`, `AmbiguousChildrenSection`, unsafe metadata, lock timeout, and write failure to stable reason codes. Keep the two specialized `ValueError` catches before generic `ValueError`. For a failed second write, recommend re-running the same parent command (which also handles reparenting safely) or `ll-issues epic-consistency --fix EPIC` for the new EPIC. Explain separately that stale old-parent bullets still need review.

## Program Design

### Types

New `ParentLinkResult` dataclass, separate from the list-only `LinkResult`: canonical `issue_id`/`target_id`, `status` (`assigned`, `would_assign`, `unchanged`, `rejected`, `partial_failure`), `reason`, `child_would_change`, `epic_would_change`, `child_written`, `epic_written`, `epic_body_status` (`updated`, `already_present`, `missing_heading`), `previous_parents`, and `warnings`. Partial-write errors must carry the actual written-file state to the CLI; predicted changes must not be reported as committed writes. Keep JSON as one flat result object (lists for displaced parents/warnings are allowed).

Existing `LinkResult`, `EpicProposal`, `ConflictingParent`, and `AmbiguousChildrenSection` retain their public contracts.

### Signatures

Proposed new API:

- `apply_parent_link(config: BRConfig, *, issue_id: str, target: str, reparent: bool = False, dry_run: bool = False) -> ParentLinkResult`

```python
def apply_parent_link(
    config: BRConfig,
    *,
    issue_id: str,
    target: str,
    reparent: bool = False,
    dry_run: bool = False,
) -> ParentLinkResult: ...
```

Expected validation exceptions are rendered as rejection results by the CLI; write errors include per-file state. The shared internal core may return the same plan/result type but must not print.

### Call Path

`main_issues` -> `cmd_link` (parent branch before list-field selection) -> `apply_parent_link` -> shared locked pair core -> preserving transforms -> changed-file writes. `cmd_link_epics` -> existing `apply_assignment` wrapper -> the same core with its original field policy. The existing `cmd_link` -> `apply_link` path stays list-only.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/issues/link.py` — parser, parent routing, result/reporting, compatible attribute reads with `getattr`.
- `scripts/little_loops/cli/issues/link_epics.py` — extract/share pair core while retaining `apply_assignment` and `ConflictingParent` patch/import points. Keep lazy file-utils imports so existing tests can intercept locking/writes. Avoid import cycles; import the shared path lazily from `link.py` if it remains here.
- `scripts/little_loops/cli/issues/create.py` — backward-compatible optional Children-bullet status argument; default/outcome/ambiguity behavior stays intact.
- `scripts/little_loops/cli/issues/__init__.py` — update the link epilog wording; dispatch does not change.
- `scripts/little_loops/cli/issues/epic_consistency.py` — add the explicit category-(b) remedy hint, keeping existing `(b)`/`no parent`/`backref` text assertions.

### Dependent Files and Similar Patterns

- `scripts/little_loops/cli/issues/scaffold_epic.py` and create-parent wiring consume the same Children helper; existing call shapes/default status and outcome/ambiguity contracts stay unchanged.
- `scripts/little_loops/frontmatter.py` and `file_utils.py` provide preserving scalars, locks, and writes.
- `scripts/little_loops/cli/issues/format_check.py` builds list-only Namespaces; new parent attributes must tolerate absence.
- `scripts/little_loops/mcp_server/tools.py` calls `apply_link` directly and recognizes list-only statuses; no parent MCP expansion in this issue.
- `scripts/little_loops/issues/cli_surface.py` discovers flags from help automatically; no separate registry to change.

### Behavior Parity

| Artifact | Preserved | Changed | Dropped |
|---|---|---|---|
| `link.py` | List-edge flags, `LinkResult`, MCP caller behavior, list reporting | Add independent scalar-parent branch and reporter | None |
| `link_epics.py` | Signature, patch points, both-key write policy, one-winner behavior, failure messages | Delegate pair implementation to shared core | None |
| `create.py` | Existing append call shapes, default open status, placement/ambiguity outcomes | Optional explicit child status for the new parent caller | None |
| `epic_consistency.py` | Category-(a) fixes and category-(b) human choice | Add assignment remedy hint | None |

### Tests

- `scripts/tests/test_link_cli.py` — category-aware fixtures; fresh assignment with correct open/done/deferred/blocked bullet status, null/absent/present `epic:`, both-key conflicts, inconsistent metadata/type, explicit reparent, missing old parent, intentional-parentless override/post-fence metadata refusal, same-parent missing-bullet repair, body-listed-only remedy, no-write rerun, missing/ambiguous headings, canonical shorthand, rejected flag combinations, dry-run parity, CRLF/modes, lock timeout, first/second write failure, and single-document JSON on each outcome. Check bytes and write calls, not only mtimes.
- `scripts/tests/test_link_epics_cli.py` — retain `TestApplyAssignment` / `TestApplyAssignmentHardening` and module-global racing interception; wrapper behavior must stay unchanged.
- `scripts/tests/test_cli_surface.py` — replace the real-parser negative `--parent` assertion with another nonexistent flag and assert the new positive surface. The synthetic `--parent` fixtures in `test_feat3048_symbol_cli_claim_gaps.py` are independent and need no re-pointing.
- Regression suites: `test_ll_issues_format_check.py::TestFormatCheckFix`, `test_bug3150_issue_mutator_atomicity.py` (one lock), `test_feat_3149_mcp_mutation_tools.py`, `test_epic_consistency.py`, `test_ll_issues_create.py`, and `test_link_epics_skill.py`.

### Documentation

- `docs/reference/CLI.md` — `link`, `link-epics`, and `epic-consistency`: exact flags, field policy, unsupported combinations, previews, partial failure, and stale old-parent listings.
- `skills/link-epics/SKILL.md` — A2 alternative selection, A3 reject/repair guidance, and S4 child write-back use the new command. Retain existing tested vocabulary.
- `docs/reference/COMMANDS.md` — update the `/ll:link-epics` guidance; no new slash-command entry is required.
- `docs/reference/API.md` — new parent API/shared behavior; existing wrapper contract remains documented.
- Run host-artifact and docs-audience gates; regenerate applicable mirrors only if stale. User-facing docs/skills must not gain internal test/source path citations.

### Configuration

No new configuration or dependency.

## Implementation Steps

1. Add the CLI/core tests for the settled flags, field policy, dry-run validation, and partial failure reporting.
2. Extract the existing locked pair core, preserving the `apply_assignment` compatibility wrapper and its regressions.
3. Add `apply_parent_link`, canonical file validation, explicit reparent handling, and CLI output/error mapping.
4. Update remedy hints, skill guidance, and reference docs; run focused suites, artifact/doc gates, then `python -m pytest scripts/tests/`.

## Acceptance Criteria

- [ ] `ll-issues link CHILD --parent EPIC [--reparent]` assigns both sides with preserving writers, exact canonical identities and accurate new-bullet status; present/null `epic:` is synchronized, absent `epic:` stays absent.
- [ ] Idempotent reruns perform no writes; same-parent missing bullets are repaired; category-(b) drift writes only the child when already listed.
- [ ] Both-key conflicts, invalid types/metadata, ambiguity, timeout, and unsupported flags reject before writes, including in dry-run. Reparent reports every displaced relationship and preserves old bullets.
- [ ] Missing heading is an explicit successful skip; second-write failure exits nonzero, truthfully reports the partial state, and provides a valid repair/reapply command.
- [ ] JSON success/error output parses as exactly one document; existing list/MCP and `apply_assignment` behavior remains compatible.
- [ ] Help, skill guidance, and docs specify the command, flags, partial-write boundary, and remedies; focused gates and `python -m pytest scripts/tests/` pass.

## Scope Boundaries

Single child-to-EPIC assignment only. No parent unlink, automatic old-bullet deletion, batch assignment, sub-EPIC assignment, MCP parent field, category-(b) automatic inference, or cross-file transaction/rollback guarantee. Existing list-edge overrides remain unchanged.

## Impact

- **Priority**: P3 — closes concrete manual-edit gaps now that BUG-3738 has landed.
- **Effort**: Medium — shared-core extraction plus precise preview/error reporting and compatibility tests.
- **Risk**: Medium — two-file partial writes and shared patch points need coverage; no breaking change to existing list-edge callers.
- **Breaking Change**: No; additive CLI capability with explicit unsupported combinations.

## Review Notes

Reviewed on `main`, 2026-10-05, with `/ll:advise` using `claude-opus-5-5`. Settled `--parent`/`--reparent`, the existing-key `epic:` policy, unlink deferral, and partial-write reporting; removed the resolved BUG-3738 blocker. Previous confidence scores (95 readiness / 71 outcome) described the prior contract and are archived here rather than reused as a fresh assessment. Re-score the revised contract at the implementation gate.

## Status

**Open** | Created: 2026-10-05 | Priority: P3

## Session Log
- `/ll:confidence-check` - 2026-10-06T01:46:32 - `2fc077e6-f247-45dc-97b8-6729a8243496.jsonl`
- `/ll:confidence-check` - 2026-10-06T01:09:31 - `c373be39-3ae5-465c-90da-c98a8ab828e9.jsonl`
- `/ll:verify-issues` - 2026-10-06T01:07:52 - `6493c397-fb81-474b-97a7-2295ce48765a.jsonl`
- `/ll:verify-issues` - 2026-10-06T01:06:23 - `10ca63b5-4074-4b4f-9add-57902bcfae70.jsonl`
- `/ll:verify-issues` - 2026-10-06T01:05:15 - `8500a46e-f51f-4ec8-9d17-7e9f56e7470e.jsonl`
- `/ll:wire-issue` - 2026-10-06T01:03:02 - `958cdfd3-c0a0-44ad-9b42-f2955c8e4922.jsonl`
- `/ll:refine-issue` - 2026-10-06T00:55:53 - `03a6fd69-1d12-493d-b61f-d9a48062a4d3.jsonl`
- `/ll:capture-issue` - 2026-10-05T23:43:06 - `dfedb32a-de04-4382-86b8-3c6cab5d9da5.jsonl`
