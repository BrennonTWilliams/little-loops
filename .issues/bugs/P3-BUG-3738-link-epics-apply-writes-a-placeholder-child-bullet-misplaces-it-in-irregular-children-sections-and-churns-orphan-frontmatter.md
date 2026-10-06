---
id: BUG-3738
type: BUG
title: 'link-epics --apply writes a placeholder child bullet, misplaces it in irregular
  ## Children sections, and churns orphan frontmatter'
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T18:53:54Z'
completed_at: '2026-10-06T00:05:58Z'
labels:
- issues
- link-epics
decision_needed: false
verify_verdict: VALID
relates_to:
- BUG-3739
confidence_score: 95
outcome_confidence: 63
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
---

# BUG-3738: link-epics --apply writes a placeholder child bullet, misplaces it in irregular ## Children sections, and churns orphan frontmatter

## Summary

`ll-issues link-epics --mode assign --apply` writes placeholder Children bullets in the wrong part of irregular EPIC sections and reserializes unrelated orphan metadata. Its broad duplicate check also mistakes a prose mention for an existing child. Make assignment writes precise, consistent with `create --parent`, and harmless on reapply.

The apply path must also maintain the existing single-parent model: keep all scored alternatives in proposal output, but apply at most the highest-ranked proposal for each orphan. Applying every alternative currently creates contradictory EPIC lists and leaves the lowest-scoring match in the orphan's frontmatter.

## Current Behavior

Verified on branch `main` on 2026-10-05:

1. `apply_assignment()` in `scripts/little_loops/cli/issues/link_epics.py` emits the placeholder `— (added by link-epics --apply)` after the bold ID instead of a title.
2. Its section-end append introduces an extra blank line and places the bullet below `### Notes` or other trailing prose. A temporary-file reproduction preserved the existing wrapped note intact; the earlier claim that this implementation splits a wrapped bullet was not reproduced and is not a required fix.
3. A missing exact `## Children` heading causes a new section at EOF, including after Status or Session Log. The create helper instead skips the EPIC body write.
4. The orphan is YAML-dumped before the EPIC duplicate check. Flow lists, comments, quoting, Unicode representation, and long titles can change even on reapply.
5. A word-boundary ID search across the whole EPIC suppresses insertion when the ID appears only in frontmatter, prose, another section, or a fenced example.
6. Proposals are sorted by descending score and all are applied. In a reproduction with scores `1.0` and `0.667`, both EPICs received the child and the orphan ended with the `0.667` EPIC as parent.
7. Universal-newline reads convert CRLF to LF. Default `atomic_write()` replaces existing modes with `0600`; its `shared_mode=True` option preserves a regular file's mode.
8. `apply_assignment()` takes no lock, while every other issue mutator (`set-status`, `link`, `set-scores`, `append_session_log_entry`) wraps its read-modify-write in the issue-tree mutation lock from `issue_lock_path()` (BUG-3150). A concurrent mutation between apply's read and write is silently lost or overwritten. `create_issue`'s parent-EPIC append (`create.py`, after the `.id-alloc.lock` hold ends) is the same unlocked read-modify-write, using plain `write_text`, so a concurrent `create --parent` can race apply on the same EPIC today.
9. `is_orphan()` requires `parent is None and epic is None`, so on the normal CLI path an orphan never has a conflicting parent/epic. The conflict case is reachable only via a race (see 8), a multi-block shadow, or a direct `apply_assignment()` call.
10. `apply_assignment()` writes the orphan first. If the EPIC write then fails, the orphan carries a parent and is no longer an orphan, so `link-epics --apply` never re-proposes it; reapply recovers the pair only when `apply_assignment()` is called directly. CLI-level recovery is `epic-consistency --fix` (category-(a) drift).

## Expected Behavior

