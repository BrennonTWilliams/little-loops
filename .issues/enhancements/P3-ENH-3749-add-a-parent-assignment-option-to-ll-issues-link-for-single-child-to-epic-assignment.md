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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-06 — based on codebase analysis:_

- **BUG-3738 has landed (`status: done`)**; its pieces are in the tree, so `blocked_by: BUG-3738` is already resolved. Existing: `apply_assignment` (`scripts/little_loops/cli/issues/link_epics.py`), `upsert_frontmatter_scalars` (`scripts/little_loops/frontmatter.py`), the three-outcome `_append_child_to_epic_children` and `AmbiguousChildrenSection` (`scripts/little_loops/cli/issues/create.py`), and `find_children_section` / `iter_child_entries` (`scripts/little_loops/cli/issues/epic_consistency.py`). `ll-issues link` itself has no parent option: `_FIELD_FLAGS` and the mutually exclusive group in `add_link_parser` hold only `blocked_by`/`depends_on`/`relates_to`.
- **`apply_assignment` today** is `apply_assignment(proposal: EpicProposal, *, orphan_path: Path, epic_path: Path, child_title: str | None = None, base_dir: str = ".issues") -> bool`. It reads only `proposal.orphan_id` / `proposal.epic_id`; it does **not** validate that the target is an EPIC or that the child is BUG/FEAT/ENH (that filtering lives upstream in `is_orphan()` and the `epics` selection in `cmd_link_epics`). It returns `appended is not None`, so `False` means "no `## Children` heading, EPIC body not written". Raises `ConflictingParent`, `AmbiguousChildrenSection`, `ValueError` (unsafe frontmatter), `TimeoutError`, `OSError`.
- **`epic:` semantics differ from this issue's wording.** `apply_assignment` writes `{"parent": epic_id, "epic": epic_id}` unconditionally (adds `epic:` when absent); Expected Behavior says "`epic` when that key is present". The conflict rule likewise checks both keys. The two must be reconciled knowingly: either the new path reuses the unconditional write, or the shared core takes the key set as a parameter. `compute_drift` in `epic_consistency.py` matches on `IssueInfo.parent` only, and `create --parent` writes `parent:` only (no `epic:`), so three writers already disagree on whether `epic:` is written.
- **Reciprocal/`create --parent` has no EPIC-type check** on its parent and silently skips wiring if the parent does not resolve; the validation this issue requires (EPIC target, BUG/FEAT/ENH child, EPIC child rejected) is new logic with no existing helper. Type is derived from the ID prefix (`startswith("EPIC-")`, `is_orphan` / `_ORPHAN_TYPE_PREFIXES`) or the `type:` frontmatter key; `resolve_issue_path` (`issue_parser.py`, wrapped by `_resolve_issue_id` in `cli/issues/show.py`) treats the type prefix as advisory, so validation must read the resolved file's own ID/type, not the user-typed prefix.

_Added by `/ll:refine-issue` — 2026-10-06 — based on codebase analysis:_

- **Additional callers constrain the `link` surface** (all consume `cmd_link`/`apply_link`/`_FIELD_FLAGS`): `scripts/little_loops/cli/issues/__init__.py` (`main_issues` dispatch, `add_link_parser`; subcommand help text ~line 177), `scripts/little_loops/cli/issues/format_check.py` (`_fix_prose_deps` builds an `argparse.Namespace` with only the list-edge attributes and calls `cmd_link` — any attribute `cmd_link` reads for the new option must tolerate absence, as `blocked_by`/`depends_on`/`relates_to` do via `getattr(args, name, None)`), and `scripts/little_loops/mcp_server/tools.py` (`_tool_issue_link` calls `apply_link` directly and branches on list-shaped `LinkResult.status`; it must keep working unchanged, and MCP code must never call `cmd_*` because stdout is the JSON-RPC frame).
- **Error-handling gap to close:** `cmd_link` catches only `ValueError` (prints `Error: …`, exit 1). `TimeoutError` from `acquire_lock` and `OSError` from `atomic_write` propagate uncaught today, yet the Acceptance Criteria require a lock timeout to be rejected cleanly with no writes. `link-epics --apply` already maps every failure class to a `rejected` reason (`conflicting_parent`, `ambiguous_children_section`, `metadata_unsafe`, `lock_timeout`, `write_failed`); the catch order matters because the first two are `ValueError` subclasses.
- **Flag spelling collision (test-enforced):** `--parent` is *not* a valid `ll-issues link` flag today, and two tests use exactly that as the stale-flag regression example: `scripts/tests/test_cli_surface.py` (`test_build_cli_surface_index_against_real_ll_issues_link` asserts `cli_surface_accepts(idx, "ll-issues", "link", "--parent") is False`) and `scripts/tests/test_feat3048_symbol_cli_claim_gaps.py` (`test_stale_cli_flag_gap_populated_feat_2942_regression`, which feeds that same `link`-plus-`--parent` example into issue text and expects a `stale_cli_flag` gap). Choosing `--parent` for the new option requires re-pointing those fixtures at a different nonexistent flag; choosing another spelling avoids it. Either way the choice is deliberate. `--parent` already means "EPIC ID" on `create` and "ancestor filter" on `list`; `--force` already means "skip target-existence validation" on `link`; `--reciprocal` is declared on `link` but out of scope here; `--re` is already ambiguous among `--remove`/`--reciprocal`/`--relates-to` (no `allow_abbrev` set), and no `--reparent`/`--move-parent`/`--set-parent` exists anywhere.
- `_write_reciprocal` and `apply_link` use `update_frontmatter` (full re-dump) and plain `atomic_write` (no `shared_mode`, `read_text()` not `newline=""`); the parent path must instead follow the preserving contract that `apply_assignment` holds (CRLF, mode, unrelated bytes unchanged), so it cannot be built by extending `apply_link`'s body.

