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
blocked_by:
- BUG-3738
relates_to:
- BUG-3739
confidence_score: 95
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/__init__.py` — update the `link` subcommand wording in two places: the epilog line `link   Write or remove a dependency edge in issue frontmatter` and the `help=` string in `add_link_parser`; both describe only dependency edges. Dispatch (`if args.command == "link": return cmd_link(...)`) needs no change [Agent 2 finding]
- `scripts/little_loops/cli/issues/link.py` — `cmd_link` line `field = next(name for name in _FIELD_FLAGS if getattr(args, name, None))` raises `StopIteration` when only the new option is set; the parent branch must be tested *before* it, and must read the new attributes via `getattr(args, ..., None/False)` [Agent 2 finding]
- `scripts/little_loops/cli/issues/epic_consistency.py` — optional: `cmd_epic_consistency` text branch prints `(b) Body-listed, no parent: backref (human decision needed):` with no remedy hint; add a one-line pointer to the new command. Must keep the substrings `body`/`(b)`/`no parent`/`backref` that `test_epic_consistency.py` asserts. The `--fix` help (`category-(a) drift`) and `fix_epic` docstring stay correct as-is [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/create.py` — source of `_append_child_to_epic_children` (consumed, not changed).
- `scripts/little_loops/frontmatter.py` — BUG-3738's scalar upsert (consumed).
- `scripts/little_loops/cli/issues/epic_consistency.py` — shared Children recognizer (consumed).
- `scripts/little_loops/file_utils.py` — `acquire_lock`, `issue_lock_path`, `atomic_write` (consumed).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/scaffold_epic.py` — `scaffold_epic` also calls `_append_child_to_epic_children` (graph-confirmed, `ll-code callers-of`); a third consumer, so the helper's three-outcome contract must not change [Agent 1 + graph finding]
- `scripts/little_loops/cli/issues/link_epics.py` — `cmd_link_epics` `--apply` branch is the only production caller of `apply_assignment`; its catch order (`ConflictingParent`, `AmbiguousChildrenSection`, `ValueError`, `TimeoutError`, `OSError`) is load-bearing because the first two subclass `ValueError`. `ConflictingParent` lives here and `link_epics.py` imports nothing from `link.py`, so `link.py` must import it lazily (or move it to a shared module) to avoid a cycle [Agent 2 finding]
- `scripts/little_loops/cli/issues/format_check.py` — `_fix_prose_deps` builds an `argparse.Namespace` with only list-edge attributes plus `json_output`/`dry_run` and calls `cmd_link`; regression surface for `getattr` tolerance (already noted above, now with the exact test: `test_ll_issues_format_check.py::TestFormatCheckFix`) [Agent 3 finding]
- `scripts/little_loops/issues/cli_surface.py` — subprocess-scrapes `ll-issues link --help` and parses option-definition lines (used by `format_check`'s `stale_cli_flag` check); the new option is picked up automatically, no registry to update [Agent 2 finding]
- `scripts/little_loops/mcp_server/tools.py` — `_tool_issue_link` treats any status outside `linked|would_link|unlinked|would_unlink` as `unchanged`; keep `_FIELD_FLAGS` list-only so a parent status can never reach it [Agent 2 finding]
- `commands/refine-issue.md` — cites `link.py` line numbers and `apply_link` internals (`_check_cycle()`, `unchanged`-on-duplicate); edits to `link.py` can stale those citations, though `test_refine_issue_command.py` only asserts `"ll-issues link"`/`"blocked_by"` substrings [Agent 1 finding]

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_surface.py::test_build_cli_surface_index_against_real_ll_issues_link` (line 170) — the **only** test coupled to the real parser: asserts `cli_surface_accepts(idx, "ll-issues", "link", "--parent") is False`. It breaks iff the new flag is spelled `--parent`; re-point it at another nonexistent flag in that case [Agent 3 finding; verified]
- `scripts/tests/test_feat3048_symbol_cli_claim_gaps.py::test_stale_cli_flag_gap_populated_feat_2942_regression` (line 174), `test_check_format_gaps_spawns_no_subprocess` — **will not break**: they use the synthetic `cli_index` fixture (`surface={"ll-issues": {"link": {"--blocked-by","--depends-on","--relates-to"}}}`, line 138). This corrects the Codebase Research Findings note above, which lists them as needing re-pointing. `test_cli_claims.py` and `test_symbol_claims.py` are likewise parse-only/synthetic [Agent 2 + 3 finding; verified]
- `scripts/tests/test_link_cli.py` — new class (e.g. `TestIssuesCLILinkParent`); `_write_issue` hardcodes `features/`, so add a category-aware helper (model: `test_link_epics_cli.py::_write_issue(issues_dir, category, filename, content)`; the shared `issues_dir` fixture in `scripts/tests/conftest.py` already creates `bugs/`, `features/`, `epics/`). Additional cases beyond the list above: CRLF + file-mode preservation (model `TestApplyAssignmentHardening::test_crlf_and_mode_preserved`), single lock acquisition (model `test_bug3150_issue_mutator_atomicity.py::TestLockIsTaken::test_link_holds_a_single_lock_across_source_and_reciprocal`), second-write `OSError` naming `epic-consistency --fix <EPIC>` (model `test_second_write_failure_names_remedy_and_direct_reapply_repairs`), bare-numeric/non-canonical-prefix target resolving by the file's own type (model `test_link_bare_numeric_id_resolves`), and a `Namespace` without parent attributes still reaching the list-edge path [Agent 3 finding]
- `scripts/tests/test_link_cli.py::TestIssuesCLILink::test_link_json_output` (line 210) — asserts only the return code; optionally tighten to `json.loads(out)` single-document parse (pattern: `capsys.readouterr().out` + `json.loads`, as in `test_link_epics_cli.py::TestApplyOneWinnerAndRejections`) [Agent 3 finding]
- `scripts/tests/test_ll_issues_format_check.py::TestFormatCheckFix` — `test_fix_without_apply_previews_and_does_not_write` asserts `"would link (dry-run)" in out`; regression only, keeps `_report`'s list-edge verb text stable [Agent 3 finding]
- `scripts/tests/test_link_epics_cli.py::TestApplyAssignment` / `TestApplyAssignmentHardening` (~lines 153-327) and the `racing` wrapper (`patch("little_loops.cli.issues.link_epics.apply_assignment", racing)`) — if the core is extracted: keep `apply_assignment(proposal, *, orphan_path, epic_path, ...)` as a module-level name in `link_epics.py` called through the module global; keep the **lazy** `acquire_lock`/`atomic_write` imports inside the function body (tests patch `little_loops.file_utils.acquire_lock`/`atomic_write`, which only take effect for lazy imports); keep `ConflictingParent` defined in `link_epics.py` and the `parent: EPIC-2` / `epic-consistency --fix EPIC-1` message substrings byte-compatible [Agent 2 + 3 finding]
- `scripts/tests/test_epic_consistency.py::TestEpicConsistencyCategoryB` (line 224) and `TestFindChildrenSection` / `TestIterChildEntries` — reusable fixtures for the category-(b) remedy test; also pin the `(b)`/`no parent`/`backref` substrings if a hint is added to `cmd_epic_consistency` [Agent 3 finding]
- `scripts/tests/test_ll_issues_create.py::TestAppendChildToEpicChildren` (`_children_helper`) — model for the none / unchanged / new-text / `AmbiguousChildrenSection` outcomes; `TestParentWiringLockAndAmbiguity::test_parent_append_waits_for_mutation_lock` is the real-lock timeout model for a CLI-level test [Agent 3 finding]
- `scripts/tests/test_link_epics_skill.py::TestLinkEpicsSkillExists` — substring checks; the rewritten wording must keep `ll-issues link-epics`, `--mode assign`, `--mode synthesize`, `## Children`, `parent:`, `--apply`, `--threshold`, `ll-issues clusters` and must not introduce `--min-score`, `--min-cluster`, `Jaccard`, `union-find`, `intersection`, `create-epics-from-unparented` [Agent 2 finding]

