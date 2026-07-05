---
id: BUG-2480
title: '`ll-issues list --group-by epic` renderer filters out nested `type: EPIC`
  children, leaving the visible list inconsistent with the `(N/total done)` counter'
status: done
priority: P2
type: BUG
captured_at: '2026-07-04T20:52:25Z'
completed_at: '2026-07-05T16:16:47Z'
discovered_date: 2026-07-04
discovered_by: capture-issue
decision_needed: false
learning_tests_required: []
max_refine_count: 3
relates_to:
- BUG-2441
labels:
- issues
- cli
- group-by-epic
- captured
confidence_score: 96
outcome_confidence: 88
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 24
score_change_surface: 22
---

# BUG-2480: `ll-issues list --group-by epic` renderer filters out nested `type: EPIC` children, leaving the visible list inconsistent with the `(N/total done)` counter

## Summary

`ll-issues list --group-by epic` reports a per-EPIC denominator that includes the EPIC's full transitive descendant set, but the children listed beneath each EPIC heading are filtered to exclude any child whose own `type` is `EPIC`. The result is a counter and a visible list that don't agree: e.g. `EPIC-2451: ... (2) (0/4 done)` next to only two FEAT rows, with two nested EPIC rows (EPIC-2447, EPIC-2449) silently missing from the rendering but present in the `4`.

BUG-2441 previously aligned the counter and the list on **transitive descendant membership** — it did *not* address the renderer-side `type != "EPIC"` filter that is the remaining source of disagreement in the current case.

## Current Behavior

Concrete example from this repository:

```
$ ll-issues list --group-by epic
...
EPIC-2451: Per-EPIC integration branch strategy (decomposed from FEAT-2339) (2) (0/4 done)
  P3  FEAT-2448  per-EPIC integration branch — worker_pool + merge_coordinator wiring
  P3  FEAT-2450  per-EPIC integration branch — CLI flags, TUI surface, docs, templates parity
```

EPIC-2451's four `parent: EPIC-2451` children in `.issues/` are:

| ID | Type | File | Shown? |
|---|---|---|---|
| FEAT-2448 | FEAT | `features/P3-FEAT-2448-…wiring.md` | yes |
| FEAT-2450 | FEAT | `features/P3-FEAT-2450-…cli-tui-docs-templates.md` | yes |
| EPIC-2449 | EPIC | `epics/P3-EPIC-2449-…completion-flow.md` | **no** |
| EPIC-2447 | EPIC | `epics/P3-EPIC-2447-…config-and-resolver.md` | **no** |

The `(0/4 done)` counter reflects all four; the renderer shows only the two non-EPIC children. There is no indication in the output that the EPIC-typed children exist or how to find them.

## Expected Behavior

The counter and the rendered children must use the same descendant set. See **Decision** below for the chosen policy.

## Decision

**Selected: policy (a)** — render nested EPIC children as a `### Sub-EPICs (k)` sub-section beneath the parent EPIC heading, with each sub-EPIC carrying its own `(j/m done)` rollup computed via `compute_epic_progress(sub_id, _all_issues)`.

Rationale:

- **Preserves information** — no nested EPIC is silently dropped; the visible list accounts for every contribution to the parent's counter.
- **Aligns with `ll-issues epic-progress`** — `compute_epic_progress` (`scripts/little_loops/issue_progress.py:83-147`) already returns a transitive child set type-agnostically; the badge path was already correct under that contract, so policy (a) is the smaller and more consistent change than re-defining `compute_epic_progress` to take an `exclude_types` parameter for policy (b).
- **Information-rich rollups** — sub-EPICs get their own `(j/m done)` so users see progress *within* a nested EPIC without needing to invoke `ll-issues epic-progress <sub_id>` manually.
- **Dedup invariant is satisfied** — `_find_epic_ancestor` (`list_cmd.py:173-181`) walks up the parent chain until it hits *any* prefix-EPIC ancestor, so a grandchild is bucketed under the outer EPIC (not also under the sub-EPIC heading); the sub-EPIC's rollup handles its own grandchildren.

Rejected: policy (b) — would require either a new `exclude_types={"EPIC"}` parameter on `compute_epic_progress` or a duplicated descendant walk in `list_cmd`, and would discard information already present in the codebase.

