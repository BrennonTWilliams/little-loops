---
id: ENH-3725
type: ENH
title: Model-specific cacheable prefix minimum for Sonnet 5.5
priority: P3
status: open
discovered_by: capture-issue
discovered_date: '2026-10-03'
captured_at: '2026-10-04T01:44:09Z'
testable: true
relates_to:
- EPIC-2456
- FEAT-2673
- BUG-3701
- EPIC-3562
---

# ENH-3725: Model-specific cacheable prefix minimum for Sonnet 5.5

## Summary

Make the cache-marking oracle select a model-specific cacheable-prefix minimum for `claude-sonnet-5-5`. The verified Sonnet 5.5 minimum is 512 tokens, while the current generic Sonnet rule requires 1024. This is a standalone follow-up related to the completed EPIC-2456, and does not reopen that epic or gate EPIC-3562.

## Current Behavior

`CACHEABLE_PREFIX_MINIMUMS` contains family defaults (Sonnet 1024, Opus 4096). `_prefix_minimum_for` performs family substring matching, so concrete Sonnet 5.5 requests with stable 512–1023-token prefixes fail the oracle's size gate. `build_anthropic_request` passes its resolved concrete model into `decide_cache_marking`; SDK/batch callers already share that request path.

## Expected Behavior

Use a verified exact model override for Sonnet 5.5 before the existing family fallback. Preserve older/pinned Sonnet defaults and the conservative unknown-model fallback. The size gate and reuse-stability gate remain independent; a sufficiently large first-sighting fragment still requires a repeat unless `require_repeat=False`.

## Motivation

The new Sonnet default makes stable prefixes in the 512–1023 range unnecessarily ineligible for marking. A model override addresses the verified gap without lowering the whole Sonnet family floor.

## Proposed Solution

Add an exact concrete-model minimum map (or equivalent small lookup) before the existing family defaults in `_prefix_minimum_for`. Do not infer suffix/provider aliases without evidence: `build_anthropic_request` already resolves normal supported aliases before calling the oracle. Reconfirm the vendor minimum at implementation time and cite its date; preserve existing conservative behavior for unverified spellings.

Source verified in the epic review: [Anthropic Sonnet 5.5 overview](https://platform.claude.com/docs/en/models/sonnet-5-5/overview), minimum cacheable prefix 512 tokens. This vendor constant is distinct from the repository's approximate `len(text) // 4` token estimator.

## Integration Map

### Files to Modify

- `scripts/little_loops/cache_marking_oracle.py` — lookup order and source comments/docstring.
- `scripts/tests/test_cache_control.py` — floor boundaries and request-shape integration.
- `scripts/tests/test_batch_request_path.py` — regression at the shared batch request boundary where needed.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/host_runner.py::build_anthropic_request`; SDK and batch dispatch using that request.

### Similar Patterns

- FEAT-2673's conservative unknown-model floor and repeat gate; keep both.

### Tests

- Sonnet 5.5 boundaries 511/512/1023 using the existing estimator convention, first/repeat sightings, `require_repeat=False`, pinned older Sonnet, and unknown models; one SDK/batch request-shape case proving the concrete ID reaches the oracle.

### Documentation

- Oracle source comments/docstring and relevant cache-control API documentation; update any cited vendor proof that is changed by the new override.

### Configuration

- No new option, tokenizer, SDK dependency, or network test.

## Program Design

### Types

- Proposed exact-model minimum map: `dict[str, int]` with `claude-sonnet-5-5: 512`; retain `CACHEABLE_PREFIX_MINIMUMS` as family defaults.

### Signatures

- `_prefix_minimum_for(model: str) -> int` — existing checks verified concrete IDs first.
- `decide_cache_marking(..., model: str, require_repeat: bool) -> CacheMarkingDecision` — existing retains its two independent gates.
- Existing `build_anthropic_request` supplies the resolved concrete model.

### Call Path

SDK/batch request builder → `build_anthropic_request` → `decide_cache_marking` → exact-model floor then family fallback → repeat gate → `cache_control` request field.

## Implementation Steps

1. Reverify and date the Sonnet 5.5 vendor minimum; add the exact override before family fallback.
2. Add size/reuse boundary tests while preserving older Sonnet and unknown-model behavior.
3. Prove resolved-model propagation at the SDK/batch request boundary and update source notes.

## Impact

- **Priority:** P3 — useful cache-marking correction, independent of the multi-host epic's implementation.
- **Effort:** Small — one override plus existing oracle/request tests.
- **Risk:** Low — exact override and preserved conservative fallbacks limit the change.
- **Breaking Change:** No; some verified Sonnet 5.5 prefixes become eligible for marking under the existing reuse rules.

## Acceptance Criteria

- [ ] Concrete `claude-sonnet-5-5` uses 512, with 511 rejected and 512/1023 accepted by the size gate under the current estimator convention.
- [ ] Size eligibility alone does not bypass the repeat requirement; repeat and `require_repeat=False` behavior are tested independently.
- [ ] Explicitly pinned older Sonnet IDs retain their prior minimum, and unknown models retain the conservative fallback; no family-wide lowering or guessed suffix matching.
- [ ] The resolved Sonnet 5.5 model reaches the oracle through `build_anthropic_request`; a qualified stable SDK/batch request carries `cache_control` as intended.
- [ ] Vendor source/date and estimator limits are documented; tests are deterministic and require no provider call or new dependency.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **In scope:** verified Sonnet 5.5 minimum override, lookup precedence, size/reuse tests, request integration and source notes.
- **Out of scope:** reopening EPIC-2456, generic tokenizer accuracy, other model-family updates without evidence, new reuse-frequency policy, and EPIC-3562's host cutovers/pricing.

## Related Key Documentation

- `docs/reference/API.md` — cache-marking and request-builder contracts.

## Status

**Open** | Created: 2026-10-03 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-10-04T01:51:02 - `7ac1ad38-c74f-402b-a14d-5845cde7ff55.jsonl`
