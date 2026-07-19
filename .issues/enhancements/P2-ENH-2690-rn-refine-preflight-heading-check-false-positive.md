---
id: ENH-2690
title: rn-refine preflight_check heading match flags legitimate decompose rewrites
  as data loss
type: ENH
priority: P2
status: done
captured_at: '2026-07-19T00:00:00Z'
completed_at: '2026-07-19T18:34:36Z'
discovered_date: 2026-07-19
discovered_by: audit-loop-run
labels:
- loops
- rn-refine
- verification
confidence_score: 95
outcome_confidence: 85
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 20
---

# ENH-2690: rn-refine preflight_check heading match flags legitimate decompose rewrites as data loss

## Summary

`preflight_check` in `loops/rn-refine.yaml` aborts the run (`finalize_aborted`,
source left untouched) whenever a source `## heading` is not found verbatim in
the reassembled `plan.md`. But `decide_decompose`'s sub-loop step
(`_subloop.decide_decompose` in the `refine_node` embedded loop) intentionally
rewrites a decomposed node's index headings and hands section ownership to
child files with different heading text/level. This is expected, correct
behavior — not data loss — yet the exact-substring check treats it as a fatal
invariant violation on every run whose root decomposes.

## Current Behavior

`preflight_check` in `loops/rn-refine.yaml` compares the source file's `##`
headings only against the reassembled `$RUN_DIR/plan.md` (an exact-substring
`comm -23` diff). Any source heading absent from that single file — including
one that was legitimately rewritten by `decide_decompose`'s index rewrite or
moved into a child node's `final.md` — trips `INVARIANT_FAIL:MISSING_SECTIONS`
and aborts the run via `finalize_aborted`, leaving the source untouched. This
fires on the common path (any root-level decompose), not just genuine
data-loss cases.

## Expected Behavior

`preflight_check` should only fail `MISSING_SECTIONS` when a source heading's
content is unaccounted for anywhere in the full decomposition tree. Before
declaring a heading missing, the check should compare against the union of
`$RUN_DIR/plan.md`'s `##` headings **and** every `$RUN_DIR/nodes/*/final.md`
file's `##`/`# ` headings (the latter covers child h1 titles produced by
`materialize_children`'s `grep -m1 '^# '` convention). A genuinely dropped
section — absent from the reassembled root and every child node — should
still fail the invariant and abort, per Acceptance Criteria.

## Motivation

`rn-refine` is designed to restructure multi-section plans, and decomposition
is the expected outcome for exactly the plans it's meant to handle. Because
the heading check currently treats every root-level decompose as fatal data
loss, the loop is effectively unusable for its primary use case — runs abort
at `finalize_aborted` (e.g. `2026-07-19T161520-rn-refine`, 18% of budget used)
despite producing a faithful, expanded reassembly (72875 bytes vs. 8761-byte
source), because the false positive can't distinguish "lost content" from
"content moved to a child + index rewritten."

## Evidence

Audit of run `2026-07-19T161520-rn-refine` (`.loops/.history/2026-07-19T161520-rn-refine/`,
processing `project-tooling-setup.md` in the `ll-product` repo):