## Steps to Reproduce

1. In a project with `ll-issues` configured, create three issues where:
   - EPIC-P has `parent:` blank (or `parent: null`).
   - FEAT-F has `parent: EPIC-P` and `type: FEAT`.
   - EPIC-Q has `parent: EPIC-P` and `type: EPIC`.
   - EPIC-R has `parent: EPIC-P` and `type: EPIC`.
2. Run `ll-issues list --group-by epic`.
3. Observe: the heading for EPIC-P reads `(N) (0/3 done)` while only FEAT-F is rendered below.

Real-world reproduction in this repo: `EPIC-2451` (or any EPIC with a `parent:` pointing to nested EPICs).

## Root Cause

- **File**: `scripts/little_loops/cli/issues/list_cmd.py` (confirmed — `group_by == "epic"` branch)
- **Anchor**: `cmd_list`, lines 183–190 (bucket-build loop) — *not* a `IssueType.EPIC` enum reference; the codebase uses bare string prefix checks. The offending line is 185: `if issue.issue_id.split("-", 1)[0] == "EPIC": continue`
- **Cause**: two filters in the same render path disagree about which descendants belong to the EPIC's bucket. The counter loop (lines 200–205, source of the `(N/total done)` denominator) uses the full transitive descendant set resolved by `compute_epic_progress(epic_key, _all_issues)` — type-agnostic, walks the parent chain upward via `_issue_descends_to()`. The children-rendering loop at lines 184–190 (the bucket-build loop) applies a separate `prefix == "EPIC"` filter that *unconditionally* drops any EPIC-typed issue from `parent_buckets` — never reaches `_find_epic_ancestor`. BUG-2441's fix aligned the counter with the bucket but did not touch the renderer's type filter. There is no `IssueType` enum in the codebase (`grep -r "IssueType\.EPIC"` in `scripts/little_loops/` returns 0 hits); the type check is purely an ID-prefix string compare, conflating "EPIC root" with "any EPIC-typed descendant".

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The full divergent site (verified at `scripts/little_loops/cli/issues/list_cmd.py:184-238`):

```python
# Bucketing (lines 183-190) — EXCLUDES nested EPICs
parent_buckets: dict[str | None, list] = {}
for issue, stat in issues_with_status:
    if issue.issue_id.split("-", 1)[0] == "EPIC":     # ← BUG-2480 anchor
        continue
    key = _find_epic_ancestor(issue.issue_id)
    if key not in parent_buckets:
        parent_buckets[key] = []
    parent_buckets[key].append((issue, stat))

# Counter (lines 196-205) — INCLUDES nested EPICs via transitive walk
epic_progress_cache: dict[str, tuple[int, int, int]] = {}
if named_keys:
    from little_loops.issue_progress import compute_epic_progress
    for epic_key in named_keys:
        prog = compute_epic_progress(epic_key, _all_issues)
        if prog is not None:
            done = prog.by_status.get("done", 0) + prog.by_status.get("cancelled", 0)
            blocked = prog.by_status.get("blocked", 0)
            epic_progress_cache[epic_key] = (done, len(prog.children), blocked)
```

The bucket is also used for the `(len(group))` header count at line 222 (`label = f"{base_label} ({len(group)}){badge}"`), the row iteration at line 226 (`for issue, stat in group`), and the footer at line 240 (`displayed = sum(len(g) for g in parent_buckets.values())`) — so the same divergence propagates to three display points beyond the badge.

`compute_epic_progress` (`scripts/little_loops/issue_progress.py:83-147`) builds its child set at lines 106-113 with a type-agnostic parent_map walk:

```python
parent_map: dict[str, str] = {i.issue_id: i.parent for i in all_issues if i.parent}
child_ids: set[str] = {
    i.issue_id
    for i in all_issues
    if i.issue_id != epic_id and _issue_descends_to(i.issue_id, epic_id, parent_map)
}
```

No `IssueType` or prefix check occurs in this resolution — confirmed by reading the function verbatim. Nested EPIC descendants are included in `prog.children`, contributing to both the denominator `total = len(prog.children)` and the `done` numerator.