_Added by `/ll:refine-issue` — 2026-10-06 — based on codebase analysis:_

- **Conventions in force:**
  - Subcommand logic is a non-printing core returning a result dataclass plus a thin `cmd_*` shell that prints and returns the exit code (`apply_link`/`cmd_link`, `link_epics.apply_assignment`/`cmd_link_epics`); `--json` emits exactly one document via `print_json`. Evidence: `link.py` `_report`, `link_epics.py` `cmd_link_epics`. The two commands disagree on the `--json` dest name (`json_output` on `link`, `json` on `link-epics`); the new option lives on `link`, so `json_output`.
  - Two-file writes: one `acquire_lock(issue_lock_path(path, base_dir))`, re-read both files inside it with `newline=""`, compute both texts, write only files whose text changed, child before EPIC, `atomic_write(..., shared_mode=True)`, and a failed second write re-raises naming `ll-issues epic-consistency --fix <EPIC>`. Evidence: `link_epics.py:apply_assignment`. `apply_link` holds one lock across source and reciprocal writes and never nests a second `acquire_lock` (flock contends within a single process; `test_bug3150_issue_mutator_atomicity.py::TestLockIsTaken` asserts a single acquisition).
  - Children placement/duplicate detection goes through `find_children_section` + `iter_child_entries`; `fix_epic` (`epic_consistency.py`) is the dissenting writer (appends `(added by epic-consistency --fix)` at section end, creates a section at EOF, no lock, no `shared_mode`) and is category-(a)-only; the new path follows `_append_child_to_epic_children`, which never creates a missing heading.
  - Bullet format written by the shared helper: `- **ID** — <title> (open)`, title whitespace-collapsed; the title fallback chain is `_fallback_title` (frontmatter title → H1 minus ID prefix → filename stem).

## Program Design

### Types
- `LinkResult(issue_id: str, field: str, target_id: str, status: str)` in `scripts/little_loops/cli/issues/link.py` — status vocabulary today is `unchanged | linked | unlinked | would_link | would_unlink`; `_report` indexes a verb dict by status, so any new status value a parent path returns must be added there or it raises `KeyError`. Whether the parent path reuses `LinkResult` (with `field="parent"`) or gets its own result type is open; `to_dict()` / the `--json` document must stay a single flat document.
- `EpicProposal` in `scripts/little_loops/cli/issues/link_epics.py` — carries `orphan_id`/`epic_id` (plus score/tier); `apply_assignment` consumes only the two IDs.
- `ConflictingParent(ValueError)` in `link_epics.py` and `AmbiguousChildrenSection(ValueError)` in `scripts/little_loops/cli/issues/create.py` — the error taxonomy the parent path must map to non-zero exits.

### Signatures
- `apply_link(config: BRConfig, *, issue_id: str, field: str, target: str, unlink: bool = False, reciprocal: bool = False, force: bool = False, dry_run: bool = False) -> LinkResult` — raises `ValueError` for a `field` outside `_FIELD_FLAGS`; the new scalar relationship does not belong in that tuple (MCP `_tool_issue_link` and `format_check._fix_prose_deps` both depend on its list-edge meaning).
- `cmd_link(config: BRConfig, args: argparse.Namespace) -> int` — exit 0 on success including `unchanged` and dry-run; exit 1 only via `ValueError`.
- `apply_assignment(proposal: EpicProposal, *, orphan_path: Path, epic_path: Path, child_title: str | None = None, base_dir: str = ".issues") -> bool` — returns `False` when the EPIC has no `## Children` heading.
- `upsert_frontmatter_scalars(content: str, updates: Mapping[str, str]) -> str` in `scripts/little_loops/frontmatter.py` — span-preserving; leaves a key untouched when its merged value already equals the request; raises `ValueError` on mixed line endings, duplicate keys, non-scalar values, unterminated blocks.
- `_append_child_to_epic_children(content: str, child_id: str, child_title: str) -> str | None` — `None` = no exact heading, same text back = already listed, otherwise new text; raises `AmbiguousChildrenSection`.
- `find_children_section(content: str) -> tuple[int, int] | None` and `iter_child_entries(section_text: str) -> list[ChildEntry]` in `scripts/little_loops/cli/issues/epic_consistency.py`.
- New (to be defined at implementation): an apply function for the parent relationship and its `add_link_parser` option wiring; the signature is the implementer's call, subject to the contract in Decision Rules.

