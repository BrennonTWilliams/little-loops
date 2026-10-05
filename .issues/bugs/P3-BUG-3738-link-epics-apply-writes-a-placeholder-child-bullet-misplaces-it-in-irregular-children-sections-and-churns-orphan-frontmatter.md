---
id: BUG-3738
type: BUG
title: 'link-epics --apply writes a placeholder child bullet, misplaces it in irregular
  ## Children sections, and churns orphan frontmatter'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T18:53:54Z'
labels:
- issues
- link-epics
decision_needed: false
verify_verdict: VALID
---

# BUG-3738: link-epics --apply writes a placeholder child bullet, misplaces it in irregular ## Children sections, and churns orphan frontmatter

## Summary

`ll-issues link-epics --mode assign --apply` (`apply_assignment()` in `scripts/little_loops/cli/issues/link_epics.py`) writes a malformed EPIC-side `## Children` entry and places it by a rule that breaks on any non-flat Children section. It also rewrites untouched frontmatter formatting on the orphan.

## Current Behavior

Observed in a real run on a downstream project's issue tree:

1. **Placeholder instead of the child's title.** The bullet is hard-coded as `- **ENH-NNN** — (added by link-epics --apply)`, so every applied link leaves a line that a person has to fix by hand. `create.py`'s `_append_child_to_epic_children()` already writes `- **ID** — <title> (open)`.
2. **Extra blank line.** `stripped + sep + "\n" + bullet` puts a blank line between the last existing child and the new bullet, which splits the list in two.
3. **Wrong insertion point in irregular sections.** `_section_bounds()` ends the section at the next `## ` heading only, so the bullet goes at the very end of everything under `## Children`. That includes `### ` subsections (for example a "Spoke follow-through" note), dependency-note bullets, and wrapped multi-line bullets. In a manual run using the same "end of section" rule, the new line landed in the middle of a wrapped bullet, and the bullet's continuation line ended up hanging under the new child.
4. **Stray `## Children` at end of file.** When an EPIC has no `## Children` heading (some EPICs track children through `parent:` frontmatter only), apply adds a new `## Children` section after `## Status` / `## Session Log`.
5. **Frontmatter churn.** `update_frontmatter()` re-dumps the whole block: `goals: [2]` becomes a block list and long `title:` values get line-wrapped, even though only `parent:`/`epic:` changed.

## Expected Behavior

- The bullet carries the child's title (taken from its `# ID: title` H1, or from frontmatter `title:`) in the same `- **ID** — title (open)` shape that `ll-issues create --parent` writes.
- No blank line between the new bullet and the previous child.
- The insertion point is right after the last top-level child bullet (`^- \*\*(BUG|FEAT|ENH)-\d+\*\*`) and any indented continuation lines it has, and before any `###` subsection or prose.
- If the EPIC has no `## Children` section, either skip the body write (the frontmatter link alone is enough, as with `create.py`) or add the section before `## Status`. Never add it at the end of the file.
- Only the `parent:` and `epic:` lines change in the orphan's frontmatter.

## Proposed Solution

Move `_append_child_to_epic_children()` into a shared helper and make it aware of child bullets and continuation lines. Have both `create --parent` and `link-epics --apply` call it. For the orphan side, use a line-level frontmatter insert (for example, add `parent:`/`epic:` before the closing fence) rather than `update_frontmatter()`'s re-dump.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

**Option A**: When the EPIC has no `## Children` heading, skip the EPIC-side body write and rely on the orphan's `parent:`/`epic:` frontmatter (the `create.py` contract: `_append_child_to_epic_children()` returns `None` and callers skip silently, pinned by `test_ll_issues_create.py:115`). Caveat found in research: `epic_consistency.compute_drift()` (`epic_consistency.py:190`) treats a missing heading as an empty body, so such an EPIC is flagged `missing_from_body` for every `parent:` child and `ll-issues ec --fix` then appends its own EOF `## Children` with a placeholder — the same stray-section defect, relocated.
> **Selected:** Option A — matches the `create --parent`/`scaffold-epic` `None`-means-skip contract (pinned by `test_ll_issues_create.py:115`) and avoids adding body sections to EPICs that track children via `parent:` only.