- Each actual insertion has the shape `- **ID** — <child title> (open)`, using the parsed title's normal precedence. A title may legitimately contain its own issue ID.
- Children are inserted into the existing child-list area, before trailing prose or subsections, without separating adjacent child bullets or disturbing wrapped content.
- A missing exact Children heading leaves the EPIC byte-identical; parent/epic frontmatter still carries the assignment.
- Only the orphan's parent/epic entries change. Unrelated content, line endings, final-newline state, and existing file modes survive.
- Reapplying the same pair changes neither file and performs no write when the content is already correct.
- One apply run selects at most one EPIC per orphan. A conflicting existing parent/epic is reported and never silently overwritten.
- Each pair's read-validate-write runs under the issue-tree mutation lock, so a concurrent `set-status`, `link`, `create --parent`, or session-log append cannot interleave with it.
- One rejected pair (ambiguous Children section, conflicting metadata discovered under the lock, lock timeout, write failure) does not abort the run: the remaining orphans are still applied, the rejection is listed in an additive `rejected` JSON key and on stderr, and the exit code is nonzero.
- Issue creation/scaffolding never fails because of Children wiring: an ambiguous Children section skips the EPIC body write with a stderr warning, exactly like the no-heading skip.

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

**Shared recognizer (coordinate with BUG-3739).** Both issues need the same pure, fence-aware Children grammar: exact-heading section selection, bullet/H3–H6 entry recognition, whole-ID matching. Do not write it twice. **Landed in `cda52e0eb`:** the recognizer now exists in `scripts/little_loops/cli/issues/epic_consistency.py` as public helpers (`find_children_section(content) -> tuple[int, int] | None` and `iter_child_entries(section_text) -> list[ChildEntry]`, with `ChildEntry` carrying the ID, kind, and source span) and the consistency checker already uses them. This issue adopts them and does not recreate them; `link_epics._section_bounds` (still its own heading regex) is replaced by `find_children_section` in the apply path. This issue's writer-only logic (placement after the last bullet and its continuations, spacing, ambiguity rejection) stays in `create.py` and builds on those helpers. Land the two issues serially, not under parallel workers: both edit `link_epics.py`, `epic_consistency.py`, `docs/reference/CLI.md`, `COMMANDS.md`, and `skills/link-epics/SKILL.md`.

**Locking.** `apply_assignment()` wraps its whole pair operation (re-read both files, validate, compute both texts, write) in one `acquire_lock(issue_lock_path(orphan_path, base_dir))`. The lock is tree-wide and non-reentrant (`flock` contends within a process), so a single acquisition per pair covers both files, nothing inside the block may call another lock holder (`session_log`, `set-status`, `link`), and `cmd_link_epics` locks per pair, never around the whole run. `TimeoutError` becomes a rejected pair. `create_issue` wraps its parent-EPIC read-append-write in the same `acquire_lock(issue_lock_path(parent_path, base_dir))`, after the `.id-alloc.lock` hold has ended, never nested inside it, and writes with `atomic_write(..., shared_mode=True)`. Without this, the Expected Behavior claim that `create --parent` cannot interleave is false. `scaffold_epic` writes a brand-new EPIC with `open(..., "x")` and needs no change. This is one wrapper plus one test, so it stays in this issue; if implementation shows it needs more than that, split it into its own ENH and also cover `fix_epic`, which has the same omission.

Add a scalar-only frontmatter upsert in `frontmatter.py` for assignment metadata. Bound edits to the canonical identity block, or the first block when no block has an ID, using the existing block-selection contract. Preserve source spans rather than reserializing unrelated YAML. Keep `update_frontmatter()` unchanged.

Keep proposal scoring/output unchanged, and deduplicate the ordered proposals by orphan ID only when applying. Pre-read and validate both files and construct both updated texts before the first write. Use preserving atomic writes only for changed content. This is preflight validation, not a claim of an atomic transaction across two files; surface write failures, and same-pair reapply must repair a missing side.

### Decision Rationale

The earlier `/ll:decide-issue` selection, **Option A**, remains binding: no exact Children heading means skip the EPIC body write. It matches the existing create/scaffold contract and avoids synthesizing sections on EPICs that use frontmatter-only children or `## Child Issues`. The separate EOF/placeholder behavior in `epic_consistency.fix_epic()` remains outside this issue.

