# FEAT-100: Add validation to config parser

## Summary

The config parser lacks input validation for required fields.

## Location

- **File**: `scripts/little_loops/config.py`
- **Line(s)**: 42-55
- **Anchor**: `in class BRConfig`

## Current Behavior

Config accepts any values without validation.

## Expected Behavior

Config should validate required fields and types.

## Proposed Solution

Add validation in `scripts/little_loops/config.py` and update `scripts/tests/test_config.py`.

## Labels

`feature`, `config`

---

## Status
**Open** | Created: 2026-01-01 | Priority: P1
