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
relates_to:
- BUG-3739
---

# BUG-3738: link-epics --apply writes a placeholder child bullet, misplaces it in irregular ## Children sections, and churns orphan frontmatter

## Summary

`ll-issues link-epics --mode assign --apply` writes placeholder Children bullets in the wrong part of irregular EPIC sections and reserializes unrelated orphan metadata. Its broad duplicate check also mistakes a prose mention for an existing child. Make assignment writes precise, consistent with `create --parent`, and harmless on reapply.

The apply path must also maintain the existing single-parent model: keep all scored alternatives in proposal output, but apply at most the highest-ranked proposal for each orphan. Applying every alternative currently creates contradictory EPIC lists and leaves the lowest-scoring match in the orphan's frontmatter.

## Current Behavior

Verified on branch `main` on 2026-10-05:

1. `apply_assignment()` in `scripts/little_loops/cli/issues/link_epics.py` emits `- **ID** — (added by link-epics --apply)` instead of a title.
2. Its section-end append introduces an extra blank line and places the bullet below `### Notes` or other trailing prose. A temporary-file reproduction preserved the existing wrapped note intact; the earlier claim that this implementation splits a wrapped bullet was not reproduced and is not a required fix.
3. A missing exact `## Children` heading causes a new section at EOF, including after Status or Session Log. The create helper instead skips the EPIC body write.
4. The orphan is YAML-dumped before the EPIC duplicate check. Flow lists, comments, quoting, Unicode representation, and long titles can change even on reapply.
5. A word-boundary ID search across the whole EPIC suppresses insertion when the ID appears only in frontmatter, prose, another section, or a fenced example.
6. Proposals are sorted by descending score and all are applied. In a reproduction with scores `1.0` and `0.667`, both EPICs received the child and the orphan ended with the `0.667` EPIC as parent.
7. Universal-newline reads convert CRLF to LF. Default `atomic_write()` replaces existing modes with `0600`; its `shared_mode=True` option preserves a regular file's mode.

## Expected Behavior

- Each actual insertion has the shape `- **ID** — <child title> (open)`, using the parsed title's normal precedence. A title may legitimately contain its own issue ID.
- Children are inserted into the existing child-list area, before trailing prose or subsections, without separating adjacent child bullets or disturbing wrapped content.
- A missing exact Children heading leaves the EPIC byte-identical; parent/epic frontmatter still carries the assignment.
- Only the orphan's parent/epic entries change. Unrelated content, line endings, final-newline state, and existing file modes survive.
- Reapplying the same pair changes neither file and performs no write when the content is already correct.
- One apply run selects at most one EPIC per orphan. A conflicting existing parent/epic is reported and never silently overwritten.

## Steps to Reproduce

1. In a temporary issue tree, create an open EPIC with `## Children`, an existing child with an indented continuation, a following `### Notes` subsection, and `## Status`.
2. Create an orphan with matching title words, flow-style `goals: [2]`, and a YAML comment.
3. Run `ll-issues link-epics --mode assign --apply --threshold 0` with only that EPIC eligible.
4. Observe a placeholder below Notes, extra list spacing, and rewritten goals/comment formatting.
5. Repeat with the orphan ID mentioned only in EPIC prose: the orphan gets a parent but no Children bullet.
6. Repeat with two matching EPICs: both gain a bullet and the last, lower-scoring EPIC wins the frontmatter.

## Root Cause

- **File**: `scripts/little_loops/cli/issues/link_epics.py`; **anchors**: `apply_assignment`, `_section_bounds`, `cmd_link_epics`, `propose_assignments`. The writer implements its own placeholder and section append, searches the entire document for duplicates, and unconditionally writes every scored pair.
- **File**: `scripts/little_loops/cli/issues/create.py`; **anchor**: `_append_child_to_epic_children`. Reusing it unchanged fixes only title/spacing: it also appends after subsections and rebuilds text with `splitlines()`/join.
- **File**: `scripts/little_loops/frontmatter.py`; **anchor**: `update_frontmatter`. It intentionally re-dumps a whole mapping. Change the assignment caller to a narrow preserving helper rather than altering this widely used API.

## Proposed Solution

Improve the existing `_append_child_to_epic_children()` helper and reuse it from `apply_assignment()` through a deferred import. Its current callers in create and scaffold already share it, and create has no import of link_epics. A new generic Markdown framework or a rewrite of the consistency fixer is unnecessary.

