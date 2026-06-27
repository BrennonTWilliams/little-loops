---
id: ENH-2358
title: "Scratch hook threshold_lines too low for issue-file markdown"
type: ENH
priority: P3
status: cancelled
captured_at: "2026-06-27T22:44:05Z"
discovered_date: 2026-06-27
discovered_by: capture-issue
labels: [scratch-hook, config, issue-files, markdown]
relates_to: [BUG-2357]
---

# ENH-2358: Scratch hook threshold_lines too low for issue-file markdown

## Summary

The `scratch_pad.threshold_lines: 200` in `.ll/ll-config.json` is calibrated for automation
output (test runs, lint, log tails) but fires on structured issue-file markdown, which routinely
reaches 200–350+ lines after `/ll:format-issue` and `/ll:refine-issue` passes. Adding
`.issues/**` to `exclude_patterns` (or raising the threshold for `.md` files) prevents the hook
from treating issue files as "large output to hide from context" — which they are not.

## Motivation

Issue files are the primary read-then-edit artifact in the little-loops workflow. They grow
incrementally through format → refine → wire → ready passes. A 200-line threshold designed to
suppress 8,000-line pytest output should not apply to a 250-line structured document that an
implementer needs to read whole and then edit inline. Miscalibration here causes the interaction
described in BUG-2357 (Edit/Write tool lock) and forces workarounds that bypass diff preview.

## Current Behavior

- `threshold_lines: 200` fires on any tracked extension (`.md`, `.py`, `.ts`, etc.) over 200
  lines.
- Issue files in `.issues/` consistently exceed 200 lines after the format + refine pipeline.
- The hook intercepts `Read`, saves to `.loops/tmp/scratch/`, and shows only the last 20 lines.
- This is correct for test output and lint logs; it is wrong for structured documents.

## Expected Behavior

One of:
- **(A) Exclude `.issues/**`** from the hook via `exclude_patterns` — issue files are never
  subject to scratch interception regardless of length.
- **(B) Raise `threshold_lines` to 400 or 500** — accommodates enriched issue files (which
  top out around 350 lines) while still catching test output (which can reach thousands of
  lines).
- **(C) Extension-scoped threshold** — a `threshold_by_extension: {".md": 500, ".py": 200}`
  config key, for finer-grained control (requires schema + hook handler changes).

Approach (A) is the lowest-effort fix and highest-confidence: `.issues/` files are always
structured documents, never bulk output.

## Integration Map

### Files to Modify
- `.ll/ll-config.json` — add `.issues/**` to `scratch_pad.exclude_patterns` (approach A).
- `config-schema.json` — if approach (C), add `threshold_by_extension` to the `scratch_pad`
  schema object.
- Scratch-pad hook handler — if approach (C), read and apply per-extension thresholds.

### Similar Patterns
- `scratch_pad.exclude_patterns` already supports glob patterns (`**/__pycache__/**`, etc.) —
  approach (A) is additive config only, no code change.

### Tests
- No automated test currently covers scratch-pad config behavior; a unit test verifying that
  files matching `exclude_patterns` are not intercepted would prevent regression.

## Implementation Steps

1. Choose approach: (A) is recommended for immediate relief; (C) for long-term flexibility.
2. For approach (A): add `".issues/**"` to `scratch_pad.exclude_patterns` in `.ll/ll-config.json`.
3. Verify `config-schema.json` already allows arbitrary glob strings in `exclude_patterns`
   (likely already valid).
4. Test: open a 250-line issue file in Claude Code, confirm `Read` returns full content and
   `Edit` works without Bash workaround.
5. Optional follow-on: consider also adding `.claude/**` (CLAUDE.md, settings) and
   `docs/**` to exclude_patterns for the same reason.

## Acceptance Criteria

- [ ] Reading a 250-line issue file via `Read` returns full content (no scratch interception).
- [ ] `Edit` works on the file immediately after `Read` in the same session.
- [ ] Scratch interception still fires on large automation output (e.g., pytest logs > 200 lines
      in `scripts/` or `.loops/`).
- [ ] `config-schema.json` validates the updated config without errors.

## Resolution

Cancelled — superseded by BUG-2357's fix. The scratch hook no longer intercepts `Read` at all
(the `Bash|Read` matcher is now `Bash`-only), so `threshold_lines` and `file_extension_filters` no
longer apply to Read. Excluding `.issues/**` or raising the threshold would only have narrowed the
blast radius of the underlying Edit/Write lock; removing the Read interception eliminates it for
*all* files, not just issue files. No config or schema change is needed.

## Session Log
- `/ll:capture-issue` - 2026-06-27T22:44:05Z - `567c4d00-9ba7-4b64-8c58-6d0231d254b8.jsonl`

---

## Status

**Current Status**: cancelled