**Note — name correction**: this issue text previously referenced a helper named `_issue_descendants_of`. That name does not exist anywhere in the codebase. The canonical helper introduced by BUG-2441 is `_issue_descends_to(issue_id, epic_id, parent_map) → bool` at `scripts/little_loops/issue_progress.py:67-80`. See the **Integration Map** section for the corrected references.

## Proposed Solution

Apply policy (a) (selected — see Decision above) consistently in `cmd_list`:

1. Keep the counter loop untouched (already correctly bucketed transitively via `compute_epic_progress` which resolves descendants via `_issue_descends_to(issue_id, epic_id, parent_map)` at `scripts/little_loops/issue_progress.py:67-80`).
2. Remove the `if issue.issue_id.split("-", 1)[0] == "EPIC": continue` filter at `list_cmd.py:185` so all issues (including EPIC-typed) enter `_find_epic_ancestor()` and get bucketed under their ancestor EPIC.
3. After rendering leaf children under each EPIC heading, add a `### Sub-EPICs (k)` sub-section listing every nested EPIC descendant. Each sub-EPIC row should carry its own `(j/m done)` rollup computed the same way `cmd_epic_progress` does (`scripts/little_loops/cli/issues/epic_progress.py:38-76` is the working precedent — it already passes `_ALL_STATUSES` to `find_issues` and walks transitively).
4. Add the explicit invariant comment in `cmd_list` next to the bucketing loop: *"Children membership for an EPIC heading MUST agree between the `(N/total done)` counter and the children list below it."*

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The badge path (`list_cmd.py:200-205` via `compute_epic_progress`, `issue_progress.py:83-147`) is the authoritative source: it uses a cycle-guarded transitive walk that *excludes no type*, and is already the contract that `ll-issues epic-progress` exposes to users. The bucket-build path (`list_cmd.py:185`) is the disagreement site; its `prefix == "EPIC"` filter has no comment, no test coverage, and no analog elsewhere in the codebase except `epic_consistency.py`'s `_REAL_ISSUE_TYPES` (which serves a different purpose — classifying sub-EPIC body refs, not bucket membership).

The standalone `ll-issues epic-progress <EPIC>` command (`scripts/little_loops/cli/issues/epic_progress.py:38-76`) is already correct: it uses `compute_epic_progress(epic_id, all_issues)` and the denominator matches the visible child rows — strong evidence the badge path is the right invariant to keep and the bucket filter should be revised.

The render loop has a **deduplication invariant that's already correct under policy (a)**: a grandchild issue whose chain is `grandchild → EPIC-2449 → EPIC-2451` will have `_find_epic_ancestor(grandchild_id)` return `EPIC-2451` (the walker walks until the first EPIC prefix). So the grandchild is bucketed under `EPIC-2451`, not under `EPIC-2449`'s sub-section. The `### Sub-EPICs (k)` section under `EPIC-2451` will only contain the immediate nested EPICs (`EPIC-2449`, `EPIC-2447`) as rows; each row's `(j/m done)` rollup (via `compute_epic_progress(sub_id, _all_issues)`) reports the sub-EPIC's own grandchildren. This matches the BUG-2441 contract and what users intuitively expect.