**Option B**: When the EPIC has no `## Children` heading, insert a new `## Children` section before `## Status` (falling back to EOF only when `## Status` is also absent). `arm_proposal_revision._append_marker` (`arm_proposal_revision.py:72`) and `dependency_mapper._add_to_section` (`operations.py:66`) already insert a missing section before `## Status`. This keeps `ll-issues ec` quiet but adds a body section to EPICs that deliberately track children through `parent:` frontmatter only.

**Recommended**: Option A — it matches the existing `create --parent` contract, keeps the fix inside the issue's stated first alternative, and leaves the `epic-consistency` EOF behavior as a separately-scoped defect rather than widening this change; re-evaluate if the `ec` drift report on such EPICs proves noisy.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-10-05.

**Selected**: Option A

**Reasoning**: Option A reuses the existing `_append_child_to_epic_children()` skip contract (`create.py:168-182`, callers at `create.py:634-637` and `scaffold_epic.py:131-133`), needs no new insertion code, and does not add a redundant body section to the ~12 heading-less EPICs (e.g. EPIC-2412, EPIC-3127 track children via `parent:`; EPIC-2700 uses `## Child Issues`, where Option B would add a second children section). Option B's "keeps `ec` quiet" benefit only holds per linked child, and it would leave `fix_epic` writing to EOF, so the two writers would still disagree. Option A's residual — `compute_drift()`/`fix_epic()` (`epic_consistency.py:190,243`) re-adding an EOF `## Children` — is the sibling defect and stays separately scoped.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| Option B | 2/3 | 2/3 | 2/3 | 1/3 | 7/12 |

**Key evidence**:
For the selected approach, the `None`-means-skip contract exists in two callers and is test-pinned; the missing-heading branch (`link_epics.py:563-564`) is a single site. Caveat: `ec --fix` relocates the stray-section defect (`epic_consistency.py:243-247`).