### Behavior Parity

Keep all alternatives, scores, tiers, and `EpicProposal.to_dict()` fields in proposal output; synthesis behavior is unchanged. The only payload change is the additive `rejected` list (assign mode; empty when nothing was rejected), which must coexist with BUG-3739's additive report keys. Preserve the create/scaffold no-heading skip contract and standard `(open)` bullet format. The intentional behavior change is that apply chooses one winner per orphan instead of writing contradictory memberships.

## Program Design

### Types

Existing `EpicProposal` and `IssueInfo` need no new fields. The optional title value is:

```python
child_title: str | None
```

### Signatures

Proposed signatures for implementation (documentation notation):

```python
class AmbiguousChildrenSection(ValueError): ...   # in create.py
apply_assignment(proposal: EpicProposal, *, orphan_path: Path, epic_path: Path, child_title: str | None = None, base_dir: str = ".issues") -> None
_append_child_to_epic_children(content: str, child_id: str, child_title: str) -> str | None
upsert_frontmatter_scalars(content: str, updates: Mapping[str, str]) -> str
```

`_append_child_to_epic_children` keeps its signature and has three distinct outcomes: **no exact Children heading** → returns `None` (unchanged contract); **child already an actual entry** → returns `content` unchanged (callers treat equality as "no write"); **ambiguous extent** (lazy continuation, unparseable list shape) → raises `AmbiguousChildrenSection`. `create_issue` and `scaffold_epic` catch it, print a one-line stderr warning naming the EPIC, and skip the EPIC body write exactly as for `None`; the child file is still created. `apply_assignment` lets it propagate as a rejected pair. `apply_assignment` raises `ValueError` for a conflicting parent/epic, `TimeoutError` for lock contention, and `OSError` for write failure; `cmd_link_epics` converts each into a `rejected` entry.

`cmd_link_epics` passes `IssueInfo.title`. Existing direct apply calls remain supported by an optional title argument; fallback reads frontmatter title, then an H1 title, then filename stem. In particular, a title-less `# FEAT-1` H1 is valid input, not an exception. Collapse title whitespace to one line so a wrapped frontmatter title cannot inject another bullet or heading.

### Call Path

`cmd_link_epics` → `propose_assignments` → first proposal per orphan → `apply_assignment` → `acquire_lock(issue_lock_path(...))` → re-read both files → preserving scalar upsert + shared Children helper → changed-file atomic writes; per-pair exceptions are collected into `rejected` and the loop continues.

`create_issue` and scaffold retain their calls to `_append_child_to_epic_children`.

### Decision Rules

