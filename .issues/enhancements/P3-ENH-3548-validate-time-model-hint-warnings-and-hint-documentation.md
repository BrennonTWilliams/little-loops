---
id: ENH-3548
type: ENH
title: Validate-time model hint warnings and hint documentation
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T17:40:15Z'
labels:
- multi-host
- loops
blocked_by:
- ENH-3527
---

# ENH-3548: Validate-time model hint warnings and hint documentation

## Summary

Add `ll-loop validate` warnings for model hints that will not resolve, and document the hint vocabulary, support matrix and precedence. This is piece 3 of ENH-3527's delivery split (its criteria 8 and 10); design details are in ENH-3527 → Config override.

## Current Behavior

- `ll-loop validate` checks `model_hint` vocabulary and exclusivity (ENH-3527) but does not check whether a hint resolves for the configured host.
- No docs describe the hint vocabulary, support matrix or precedence.

## Expected Behavior

- For each declared hint, `ll-loop validate` resolves it against the configured host (`orchestration.host_cli` / `LL_HOST_CLI`) and emits a WARNING, not an error, for any hint that cannot resolve on a reachable request path: the state's `request_path` if set, else `orchestration.request_path`, plus the CLI fallback for SDK/batch.
- States that always downgrade to CLI (a `/ll:` skill action per `_SKILL_INVOKE_RE`, or `tools:` per BUG-2831) are checked for CLI only.
- Action hints are checked for the streaming operation, evaluator hints for blocking.
- `haiku-gen` guidance covers hint-only `burst` generation without rejecting valid `burst` verdict states.

## Scope Boundaries

- **In scope**: validate-time WARNINGs, `haiku-gen` guidance, documentation.
- **Out of scope**: runtime dispatch (ENH-3547); new vocabulary.

## Program Design

### Types

- No new types.

### Signatures

- `resolve_model_hint(hint, *, backend, operation, overrides=None) -> str` — from ENH-3527; validation catches its error and emits a WARNING.

### Call Path

- `ll-loop validate` → `validate_fsm` → structural rules → `resolve_model_hint` (per reachable path/operation) → WARNING

## Integration Map

- `scripts/little_loops/fsm/validation/{structural_rules,evaluator_rules}.py`.
- Tests: `test_fsm_validation_structural.py`, `test_fsm_validation_evaluator_rules.py`, `test_wiring_reference_docs.py`.

## Impact

- **Priority**: P3.
- **Effort**: Small.
- **Risk**: Low.

## Acceptance Criteria

- [ ] Warnings fire for an unmapped hint on a reachable path/operation and not when every path resolves; downgrade-only states produce no SDK warning.
- [ ] Vocabulary semantics, support matrix, precedence and the deferred skill/agent scope (ENH-3533) are documented in `docs/guides/LOOPS_GUIDE.md`, `docs/generalized-fsm-loop.md`, `docs/reference/{API,CLI,HOST_COMPATIBILITY,CONFIGURATION}.md` and `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`.

## Status

**Open** | Created: 2026-09-24 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue covers validate-time WARNINGs, `haiku-gen` guidance, and documentation only. Resolver/config is ENH-3527 and dispatch wiring is ENH-3547. Its use of the `operation` parameter follows whatever ENH-3527 settles.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-24T17:53:57 - `5250dd00-ed7b-4310-8dee-527fe13b2b07.jsonl`