For the rejected approach, two precedents insert before `## Status`, but with divergent anchors (`^## Status\b` vs `^## Status\s*$`; EPIC-3127's `## Status: what shipped…` sits mid-document), and `fix_epic` would still disagree.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

**Files to Modify**
- `scripts/little_loops/cli/issues/link_epics.py` — `apply_assignment()` (:536) owns the placeholder bullet (:561), the local `_section_bounds()` (:525, ends only at the next `^##\s`), the stray-`## Children` EOF fallback (:564), and the orphan write through `update_frontmatter()` (:552). `EpicProposal` (:115) has only `orphan_id`, `epic_id`, `score`, `tier` — no title — and `apply_assignment(proposal, *, orphan_path, epic_path)` receives none.
- `scripts/little_loops/cli/issues/create.py` — `_append_child_to_epic_children(content, child_id, child_title) -> str | None` (:168) is the existing `- **ID** — <title> (open)` writer; it returns `None` when `## Children` is absent.
- `scripts/little_loops/frontmatter.py` — `update_frontmatter()` (:439) re-dumps via `yaml.dump(default_flow_style=False)`, which is the source of the `goals: [2]` and wrapped-`title:` churn. `remove_frontmatter_keys()` (:474) is the only byte-preserving helper, and it is delete-only; no line-level upsert exists in this module.

**Dependent Files (Callers/Importers)**
- `scripts/little_loops/cli/issues/link_epics.py:664` — `cmd_link_epics()` is the only production caller of `apply_assignment()`. It already holds `IssueInfo` objects (`by_id`, :660) whose `.title` is frontmatter `title:` first, then the `# ID: title` H1, then the filename stem (`issue_parser.py:4288`).
- `scripts/little_loops/cli/issues/create.py:634` (`create_issue`) and `scripts/little_loops/cli/issues/scaffold_epic.py:131` — the only callers of `_append_child_to_epic_children()`; `scaffold_epic.py:23` imports it by private name. Both treat `None` as "skip silently". `create_issue` writes with `write_text`, `apply_assignment` with `atomic_write`.
- `scripts/little_loops/cli/issues/epic_consistency.py:98,190,243` — a second, different `_section_bounds(content, heading: str)` plus `fix_epic()` (:227), which is a third independent `## Children` appender with its own placeholder `(added by epic-consistency --fix)` (:239), the same `stripped + sep + "\n" + bullets` blank-line shape, and the same EOF-heading fallback.
- `update_frontmatter()` has ~40 production callers repo-wide; its behavior must not change for them.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/mcp_server/tools.py` — local import of `create_issue` (:268) in the MCP create tool; reaches `_append_child_to_epic_children` whenever a parent is set, so a shared-helper change to placement/trailing-newline also changes MCP-created children [Agent 1 finding]
- `scripts/little_loops/cli/issues/__init__.py` — lazy-imports `add_link_epics_parser, cmd_link_epics` and routes `args.command == "link-epics"`; no signature change needed unless `cmd_link_epics`'s import surface changes (e.g. a new `link_epics` → `create` import) [Agent 1 finding]
- `scripts/little_loops/cli/issues/epic_consistency.py:_BODY_BULLET_RE` (`^\s*[-*]\s+\*{0,2}([A-Z]+-\d+)`) and `compute_drift()` — read the new `- **ID** — title (open)` bullet exactly as the placeholder form, and `compute_drift()`'s `_section_bounds(content, "Children")` window still contains a bullet inserted after the last top-level child (before `###`), so `missing_from_body`/`body_without_parent` stay correct [Agent 2 finding]
- `scripts/little_loops/issues/prose_deps.py:extract_prose_deps` (`_SCOPE_BOUNDARY_RE`, `_scope_subject`) — scans EPIC `## Children` bullets and attributes a dependency phrase to the last issue ID in a list item; a child title containing "depends on …" would now be attributed to that child [Agent 2 finding]
- `scripts/little_loops/cli/issues/link_epics.py:cmd_link_epics` — prints `"Applied {n} proposal(s)."` and builds `applied` from `proposal.to_dict()` even when the EPIC body write is skipped (Option A no-heading path), so the count still includes heading-less EPICs [Agent 2 finding]
- `scripts/little_loops/frontmatter.py:_canonical_frontmatter_block` (:224) and `_iter_frontmatter_blocks` (:161) — a line-level upsert should use these (as `update_frontmatter` does at :466) to inherit BUG-2955 multi-block safety; `remove_frontmatter_keys` (:474) does not use the canonical-block rule [Agent 2 finding]

**Conventions in Force**
- No shared Children-section helper exists: three separate writers (`create.py`, `link_epics.py`, `epic_consistency.py`) disagree on section end (`startswith("## ")` vs `^##\s`), bullet shape, no-heading behavior (skip vs EOF append) and blank-line handling. Evidence: the three function bodies above.
- There is no common helper module under `cli/issues/`; helpers live in the module that first needed them and are imported across modules by private `_name`, often inside the function body. Evidence: `scaffold_epic.py:19-27` importing from `create.py`; `show._resolve_issue_id` imported by `create.py:629`. `link_epics.py` defers `little_loops.*` imports into function bodies and does not import `create.py` today.
- A fence-aware section locator exists: `issue_parser._section_body_with_offset(content, heading)` (`issue_parser.py:450`) and `text_utils.fence_spans`/`in_fence` (:64/:97). `arm_proposal_revision._append_marker` (`arm_proposal_revision.py:72`) already inserts after the last list item of a section through it. Neither Children writer is fence-aware today.
- Line-level frontmatter insert precedent: `cli/migrate.py:_set_fields` (:20) and `cli/migrate_labels.py:_set_labels_frontmatter` (:26) replace `^key:.*$` or insert before the second `^---\s*$` match, with no YAML round-trip. Both scan the whole file rather than the `FrontmatterBlock` spans from `frontmatter._iter_frontmatter_blocks()` (:161), so they are not multi-block-safe (BUG-2955) and neither has tests.
- Byte-preservation tests in this repo use `read_bytes()` before/after equality (`test_cli_doctor_install_checks.py:602-606`); source-text pins are per-module (`Path(mod.__file__).read_text()` then `assert "…" not in src`, e.g. `test_git_operations.py:306`). No frontmatter flow-style/long-title preservation test exists.

**Tests**
- `scripts/tests/test_link_epics_cli.py` — `TestApplyAssignment` (:152; `test_writes_parent_and_epic_fields`, `test_idempotent_reapply`) and `TestLinkEpicsCLI.test_apply_writes_frontmatter` (:243). None asserts bullet text, blank lines, or byte equality of the orphan; the only EPIC-body assertions are `"FEAT-1" in text` and `.count("FEAT-1") == 1`, so no existing test pins the placeholder string. Fixture EPICs there are the bare `...## Children\n` shape and some orphans have a title-less `# FEAT-1` H1 (:310) — the title fallback must tolerate that.
- `scripts/tests/test_ll_issues_create.py:107` (`test_parent_wiring_appends_epic_children_bullet`) pins `- **{id}** — Child thing (open)`; `:115` (`test_parent_wiring_skipped_silently_for_non_epic_parent`) pins the `None`/skip contract. Both must keep passing if the helper is shared.
- `scripts/tests/test_ll_issues_scaffold_epic.py` (`TestScaffoldEpic`) asserts `- **{id}**` presence only. `scripts/tests/test_epic_consistency.py` (`TestEpicConsistencyFix`, :364) asserts by substring and never pins the `epic-consistency --fix` placeholder.
- `scripts/tests/test_link_epics_skill.py:86` (`TestUpdateFrontmatterRoundTrip`) covers `update_frontmatter` itself and must stay green.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_link_epics_cli.py` — `TestApplyAssignment.test_writes_parent_and_epic_fields` and `test_idempotent_reapply` call `apply_assignment(proposal, orphan_path=, epic_path=)` and build `EpicProposal` with four keywords; a required new `title=` kwarg or required `EpicProposal` field breaks both, so any new parameter needs a default (or update both). `test_idempotent_reapply` asserts `.count("FEAT-1") == 1` — the bullet title must not contain the orphan ID (its H1 is `# FEAT-1: Orphan`, so `Orphan` is safe) [Agent 3 finding]
- `scripts/tests/test_link_epics_cli.py` (new tests in `TestApplyAssignment`) — no test covers a missing `## Children` heading today (every EPIC fixture ends `## Children\n`), so nothing pins the current EOF-append and Option A inverts nothing; write: title bullet shape, title-less `# FEAT-1` H1, flat list with no blank line, `###` subsection after list, wrapped last bullet, missing heading leaves EPIC bytes unchanged, empty/prose-only `## Children`, trailing-newline preserved, prose mention of orphan ID, idempotent reapply leaves orphan bytes unchanged, orphan byte-identity outside `parent:`/`epic:` (flow `goals: [2]` + long `title:`), null-valued and already-set `parent:`/`epic:`, plus the source-text pin on `(added by link-epics --apply)` [Agent 3 finding]
- `scripts/tests/test_frontmatter.py` — new class (e.g. `TestUpsertFrontmatterLines`) beside `TestUpdateFrontmatter` (:399) if the line-level upsert lands in `frontmatter.py`: absent key inserted before closing fence, existing key replaced in place, null-valued key replaced, `_DOUBLE_BLOCK` (`TestMultiFrontmatterBlocks`, :570) writes only the canonical block (template: `test_update_writes_canonical_block_only`, :634), no-frontmatter and CRLF input. No `remove_frontmatter_keys` unit test exists there either [Agent 3 finding]
- `scripts/tests/test_ll_issues_create.py` — add direct tests of `_append_child_to_epic_children` if it is shared/changed: returns `None` without a heading (`:115` only asserts `parent` is written and nothing raises, it does not pin `None`), continuation-line and `###` placement, trailing-newline preservation (current `"\n".join(splitlines())` rejoin drops the final newline) [Agent 3 finding]
- `scripts/tests/test_ll_issues_scaffold_epic.py` — `TestScaffoldEpic.test_creates_epic_and_children_both_directions_wired` (:59) asserts only `- **{child.id}**` presence; add a multi-child placement case if the shared helper changes output shape [Agent 3 finding]
- `scripts/tests/test_epic_consistency.py` — `TestEpicConsistencyFix.test_fix_adds_missing_category_a_children` (:367) uses `_write_epic(..., children_section="")` (no heading) and asserts `"FEAT-060" in updated`, i.e. it relies on `fix_epic()`'s EOF-heading creation; it breaks only if the sibling `fix_epic` is brought into scope. Option A as selected leaves it green [Agent 3 finding]
- `scripts/tests/test_link_epics_skill.py` — `TestLinkEpicsSkillExists.test_children_section_documented` (:62) requires `"## Children"` and `test_apply_flag` (:17) requires the `--apply` text to remain in `skills/link-epics/SKILL.md`; any SKILL.md prose edit must keep both [Agent 3 finding]
- `scripts/tests/test_issue_parser.py:1635` — hard-codes the `"epic_consistency:274"` key; only matters if `epic_consistency.py` edits shift it (not expected under Option A) [Agent 1 finding]
- `scripts/tests/test_prose_deps.py::TestSubjectAttribution.test_epic_children_list_attributes_to_the_child` (:168) — ready-made wrapped-bullet `## Children` fixture shape for the new continuation-line tests [Agent 3 finding]

**Documentation**
- `docs/reference/API.md:1556-1562` (`apply_assignment` description), `docs/reference/CLI.md:3222-3246` (`ll-issues link-epics`), `docs/reference/COMMANDS.md:460-469` (`/ll:link-epics`), `skills/link-epics/SKILL.md:82,93,97,228` (describes `--apply` as appending to `## Children`, idempotent). `skills/link-epics/` and `README.md` edits trip the mirror gates (`ll-adapt`, README sync) per project memory.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `little_loops.cli.issues.link_epics` > `class EpicProposal` block (restates the four fields and the `to_dict` comment) and `### apply_assignment` Parameters table (lists only `proposal`, `orphan_path`, `epic_path`): update both if a title field/kwarg is added; also the `little_loops.frontmatter` section (`update_frontmatter`/`remove_frontmatter_keys` entries, one-line table row at :41) needs a row and a short section if a new line-level upsert helper is added (model on the `remove_frontmatter_keys` "does not round-trip the block through YAML" text). No docs gate fails for a new function (`doc_counts.verify_coverage` checks entry points/hooks/counts only), so this is manual [Agent 2 + 3 finding]
- `docs/reference/CLI.md` — `#### ll-issues link-epics` `--apply` flag row ("`parent:`/`epic:` frontmatter + EPIC `## Children` append") and trailing paragraph ("`--apply` is idempotent — re-running is a no-op on any pair already applied"); reword for title bullet, skip-on-no-heading, and byte-preserving orphan write. Also `ll-issues create` section ("appends a wired bullet there too") if the shared helper's placement changes [Agent 2 finding]
- `docs/reference/COMMANDS.md` — `### /ll:link-epics` "**Output:**" paragraph (:460-469) and the `/ll:create` (`--parent`)/scaffold-epic Output descriptions of `## Children` wiring [Agent 2 finding]
- `skills/link-epics/SKILL.md` — "A1" documents the proposals JSON shape `{orphan_id, epic_id, score, tier}` (keep any title field out of `EpicProposal.to_dict()` or update this line); "A2: Present" and "A3: Apply Assignments" describe `--apply` ("appends to the target EPIC's `## Children` section"); "S4" step 4 has the LLM write `parent:`/`epic:` directly (synthesize mode never calls `apply_assignment`, so a new helper does not reach it) [Agent 2 finding]
- `skills/capture-issue/SKILL.md` — "#### 2. Append child to `## Children` section" (:370-381) tells the LLM to append at the end of `## Children` and, if absent, insert a section before `## Status`; this manual path conflicts with the new placement rule and Option A. Out of scope to rewrite here but must be consciously left or aligned (editing `skills/` trips the `ll-adapt` mirror gates) [Agent 1 + 2 finding]
- `skills/scope-epic/SKILL.md` — three `## Children` passages assert `--parent`/`scaffold-epic` "already guarantee" the EPIC bullet and a post-write consistency check keys on bullet presence; unaffected by Option A for EPICs that have the heading, but heading-less EPICs now never get a bullet [Agent 2 finding]
- `.issues/epics/P3-EPIC-3493-policy-builder-router-execution.md:38-46` — five existing `(added by link-epics --apply)` bullets (already noted under Live Data); a separate data fix, not covered by the source change [Agent 2 finding]

**Live Data**
- `.issues/epics/P3-EPIC-3493-policy-builder-router-execution.md:38-46` already carries five `(added by link-epics --apply)` bullets (ENH-3511, ENH-3513, ENH-3514, ENH-3510, BUG-3516). A code fix does not repair them, and "the placeholder string is gone from the codebase" can only be true for source, not for these existing issue files.

## Impact

- **Priority**: P3 - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Steps to Reproduce

1. Make an EPIC whose `## Children` list is followed by a `### Notes` subsection that contains a wrapped `- ...` bullet.
2. Make an orphan ENH with `goals: [2]` in flow style.
3. Run `ll-issues link-epics --mode assign --apply --threshold 0`.
4. The new bullet lands under `### Notes`, after a blank line, with the placeholder title, and the orphan's `goals:` has been reformatted.

## Root Cause

`apply_assignment()` builds its own bullet and its own section bounds instead of reusing `create.py`'s child-wiring helper, and it writes through a full YAML re-dump.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-05 — based on codebase analysis:_

- **Reuse alone does not fix symptom 3.** `create.py:_append_child_to_epic_children()` (:168) has the same irregular-section defect: it ends the section at the first `startswith("## ")` line, so a `### ` subsection, prose, or a wrapped last bullet is treated as part of the list and the bullet lands after it. It has no child-bullet regex and no continuation-line handling. The "reuse create.py's helper" framing therefore fixes symptoms 1 and 2 (title, blank line) for `link-epics` but must also gain bullet/continuation awareness, and doing so changes `create --parent` and `scaffold-epic` too (`create.py:634`, `scaffold_epic.py:131`).
- **Title is not reachable from `apply_assignment()` today.** `EpicProposal` carries no title and the function signature takes only paths; the title is available one frame up in `cmd_link_epics()` (`by_id[...]` → `IssueInfo.title`, `link_epics.py:660`). Whatever supplies it must tolerate the title-less `# FEAT-1` H1 fixtures in `test_link_epics_cli.py:310` (the `IssueInfo` fallback ends at the filename stem).
- **Heading matchers disagree.** `link_epics._CHILDREN_HEADING_RE` is `^##\s+Children\s*$` (accepts `##  Children` and trailing spaces); `create.py` matches `line.strip() == "## Children"` (rejects `##  Children`, accepts an indented heading). A shared helper must pick one rule knowingly. Neither is fence-aware.
- **Rejoin changes file endings.** `create.py` rebuilds with `"\n".join(lines)` after `splitlines()`, which drops the original trailing newline unless the insertion point was EOF; `apply_assignment` preserves the trailing newline. The new bullet must not flip a file's final-newline state.
- **Orphan write is not conditional on the EPIC write.** `apply_assignment()` rewrites the orphan (`atomic_write`, :553) *before* the `\bORPHAN_ID\b` already-listed check (:557). That check matches the ID anywhere in the EPIC — frontmatter `relates_to`, prose, another section — not just `## Children`, so an EPIC that mentions the ID in prose silently gets no bullet while the orphan is still rewritten. Idempotent reapply is therefore a frontmatter rewrite each time, which is churn even when nothing semantic changes.
- **One orphan can be applied to several EPICs.** `propose_assignments()` (:170-204) returns every orphan×EPIC pair at or above the threshold, not one best EPIC per orphan, and the `--apply` loop (`cmd_link_epics`, :655-665) applies them all: the orphan's `parent:`/`epic:` end up holding the last-applied EPIC while every matching EPIC gains a bullet. Whatever frontmatter write replaces `update_frontmatter()` has to define behavior when `parent:`/`epic:` already hold a value from an earlier proposal in the same run.
- **`is_orphan()` (:164) means `parent is None and epic is None`**, which covers both an absent key and an explicit `parent:` / `parent: null` key. A line-level write must replace an existing null-valued line rather than append a duplicate key (a duplicate key is a YAML error and `update_frontmatter` currently overwrites in place).
- **Sibling instance outside this issue's scope line.** `epic_consistency.fix_epic()` (:227) has the identical placeholder, blank-line and EOF-heading defects with its own string `(added by epic-consistency --fix)` (:239). The acceptance criterion "the placeholder string is gone from the codebase" is satisfied by removing `(added by link-epics --apply)` (single non-issue-file occurrence: `link_epics.py:561`); whether the sibling is in scope is a scoping decision, not a consequence of this fix.

## Program Design

### Types
- `EpicProposal` (dataclass: `orphan_id: str`, `epic_id: str`, `score: float`, `tier: str`) — has no title field; whether the title travels on it or as a separate argument is open.
- `IssueInfo.title: str` — already populated by `IssueParser` (frontmatter `title:`, then `# ID: title` H1, then filename stem) and held by `cmd_link_epics` in `by_id`.

### Signatures
- `apply_assignment(proposal: EpicProposal, *, orphan_path: Path, epic_path: Path) -> None` — current signature in `link_epics.py`; takes no title.
- `_append_child_to_epic_children(content: str, child_id: str, child_title: str) -> str | None` — current signature in `create.py`; `None` means no `## Children` heading.
- `update_frontmatter(content: str, updates: dict[str, Any]) -> str` — YAML re-dump writer in `frontmatter.py`, the source of the orphan-side churn.
- `remove_frontmatter_keys(content: str, keys: Iterable[str]) -> str` — the existing byte-preserving frontmatter writer in `frontmatter.py` (delete-only), the shape a line-level upsert has to match.
- `_section_bounds(content: str, heading_re: re.Pattern[str]) -> tuple[int, int] | None` — local to `link_epics.py`; ends a section only at the next `^##\s`.

### Call Path
`cmd_link_epics` -> `apply_assignment` -> `update_frontmatter` (orphan) and the Children-bullet writer (EPIC); `create_issue` -> `_append_child_to_epic_children` and `scaffold_epic` -> `_append_child_to_epic_children` share the EPIC-side writer today.

### Decision Rules
- A top-level child bullet is a line matching `^- \*\*(BUG|FEAT|ENH)-\d+\*\*` inside the `## Children` section.
- A continuation line of such a bullet is any directly following non-blank line that begins with whitespace; the bullet ends at the first blank line, next top-level bullet, `###`+ heading, or `## ` heading.
- The new bullet goes immediately after the last top-level child bullet and its continuation lines, with no blank line inserted between them, and always before any `###`+ subsection or trailing prose in the section.
- No qualifying bullet in an existing `## Children` section (empty or prose-only): the placement is unspecified by the issue and must be pinned by the implementer with a test.
- No `## Children` heading: skip the EPIC-side body write (Option A, selected); the orphan's `parent:`/`epic:` frontmatter alone carries the link, and no section is ever appended at end of file.
- Orphan frontmatter: only the `parent:` and `epic:` lines may differ byte-for-byte after apply; an existing `parent:`/`epic:` line (including null-valued) is replaced in place, an absent one is added inside the canonical block's closing fence.

## Implementation Steps

1. `link-epics --apply` writes `- **ID** — <title> (open)`, with the title from the orphan's `IssueInfo`, and `(added by link-epics --apply)` no longer appears under `scripts/`. Verified by a test that reads the EPIC after `apply_assignment()`/the CLI `--apply` path, plus a source-text pin on `link_epics.py` in the style of `test_git_operations.py:306`.
2. Child-bullet placement honors the Decision Rules for: a `###` subsection after the list, a wrapped multi-line last bullet, an existing flat list (no blank line added), and a missing `## Children` heading. Each shape has its own case beside `TestApplyAssignment` (`test_link_epics_cli.py:152`).
3. If the EPIC-side writer is shared with `create --parent` and `scaffold-epic`, `test_ll_issues_create.py:107`/`:115` and `test_ll_issues_scaffold_epic.py` keep passing and the trailing-newline state of the EPIC file is unchanged.
4. Orphan frontmatter is byte-identical outside `parent:`/`epic:` (flow-style `goals: [2]` and a long wrapped `title:` asserted via before/after `read_text()`/`read_bytes()` comparison), including when the orphan's `parent:`/`epic:` keys are absent, null-valued, or already set by an earlier proposal in the same run.
5. `python -m pytest scripts/tests/test_link_epics_cli.py scripts/tests/test_ll_issues_create.py scripts/tests/test_ll_issues_scaffold_epic.py scripts/tests/test_epic_consistency.py scripts/tests/test_frontmatter.py scripts/tests/test_link_epics_skill.py` passes, followed by the full `python -m pytest scripts/tests/`; `docs/reference/API.md:1556`, `skills/link-epics/SKILL.md:97`, and `docs/reference/COMMANDS.md:469` still describe the final behavior (re-run the mirror gates if `skills/` or `README.md` change).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_link_epics_cli.py` — give any new `apply_assignment`/`EpicProposal` parameter a default so `TestApplyAssignment.test_writes_parent_and_epic_fields` and `test_idempotent_reapply` keep passing; keep the bullet title free of the orphan ID (`.count("FEAT-1") == 1`)
- Add `TestUpsertFrontmatterLines` (or equivalent) to `scripts/tests/test_frontmatter.py` — line-level upsert via `_iter_frontmatter_blocks`/`_canonical_frontmatter_block`, covering absent, existing, null-valued, multi-block (`_DOUBLE_BLOCK`), no-frontmatter and CRLF inputs
- Add direct `_append_child_to_epic_children` tests to `scripts/tests/test_ll_issues_create.py` (returns `None` without heading, `###`/continuation placement, trailing newline) — the shared helper also reaches MCP `create_issue` (`mcp_server/tools.py:268`), so run `ll-issues create --parent` and scaffold-epic tests together with the link-epics suite
- Keep `EpicProposal.to_dict()` at `{orphan_id, epic_id, score, tier}` (or update `skills/link-epics/SKILL.md` "A1" and `docs/reference/API.md` `EpicProposal` block); update `apply_assignment` Parameters table in `docs/reference/API.md` if the signature changes
- Update `docs/reference/CLI.md` (`ll-issues link-epics` `--apply` row and idempotency paragraph), `docs/reference/COMMANDS.md` (`/ll:link-epics` Output), `skills/link-epics/SKILL.md` ("A2"/"A3") for title bullets, skip-on-no-heading, and byte-preserving orphan write; re-run `ll-adapt --host <gemini|kimi-code|qwen> --apply` if `skills/` changes
- Decide knowingly on `skills/capture-issue/SKILL.md` "#### 2. Append child to `## Children` section" (end-of-section append / insert-before-`## Status`), which conflicts with the new placement rule and Option A
- Leave `epic_consistency.fix_epic` and `test_epic_consistency.py:367` untouched (sibling defect, separately scoped); if pulled in, that test must be rewritten

## Acceptance Criteria

- [ ] Applied bullets carry the child title; the placeholder string is gone from the codebase.
- [ ] Tests in `test_link_epics_cli.py` for: a `###` subsection after the list, a wrapped multi-line last bullet, a missing `## Children` heading, and an existing child list (no blank line added).
- [ ] An orphan with flow-style `goals:` and a long `title:` keeps both lines byte-identical after apply.

## Status

**Open** | Created: 2026-10-05 | Priority: P3


## Session Log
- `/ll:verify-issues` - 2026-10-05T19:22:16 - `c19d01fe-ea18-43c7-87be-75e6ac5814be.jsonl`
- `/ll:wire-issue` - 2026-10-05T19:20:19 - `4d2fe865-6096-4837-afde-ff1ae6f6247a.jsonl`
- `/ll:decide-issue` - 2026-10-05T19:14:48 - `58840838-a80a-43b5-a8f1-a715c24cacdc.jsonl`
- `/ll:refine-issue` - 2026-10-05T19:10:34 - `b3247adb-4297-48f8-b282-e67dbd158ed2.jsonl`
