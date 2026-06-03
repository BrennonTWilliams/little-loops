---
id: ENH-1900
title: Harden svg-textgrad loop (best.svg, on_error, threshold)
type: enhancement
priority: P3
status: open
captured_at: "2026-06-03T19:12:59Z"
discovered_date: 2026-06-03
discovered_by: capture-issue
labels: [loops, svg-textgrad]
---

# ENH-1900: Harden `svg-textgrad` loop (best.svg, on_error, threshold)

## Summary

Three content fixes to the bundled `scripts/little_loops/loops/svg-textgrad.yaml`
surfaced by the 2026-06-03 two-run audit: missing best-output artifacts on
first-pass success, a missing error route on the `generate` state, and a quality
gate that is both mislabeled and too loose to catch a measured 9.3% quality
regression between runs.

## Current Behavior

1. **Missing best-output artifacts.** `track_best` (line ~191) copies
   `image.svg` → `best.svg`, but only fires via `on_no`/`on_error` (lines
   ~188–189). When `verify_score` passes on the first iteration, the FSM jumps
   straight to `done` (line ~298) and `best.svg`/`best-brief.md` are never
   created — even though the `done` prompt (line ~312) claims they are "present
   if at least one score was recorded." The audit confirmed both files missing
   in both runs.
2. **`generate` has no `on_error`.** The `generate` prompt state (lines ~61–85)
   has `next: screenshot` and no error route, while neighboring states route to
   `diagnose`/`check_capture_fails`. A prompt failure (API error, token limit)
   aborts the whole loop instead of producing a structured failure report.
3. **Quality gate mislabeled and loose.** `pass_threshold: 6` (line ~18) is
   commented `# minimum score per criterion (1-10) to pass`, but line ~172 uses
   it as a weighted-average gate `(2×VC + 2×OG + CR + SC) / 6 ≥ threshold`
   (36/60). The comment is wrong, and the weighted formula masks weak individual
   criteria: Run B passed with scalability 5/10 (below the nominal threshold)
   and a 39/60 weighted score (65%) vs Run A's 43/60 (71.7%).

## Expected Behavior

1. `best.svg` and `best-brief.md` always exist when the loop reaches `done`
   having recorded at least one score (including first-pass success).
2. A `generate` prompt failure routes to `diagnose` for a structured failure
   report rather than aborting the loop.
3. The quality gate is correctly documented and tight enough that a
   per-criterion regression (e.g. scalability 5/10) forces a gradient iteration
   instead of passing.

## Motivation

The loop's gradient-optimization path is a fallback that, in practice, never
fired in either audited run because the first generation always cleared the
loose threshold. Tightening the gate exercises the textgrad machinery when
quality actually regresses, and the artifact/error-route fixes close
correctness gaps a downstream consumer would hit.

## Proposed Solution

**(a) `done` ensures best artifacts** — add a shell preamble to `done`:

```yaml
done:
  action: |
    DIR="${captured.run_dir.output}"
    [ -f "$DIR/best.svg" ] || cp "$DIR/image.svg" "$DIR/best.svg"
    [ -f "$DIR/best-brief.md" ] || cp "$DIR/brief.md" "$DIR/best-brief.md"
    # ... existing prompt action follows
```

**(b) `generate` error route**:

```yaml
generate:
  action_type: prompt
  next: screenshot
  on_error: diagnose
```

**(c) tighten + relabel the gate** — fix the misleading comment, raise
`pass_threshold` to 7 (≈70% / 42/60), and add a per-criterion floor in the
`verify_score` shell action:

```yaml
context:
  pass_threshold: 7          # weighted-average gate: (2VC+2OG+CR+SC)/6 >= threshold
  min_per_criterion: 6       # each criterion must be >= this
```

```bash
# in verify_score, after extracting VC OG CR SC:
MIN="${context.min_per_criterion}"
if [ "$VC" -lt "$MIN" ] || [ "$OG" -lt "$MIN" ] || \
   [ "$CR" -lt "$MIN" ] || [ "$SC" -lt "$MIN" ]; then
  echo "SHELL_ITERATE"; exit 0
fi
```

Per the audit, `pass_threshold: 7` + `min_per_criterion: 6` would have caught
Run B on both the weighted average (39 < 42) and the scalability floor (5 < 6).

## Scope Boundaries

- In scope: edits to `svg-textgrad.yaml` only.
- Out of scope: the runtime `model: "unknown"` attribution gap (see BUG-1897)
  and a `required_inputs` guard (see ENH-1898) — both are framework-level and
  tracked separately.

## Backwards Compatibility

Loop-local changes only; no schema or runtime impact. Tighter thresholds change
pass/fail behavior for borderline generations by design.

## Integration Map

- `scripts/little_loops/loops/svg-textgrad.yaml` — `done`, `generate`,
  `context`, and `verify_score` states.
- Validate with `ll-loop validate svg-textgrad` after editing.

## Implementation Steps

1. Add the copy-if-missing preamble to `done`.
2. Add `on_error: diagnose` to `generate`.
3. Fix the `pass_threshold` comment; raise to 7; add `min_per_criterion` and the
   floor check in `verify_score`.
4. Run `ll-loop validate svg-textgrad`; optionally re-run the loop to confirm a
   regressed generation now triggers a gradient iteration.

## Impact

Closes two correctness gaps (artifacts, error handling) and makes the quality
gate actually discriminating, so the gradient path is exercised when output
quality drops.

- **Priority**: P3 - Quality/correctness hardening of one bundled loop; no
  active consumer is blocked, but the gaps produce silently-missing artifacts
  and an unexercised gradient path.
- **Effort**: Small - Three localized edits to a single YAML file
  (`svg-textgrad.yaml`); no new patterns, reuses existing FSM states and
  context variables.
- **Risk**: Low - Loop-local changes only, no schema or runtime impact. Tighter
  thresholds alter pass/fail for borderline generations by design (see
  Backwards Compatibility).
- **Breaking Change**: No

## Status

- **Created**: 2026-06-03 via `/ll:capture-issue` (from `svg-textgrad` audit)
- **State**: open

## Session Log
- `/ll:format-issue` - 2026-06-03T19:21:26 - `2115b373-786c-489c-aa3d-71ed6687c4c6.jsonl`
- `/ll:capture-issue` - 2026-06-03T19:12:59Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5cba1a69-7a53-425f-8c5d-4f1ba61f51bb.jsonl`
