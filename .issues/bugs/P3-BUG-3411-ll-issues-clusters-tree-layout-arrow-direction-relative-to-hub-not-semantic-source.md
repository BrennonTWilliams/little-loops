---
id: BUG-3411
type: BUG
title: 'll-issues clusters tree layout: arrow direction relative to hub, not semantic
  source'
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-08'
captured_at: '2026-09-08T19:25:17Z'
completed_at: '2026-09-08T22:16:41Z'
confidence_score: 95
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
decision_needed: false
---

# BUG-3411: ll-issues clusters tree layout: arrow direction relative to hub, not semantic source

## Summary

`ll-issues clusters` in the default `--layout tree` renders the same relationship type
(e.g. `blocked_by`) with opposite arrow glyphs depending on which endpoint of the edge
happens to be the tree's hub/root, even though the legend documents a single fixed
meaning per relationship type.

## Current Behavior

In the default `--layout tree`, `_annot()` computes each edge's arrow glyph relative
to which endpoint is the current tree-walk parent, not the edge's stored `from_id`/
`to_id` semantic direction. When the hub node is the `from_id` for one neighbor and
the `to_id` for another neighbor of the same relationship type, the arrow flips
between `→` and `←` for that same relationship type within one cluster render,
contradicting the fixed meaning documented in `_EDGE_MEANING`.

## Expected Behavior

The same relationship type should always render with the same arrow glyph, reflecting
the edge's fixed semantic direction (`from_id → to_id` as stored in frontmatter),
regardless of which node the tree layout picked as hub/root or which direction the
tree walk is traversing — matching the behavior `--layout list` already has.

## Motivation

`clusters` (default `--layout tree`) is meant to let a reader scan dependency
direction at a glance. A relationship glyph that flips depending on hub selection
undermines the documented legend and can lead a reader to misjudge dependency
direction between issues. It's rendering-only (frontmatter data is unaffected), but
it erodes trust in the tool's default, most-used view.

## Proposed Solution

Make the tree's arrow direction reflect the edge's fixed semantic direction (arrow
always points from `from_id` to `to_id` as stored) instead of direction-relative-to-parent:

```python
def _annot(parent: str, child: str) -> str:
    from_id, _to_id, rel = rel_of[frozenset({parent, child})]
    arrow = "→" if from_id == parent else "←"
    return f"{arrow} {colorize(rel, EDGE_COLOR.get(rel, '37'))}"
```

