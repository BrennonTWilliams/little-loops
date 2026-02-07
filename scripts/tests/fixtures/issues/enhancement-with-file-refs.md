# ENH-200: Improve config error messages

## Summary

Config error messages are unhelpful when validation fails.

## Location

- **File**: `scripts/little_loops/config.py`
- **Line(s)**: 60-70
- **Anchor**: `in function validate_config`

## Current Behavior

Generic error messages.

## Expected Behavior

Specific error messages indicating which field failed and why.

## Proposed Solution

Refactor error handling in `scripts/little_loops/config.py`.

## Labels

`enhancement`, `config`

---

## Status
**Open** | Created: 2026-01-02 | Priority: P2
