---
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24T22:31:44Z
discovered_by: scan-codebase
relates_to: [ENH-2308]
---

# ENH-2785: Complete the `editorial-mono` design-token theme so `ll-verify-design-tokens` can gate on exit 0

## Summary

`ll-verify-design-tokens` lints half-flipped themes (inverted
`surface`/`text` with light-tuned `border`/`action` defaults). Its own
docstring records that the bundled `editorial-mono` profile currently fails
this lint, with the fix deferred to a follow-on — but no open issue tracks
that follow-on (ENH-2308, which added the lint and fixed `warm-paper`/
`default`, is done).

## Location

- **File**: `scripts/little_loops/cli/verify_design_tokens.py`
- **Line(s)**: 197-205 (at scan commit: fb567390)
- **Anchor**: `docstring of main_verify_design_tokens`
- **Code**:
```python
    """Entry point for ll-verify-design-tokens.

    Returns 0 when no half-flipped themes are found; 1 otherwise.

    Note: run against the bundled little-loops templates this currently flags
    ``editorial-mono`` (a known-incomplete profile pending a follow-on); fix or
    point ``--profiles-dir`` at a complete profile set to gate CI on exit 0.
    """
```

## Current Behavior

Running the tool against the bundled templates exits 1 because
`editorial-mono` is half-flipped, so the lint cannot be used as a
zero-tolerance gate in the test suite.

## Expected Behavior

`editorial-mono` gets complete dark-tuned `border`/`action` token values;
`ll-verify-design-tokens` exits 0 on the bundled templates and can be wrapped
as a pytest gate.

## Proposed Solution

Flip the remaining `border`/`action` tokens in the `editorial-mono` dark
theme (mirroring the ENH-2308 fixes for `warm-paper`/`default`), update the
docstring note, and add a pytest test asserting exit 0 on bundled templates.

## Impact

- **Effort**: Small
- Unlocks using the verify tool as an enforced local CI gate.

## Status

`open` — discovered by `/ll:scan-codebase`.

## Session Log
- `/ll:scan-codebase` - 2026-07-24T22:41:56 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`