Derive the arrow from whether the *child* is `to_id`, independent of walk direction —
i.e. always show `from_id → to_id` semantics (e.g. render as `blocked_by →` when the
child is the target), or restructure the label to name both IDs explicitly (e.g.
`blocked_by ENH-3406`) so the same relationship type never flips glyphs within one
cluster. `_render_cluster_compact` (lines 148-177, `--layout list`) already renders
each node's edges from its own fixed perspective and can serve as the reference for
correct fixed-direction semantics.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- The codebase holds a single, consistently-applied convention for directed-edge rendering: derive the arrow/glyph from the edge's own stored `(from_id, to_id)` tuple, never from walk/traversal position. This holds across `_render_cluster_diagram()` (`clusters.py:437-515`, `forward = (a_id, b_id) in edge_map` tests literal tuple membership against `edge_map` built directly from `cd.edges`, with an explicit code comment at `clusters.py:472-474` stating the rule), `_render_cluster_compact()` (`clusters.py:148-177`, iterates `out_edges` keyed by the edge's own `from_id`), `format_text_graph._arrow()` (`dependency_mapper/formatting.py:199-204`, glyph chosen by edge-type membership in a fixed set), `format_epic_tree()` (`dependency_mapper/formatting.py:252-296`, unconditional "blocks" annotation from a fixed `blocker -> blocked` map), and the FSM back-edge renderer (`cli/loop/layout.py:1656-1750`, arrowhead placed by the edge's own `src`/`dst` fields, independent of vertical draw order). `_render_cluster_tree`'s `_annot()` (`clusters.py:210-214`) is the sole renderer in the codebase (among those searched) that instead keys direction off the current DFS walk's `parent` argument, which varies with hub/root selection (`_walk`/root-selection at `clusters.py:224-251`).
- This narrows Confidence Check Notes gap #2 (`_render_cluster_diagram` "also varies its arrow glyph by direction relative to render position"): `_render_cluster_diagram`'s `forward` check tests membership against `edge_map`'s literal stored tuple, not against a per-edge "parent" role — it is fixed-direction, not position-relative, in the same sense the other renderers are. It shares the "anchor to stored edge" pattern with the other four call sites above; it is not a second position-relative outlier alongside `_annot()`.
- No prior bug fix in this codebase addresses this "arrow computed from traversal role" class of bug (searched "arrow direction", "direction relative", "flip arrow", "reversed arrow" repo-wide — no hits beyond an unrelated FSM back-edge fix noted in `CHANGELOG.md:4470`).
- Test idiom for these renderers is literal-substring assertion on rendered arrow/relationship text (e.g. `scripts/tests/test_issues_cli.py::test_compact_renders_one_line_per_issue`, ~line 6007: `assert "[P1] BUG-002  blocked_by→ BUG-001" in captured.out`). No existing test in `test_issues_cli.py` asserts the `←` glyph branch of `_annot()` — a repo-wide search of that file for `←` returns no matches, confirming no current test pins `_annot()`'s reversed-arrow output either way.

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

**Option A**: Confirm the premise is falsified and document, no logic change. `_annot()`'s comparison `arrow = "→" if from_id == parent else "←"` is mathematically equivalent to `arrow = "→" if to_id == child else "←"` — for a two-node edge, `parent`/`child` always partition `{from_id, to_id}`. This means `_annot()` already derives direction from the edge's fixed semantic `from_id`/`to_id`, not from tree-walk position. The observed glyph flip (hub shows `→` for one `blocked_by` edge, `←` for another) reflects the hub genuinely holding opposite `from_id`/`to_id` roles across its two edges — correct output, not a computation defect. Resolve by adding an inline comment on `_annot()` stating this equivalence explicitly, following the direct precedent at `BUG-2519` (`.issues/bugs/P2-BUG-2519-autodev-check-decision-before-size-review-shares-bug-2513-on-success-coupling.md`), where a bug's literal premise was falsified by investigation and the resolution was an additive inline comment documenting the already-correct defensive/fixed-direction behavior, not a redesign or a bare close.

> **Selected:** Option A — root cause premise is falsified (mathematically equivalent to the already-correct fixed-direction form); resolve via documentation, per BUG-2519 precedent, not a logic redesign.

**Option B**: Redesign the label to remove reader ambiguity. Even though the computation is correct, `_annot()`'s bare `→`/`←` glyph requires a reader to already know which node is "parent" in the current tree walk to interpret it — a context no other directed-edge renderer in this codebase requires. `_render_cluster_compact()` (`clusters.py:148-177`) fixes perspective by keying every row off its own node as implicit subject (`blocked_by→ BUG-001`, pinned by `test_issues_cli.py:6007`). `format_epic_tree()` (`dependency_mapper/formatting.py:290-294`) uses a verb-phrase annotation under the blocker's own line (`⮡ blocks FEAT-002`, pinned by `test_dependency_mapper.py:1044-1052`) instead of a bare glyph. Redesign `_render_cluster_tree`'s output to match this established self-perspective/verb-phrase convention — e.g. always render the relationship naming the target explicitly (`blocked_by → ENH-3406`) — so the same relationship type reads unambiguously regardless of hub selection.

### Decision Rationale

**Selected**: Option A — document the falsified premise, no logic change.

**Reasoning**: Direct inspection of `_annot()` (`clusters.py:210-214`, confirmed independently during this decision pass and again by a `codebase-pattern-finder` agent) shows `arrow = "→" if from_id == parent else "←"` is mathematically equivalent to `arrow = "→" if to_id == child else "←"`, since `parent`/`child` always partition the edge's two endpoints `{from_id, to_id}`. `_annot()` therefore already derives its glyph from the edge's fixed semantic direction, not from tree-walk position — the bug as filed does not exist. The reported repro (hub renders `→` for one `blocked_by` edge and `←` for another) is explained by the hub genuinely holding opposite `from_id`/`to_id` roles across the two edges, which is correct output. This codebase has a direct precedent for this exact situation — `BUG-2519`, where an investigation falsified a bug's literal premise (a gate assumed dead was in fact reachable) and the recorded resolution was an additive inline comment documenting the already-correct behavior, not a redesign or a bare close. Option B is a legitimate, separately-motivated UX proposal — this codebase's other directed-edge renderers (`_render_cluster_compact`, `format_epic_tree`) avoid bare directional glyphs in favor of self-perspective/verb-phrase labels — but it changes an existing view's output format for a concern the issue as filed does not raise, and un-pinned output format changes carry more implementation and consistency risk than a documentation-only fix.

**Scoring**:

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 3 | 3 |
| Simplicity | 3 | 1 |
| Testability | 2 | 3 |
| Risk | 3 | 2 |
| **Total** | **11/12** | **9/12** |

**Key evidence**: `clusters.py:210-214` (`_annot()`, the falsified-premise code); `.issues/bugs/P2-BUG-2519-autodev-check-decision-before-size-review-shares-bug-2513-on-success-coupling.md` Decision/Decision Rationale (direct precedent for the resolution form); `clusters.py:148-177` and `dependency_mapper/formatting.py:290-294` (established self-perspective/verb-phrase convention, evidence for Option B's independent merit, not adopted here).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/clusters.py` — `_annot()` (lines 210-214)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/clusters.py` — `_render_cluster_tree()` (calls `_annot()`, root selection at line 248)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/clusters.py:231,241` — `_walk()` closure inside `_render_cluster_tree()` calls `_annot(node, c)` for cross edges (231) and child edges (241) — no edit needed, comment-only fix [Agent 1 finding]
- `scripts/little_loops/cli/issues/clusters.py:674` — `cmd_clusters()` calls `_render_cluster_tree(...)`, the entry point invoking this code path — no edit needed [Agent 1 finding]
- `scripts/little_loops/cli/issues/__init__.py:44,1025` — lazy import and dispatch of `cmd_clusters` — no edit needed [Agent 1 finding]

### Similar Patterns
- `_render_cluster_compact()` (lines 148-177) already renders edges from each node's fixed perspective — use as the reference implementation, no change needed there

### Tests
- No dedicated test file exists for `clusters` tree rendering; add coverage (e.g. `scripts/tests/test_issues_cli.py` or a new `test_clusters_cli.py`) asserting the same relationship type renders with a consistent glyph across both neighbors of a hub

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issues_cli.py::TestIssuesCLIClustersTreeLayout` (lines 5348-5637) — a dedicated test class for `--layout tree` rendering already exists (the claim above that "no dedicated test file exists" is inaccurate); neither `test_tree_multi_root` (5464-5488) nor `test_tree_cross_edge_shown_for_dag` (5490-5527) constructs a hub holding both `from_id` and `to_id` roles for the same relationship type, and a repo-wide search of `test_issues_cli.py` for `←` returns zero hits — no test asserts `_annot()`'s reversed-arrow branch [Agent 1 + Agent 3 finding]
- Add the new pinning test inside `TestIssuesCLIClustersTreeLayout`, following the literal-substring convention at `test_issues_cli.py:6007` (`"blocked_by→"`, `--layout list`/`_render_cluster_compact`) and `test_dependency_mapper.py:1044-1052` (`"⮡ blocks FEAT-002"`) [Agent 3 finding]

### Documentation
- N/A — legend text in `_EDGE_MEANING` already documents the intended fixed semantics; no doc change needed

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- The codebase's other directed-edge renderers derive arrow/label direction by checking membership against the edge's own stored `(from_id, to_id)`, never by comparing to the current traversal node: `_render_cluster_diagram()` (`scripts/little_loops/cli/issues/clusters.py:475-489`, with an explicit comment at `clusters.py:472-474` — "Arrow head direction matches the semantic edge direction, not the topo-sort layout order"), `format_epic_tree()` (`scripts/little_loops/dependency_mapper/formatting.py:252-296`, walks a fixed `blocker → blocked` map), and `format_text_graph._arrow()` (`dependency_mapper/formatting.py:199-204`, tests membership in fixed edge sets). `_render_cluster_tree._annot()` (`clusters.py:210-214`) is the one place in this area that instead compares `from_id == parent`.
- `_annot()`'s existing `rel_of: dict[frozenset[str], tuple[str, str, str]]` lookup (`clusters.py:201,206,212`) already carries the full `(from_id, to_id, rel)` tuple — the fixed direction is already in scope at the call site; `_annot` currently discards `from_id` in favor of comparing to `parent`.
- Caveat: `_render_cluster_tree`'s walk is structurally undirected (bidirectional adjacency, multi-root by degree — `clusters.py:199-206,248`), unlike `format_epic_tree`/`format_text_graph`'s single-root, single-direction walks. Neither is a direct precedent for a bidirectional walk computing arrow direction at each step; `_render_cluster_diagram`'s fixed-direction arrowhead logic is the closest same-file precedent, but it walks a fixed topo-sorted sequence, not a bidirectional adjacency.
- No shared from_id/to_id edge-direction resolver utility exists in the codebase (searched for `resolve_edge_direction`, `edge_of`, `resolve_edge` — only `_resolve_edge_types` matched, which resolves edge-*type* sets, not direction).
- No prior bug fix in this codebase addresses this "arrow flips depending on traversal root" class of bug (searched for "arrow", "semantic direction", "direction relative" — no prior issue or commit found; the only related precedent is the same-file `_render_cluster_diagram` fixed-direction logic above).
- Existing cluster CLI tests (`scripts/tests/test_issues_cli.py::TestClustersCommand`, class starting `test_issues_cli.py:4770`) assert relationship-type presence and edge counts (e.g. `test_tree_multi_root` at `:5464-5488`, `test_tree_cross_edge_shown_for_dag` at `:5490-5527`) but none assert the `→`/`←` glyph's direction against semantic source — confirming no existing regression coverage for this bug. `test_dependency_mapper.py::TestFormatEpicTree` (`:1004-1066`) uses the same literal-substring-assertion convention for direction-labeled output (e.g. `"⮡ blocks FEAT-002"` at `:1052`), which a new clusters regression test could follow.

## Program Design

### Signatures

- `_annot(parent: str, child: str) -> str` — unchanged signature; internal arrow-direction logic changes to key off `to_id` fixed semantics instead of `parent`

### Call Path

`clusters._render_cluster_tree()` -> `clusters._annot(parent, child)`

## Implementation Steps

1. Change `_annot()`'s arrow derivation to depend on the edge's stored `from_id`/`to_id`, not on which side is the current tree-walk `parent`
   > ⚠ Superseded — Option A selected: no logic change, comment-only
2. Verify against the repro case (`ENH-3407` hub with two `blocked_by` edges) that both render the same glyph
3. Add a regression test asserting consistent glyphs for a hub with edges on both sides of the same relationship type
4. Run `--layout list` alongside `--layout tree` on the same cluster to confirm both agree on direction

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add a pinning regression test in `scripts/tests/test_issues_cli.py::TestIssuesCLIClustersTreeLayout` (lines 5348-5637) asserting `_annot()`'s current output for a hub holding both `from_id` and `to_id` roles across two edges of the same relationship type — no existing test in this class covers that case, and none in `test_issues_cli.py` assert the `←` glyph branch
- No caller changes required: `_annot()`'s signature and behavior are unchanged per the selected Option A resolution — `_walk()` (`clusters.py:231,241`), `cmd_clusters()` (`clusters.py:674`), and the `cli/issues/__init__.py:44,1025` dispatch chain need no edits
- No documentation, CLI reference, registration, or config changes required — `docs/reference/CLI.md`, `README.md`, `commands/*.md`, `skills/*/SKILL.md`, and the config schema were searched; none reference `_annot()`'s arrow semantics or claim a known bug here
- Follow the BUG-2519 precedent's comment style — an inline `#` comment block placed directly above the code it clarifies (confirmed live at `scripts/little_loops/loops/autodev.yaml:1342-1349`), opening with the falsified/clarified premise, then the mathematical/structural equivalence, then citing `BUG-3411`

## Impact

- **Priority**: P3 - rendering-only bug in a diagnostic/reporting view; no data corruption, but reduces trust in the default cluster visualization
- **Effort**: Small - single-function fix in `_annot()`, no schema or data changes
- **Risk**: Low - isolated to tree-layout arrow rendering; `--layout list` and underlying frontmatter data are unaffected
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Completed** | Created: 2026-09-08 | Priority: P3 | Completed: 2026-09-08

---

## Resolution

- **Action**: fix (Option A — documentation, no logic change)
- **Completed**: 2026-09-08
- **Status**: Completed

### Changes Made
- `scripts/little_loops/cli/issues/clusters.py:210-217` (`_annot()`): added an inline
  comment documenting that `arrow = "→" if from_id == parent else "←"` is
  mathematically equivalent to keying off `to_id == child` — the arrow already
  reflects the edge's fixed semantic direction, not tree-walk position. No logic
  change, per the Decision Rationale's selected Option A and the BUG-2519 precedent.
- `scripts/tests/test_issues_cli.py::TestIssuesCLIClustersTreeLayout::test_tree_hub_arrow_direction_pinned_to_semantic_source`:
  new regression test pinning a hub that is `from_id` for one `blocked_by` edge and
  `to_id` for another, asserting both `→ blocked_by` and `← blocked_by` render —
  confirming this is correct fixed-direction output, not a flip bug.

### Verification Results
- Tests: PASS (23440 passed, 43 skipped; 5 pre-existing failures unrelated to this
  change, confirmed identical on unmodified `main` via `git stash`)
- Lint: PASS (`ruff check` on both changed files)

## Steps to Reproduce

1. In a repo with a cluster where the hub node is the `from_id` for one edge and the `to_id` for another edge of the same relationship type (e.g. `blocked_by`), run `ll-issues clusters` (default `--layout tree`).
<!-- ll-evidence-ok: illustrative `ll-issues clusters` rendered-output example ("e.g."), not a quote from ENH-3407's own file -->
2. Observe the hub's two neighbors of the same relationship type render with opposite arrow glyphs — e.g. hub `ENH-3407` shows `ENH-3406 → blocked_by` for one edge and `ENH-3408 ← blocked_by` for the other, despite both being `blocked_by` edges and both frontmatter records being internally consistent with a single forward dependency chain.
3. Compare against `ll-issues clusters --layout list` on the same cluster: it renders both edges consistently from each node's own fixed perspective, with no flip.

## Root Cause

- **File**: `scripts/little_loops/cli/issues/clusters.py`
- **Anchor**: `in function _annot()` (lines 210-214)
- **Cause**: The arrow glyph is computed as `"→" if from_id == parent else "←"`, i.e. relative to the current tree-walk `parent`, not the edge's fixed `from_id`/`to_id`. The tree picks the max-degree node as hub/root (`_render_cluster_tree`'s root selection at line 248, mirroring the hub heuristic in `_cluster_header` at line 131) and walks outward from it. When the hub is `from_id` for one neighbor and `to_id` for another, the same relationship type gets opposite glyphs even though `_EDGE_MEANING` (line 38, e.g. `"blocked_by": "source is blocked by target"`) defines a single fixed, non-relative meaning.

## Error Messages

N/A - rendering-only bug, no exceptions or error output

## Location

- **File**: `scripts/little_loops/cli/issues/clusters.py`
- **Line(s)**: 210-214
- **Anchor**: `in function _annot()`
- **Code**:
```python
def _annot(parent: str, child: str) -> str:
    from_id, _to_id, rel = rel_of[frozenset({parent, child})]
    arrow = "→" if from_id == parent else "←"
    return f"{arrow} {colorize(rel, EDGE_COLOR.get(rel, '37'))}"
```

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-08_

**Readiness Score**: 60/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 52/100 → LOW

### Gaps to Address
- Root cause is unverified: `_annot()`'s `arrow = "→" if from_id == parent else "←"` is mathematically equivalent to `arrow = "→" if to_id == child else "←"`, because for a two-node edge `parent`/`child` always partition `{from_id, to_id}` — the comparison already reflects the edge's fixed stored direction, not tree-walk position. The cross-edge glyph difference the issue reports (hub shows `→` for one `blocked_by` edge, `←` for another) arises because the hub is `from_id` (blocked) in one edge and `to_id` (blocker) in the other — genuinely different semantic roles, not a computation bug. Re-verify against a real repro before implementing.
- `_render_cluster_diagram` (`clusters.py:472-489`, the issue's own cited "fixed direction" precedent) also varies its arrow glyph (▼ vs ▲) by direction relative to render position (`forward = (a_id, b_id) in edge_map`) rather than using one fixed glyph per relationship type — this contradicts the issue's premise that "the same relationship type should always render the same glyph" is the codebase's established pattern.
- The Proposed Solution code sample (lines 51-56) is byte-identical to the current `_annot()` implementation (`clusters.py:210-214`) — it demonstrates no behavior change and cannot serve as an implementation reference as written.
- Proposed Solution offers two unresolved alternative approaches ("show `from_id → to_id`" vs. "restructure the label to name both IDs explicitly") without picking one — resolve via `/ll:decide-issue` once the underlying premise above is re-confirmed.

### Outcome Risk Factors
- Ambiguity is at its floor: the issue's own proposed fix is logically a no-op, and no correct alternative implementation is specified — expect this to require re-diagnosis before any code change, not just implementation.
- No regression test currently exists for tree-layout arrow direction; the issue proposes adding one, but the correct expected behavior needs to be settled first.

## Session Log
- `/ll:manage-issue` - 2026-09-08T22:16:10 - `7db37a92-093d-4d5a-9a59-dd77ca414993.jsonl`
- `/ll:confidence-check` - 2026-09-08T21:03:15 - `2d270e0e-548d-4750-9a2e-a5ff79625865.jsonl`
- `/ll:confidence-check` - 2026-09-08T20:53:43 - `3f9b59f1-b272-4917-896e-999f8ef8d9d9.jsonl`
- `/ll:wire-issue` - 2026-09-08T20:18:10 - `2894e5fe-06e8-41c0-a899-75965afc819e.jsonl`
- `/ll:decide-issue` - 2026-09-08T20:01:37 - `aa86cabe-2995-47f1-90c9-cd63b1a7eb73.jsonl`
- `/ll:refine-issue` - 2026-09-08T19:52:03 - `cb4b9ca3-dab7-4f31-8422-5d785ebaffef.jsonl`
- `/ll:confidence-check` - 2026-09-08T19:44:38 - `ec62a17d-6d92-4eb9-8c86-638b441ac713.jsonl`
- `/ll:refine-issue` - 2026-09-08T19:39:16 - `c6c87baa-cf5d-4331-a1e1-c1b5804310d4.jsonl`
- `/ll:format-issue` - 2026-09-08T19:31:30 - `0c192ccc-320f-40d5-b594-123949e3b0f3.jsonl`
- `/ll:capture-issue` - 2026-09-08T19:25:23 - `11906448-7df7-4fe2-877f-bca8a2a33d89.jsonl`