- **Section selection**: choose the first non-fenced, unindented H2 whose text is exactly `Children`, allowing horizontal whitespace between `##` and the name and after it. Stop at the next non-fenced H1/H2. Do not treat whitespace as permission to consume another physical line. Other Children headings, aliases, and suffixed headings are left alone; no matching heading means skip.
- **Placement**: before the first non-fenced H3+ heading, find the last eligible top-level `-`/`*` child bullet, with optional bold wrappers and a whole BUG/FEAT/ENH/EPIC ID. Introductory prose and loose-list spacing may precede it. Insert after that bullet and its complete continuations, before its trailing separator blanks. Continuations are lines indented by at least two spaces or a tab, including nested items and blank lines followed by another indented continuation; stop at an unindented nonblank line or heading. Do not split an existing item, including a lazy continuation paragraph: if its extent is ambiguous, reject the pair before writing rather than guessing. If there are no eligible bullets before H3, insert at the beginning of the section before existing prose/H3 content.
- **Spacing**: no new blank line between adjacent child bullets; preserve existing separation from trailing notes/headings, adding one blank line if necessary to keep following prose/headings from becoming a lazy continuation of the new item. Never insert inside a fenced block or between a bullet and its continuation. Preserve LF/CRLF and whether the file ends with a newline. Match backtick and tilde fences by character and closing length using the existing fence utilities.
- **Duplicate detection**: only an actual whole-ID child entry inside the selected Children section counts, including recognized bullet or per-child H3–H6 forms. Ignore fenced examples and mentions elsewhere. A prefix such as `FEAT-1` inside `FEAT-10` or `FEAT-1suffix` does not count.
- **Winner selection**: preserve the existing `(-score, orphan_id, epic_id)` ordering and apply the first pair for each orphan. Equal-score ties therefore follow the existing EPIC-ID order. `applied` lists only selected successful pairs; proposal output still lists every alternative.
- **Existing relationship**: absent/null parent or epic may be filled; a value already equal to the selected EPIC is retained in its original representation. Any non-null conflicting parent/epic rejects that pair before either file changes, names the orphan and conflicting field, and causes a nonzero command result. Do not implicitly reparent. Do not fall through to a lower-ranked alternative after a rejected winner. This check is the **under-lock re-validation** of what `is_orphan()` saw at scan time: on the normal CLI path it fires only when a concurrent writer assigned a parent in between (or a multi-block shadow exists), so it gets one deterministic test (set the conflicting parent after the scan, before apply) and no separate documentation section beyond the `rejected` entry.
- **Locking**: the whole pair (re-read, validate, compute, write) executes inside one `acquire_lock(issue_lock_path(orphan_path, base_dir))`; both files are re-read under the lock, never reused from the scan. Lock timeout rejects the pair with no write.
- **Per-pair failure policy**: continue-and-report. Each rejected pair appends `{"orphan_id", "epic_id", "reason"}` to `rejected` (`reason` one of `conflicting_parent`, `ambiguous_children_section`, `lock_timeout`, `write_failed`, `metadata_unsafe`, plus a human-readable `detail`), prints one stderr line, and the command exits 1 after processing every orphan. `applied` lists only fully successful pairs. A rejected winner never falls through to a lower-ranked EPIC. A pair rejected before any write (everything except `write_failed`) leaves both files byte-identical. This is a flat reason code on failures only, not the broad per-proposal outcome enum declined earlier.
- **Missing heading is visible**: a pair whose EPIC has no exact Children heading still applies the orphan frontmatter and is listed in `applied`, but the apply output (text and JSON `applied[]` entry via an additive `children_wired: false` field) states that the EPIC body write was skipped, so the skip is never silent.
- **Frontmatter safety**: the new helper supports only single-line scalar assignment entries, including null/empty values. Reject multiline/block/collection values and duplicate assignment keys rather than changing only their first line. A same-value reapply preserves the original quote/comment representation. No frontmatter means prepend a minimal block while preserving the body. Unterminated/malformed blocks or conflicts reject the pair before writing. Re-parse the proposed text using the existing merged semantics and require both parent and epic to equal the selected ID; a later block containing null can shadow an update just as a different parent can. Keep exact issue-ID identity rather than silently equating padded IDs, and do not rely on YAML's last-key-wins behavior.
- **Writes**: read without universal-newline conversion; use `atomic_write(..., shared_mode=True)` for changed existing files. Compute/validate both texts first; unchanged texts produce no write. Preserve raw newline offsets in the narrow helper without changing general parser precedence. Write orphan then EPIC (orphan-first is deliberate: a failed EPIC write leaves category-(a) drift, which `epic-consistency --fix` repairs; EPIC-first would leave unrepairable category-(b) drift). If the second write fails, reject the pair as `write_failed` with a message naming the partial pair and the remedy (`ll-issues epic-consistency --fix <EPIC>`). Direct `apply_assignment()` reapply repairs a missing EPIC bullet even when both frontmatter values were already correct; the CLI does not re-propose such an orphan (it is no longer parentless), so docs must state that CLI-level recovery is the epic-consistency fixer, not reapply.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/issues/link_epics.py` — title plumbing, scoped duplicate handling, per-pair lock, preflight/conditional writes, one-winner apply bookkeeping, and `rejected`/continue-and-report handling with exit code 1.
- `scripts/little_loops/cli/issues/create.py` — shared Children helper's placement, three-outcome contract (`None` / unchanged / `AmbiguousChildrenSection`), fence awareness, and source preservation; `create_issue` catches the ambiguous case and skips wiring with a warning, and takes the issue-tree mutation lock around its parent-EPIC append.
- `scripts/little_loops/cli/issues/epic_consistency.py` — no recognizer work needed: `find_children_section`/`iter_child_entries`/`ChildEntry` already landed (`cda52e0eb`); import them from here.
- `scripts/little_loops/frontmatter.py` — add scalar upsert; reuse `_iter_frontmatter_blocks` and `_canonical_frontmatter_block` selection semantics without changing general YAML-dump behavior.

### Dependent Files

- `scripts/little_loops/cli/issues/scaffold_epic.py` imports the create helper; retain its signature and skip behavior, and catch `AmbiguousChildrenSection` per child (warn, skip the EPIC body write for that child, keep creating files).
- `scripts/little_loops/file_utils.py` — consumed only: `acquire_lock` and `issue_lock_path` (same pattern as `cli/issues/link.py`, `set_status.py`, `set_scores.py`). No change.
- `scripts/little_loops/mcp_server/tools.py` reaches the helper through `create_issue`; no MCP API change.
- `scripts/little_loops/cli/issues/epic_consistency.py` reads the resulting bullet format. Its `fix_epic` writer and missing-heading behavior stay out of scope.
- `scripts/little_loops/issues/prose_deps.py` scans child titles/continuations; keep existing title-based subject attribution working.
- BUG-3739 changes upstream candidate filtering and payload reporting in the same command. Coordinate edits and test the combined output; neither fix requires the other to land first.

### Tests

- `scripts/tests/test_link_epics_cli.py` — actual bullet content, body mentions versus membership, first-winner/tie behavior, existing-parent conflicts, missing heading, exact-ID/fence cases, and repeated apply with no writes. Replace whole-file ID-count assertions with assertions on actual child entries; valid titles may repeat an ID.
- `scripts/tests/test_ll_issues_create.py` and `scripts/tests/test_ll_issues_scaffold_epic.py` — shared-helper placement, intro prose before bullets, loose lists, nested/paragraph continuations, ambiguous lazy continuations, prose-only separation, no-heading skip, multi-child creation, and final-newline preservation.
- `scripts/tests/test_frontmatter.py` — absent/null/existing scalar keys, same-value representation, comments/flow lists/wrapped titles/Unicode, multi-block precedence (including later-block null shadowing), multiline/collection/malformed/duplicate metadata rejection, no-frontmatter, and LF/CRLF cases. Apply tests also cover a failed second write (reason `write_failed`, remedy message) and recovery by calling `apply_assignment()` again directly; a CLI-level test asserts the orphan is *not* re-proposed after a partial write and that `epic-consistency --fix` repairs it. Further tests: a conflicting parent set after the scan but before apply is rejected under the lock (single deterministic test, no docs surface); lock `TimeoutError` becomes `lock_timeout` with both files untouched; one rejected pair does not stop later orphans and the exit code is 1 with a populated `rejected` list; the no-heading apply output flags `children_wired: false`; `create_issue` and `scaffold_epic` on an ambiguous Children section still create the child file and warn; `create_issue`'s parent-EPIC append holds the mutation lock (a held lock makes it wait and then time out, without leaving a partial write).
- `scripts/tests/test_epic_consistency.py`, `scripts/tests/test_link_epics_skill.py`, and `scripts/tests/test_prose_deps.py` — consumer regression coverage. Assert observable output; a source-text ban on the placeholder is unnecessary.

### Documentation

Update `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/reference/COMMANDS.md`, and `skills/link-epics/SKILL.md` for one-winner apply, title bullets, no-heading skip (and its visible `children_wired: false` flag), the `rejected` list with continue-and-report and exit code 1, and the truthful recovery story (partial writes are repaired by `ll-issues epic-consistency --fix`, not by re-running link-epics). The skill must also stop suggesting a threshold as a way to pick a non-top EPIC for an orphan (one-winner makes that impossible); say a different EPIC requires a manual edit. A parent-assignment option for `ll-issues link` would close that gap and is tracked as follow-up, not part of this issue. The skill currently promises every above-threshold pair is applied; revise that promise. Do not claim a score threshold can represent an arbitrary user-selected subset. Keep this issue to truthful documentation of the existing CLI; adding pair-selection flags is separate work.

Check child-wiring instructions in `skills/capture-issue/SKILL.md` for agreement with the selected skip/placement contract. Regenerate affected host mirrors with `ll-adapt` when skill text changes; use the repository's mirror gates. Add API documentation for the new scalar helper.

### Configuration

No new setting, dependency, or host invocation.

## Implementation Steps

1. Add temporary-tree regressions for the observed placement/churn/duplicate defects and two-EPIC contradictory assignment.
2. Adopt the already-landed shared Children recognizer (`find_children_section`/`iter_child_entries` in `epic_consistency.py`, `cda52e0eb`); no prerequisite commit is needed. Improve the existing shared Children helper according to the Decision Rules (three outcomes; create/scaffold catch the ambiguous case) and wire apply's title/duplicate behavior to it.
3. Add preserving scalar upsert and preflight both sides inside the per-pair lock; reject conflicting metadata, preserve modes/newlines, and skip identical writes.
4. Keep all proposed alternatives but apply only the first ranked pair per orphan. Add continue-and-report with the `rejected` list, `children_wired`, and exit code 1; update result bookkeeping and user-facing contracts.
5. Run the focused tests above, then the authoritative `python -m pytest scripts/tests/`, lint and type checks for changed Python, and mirror checks when skill text changes.

## Acceptance Criteria

- [ ] Applied bullets use the actual title in the standard `(open)` form; no placeholder is emitted. Frontmatter/H1/filename fallbacks and a title containing its own ID are covered.
- [ ] Flat, empty, prose-only, wrapped/multi-paragraph, subsection, noncanonical bullet, sub-EPIC, fenced example, duplicate-heading, and absent-heading shapes obey the specified placement/skip rules without disturbing existing content.
- [ ] Exact child entries suppress duplicates; prose/frontmatter/other-section mentions and partial IDs do not. Reapply leaves both files byte-identical and invokes no writer for unchanged content.
- [ ] Orphan bytes outside updated parent/epic entries, LF/CRLF style, final newline, and existing file modes are preserved. Null, missing, already-correct, malformed, duplicate-key, and multi-block inputs have explicit tests.
- [ ] Each pair applies under the issue-tree lock with both files re-read under it; lock timeout, ambiguous Children sections, conflicting metadata, and write failures reject only that pair (listed in `rejected`, exit 1) while later orphans still apply. The no-heading skip is visible in apply output. Create/scaffold never fail over an ambiguous Children section.
- [ ] Docs state the real recovery path (`epic-consistency --fix`) and no document or skill claims that re-running `link-epics --apply` repairs a partial write.
- [ ] The shared Children recognizer exists once (in `epic_consistency.py`; already landed in `cda52e0eb`) and is used by this writer, BUG-3739's reader/index, and the consistency checker.
- [ ] With multiple matches, only the highest-ranked EPIC is applied/listed for each orphan; ties are deterministic and all alternatives remain in `proposals`. Existing conflicting relationships cause no writes for the rejected pair and a visible nonzero result.
- [ ] Create/scaffold/MCP child wiring retains the no-heading contract; the focused regression suites and full local test suite pass, with docs and skill mirrors describing the final behavior.

## Impact

- **Priority**: P3 — normal issue organization is affected; metadata churn and contradictory parent links make repeated automated application unreliable.
- **Effort**: Medium — two preserving text transforms plus command-level selection and consumer tests; no new framework is needed.
- **Risk**: Medium — a shared writer affects create/scaffold, and apply's parent selection changes. Explicit parity rules and end-to-end fixtures bound those risks.
- **Breaking Change**: Yes, limited to defective apply behavior: multiple alternatives no longer all write, and existing conflicting relationships are rejected. Proposal payload fields and scoring stay compatible.

## Review Notes

**Review verdict: CORRECTED — ready for implementation.** Format, concrete program design, and unresolved-decision gates pass. No open dependency is required between these issues.

2026-10-05: Reconciled the earlier refine/wire/decision findings into one directive specification. Verified on `main`; temporary-file reproductions confirmed misplaced placeholders, lost flow style/comments, prose-mention suppression, and lowest-score overwrite. They did not confirm the reported wrapped-bullet split. Existing relevant suites passed: **235 tests** across link-epics, create, scaffold, consistency, frontmatter, and skill tests. These establish a baseline, not proof that the proposed fix exists.

Used `/ll:advise --signal user_requested --host claude-code --model opus` for critique (confidence **0.76**). Adopted its prose-separation, merged-result validation, scalar-only safety, and partial-write tests. Kept the selected missing-heading skip and bounded single-winner fix. Advisor dissent concerned ties, CRLF scope, and whether the other issue should depend on this one: retain deterministic existing tie order, preserve bytes at these write sites, and keep the two issues independently implementable. Numeric-ID normalization and a broad per-proposal outcome enum are outside this change.

2026-10-05 (second pre-implementation review, with `/ll:advise --signal user_requested --host claude-code --model fable`, confidence **0.82**): verified in code that `is_orphan()` makes the conflicting-parent path race-only, that `apply_assignment()` is the only issue mutator without `acquire_lock(issue_lock_path(...))`, that orphan-first ordering means CLI reapply cannot recover a partial write, and that the shared helper had a single `None` channel for several outcomes. Adopted: honest recovery story (orphan-first retained; fixer is `epic-consistency --fix`), per-pair lock with under-lock re-validation (kept in this issue — one wrapper plus one test; split into its own ENH if it grows, and cover `fix_epic` there), continue-and-report with a flat `rejected` reason list, three-outcome helper contract with create/scaffold never failing over wiring, visible no-heading skip, and a single shared Children recognizer landed by whichever of this issue/BUG-3739 goes first (serial landing, not parallel). Follow-up not in scope: a parent-assignment option for `ll-issues link` (single-pair assignment and the remedy for children-listed drift). Advisor dissent (lock may belong in its own issue since `fix_epic` shares the gap) is handled by the split-if-it-grows condition. Confidence/outcome scores predate these edits; re-run `/ll:confidence-check` before implementation.

---

## Resolution

- **Action**: fix
- **Completed**: 2026-10-05
- **Status**: Completed

### Changes Made
- `scripts/little_loops/frontmatter.py`: new `upsert_frontmatter_scalars()` — span-preserving single-line scalar upsert bounded to the canonical block (CRLF-safe, rejects multiline/duplicate/shadowed entries).
- `scripts/little_loops/cli/issues/create.py`: `_append_child_to_epic_children()` rewritten on the shared `find_children_section`/`iter_child_entries` recognizer (three outcomes, `AmbiguousChildrenSection`, placement before subsections, byte/newline-preserving); `create_issue` wraps the parent-EPIC append in the issue-tree lock, writes with `atomic_write(shared_mode=True)`, and tolerates ambiguous sections.
- `scripts/little_loops/cli/issues/scaffold_epic.py`: tolerates `AmbiguousChildrenSection` (warn + skip body write).
- `scripts/little_loops/cli/issues/link_epics.py`: `apply_assignment()` now locked per pair, title bullets, conflict rejection, preserving writes, no-op reapply; `cmd_link_epics` applies one winner per orphan with continue-and-report (`rejected` key, `children_wired: false`, exit 1).
- Tests: `test_frontmatter.py`, `test_ll_issues_create.py`, `test_link_epics_cli.py`.
- Docs: `docs/reference/{CLI,API,COMMANDS}.md`, `skills/link-epics/SKILL.md`.

### Deviations
- `apply_assignment()` returns `bool` (children wired) rather than `None`, so the CLI can flag `children_wired: false`.
- `skills/capture-issue/SKILL.md` Phase 4c (manual update-existing path) still describes inserting a missing `## Children` section; left unchanged, as it is a separate hand-edit path, not the `create --parent` helper.