### Call Path
`main_issues` -> `cmd_link` -> (existing) `apply_link` -> `atomic_write`; and (new) `main_issues` -> `cmd_link` -> parent-assignment apply -> `acquire_lock` -> `upsert_frontmatter_scalars` + `_append_child_to_epic_children` -> `atomic_write`. `cmd_link_epics` -> `apply_assignment` is the existing sibling of the new path and must keep its behavior and tests unchanged if its core is shared.

### Decision Rules
- **Target validation:** the resolved target's own ID/`type` must be EPIC, else exit 1 with no writes. The child must resolve to BUG/FEAT/ENH; an EPIC child is rejected (sub-EPICs use `relates_to` + prose). A target that does not resolve is an error (no `--force` bypass specified).
- **Conflict rule:** if the child's `parent` or `epic` is non-null and differs from the target EPIC ID, exit 1 with no writes unless the explicit reparent switch is given; same ID = idempotent, not a conflict. This mirrors `apply_assignment`'s `ConflictingParent` check.
- **Idempotency:** unchanged frontmatter and an already-listed child produce no write on either file and report `unchanged`. Already-listed child + missing back-reference (category-(b) drift) writes the child's frontmatter only.
- **Failure mapping:** `AmbiguousChildrenSection`, unsafe frontmatter, lock `TimeoutError`, and `OSError` each exit non-zero with no further writes; a second-write failure names `ll-issues epic-consistency --fix <EPIC>`. Missing `## Children` heading is **not** a failure: frontmatter is written, exit 0, and the output (text and `--json`) says the body write was skipped.
- **Reparent:** moves `parent`/`epic` and adds the bullet on the new EPIC; the old EPIC's stale bullet is reported, never removed.
- **Escape hatch:** the explicit reparent switch is the only override; `--force` keeps its existing meaning.

## Implementation Steps

1. After BUG-3738 lands, extract its per-pair apply core (lock, re-read, validate, compute both texts, ordered changed-file writes) into a reusable function, keeping `link-epics` behavior and tests unchanged.
2. Add the option to `ll-issues link`, with validation (EPIC target, BUG/FEAT/ENH child), conflict and reparent handling, and `--dry-run`/`--json` reporting.
3. Add the `test_link_cli.py` cases above, then update CLI.md, COMMANDS.md, the link-epics skill and its mirrors.
4. Run the focused suites, then `python -m pytest scripts/tests/`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-06 — based on codebase analysis:_

- **Test conventions:** class-based, inline issue text, "no writes" asserted by `read_bytes()`/`read_text()` equality or a patched `little_loops.file_utils.atomic_write` with `assert_not_called()` — not mtime. Lock-timeout is tested by patching `little_loops.file_utils.acquire_lock` with `side_effect=TimeoutError` (`test_link_epics_cli.py::TestApplyAssignmentHardening::test_lock_timeout_leaves_files_untouched`); second-write failure by wrapping `atomic_write` to raise `OSError` for the EPIC path. `test_link_cli.py::TestIssuesCLILink` drives `main_issues()` via patched `sys.argv` and has no lock-timeout test and no parsed-JSON assertion today (`test_link_json_output` only checks the return code), so the single-document `--json` criterion needs a test that actually parses the output. `_write_issue` there writes only under `features/`; EPIC fixtures need `epics/`.
- **Regression surfaces to keep green:** `test_link_epics_cli.py` (if the core is shared), `test_bug3150_issue_mutator_atomicity.py::TestLockIsTaken` (single lock acquisition per link), `test_feat_3149_mcp_mutation_tools.py` (`issue_link`, `not_a_field`), `test_cli_surface.py` and `test_feat3048_symbol_cli_claim_gaps.py` (the `--parent` stale-flag fixtures, see Integration Map), and `test_link_epics_skill.py` (substring checks on `skills/link-epics/SKILL.md`).
- **Docs sync surface:** `docs/reference/CLI.md` `ll-issues link` section (~lines 3189-3223, flag table + Examples; the `link-epics` section after it documents reason codes and `epic-consistency --fix`), `skills/link-epics/SKILL.md` (~lines 82-88 currently say a non-top EPIC "need[s] a manual edit"; A3 documents reject reasons), and `scripts/little_loops/cli/help.py` / `docs/reference/API.md` where link-epics is named. `docs/reference/COMMANDS.md` has no `ll-issues link` entry (only the `/ll:link-epics` skill), so adding an entry there is a new-content decision, not an update. Host mirrors are gated by `test_wiring_skills_and_commands.py::test_host_artifacts_are_not_stale` (regenerate with `ll-adapt --host <host> --apply`).
- **Stale ordering note:** Step 1 above is phrased "After BUG-3738 lands"; it has landed, so the shared per-pair core can be extracted from `apply_assignment` immediately (it currently takes an `EpicProposal` and a path pair, with no ID/type validation).

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
- `/ll:refine-issue` - 2026-10-06T00:55:53 - `03a6fd69-1d12-493d-b61f-d9a48062a4d3.jsonl`
- `/ll:capture-issue` - 2026-10-05T23:43:06 - `dfedb32a-de04-4382-86b8-3c6cab5d9da5.jsonl`