Add a scalar-only frontmatter upsert in `frontmatter.py` for assignment metadata. Bound edits to the canonical identity block, or the first block when no block has an ID, using the existing block-selection contract. Preserve source spans rather than reserializing unrelated YAML. Keep `update_frontmatter()` unchanged.

Keep proposal scoring/output unchanged, and deduplicate the ordered proposals by orphan ID only when applying. Pre-read and validate both files and construct both updated texts before the first write. Use preserving atomic writes only for changed content. This is preflight validation, not a claim of an atomic transaction across two files; surface write failures, and same-pair reapply must repair a missing side.

### Decision Rationale

The earlier `/ll:decide-issue` selection, **Option A**, remains binding: no exact Children heading means skip the EPIC body write. It matches the existing create/scaffold contract and avoids synthesizing sections on EPICs that use frontmatter-only children or `## Child Issues`. The separate EOF/placeholder behavior in `epic_consistency.fix_epic()` remains outside this issue.

### Behavior Parity

Keep all alternatives, scores, tiers, and `EpicProposal.to_dict()` fields in proposal output; synthesis behavior is unchanged. Preserve the create/scaffold no-heading skip contract and standard `(open)` bullet format. The intentional behavior change is that apply chooses one winner per orphan instead of writing contradictory memberships.

## Program Design

### Types

Existing `EpicProposal` and `IssueInfo` need no new fields. The optional title value is:

```python
child_title: str | None
```

### Signatures

Proposed signatures for implementation (documentation notation):

```python
apply_assignment(proposal: EpicProposal, *, orphan_path: Path, epic_path: Path, child_title: str | None = None) -> None
_append_child_to_epic_children(content: str, child_id: str, child_title: str) -> str | None
upsert_frontmatter_scalars(content: str, updates: Mapping[str, str]) -> str
```

`cmd_link_epics` passes `IssueInfo.title`. Existing direct apply calls remain supported by an optional title argument; fallback reads frontmatter title, then an H1 title, then filename stem. In particular, a title-less `# FEAT-1` H1 is valid input, not an exception. Collapse title whitespace to one line so a wrapped frontmatter title cannot inject another bullet or heading.

### Call Path

`cmd_link_epics` → `propose_assignments` → first proposal per orphan → `apply_assignment` → preserving scalar upsert + shared Children helper → changed-file atomic writes.

`create_issue` and scaffold retain their calls to `_append_child_to_epic_children`.

### Decision Rules