### Verification Results
- Tests: PASS for all touched suites; full suite 28418 passed, 1 failed (`test_verify_evidence` corpus gate on ENH-3700, untouched file) and 8 errors (`test_libsql_integration` live-endpoint tests) — both unrelated to this change
- Lint: PASS
- Types: PASS

## Status

**Completed** | Created: 2026-10-05 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-05_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE

Re-scored after the second pre-implementation review, which added the lock, `rejected`, the three-outcome helper and the shared recognizer.

### Concerns
- Corrected during this check: the spec claimed that a concurrent `create --parent` cannot interleave with apply. That was false, because `create_issue`'s parent-EPIC append runs outside the mutation lock and uses plain `write_text`. The Locking paragraph now puts that append under the same lock, outside `.id-alloc.lock` and never nested in it. The change is small, but it widens the lock's footprint past "one wrapper".

### Outcome Risk Factors
- Deep per-site complexity: the byte-preserving scalar upsert, the fence-aware placement grammar with its lazy-continuation rejection, and the per-pair lock with re-read under it are each new logic that shares state across functions.
- Wide blast radius: the shared `_append_child_to_epic_children()` helper feeds `create_issue` (CLI and MCP), `scaffold_epic` and `link-epics`, and the shared recognizer refactor repoints `epic_consistency`'s readers. A placement or newline regression would affect all of them. Mitigation: land the recognizer as its own prerequisite commit, then the helper with its create/scaffold tests, then apply.
- Broad change footprint (~10 sites): four source files, plus CLI.md, API.md, COMMANDS.md, the `link-epics` and `capture-issue` skills, and their host mirrors. Mitigation: run the `ll-adapt` mirror gates after skill edits.
- Coordination with BUG-3739 in the same command (candidate filtering and payload keys in `cmd_link_epics`): land serially and test the combined output.