The `epic_progress_cache` loop at `list_cmd.py:200-205` currently iterates only `named_keys` (i.e., the EPICs that already appear as bucket headings). Under policy (a), to give each sub-EPIC its own `(j/m done)` rollup inline in the sub-section, either: (1) extend the cache loop to include sub-EPICs as it discovers them in the render pass; or (2) call `compute_epic_progress(sub_epic_id, _all_issues)` per-row in the sub-section emission. Both are O(N·D) where D is parent-chain depth (cycle-guarded, bounded). Option (2) is simpler and keeps the cache size predictable; option (1) is preferred if rendering speed becomes a concern.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/list_cmd.py` — fix the divergent filter in the `group_by == "epic"` branch of `cmd_list` (lines 183–190 in `cmd_list`).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_history/__init__.py`, `scripts/little_loops/issue_history/models.py`, `scripts/little_loops/issue_history/quality.py`, `scripts/little_loops/history_reader.py` — recently modified per `git status`. **Research finding**: `grep -r "_find_epic_ancestor\|_parent_map\|group_by_epic\|nested" scripts/little_loops/issue_history/` returned zero matches in `parsing.py`/`analysis.py`/`summary.py`/`quality.py`/`models.py`. The only history-adjacent usage is `_group_by_period` in `summary.py:85` (unrelated period-bucketing helper for history windows). The `--group-by epic` grouping logic is **not** surfaced via history/analytics — safe to skip updating these modules.
- `scripts/little_loops/issue_progress.py` — *not* modified by the fix, but is the source-of-truth for `compute_epic_progress` and `_issue_descends_to`; policy (a) consumers will call it per-sub-EPIC for rollups.
- `scripts/little_loops/cli/issues/epic_progress.py` (`cmd_epic_progress`) — already calls `compute_epic_progress(epic_id, all_issues)`. **Research finding**: confirmed that the standalone `ll-issues epic-progress <EPIC>` command correctly counts nested-EPIC descendants via the same transitive walk. The bug is *only* in `--group-by epic`'s bucket filter.

### Similar Patterns
- BUG-2441 introduced `_issue_descends_to(issue_id, epic_id, parent_map) → bool` at `scripts/little_loops/issue_progress.py:67-80` — a cycle-guarded transitive walk. **The original issue text referenced `_issue_descendants_of`; that name does not exist. Use `_issue_descends_to`.** Same cycle-defense shape (`seen: set[str] = set()`) as the in-function `_find_epic_ancestor` closure at `list_cmd.py:173-181`.
- BUG-2382 fixed `_parent_map` being built from status-filtered sets (`list_cmd.py:171`); the bucket-build at `list_cmd.py:185` is a sibling class of that issue — two paths to the same EPIC, disagreeing on membership.
- BUG-2441's existing test pattern in `scripts/tests/test_issue_progress.py:244-274` (`TestComputeEpicProgress.test_transitive_chain_includes_grandchildren`) is the canonical transitive-rollup test model — but tests the rollup helper, not the renderer; BUG-2480 needs a renderer-level fixture too.
- `epic_consistency.py:_REAL_ISSUE_TYPES` (`scripts/little_loops/cli/issues/epic_consistency.py:25`, `sub_epic_advisory` at lines 121-131) is the only module that uses a `_REAL_ISSUE_TYPES = {"BUG","FEAT","ENH"}` classification to distinguish nested EPICs. **Note**: this conflicts with the proposed fix direction (policy (a) wants nested EPICs visible too). Document this divergence so a future cleanup can harmonize.
- `sprint.py:321-331` resolves EPIC membership via **direct** `info.parent == epic_id` only — docs (`docs/reference/CLI.md`) already call this out as a known gap (FEAT-2339). Different traversal depth is independently maintained.

### Tests
- `scripts/tests/test_issues_cli.py` — primary test surface; BUG-2382 precedent at lines 184-202 (`issues_dir_with_completed_intermediate` fixture) and lines 963-994 (`test_list_group_by_epic_completed_intermediate_parent`) show the layered-fixture pattern. Add:
  - `issues_dir_with_nested_epic` fixture — composes on `issues_dir_with_epic`, drops in two EPIC files with `parent: EPIC-001`. Models the structure described in EPIC-2449's in-flight test plan.
  - `test_list_group_by_epic_with_nested_epic_children` — assert both EPIC-002 and EPIC-003 appear in the rendered output **and** that the `(N)` count matches the badge denominator.
  - `test_list_group_by_epic_nested_badge_consistency` — strict assertion: `Total` footer count + leaf rows + sub-EPIC rows == badge denominator.
- `scripts/tests/test_issue_progress.py:244-274` — already covers transitive rollup; no new test needed there for the renderer fix, but reference BUG-2480 from the existing `test_transitive_chain_includes_grandchildren` docstring to indicate the fix is complete.
- `scripts/tests/test_cli_output.py` (`TestIssueListNoColor.test_no_color_produces_plain_text`) — per `EPIC-1727` research, builds a bare `argparse.Namespace` and may need `group_by="type"` added; unrelated to BUG-2480 but worth flagging if the test surface is touched.
- **No test changes needed** in `test_issue_history_advanced_analytics.py` or `test_issue_history_formatting.py` — the renderer is not surfaced through the history/analytics entry points (see Dependent Files above).