- `preflight_check` output: `INVARIANT_FAIL: MISSING_SECTIONS:Constraints & conventions (confirmed with user),Tool 1 — \`promote\` (flagship),Tool 2 — \`docs-sync\`,Tool 3 — \`promotion-status\``
- Root cause: `## Constraints & conventions (confirmed with user)` became
  `## Constraints & conventions (confirmed with user, verified against current CLI — apply across all three tools)`
  in the reassembled plan (the node's index rewrite), and
  `## Tool 1 — \`promote\` (flagship)` etc. became child-owned `# Tool 1 — ...`
  h1 titles (different heading level, different file) rather than `##` in the
  root — by design, per the `decide_decompose` prompt's own instructions.
- Run reached `finalize_aborted` with `iterations: 54` of `max_steps: 300`
  (18% of budget — not a budget-exhaustion failure), reporting
  `success: false, original_unchanged: true`. Correctly avoided corrupting the
  source, but for the wrong reason — the run actually succeeded at producing a
  faithful, expanded reassembly (72875 bytes vs. 8761 source, well above the
  0.5 floor-fraction check), just failed a heading-match heuristic that can't
  distinguish "lost content" from "content moved to a child + index rewritten."

## Proposed Solution

Before declaring `MISSING_SECTIONS`, check whether a "missing" source heading
(or a close variant of it) is covered somewhere in the full decomposition
tree — i.e. compare against the union of the reassembled `plan.md` headings
**and** every `nodes/*/final.md` heading (including `# ` h1 child titles) —
not just the reassembled root in isolation. Only fail the invariant when a
source section's content is unaccounted for anywhere in the tree.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The exact check lives in `preflight_check`'s shell action in
  `scripts/little_loops/loops/rn-refine.yaml` (~lines 554-563):
  `SOURCE_HEADINGS`/`NEW_HEADINGS` are built via
  `grep -E "^##[[:space:]]"` + `comm -23`, comparing only `$SOURCE` (the
  original file) against `$RUN_DIR/plan.md` (the reassembled root, copied
  from `nodes/n0/final.md` by the `assemble` state). It never reads
  `$RUN_DIR/nodes/*/final.md`.
- `nodes/<id>/final.md` files already exist on disk for every node in the
  tree (leaf and internal alike) at `preflight_check` time — seeded by
  `emit_leaf`/`emit_capped` in `oracles/plan-node-refine.yaml` for leaves,
  and by `integrate` in `oracles/integrate-node.yaml` for internal nodes
  (which re-inlines each child's `final.md` "under clear sub-headings").
  `edges.tsv` (`parent<TAB>child<TAB>title` rows) records the full
  parent→child structure and is already parsed by
  `rn_synth_queue._children_of()` / `_is_ready()` in
  `scripts/little_loops/rn_synth_queue.py` — the existing reusable
  primitive for walking the node tree, already invoked from a loop shell
  state via `python3 -m little_loops.rn_synth_queue ...` (see `pop` in
  `integrate-node.yaml`).
- Child h1 titles are extracted via the existing `grep -m1 '^# '`
  convention in `materialize_children` (`oracles/plan-node-refine.yaml`) —
  the same extraction should be mirrored when building the "moved to a
  child" side of the union, so a `# <title>` line in a child `final.md`
  counts as satisfying a `##` source heading.
- Recommended implementation shape, matching the existing `BELOW_FLOOR`
  precedent in the same state (which promotes its ratio comparison to an
  inline `python3 -c` heredoc rather than shell-only arithmetic, per its
  own comment: "BSD awk on macOS lacks ?: ternary"): extend `NEW_HEADINGS`
  to be the union of `$RUN_DIR/plan.md`'s `##` lines **and** every
  `$RUN_DIR/nodes/*/final.md`'s `##`+`# ` lines, before diffing against
  `SOURCE_HEADINGS`.
- No existing fuzzy/close-variant heading-matching utility exists in this
  codebase — `difflib` is only used for `unified_diff` (line-level diffs in
  `sync.py` and `cli/logs.py`), never `get_close_matches`/
  `SequenceMatcher.ratio()`. Exact membership in the tree-wide union is the
  readily available approach; true "close variant" matching (per this
  issue's Proposed Solution phrasing) would require new fuzzy-matching code
  if pursued beyond exact set membership.

## Scope Boundaries

Out of scope for this issue:
- True fuzzy/"close variant" heading matching (e.g. `difflib.get_close_matches`
  or `SequenceMatcher.ratio()`) — no such utility exists in this codebase
  today; this fix uses exact membership in the tree-wide heading union, not
  approximate text similarity, per the Codebase Research Findings.
- Changes to `decide_decompose`'s index-rewrite behavior or
  `materialize_children`'s child-title extraction convention — both are
  correct, intentional behavior that `preflight_check` needs to account for,
  not change.
- The `BELOW_FLOOR` byte-ratio check in the same `preflight_check` state —
  unaffected, only the `MISSING_SECTIONS` heading-diff logic changes.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-refine.yaml` — `preflight_check` state's
  heading-check block (~lines 554-563): glob `${run_dir}/nodes/*/final.md`
  in addition to `$RUN_DIR/plan.md` when building `NEW_HEADINGS`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/oracles/plan-node-refine.yaml` —
  `decide_decompose` (source of the intentional index/heading rewrite that
  `preflight_check` currently misfires on) and `materialize_children`
  (`grep -m1 '^# '` convention for child h1 titles).
- `scripts/little_loops/loops/oracles/integrate-node.yaml` — `integrate`
  re-inlines child `final.md` content into the parent's `final.md` under
  new sub-headings; `pop` already shells out to `rn_synth_queue.py`.
- `scripts/little_loops/rn_synth_queue.py` — `_children_of()` and
  `_is_ready()` are the existing `edges.tsv`-driven tree-walk primitives;
  reusable (via `python3 -m little_loops.rn_synth_queue`) instead of
  reimplementing tree traversal inline.

### Similar Patterns
- `preflight_check`'s own `BELOW_FLOOR` check — tolerance-based inline
  `python3 -c` ratio comparison, the precedent to follow instead of strict
  equality.
- `loop-composer-adaptive.yaml`, state `read_completed_summaries` (and the
  identical pattern in `loop-composer.yaml`) — canonical
  `python3 <<'PYEOF' ... glob.glob(...)` shape for aggregating content
  across a directory of per-item files.

### Tests
- `scripts/tests/test_rn_refine.py`, class `TestFinalizeSafety`
  (~lines 714-815) — existing preflight test harness: `_seed()`,
  `_render()`, `_bash()`, `_load_rn_refine()`.
  `test_preflight_aborts_on_missing_required_sections` (~line 765) encodes
  today's exact-substring behavior; confirmed its own fixture (no
  `nodes/*/final.md` present) is exactly the still-genuinely-missing case
  from AC #2 and needs no behavior change once the check is tree-aware —
  only `_seed()` needs extending (add an optional `children: dict[str, str]`
  param that writes `nodes/<id>/final.md` fixtures) to support a *new*
  regression test for AC #1 (redeemed-by-child case).

  _Wiring pass added by `/ll:wire-issue`:_
  - Follow the existing `nodes/<id>/final.md` + `edges.tsv` fixture
    convention already established in the same file by
    `TestSynthPopReadinessGate` (`_node_dir()`/`_seed_final()` helpers,
    ~lines 834-842) rather than inventing a new fixture shape.
  - Add `test_preflight_ok_when_heading_moved_to_child` — seeds a source
    heading (e.g. `` ## Tool 1 — `promote` (flagship) ``) that the root
    rewrites (decompose index rewrite) but whose content is redeemed by a
    child `nodes/n1/final.md` `# ` h1 title; asserts `INVARIANT_OK` and
    `returncode == 0`, no `INVARIANT_FAIL`.
  - `scripts/tests/test_builtin_loops.py`,
    `TestRnRefineRecursiveDecomposition` (~line 9364) — structural
    FSM-shape tests for `rn-refine.yaml` (no preflight content
    assertions); confirmed no change needed, listed for awareness since it
    re-parses the same loop file.

### Documentation
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md` — describes the rn-refine
  decompose/reassemble contract; may warrant a note on the heading-union
  check.
- `docs/guides/LOOPS_REFERENCE.md` — rn-refine context variable table / FSM
  flow diagram.

  _Wiring pass added by `/ll:wire-issue`:_
  - Line ~370: `on_no/on_error → finalize_aborted (terminal —
    diff-invariant/backup/section-presence guard tripped)` — update
    "section-presence guard" wording once the check becomes tree-aware.
  - Line ~384: prose under "Diff-invariant safety guard (ENH-2418)", item
    (3) `**section-presence check** — required top-level sections ...
    must still be present` — this is the specific sentence describing
    today's (incorrect) root-only semantics; update to describe the
    reassembled-root + `nodes/*/final.md` tree-wide union.

## Acceptance Criteria

- [x] A run whose root node decomposes and rewrites its own index headings
      (matching the current `decide_decompose` prompt's documented behavior)
      does not trip `MISSING_SECTIONS` when the content is present under a
      child node.
- [x] A run that genuinely drops a section (no reassembled heading and no
      matching child node) still fails the invariant and aborts.
- [x] Regression test covering a decompose-then-reassemble run with rewritten
      index headings.

## Impact

- **Priority**: P2 — this is not an edge case; it fires on the common path
  (any root-level decompose), making `rn-refine` unusable for exactly the
  multi-section plans it's designed to restructure.
- **Effort**: Medium — touches `preflight_check`'s shell logic in
  `loops/rn-refine.yaml`; needs to read `nodes/*/final.md` headings in
  addition to the reassembled root.

## Related Files

- `loops/rn-refine.yaml` (`preflight_check`, `_subloop.decide_decompose`)
- `scripts/little_loops/loops/rn-refine.yaml` — `preflight_check` (~lines
  509-570), `assemble`, `finalize`, `finalize_aborted`
- `scripts/little_loops/loops/oracles/plan-node-refine.yaml` —
  `decide_decompose`, `materialize_children`, `emit_leaf`/`emit_capped`
- `scripts/little_loops/loops/oracles/integrate-node.yaml` — `integrate`,
  `pop`
- `scripts/little_loops/rn_synth_queue.py` — `_children_of()`, `_is_ready()`
- `scripts/tests/test_rn_refine.py` — `TestFinalizeSafety`

---

## Resolution

- **Action**: improve
- **Completed**: 2026-07-19
- **Status**: Completed

### Changes Made
- `scripts/little_loops/loops/rn-refine.yaml`: `preflight_check`'s
  `MISSING_SECTIONS` check now builds `NEW_HEADINGS` from the union of
  `plan.md`'s `##` headings and every `nodes/*/final.md`'s `##`/`# ` headings,
  instead of comparing against the reassembled root in isolation.
- `scripts/tests/test_rn_refine.py`: `TestFinalizeSafety._seed` gained an
  optional `children: dict[str, str]` param that writes `nodes/<id>/final.md`
  fixtures; added `test_preflight_ok_when_heading_moved_to_child` covering the
  redeemed-by-child case (AC #1). `test_preflight_aborts_on_missing_required_sections`
  (genuinely dropped section, AC #2) needed no change.
- `docs/guides/LOOPS_REFERENCE.md`: updated the section-presence-check prose
  and state-graph comment to describe the tree-wide union instead of the old
  root-only semantics.

### Verification Results
- Tests: PASS (`python -m pytest scripts/tests/` — 15492 passed, 38 skipped)
- Lint: PASS (`ruff check scripts/`)
- Types: PASS (pre-existing unrelated `ruamel` stub-noise only)
- FSM validation: PASS (`rn-refine.yaml` loads clean, all states intact)

## Status

**Done** | Created: 2026-07-19 | Priority: P2


## Session Log
- `/ll:ready-issue` - 2026-07-19T18:29:04 - `92bec9d9-d175-407a-8562-6963d0450ceb.jsonl`
- `/ll:confidence-check` - 2026-07-19T19:00:00 - `98718d2c-508e-41e0-8c96-f1d4e6d9ca9a.jsonl`
- `/ll:wire-issue` - 2026-07-19T18:24:52 - `af624239-0c24-4456-ae65-239eb67a244b.jsonl`
- `/ll:refine-issue` - 2026-07-19T18:18:51 - `a7d63538-a37e-4349-af52-3b1ba14082c9.jsonl`
- `/ll:manage-issue` - 2026-07-19T18:33:41 - `39866588-3dbd-469e-8859-1ec05d5de805.jsonl`
