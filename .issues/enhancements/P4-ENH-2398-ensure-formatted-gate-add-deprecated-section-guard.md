---
id: ENH-2398
title: ensure_formatted gate should honor the `deprecated` section flag like is_formatted()
type: enhancement
status: open
priority: P4
discovered_date: 2026-06-29
discovered_by: BUG-2395 reconciliation
relates_to:
- BUG-2395
labels:
- rn-remediate
- format-guard
- hardening
decision_needed: false
---

# ENH-2398: ensure_formatted gate should honor the `deprecated` section flag like is_formatted()

## Summary

The `ensure_formatted` Phase-0 gate in `rn-remediate.yaml` builds its
required-section list from `ll-issues sections` but, unlike
`issue_parser.py:is_formatted()`, does **not** skip entries marked
`deprecated: true`. The two code paths are meant to agree on "what counts as
required" but only one honors the deprecated flag.

## Current Behavior

`is_formatted()` (`issue_parser.py:86,89`) excludes deprecated sections:

```python
if defn.get("required") is True and not defn.get("deprecated", False): ...
if defn.get("level") == "required" and not defn.get("deprecated", False): ...
```

The `ensure_formatted` inline Python (`rn-remediate.yaml`) has no such guard:

```python
if isinstance(meta, dict) and meta.get("required") is True:
    required.append(title)
if isinstance(meta, dict) and meta.get("level") == "required":
    required.append(title)
```

Today this is harmless only because BUG-2395 demoted the one offending
deprecated-but-required entry (`feat` `User Story`, `level: required`,
`deprecated: true`) to `optional`. Any future deprecated-but-`required` section
would re-introduce a non-idempotent format gate (the original BUG-2395 failure
mode) while `is_formatted()` stays correct — a silent divergence.

## Expected Behavior

The gate skips `deprecated: true` sections, matching `is_formatted()`. Add a
`if meta.get("deprecated"): continue` guard to both loops in the inline Python.

## Scope Boundaries

- In scope: the `deprecated` guard in `ensure_formatted`'s inline Python only.
- Out of scope: the `Labels`/`User Story` demotions (done in BUG-2395); any
  change to `is_formatted()` (already correct).

## Impact

Defensive: prevents a future template author from silently re-creating the
BUG-2395 non-idempotency. Low urgency — no current section triggers it.

## Status

open