### Documentation
- `docs/reference/CLI.md` — `--group-by` flag row at line 1026 and the `ll-issues epic-progress` semantics note at line 1538 (which references BUG-2441's transitive-rollup fix). Add a sentence clarifying that with `--group-by epic` the denominator is **transitive descendants including nested EPICs** (per chosen policy).
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — `--group-by epic` usage section at lines 482-491; clarify the nested-EPIC visibility policy.
- `docs/reference/API.md` — under the epic grouping / `ll-issues list` section, document the chosen policy (a vs b) and the meaning of `(N/total done)`.
- **Existing references to update in `CHANGELOG.md`**: confirm the next entry references BUG-2480 with the chosen policy.

### Configuration
- N/A (no `ll-config.json` key needed).

## Implementation Steps

1. Locate the `group_by == "epic"` branch in `cmd_list` at `list_cmd.py:153-242`. The offending filter is `list_cmd.py:185` (`if issue.issue_id.split("-", 1)[0] == "EPIC": continue`). The render loop following the bucket-build is at `list_cmd.py:207-238`, with the footer line at `list_cmd.py:240` — all three places derive from `parent_buckets` and must be fixed together.
2. Remove the `continue` at `list_cmd.py:185` so all issues (including EPIC-typed) enter the bucketing loop and `_find_epic_ancestor()` resolves their parent EPIC (note: `_find_epic_ancestor` walks until it hits *any* prefix-EPIC ancestor; for an EPIC whose `parent:` is another EPIC, the walker will return the outer EPIC — confirmed).
3. In the render loop (`list_cmd.py:226-237`), split `parent_buckets[key]` into leaves (`prefix != "EPIC"`) and sub-EPICs (`prefix == "EPIC"`). Render leaves first as `for issue, stat in leaves` using the existing row format. Then add a `### Sub-EPICs (k)` sub-section header and render each sub-EPIC as its own colored row carrying its `(j/m done)` rollup via `compute_epic_progress(sub_epic_id, _all_issues)` — the same call already used in `epic_progress_cache` at `list_cmd.py:200-205`. Consider extending the cache loop to iterate over all sub-EPICs, or call `compute_epic_progress` inline per sub-EPIC in the render loop.
4. Update the header `(len(group))` count at `list_cmd.py:222` to reflect the union (leaves + sub-EPICs), matching the badge denominator. Update the footer at `list_cmd.py:240` likewise (`displayed = sum(len(parent_buckets[k]) for k in parent_buckets)` — same sum, but now inclusive of nested EPICs).
5. Add the explicit invariant comment above the bucketing loop: *"Children membership for an EPIC heading MUST agree between the `(N/total done)` counter and the children list below it."*
6. **Deduplication concern**: a grandchild under a nested EPIC will have `_find_epic_ancestor` walk up through the nested EPIC and resolve to the outer EPIC (e.g. EPIC-2451) — so it's bucketed once under the outer EPIC, NOT also under the sub-EPIC heading. This is correct: the sub-EPIC's own `(j/m done)` rollup (via `compute_epic_progress(sub_epic_id, _all_issues)`) reports its grandchildren's progress; the sub-EPIC *heading* just links the sub-EPIC as a row under its parent. Confirmed via `_find_epic_ancestor`'s walk semantics at `list_cmd.py:173-181`.
7. Update `test_issues_cli.py` with: (a) an `issues_dir_with_nested_epic` fixture that composes on `issues_dir_with_epic` (per BUG-2382 precedent at `test_issues_cli.py:184-202`), adding two EPIC files with `parent: EPIC-001`; (b) `test_list_group_by_epic_with_nested_epic_children` asserting both visible rows and badge consistency; (c) a regression test of the invariant ("`Total:` footer count + sub-EPIC rows + leaf rows == badge denominator").
8. Run `python -m pytest scripts/tests/` (full suite — required by the project's CI policy; no hosted CI per `CLAUDE.md`).
9. Re-run `ll-issues list --group-by epic` against `EPIC-2451` and confirm: (a) the `(0/4 done)` counter and the rendered list agree, (b) `EPIC-2449` and `EPIC-2447` appear as `### Sub-EPICs (2)` rows under `EPIC-2451`.

## Impact

- **Priority**: P2 — primary listing command reports inconsistent numbers, undermining trust in the EPIC rollup display; matches the severity of BUG-2382 and BUG-2441, both P2/P3 fixes.
- **Effort**: Small — one filter line, one helper-call site, one test; bounded by the `cmd_list` function.
- **Risk**: Low — the change is confined to a single renderer's filtering logic; downstream consumers (analytics, quality, history_reader) already use the same descendant helper that BUG-2441 introduced.
- **Breaking Change**: No — purely a display fix; existing consumers of `(N/total done)` semantics already see the same set post-fix.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`issues`, `cli`, `group-by-epic`, `captured`

## Session Log
- `/ll:refine-issue` - 2026-07-04T21:01:29 - `8076ccee-55b0-4c2b-bd39-0509e3000fe3.jsonl`

- `/ll:capture-issue` - 2026-07-04T20:52:25Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/61b30d3c-623f-46ff-a1cd-ae56b1edb94e.jsonl`

- Decision recorded (policy (a) selected) - 2026-07-04 - flagged `decision_needed: false`; rationale captured in `## Decision` section above.

- `/ll:manage-issue` - 2026-07-05T16:16:47Z - `e235f9e8-00b4-4cc3-8140-9c3d933bb246.jsonl`

## Resolution

Fixed in `scripts/little_loops/cli/issues/list_cmd.py` (`cmd_list`, `group_by == "epic"` branch), following the selected policy (a) with one refinement discovered during implementation:

- Removed the unconditional `if issue.issue_id.split("-", 1)[0] == "EPIC": continue` filter. The bucket-build loop now computes `key = _find_epic_ancestor(issue.issue_id)` for every issue first, and only skips an issue when `key is None` **and** it is itself EPIC-typed — i.e. a root EPIC with no EPIC ancestor. This avoids a regression the literal "remove the filter unconditionally" instruction would have introduced: a root EPIC (e.g. `EPIC-001` with no `parent:`) would otherwise land in the `Unparented` bucket as a spurious duplicate row, since it already owns its own heading elsewhere in the output. Nested EPICs (an EPIC whose `_find_epic_ancestor` resolves to another EPIC) are unaffected by this guard and now enter their ancestor's bucket as intended.
- Each EPIC bucket's members are split into `leaves` (non-EPIC) and `sub_epics` (EPIC-typed) at render time. Leaves render as before; if `sub_epics` is non-empty, a `Sub-EPICs (k)` sub-section follows, with each row carrying its own `(j/m done)` rollup computed via a per-key `compute_epic_progress` call (cache extended to cover every EPIC ID appearing as a bucket member, not just named headings).
- The header `(len(group))` count and the footer `displayed` sum are unchanged in shape — both now naturally include nested EPICs since they're real bucket members — but the footer text changed from `"(excluding EPICs)"` to `"(including nested EPICs)"` since it's no longer literally true that EPICs are excluded.
- Added `issues_dir_with_nested_epic` fixture and two tests (`test_list_group_by_epic_with_nested_epic_children`, `test_list_group_by_epic_nested_badge_consistency`) to `scripts/tests/test_issues_cli.py`, following TDD: both failed with plain assertion errors against the pre-fix code, then passed after the fix. Full suite: 13721 passed, 27 skipped.
- Updated `docs/reference/CLI.md` (`--group-by` flag row + the BUG-2441 rollup-semantics callout) and `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` (`--group-by epic` section) to describe the Sub-EPICs rendering. Skipped `docs/reference/API.md` — it's an auto-generated per-module reference with no existing `issue_progress`/`list_cmd` section to anchor a prose policy note; the CLI docs already cover the user-facing contract. Skipped a `CHANGELOG.md [Unreleased]` entry per this project's policy of not adding per-issue changelog entries there (promoted at release-prep time instead).

---

## Status

**Done** | Created: 2026-07-04 | Priority: P2