## Session Log
- `/ll:manage-issue` - 2026-10-06T00:05:57 - `fc42cbbf-006d-4634-929d-b960b7ebdf31.jsonl`
- `/ll:ready-issue` - 2026-10-05T23:49:31 - `f8067c93-8b28-43bf-a1c4-30200a4c6f5b.jsonl`
- `/ll:confidence-check` - 2026-10-05T23:26:53 - `dfedb32a-de04-4382-86b8-3c6cab5d9da5.jsonl`
- `/ll:confidence-check` - 2026-10-05T21:03:15 - `a064a912-bbb2-49a6-9207-e4cd54b3663a.jsonl`
- `/ll:ready-issue` - 2026-10-05T20:18:56 - `3e2de759-3a68-4bde-a95a-631efbd7d020.jsonl`
- `/ll:verify-issues` - 2026-10-05T20:12:03 - `a57c7663-4e50-4ae2-b421-f80e0bc409b6.jsonl`
- `/ll:verify-issues` - 2026-10-05T19:31:15 - `c39a9b88-efc2-4837-8447-c4c6f8c5acb5.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-05T19:28:04 - `2e17f620-0f9e-4bd7-92e3-c417d5338f4a.jsonl`
- `/ll:verify-issues` - 2026-10-05T19:22:16 - `c19d01fe-ea18-43c7-87be-75e6ac5814be.jsonl`
- `/ll:wire-issue` - 2026-10-05T19:20:19 - `4d2fe865-6096-4837-afde-ff1ae6f6247a.jsonl`
- `/ll:decide-issue` - 2026-10-05T19:14:48 - `58840838-a80a-43b5-a8f1-a715c24cacdc.jsonl`
- `/ll:refine-issue` - 2026-10-05T19:10:34 - `b3247adb-4297-48f8-b282-e67dbd158ed2.jsonl`
