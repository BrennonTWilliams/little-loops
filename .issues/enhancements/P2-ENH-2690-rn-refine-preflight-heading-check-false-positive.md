---
id: ENH-2690
title: "rn-refine preflight_check heading match flags legitimate decompose rewrites as data loss"
type: ENH
priority: P2
status: open
captured_at: '2026-07-19T00:00:00Z'
discovered_date: 2026-07-19
discovered_by: audit-loop-run
labels:
- loops
- rn-refine
- verification
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

## Acceptance Criteria

- [ ] A run whose root node decomposes and rewrites its own index headings
      (matching the current `decide_decompose` prompt's documented behavior)
      does not trip `MISSING_SECTIONS` when the content is present under a
      child node.
- [ ] A run that genuinely drops a section (no reassembled heading and no
      matching child node) still fails the invariant and aborts.
- [ ] Regression test covering a decompose-then-reassemble run with rewritten
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

## Status

**Open** | Created: 2026-07-19 | Priority: P2