- **Section selection**: choose the first non-fenced, unindented H2 whose text is exactly `Children`, allowing horizontal whitespace between `##` and the name and after it. Stop at the next non-fenced H1/H2. Do not treat whitespace as permission to consume another physical line. Other Children headings, aliases, and suffixed headings are left alone; no matching heading means skip.
- **Placement**: before the first non-fenced H3+ heading, find the last eligible top-level `-`/`*` child bullet, with optional bold wrappers and a whole BUG/FEAT/ENH/EPIC ID. Introductory prose and loose-list spacing may precede it. Insert after that bullet and its complete continuations, before its trailing separator blanks. Continuations are lines indented by at least two spaces or a tab, including nested items and blank lines followed by another indented continuation; stop at an unindented nonblank line or heading. Do not split an existing item, including a lazy continuation paragraph: if its extent is ambiguous, reject the pair before writing rather than guessing. If there are no eligible bullets before H3, insert at the beginning of the section before existing prose/H3 content.
- **Spacing**: no new blank line between adjacent child bullets; preserve existing separation from trailing notes/headings, adding one blank line if necessary to keep following prose/headings from becoming a lazy continuation of the new item. Never insert inside a fenced block or between a bullet and its continuation. Preserve LF/CRLF and whether the file ends with a newline. Match backtick and tilde fences by character and closing length using the existing fence utilities.
- **Duplicate detection**: only an actual whole-ID child entry inside the selected Children section counts, including recognized bullet or per-child H3–H6 forms. Ignore fenced examples and mentions elsewhere. A prefix such as `FEAT-1` inside `FEAT-10` or `FEAT-1suffix` does not count.
- **Winner selection**: preserve the existing `(-score, orphan_id, epic_id)` ordering and apply the first pair for each orphan. Equal-score ties therefore follow the existing EPIC-ID order. `applied` lists only selected successful pairs; proposal output still lists every alternative.
- **Existing relationship**: absent/null parent or epic may be filled; a value already equal to the selected EPIC is retained in its original representation. Any non-null conflicting parent/epic rejects that pair before either file changes, names the orphan and conflicting field, and causes a nonzero command result. Do not implicitly reparent. Do not fall through to a lower-ranked alternative after a rejected winner.
- **Frontmatter safety**: the new helper supports only single-line scalar assignment entries, including null/empty values. Reject multiline/block/collection values and duplicate assignment keys rather than changing only their first line. A same-value reapply preserves the original quote/comment representation. No frontmatter means prepend a minimal block while preserving the body. Unterminated/malformed blocks or conflicts reject the pair before writing. Re-parse the proposed text using the existing merged semantics and require both parent and epic to equal the selected ID; a later block containing null can shadow an update just as a different parent can. Keep exact issue-ID identity rather than silently equating padded IDs, and do not rely on YAML's last-key-wins behavior.
- **Writes**: read without universal-newline conversion; use `atomic_write(..., shared_mode=True)` for changed existing files. Compute/validate both texts first; unchanged texts produce no write. Preserve raw newline offsets in the narrow helper without changing general parser precedence. Write orphan then EPIC; if the second write fails, report a nonzero error naming the partial pair. Reapply must repair a missing EPIC bullet even when both frontmatter values were already correct.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/issues/link_epics.py` — title plumbing, scoped duplicate handling, preflight/conditional writes, and one-winner apply bookkeeping.
- `scripts/little_loops/cli/issues/create.py` — shared Children helper's placement, fence awareness, entry recognition, and source preservation.
- `scripts/little_loops/frontmatter.py` — add scalar upsert; reuse `_iter_frontmatter_blocks` and `_canonical_frontmatter_block` selection semantics without changing general YAML-dump behavior.

### Dependent Files

- `scripts/little_loops/cli/issues/scaffold_epic.py` imports the create helper; retain its signature and skip behavior.
- `scripts/little_loops/mcp_server/tools.py` reaches the helper through `create_issue`; no MCP API change.
- `scripts/little_loops/cli/issues/epic_consistency.py` reads the resulting bullet format. Its `fix_epic` writer and missing-heading behavior stay out of scope.
- `scripts/little_loops/issues/prose_deps.py` scans child titles/continuations; keep existing title-based subject attribution working.
- BUG-3739 changes upstream candidate filtering and payload reporting in the same command. Coordinate edits and test the combined output; neither fix requires the other to land first.

### Tests

- `scripts/tests/test_link_epics_cli.py` — actual bullet content, body mentions versus membership, first-winner/tie behavior, existing-parent conflicts, missing heading, exact-ID/fence cases, and repeated apply with no writes. Replace whole-file ID-count assertions with assertions on actual child entries; valid titles may repeat an ID.
- `scripts/tests/test_ll_issues_create.py` and `scripts/tests/test_ll_issues_scaffold_epic.py` — shared-helper placement, intro prose before bullets, loose lists, nested/paragraph continuations, ambiguous lazy continuations, prose-only separation, no-heading skip, multi-child creation, and final-newline preservation.
- `scripts/tests/test_frontmatter.py` — absent/null/existing scalar keys, same-value representation, comments/flow lists/wrapped titles/Unicode, multi-block precedence (including later-block null shadowing), multiline/collection/malformed/duplicate metadata rejection, no-frontmatter, and LF/CRLF cases. Apply tests also cover a failed second write and recovery by reapplying the pair.
- `scripts/tests/test_epic_consistency.py`, `scripts/tests/test_link_epics_skill.py`, and `scripts/tests/test_prose_deps.py` — consumer regression coverage. Assert observable output; a source-text ban on the placeholder is unnecessary.

### Documentation

Update `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/reference/COMMANDS.md`, and `skills/link-epics/SKILL.md` for one-winner apply, title bullets, no-heading skip, and conflict/reapply behavior. The skill currently promises every above-threshold pair is applied; revise that promise. Do not claim a score threshold can represent an arbitrary user-selected subset. Keep this issue to truthful documentation of the existing CLI; adding pair-selection flags is separate work.

Check child-wiring instructions in `skills/capture-issue/SKILL.md` for agreement with the selected skip/placement contract. Regenerate affected host mirrors with `ll-adapt` when skill text changes; use the repository's mirror gates. Add API documentation for the new scalar helper.

### Configuration

No new setting, dependency, or host invocation.

## Implementation Steps

1. Add temporary-tree regressions for the observed placement/churn/duplicate defects and two-EPIC contradictory assignment.
2. Improve the existing shared Children helper according to the Decision Rules and wire apply's title/duplicate behavior to it.
3. Add preserving scalar upsert and preflight both sides; reject conflicting metadata, preserve modes/newlines, and skip identical writes.
4. Keep all proposed alternatives but apply only the first ranked pair per orphan. Update result bookkeeping and user-facing contracts.
5. Run the focused tests above, then the authoritative `python -m pytest scripts/tests/`, lint and type checks for changed Python, and mirror checks when skill text changes.

## Acceptance Criteria

- [ ] Applied bullets use the actual title in the standard `(open)` form; no placeholder is emitted. Frontmatter/H1/filename fallbacks and a title containing its own ID are covered.
- [ ] Flat, empty, prose-only, wrapped/multi-paragraph, subsection, noncanonical bullet, sub-EPIC, fenced example, duplicate-heading, and absent-heading shapes obey the specified placement/skip rules without disturbing existing content.
- [ ] Exact child entries suppress duplicates; prose/frontmatter/other-section mentions and partial IDs do not. Reapply leaves both files byte-identical and invokes no writer for unchanged content.
- [ ] Orphan bytes outside updated parent/epic entries, LF/CRLF style, final newline, and existing file modes are preserved. Null, missing, already-correct, malformed, duplicate-key, and multi-block inputs have explicit tests.
- [ ] With multiple matches, only the highest-ranked EPIC is applied/listed for each orphan; ties are deterministic and all alternatives remain in `proposals`. Existing conflicting relationships cause no writes for the rejected pair and a visible nonzero result.
- [ ] Create/scaffold/MCP child wiring retains the no-heading contract; the focused regression suites and full local test suite pass, with docs and skill mirrors describing the final behavior.

## Impact

- **Priority**: P3 — normal issue organization is affected; metadata churn and contradictory parent links make repeated automated application unreliable.
- **Effort**: Medium — two preserving text transforms plus command-level selection and consumer tests; no new framework is needed.
- **Risk**: Medium — a shared writer affects create/scaffold, and apply's parent selection changes. Explicit parity rules and end-to-end fixtures bound those risks.
- **Breaking Change**: Yes, limited to defective apply behavior: multiple alternatives no longer all write, and existing conflicting relationships are rejected. Proposal payload fields and scoring stay compatible.

## Review Notes

2026-10-05: Reconciled the earlier refine/wire/decision findings into one directive specification. Verified on `main`; temporary-file reproductions confirmed misplaced placeholders, lost flow style/comments, prose-mention suppression, and lowest-score overwrite. They did not confirm the reported wrapped-bullet split. Existing relevant suites passed: **235 tests** across link-epics, create, scaffold, consistency, frontmatter, and skill tests. These establish a baseline, not proof that the proposed fix exists.

Used `/ll:advise --signal user_requested --host claude-code --model opus` for critique (confidence **0.76**). Adopted its prose-separation, merged-result validation, scalar-only safety, and partial-write tests. Kept the selected missing-heading skip and bounded single-winner fix. Advisor dissent concerned ties, CRLF scope, and whether the other issue should depend on this one: retain deterministic existing tie order, preserve bytes at these write sites, and keep the two issues independently implementable. Numeric-ID normalization and a broad per-proposal outcome enum are outside this change.

## Status

**Open** | Created: 2026-10-05 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-10-05T20:18:56 - `3e2de759-3a68-4bde-a95a-631efbd7d020.jsonl`
- `/ll:verify-issues` - 2026-10-05T20:12:03 - `a57c7663-4e50-4ae2-b421-f80e0bc409b6.jsonl`
- `/ll:verify-issues` - 2026-10-05T19:31:15 - `c39a9b88-efc2-4837-8447-c4c6f8c5acb5.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-05T19:28:04 - `2e17f620-0f9e-4bd7-92e3-c417d5338f4a.jsonl`
- `/ll:verify-issues` - 2026-10-05T19:22:16 - `c19d01fe-ea18-43c7-87be-75e6ac5814be.jsonl`
- `/ll:wire-issue` - 2026-10-05T19:20:19 - `4d2fe865-6096-4837-afde-ff1ae6f6247a.jsonl`
- `/ll:decide-issue` - 2026-10-05T19:14:48 - `58840838-a80a-43b5-a8f1-a715c24cacdc.jsonl`
- `/ll:refine-issue` - 2026-10-05T19:10:34 - `b3247adb-4297-48f8-b282-e67dbd158ed2.jsonl`