### Documentation
- `docs/reference/CLI.md` (the `ll-issues link` section) and `docs/reference/COMMANDS.md`.
- `skills/link-epics/SKILL.md`: replace BUG-3738's "a different EPIC requires a manual edit" wording with this command, and point children-listed drift reports at it as the remedy. Regenerate host mirrors with `ll-adapt`.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` `#### ll-issues link <issue_id>` — lede says "frontmatter-key writer ... dependency edge" and the flag table says `--blocked-by` is "mutually exclusive with the two below"; both need the new option, a parent example in Examples, and "list edges only" qualifiers on `--force`/`--reciprocal` [Agent 2 finding]
- `docs/reference/CLI.md` `#### ll-issues link-epics` — the `--apply` row ("lower-ranked alternatives stay in `proposals` but are not written") and the "A rejected pair does not fall through to a lower-ranked EPIC" paragraph are the natural places to point at the new command [Agent 2 finding]
- `docs/reference/CLI.md` `#### ll-issues epic-consistency` — covers category-(a) only; add the category-(b) remedy pointer [Agent 2 finding]
- `docs/reference/API.md` `### apply_assignment` (~line 1630 parameter table; also the "calling `apply_assignment()` again directly also repairs it" sentence) — update only if the core is extracted or the signature changes [Agent 2 finding]
- `skills/link-epics/SKILL.md` — three sites, not one: `### A2: Proposal Flow` (line 86, "need a manual edit of the orphan's `parent:`/`epic:`…"), `### A3: Apply Assignments` (`write_failed` / `epic-consistency --fix <EPIC>` guidance), and `### S4: Create Accepted EPICs and Write-Back` step 4 (line 237, "insert `parent:`/`epic:` into each child's frontmatter block directly (same fields `apply_assignment()` writes)" — a hand-edit that the new command could replace). `allowed-tools: Bash(ll-issues:*, git:*)` already covers it [Agent 2 finding; verified lines 86, 237]
- `docs/reference/COMMANDS.md` — only `### /ll:link-epics` (~line 460) exists; no `ll-issues link` entry, so adding one is a new-content decision (confirmed) [Agent 2 finding]
- Host mirrors: no tracked `.gemini/.qwen/.kimi-code` mirror of `link-epics` exists, and `skills/link-epics/agents/openai.yaml` carries only `display_name`/`short_description`, so a SKILL.md body edit is unlikely to trip `test_host_artifacts_are_not_stale`; still run it to confirm before spending effort on `ll-adapt` [Agent 2 finding]
- Doc-audience gate: new prose in `docs/reference/` and `skills/` must not cite `scripts/tests/` or `scripts/little_loops/` paths (`test_docs_audience_gate.py`) [Agent 2 finding]

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
- **Flag spelling collision (test-enforced):** `--parent` is *not* a valid `ll-issues link` flag today, and two tests use exactly that as the stale-flag regression example: `scripts/tests/test_cli_surface.py` (`test_build_cli_surface_index_against_real_ll_issues_link` asserts `cli_surface_accepts(idx, "ll-issues", "link", "--parent") is False`) and `scripts/tests/test_feat3048_symbol_cli_claim_gaps.py` (`test_stale_cli_flag_gap_populated_feat_2942_regression`, which feeds that same `link`-plus-`--parent` example into issue text and expects a `stale_cli_flag` gap). Only `test_cli_surface.py` queries the real parser, so choosing `--parent` for the new option requires re-pointing that one fixture at a different nonexistent flag; the `test_feat3048_symbol_cli_claim_gaps.py` stale-flag test feeds a synthetic `cli_index` fixture and needs no change (see the wiring note under Tests). Choosing another spelling avoids the re-pointing entirely. Either way the choice is deliberate. `--parent` already means "EPIC ID" on `create` and "ancestor filter" on `list`; `--force` already means "skip target-existence validation" on `link`; `--reciprocal` is declared on `link` but out of scope here; `--re` is already ambiguous among `--remove`/`--reciprocal`/`--relates-to` (no `allow_abbrev` set), and no `--reparent`/`--move-parent`/`--set-parent` exists anywhere.
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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/cli/issues/link.py` `cmd_link` — route the parent option before the `next(name for name in _FIELD_FLAGS ...)` line, read new attributes with `getattr(..., None/False)`, add `parent`-path statuses to `_report`'s verb dict (or give the path its own reporter), and catch `TimeoutError`/`OSError` (not just `ValueError`) with `ConflictingParent`/`AmbiguousChildrenSection` ordered first
- Update `scripts/little_loops/cli/issues/__init__.py` — change the `link` epilog line and `add_link_parser` `help=` text so they no longer say "dependency edge" only
- If extracting the core from `apply_assignment`: keep it a module-level name in `link_epics.py`, keep lazy `acquire_lock`/`atomic_write` imports and `ConflictingParent` in `link_epics.py` (import it lazily from `link.py`); parameterize the `epic:` key policy
- Update `scripts/tests/test_cli_surface.py` line 170 only if the flag is spelled `--parent` (re-point at another nonexistent flag); otherwise leave all `--parent` fixtures alone
- Add `TestIssuesCLILinkParent` to `scripts/tests/test_link_cli.py` with a category-aware EPIC fixture helper, covering the Tests-section additions above
- Update `docs/reference/CLI.md` (`link`, `link-epics`, `epic-consistency` sections) and `skills/link-epics/SKILL.md` (A2, A3, S4); optionally add the category-(b) remedy hint to `epic_consistency.cmd_epic_consistency` text output, keeping its asserted substrings
- Run `test_link_epics_skill.py`, `test_wiring_skills_and_commands.py::test_host_artifacts_are_not_stale`, `test_docs_audience_gate.py`, `test_ll_issues_format_check.py::TestFormatCheckFix`, `test_bug3150_issue_mutator_atomicity.py`, and `test_feat_3149_mcp_mutation_tools.py` as regression surfaces

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

## Verification Notes

Verdict at time of check: **CLAIMS_OUTDATED** (correction below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- Codebase Research Findings, flag-spelling bullet claimed that both the real-parser surface test and the feat3048 stale-flag test would need re-pointing if the new option is spelled like the existing `create` option. Only the real-parser surface test does; the feat3048 test uses a synthetic index fixture. Bullet rewritten in place to match the wiring note under Tests.

## Status

**Open** | Created: 2026-10-05 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-06_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Concerns
- `epic:` key policy is unreconciled: `apply_assignment` writes `epic:` unconditionally, this issue says "when that key is present", and `create --parent` writes `parent:` only. Pick one before extracting the shared core.
- Flag spellings (the parent option and the reparent switch) are left to the implementer; `--parent` would force re-pointing `test_cli_surface.py:170`.

### Outcome Risk Factors
- Moderate per-site complexity: extracting `apply_assignment`'s core touches shared state (lock, two-file ordered writes, error taxonomy) and must keep `test_link_epics_cli.py` patch points (lazy `acquire_lock`/`atomic_write` imports, `ConflictingParent` location) byte-compatible.
- Broad enumeration across ~8-10 sites (link.py, link_epics.py, `__init__.py`, optional epic_consistency.py hint, CLI.md, link-epics SKILL.md, tests) with several regression surfaces (MCP `_tool_issue_link`, `format_check._fix_prose_deps`).
- Minor open design points (epic: key policy, flag spellings, whether `--unlink` ships) can be resolved during implementation but may cause one iteration.

## Session Log
- `/ll:confidence-check` - 2026-10-06T01:09:31 - `c373be39-3ae5-465c-90da-c98a8ab828e9.jsonl`
- `/ll:verify-issues` - 2026-10-06T01:07:52 - `6493c397-fb81-474b-97a7-2295ce48765a.jsonl`
- `/ll:verify-issues` - 2026-10-06T01:06:23 - `10ca63b5-4074-4b4f-9add-57902bcfae70.jsonl`
- `/ll:verify-issues` - 2026-10-06T01:05:15 - `8500a46e-f51f-4ec8-9d17-7e9f56e7470e.jsonl`
- `/ll:wire-issue` - 2026-10-06T01:03:02 - `958cdfd3-c0a0-44ad-9b42-f2955c8e4922.jsonl`
- `/ll:refine-issue` - 2026-10-06T00:55:53 - `03a6fd69-1d12-493d-b61f-d9a48062a4d3.jsonl`
- `/ll:capture-issue` - 2026-10-05T23:43:06 - `dfedb32a-de04-4382-86b8-3c6cab5d9da5.jsonl`
