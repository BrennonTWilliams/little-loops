---
id: ENH-2158
title: Add rubric-refine, cua-agent-desktop, and oracle sub-loops to LOOPS_REFERENCE.md
type: ENH
priority: P3
status: open
created: 2026-06-14
affects:
  - docs/guides/LOOPS_REFERENCE.md
---

## Problem

Four loops exist in the codebase but are not documented in `docs/guides/LOOPS_REFERENCE.md`:

1. **`rubric-refine`** — added in commit `aa38dc03`; has its own YAML at `scripts/little_loops/loops/rubric-refine.yaml`. Referenced only in the internal `loops/README.md`.
2. **`cua-agent-desktop`** — listed in CHANGELOG v1.124.0 as a new built-in loop; not in LOOPS_REFERENCE.md.
3. **`oracles/enumerate-and-prove`** — oracle sub-loop; not in the oracle sub-loops table.
4. **`oracles/verify-confidence-scores`** — oracle sub-loop; not in the oracle sub-loops table.

## Acceptance Criteria

- [ ] Add `rubric-refine` entry to the appropriate LOOPS_REFERENCE.md section (harness/rubric category) with: description, primary use case, key states
- [ ] Add `cua-agent-desktop` entry with: description, primary use case, key states
- [ ] Add `oracles/enumerate-and-prove` and `oracles/verify-confidence-scores` rows to the oracle sub-loops table
- [ ] `ll-loop list` output matches all entries added (spot-check that loop names are correct)

## Notes

Source of truth for each loop's description is the `description:` field at the top of its YAML file. Key states can be derived from the `states:` block.
